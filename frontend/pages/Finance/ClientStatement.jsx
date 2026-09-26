import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import DetailCard from "../../components/shadcn/detail-card.jsx";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import DetailAmount from "../../components/shadcn/detail-amount.jsx";
import Section from "../../components/shadcn/section.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";
import { fmt } from "../../utils/format.js";

const TYPE_TONE = {
  charge: "badge-blue",
  payment: "badge-green",
  allocate: "badge-yellow",
  transfer: "badge-purple",
  refund: "badge-orange",
  penalty: "badge-red",
  reversal: "badge-gray",
};

const AGING_BUCKETS = [
  ["0_30", "0–30 days"],
  ["31_60", "31–60 days"],
  ["61_90", "61–90 days"],
  ["90_plus", "90+ days"],
];

const AR_CONTACT = {
  name: "Konoz United Surabaya",
  address: "Jl. Ikan Mungsing VII No.51, Perak Bar., Krembangan, Surabaya 60177",
  email: "konozsurabaya@gmail.com",
};

export default function ClientStatement({ client = {}, statement = {}, aging = {}, mode = "balance", date_from, date_to }) {
  const { t } = useI18n();
  const canExportPdf = usePerms().can("clients", "export");
  const {
    transactions = [],
    open_items = [],
    total_open = 0,
    closing_balance = 0,
    total_debit = 0,
    total_credit = 0,
    opening_balance = 0,
  } = statement;
  const { buckets = {}, total: aging_total = 0 } = aging;

  const [from, setFrom] = useState(date_from || "");
  const [to, setTo] = useState(date_to || "");
  const [viewMode, setViewMode] = useState(mode || "balance");

  const qs = () => {
    const p = new URLSearchParams();
    if (from) p.set("from", from);
    if (to) p.set("to", to);
    p.set("mode", viewMode);
    const s = p.toString();
    return s ? `?${s}` : "";
  };
  const navigate = () => router.get(`/finance/clients/${client.id}/statement/${qs()}`, {}, { preserveScroll: true });

  const switchMode = (m) => {
    setViewMode(m);
    router.get(`/finance/clients/${client.id}/statement/?mode=${m}`, {}, { preserveScroll: true });
  };

  const isOpen = viewMode === "open";
  const activeBalance = isOpen ? total_open : closing_balance;

  // Balance Forward columns — simplified for the client audience.
  const balanceColumns = [
    { header: t("Date"), render: (row) => row.date },
    {
      header: t("Invoice"),
      render: (row) =>
        row.invoice_number ? <span className="mono">{row.invoice_number}</span> : <span style={{ color: "var(--muted-foreground)" }}>—</span>,
    },
    {
      header: t("Type"),
      render: (row) => (
        <span className={`badge ${TYPE_TONE[row.entry_type] || "badge-gray"}`}>{row.entry_type_display}</span>
      ),
    },
    { header: t("Description"), render: (row) => row.description },
    {
      header: t("Amount"),
      align: "right",
      render: (row) => (
        <span className="mono" style={{ color: row.amount_sar > 0 ? "var(--green)" : row.amount_sar < 0 ? "var(--red)" : undefined }}>
          {row.amount_sar > 0 ? "+" : ""}
          {fmt(row.amount_sar)}
        </span>
      ),
    },
    {
      header: t("Balance"),
      align: "right",
      strong: true,
      render: (row) => (
        <span className="mono" style={{ color: row.balance > 0 ? "var(--red)" : row.balance < 0 ? "var(--green)" : undefined }}>
          {fmt(row.balance)}
        </span>
      ),
    },
  ];

  // Open Item columns: invoice-level, unpaid balance focus.
  const openColumns = [
    {
      header: t("Invoice"),
      render: (row) => <span className="mono">{row.invoice_number}</span>,
    },
    {
      header: t("Issued"),
      render: (row) => row.issued_date || "—",
    },
    {
      header: t("Due"),
      render: (row) => (
        <span style={{ color: row.overdue ? "var(--red)" : undefined, fontWeight: row.overdue ? 600 : undefined }}>
          {row.due_date || "—"}
          {row.overdue ? <span style={{ marginLeft: 6 }}><StatusPill small tone="red" label={t("Overdue")} /></span> : null}
        </span>
      ),
    },
    { header: t("Billed"), align: "right", render: (row) => <span className="mono">{fmt(row.billed)}</span> },
    { header: t("Paid"), align: "right", render: (row) => <span className="mono">{fmt(row.paid)}</span> },
    {
      header: t("Open"),
      align: "right",
      strong: true,
      render: (row) => <span className="mono" style={{ color: "var(--red)" }}>{fmt(row.remaining)}</span>,
    },
  ];

  const openFooter = isOpen
    ? [{ label: t("Total due"), value: fmt(total_open), total: true, tone: "red" }]
    : [];

  return (
    <div className="page dv-page hms-dv-page shadcn-root">
      <PageBack href={client.id ? `/clients/${client.id}/` : "/clients/"} label={t("Back to client")} />

      <DetailCard
        crumbs={[
          { label: t("Clients"), href: "/clients/" },
          client.id ? { label: client.name, href: `/clients/${client.id}/` } : null,
        ].filter(Boolean)}
        kicker={client.name}
        title={t("Client Statement")}
        sub={isOpen ? t("Open items") : date_from || date_to ? `${date_from || t("Start")} — ${date_to || t("Now")}` : t("All time")}
        pill={{
          label: activeBalance > 0 ? t("Amount due") : activeBalance < 0 ? t("Credit") : t("Settled"),
          tone: activeBalance > 0 ? "red" : activeBalance < 0 ? "green" : "gray",
        }}
        actions={
          <>
            <select
              className="hms-dv-date"
              value={viewMode}
              onChange={(e) => switchMode(e.target.value)}
              aria-label={t("Statement mode")}
              style={{ height: 34, padding: "0 8px" }}
            >
              <option value="balance">{t("Balance Forward")}</option>
              <option value="open">{t("Open Items")}</option>
            </select>
            {!isOpen && (
              <>
                <input type="date" className="hms-dv-date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} aria-label={t("From")} />
                <span style={{ color: "var(--muted-foreground)" }}>–</span>
                <input type="date" className="hms-dv-date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} aria-label={t("To")} />
                <button type="button" className="hms-dv-act" onClick={navigate}>{t("Apply")}</button>
              </>
            )}
            {canExportPdf && (
              <a className="hms-dv-act" href={`/clients/${client.id}/statement/pdf/${isOpen ? "?mode=open" : qs()}`} target="_blank" rel="noreferrer">
                PDF
              </a>
            )}
            {canExportPdf && (
              <a
                className="hms-dv-act"
                href={`/clients/${client.id}/statement/pdf/?mode=byres${from ? `&from=${from}` : ""}${to ? `&to=${to}` : ""}`}
                target="_blank"
                rel="noreferrer"
              >
                {t("PDF per reservation")}
              </a>
            )}
          </>
        }
      >
        {!isOpen && (
          <Section label={t("Account Summary")}>
            <div
              style={{
                margin: "0 20px 16px",
                maxWidth: 360,
                border: "1px solid var(--border)",
                borderRadius: 10,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  padding: "8px 14px 6px",
                  fontSize: 10.5,
                  textTransform: "uppercase",
                  letterSpacing: 1,
                  color: "var(--muted-foreground)",
                  fontWeight: 700,
                  background: "var(--muted)",
                  borderBottom: "1px solid var(--border)",
                }}
              >
                {t("Account Summary")}
              </div>
              <div style={{ padding: "4px 0", display: "flex", flexDirection: "column", gap: 4 }}>
                <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 14px", fontSize: 12 }}>
                  <span style={{ color: "var(--muted-foreground)" }}>{t("Opening Balance")}</span>
                  <span className="mono">{fmt(opening_balance)}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 14px", fontSize: 12 }}>
                  <span style={{ color: "var(--muted-foreground)" }}>
                    {t("Charges")} <span style={{ fontSize: 10.5, color: "var(--border)" }}>({t("billed")})</span>
                  </span>
                  <span className="mono">{fmt(total_debit)}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 14px", fontSize: 12 }}>
                  <span style={{ color: "var(--muted-foreground)" }}>
                    {t("Payments")} <span style={{ fontSize: 10.5, color: "var(--border)" }}>({t("received")})</span>
                  </span>
                  <span className="mono">−{fmt(total_credit)}</span>
                </div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    padding: "8px 14px",
                    fontSize: 12.5,
                    fontWeight: 700,
                    borderTop: "1px solid var(--border)",
                    background: "var(--muted)",
                  }}
                >
                  <span>{t("Balance Due")}</span>
                  <span className="mono" style={{ color: activeBalance > 0 ? "var(--red)" : activeBalance < 0 ? "var(--green)" : undefined }}>
                    {fmt(activeBalance)}
                  </span>
                </div>
              </div>
            </div>
          </Section>
        )}

        <div style={{ display: "flex", gap: 12, padding: "16px 20px", flexWrap: "wrap", alignItems: "center" }}>
          <DetailAmount label={isOpen ? t("Amount Due") : t("Closing Balance")} value={activeBalance} currency="SAR" tone={activeBalance > 0 ? "red" : "green"} />
          {aging_total > 0 && <DetailAmount label={t("Outstanding")} value={aging_total} currency="SAR" tone="red" />}
        </div>

        {!isOpen && aging_total > 0 && (
          <Section label={t("Aging Analysis")}>
            <div style={{ display: "flex", gap: 12, padding: "0 20px 16px", flexWrap: "wrap" }}>
              {AGING_BUCKETS.map(([key, label]) => (
                <div
                  key={key}
                  style={{
                    border: "1px solid var(--border)",
                    borderRadius: 10,
                    padding: "10px 16px",
                    minWidth: 140,
                    background: "var(--card)",
                  }}
                >
                  <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".5px", color: "var(--muted-foreground)" }}>{t(label)}</div>
                  <div className="mono" style={{ fontSize: 16, fontWeight: 700, color: (buckets[key] || 0) > 0 ? "var(--red)" : "inherit" }}>
                    {fmt(buckets[key] || 0)} SAR
                  </div>
                </div>
              ))}
            </div>
          </Section>
        )}

        {isOpen ? (
          <Section label={t("Open Items")} count={open_items.length}>
            <DetailTable
              columns={openColumns}
              rows={open_items}
              rowKey={(row) => row.invoice_number}
              footer={openFooter}
              empty={t("No open items — all invoices settled.")}
            />
          </Section>
        ) : (
          <Section label={t("Transactions")} count={transactions.length}>
            <DetailTable
              columns={balanceColumns}
              rows={transactions}
              rowKey={(row) => row.entry_number}
              empty={t("No transactions found for this client.")}
            />
          </Section>
        )}

        <div
          style={{
            marginTop: 8,
            padding: "14px 20px 18px",
            borderTop: "1px solid var(--border)",
            display: "flex",
            flexDirection: "column",
            gap: 3,
            fontSize: 12,
            color: "var(--muted-foreground)",
          }}
        >
          <div style={{ fontWeight: 700, color: "var(--foreground)", fontSize: 12, textTransform: "uppercase", letterSpacing: ".5px" }}>
            {t("Payment & Contact")}
          </div>
          <div>{AR_CONTACT.name}</div>
          <div>{AR_CONTACT.address}</div>
          <div>
            {t("Payments / inquiries")}: <a href={`mailto:${AR_CONTACT.email}`} style={{ color: "var(--foreground)" }}>{AR_CONTACT.email}</a>
          </div>
        </div>
      </DetailCard>
    </div>
  );
}
