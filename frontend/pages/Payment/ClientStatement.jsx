import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import DetailCard from "../../components/shadcn/detail-card.jsx";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import DetailAmount from "../../components/shadcn/detail-amount.jsx";
import Section from "../../components/shadcn/section.jsx";
import { useI18n } from "../../utils/i18n.jsx";
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

export default function ClientStatement({ client = {}, statement = {}, date_from, date_to }) {
  const { t } = useI18n();
  const { transactions = [], closing_balance = 0, total_debit = 0, total_credit = 0 } = statement;

  const [from, setFrom] = useState(date_from || "");
  const [to, setTo] = useState(date_to || "");
  const rangeQs = (() => {
    const p = new URLSearchParams();
    if (from) p.set("from", from);
    if (to) p.set("to", to);
    const s = p.toString();
    return s ? `?${s}` : "";
  })();
  const applyRange = () => router.get(`/finance/clients/${client.id}/statement/${rangeQs}`, {}, { preserveScroll: true });

  const columns = [
    {
      header: t("Date"),
      render: (row) => row.date,
    },
    {
      header: t("Entry #"),
      render: (row) => <span className="mono">{row.entry_number}</span>,
    },
    {
      header: t("Type"),
      render: (row) => (
        <span className={`badge ${TYPE_TONE[row.entry_type] || "badge-gray"}`}>
          {row.entry_type_display}
        </span>
      ),
    },
    {
      header: t("Description"),
      render: (row) => row.description,
    },
    {
      header: t("Account"),
      render: (row) => row.account_display,
    },
    {
      header: t("Amount"),
      align: "right",
      render: (row) => (
        <span className="mono" style={{ color: row.amount_sar > 0 ? "var(--green)" : row.amount_sar < 0 ? "var(--red)" : undefined }}>
          {row.amount_sar > 0 ? "+" : ""}{fmt(row.amount_sar)}
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

  return (
    <div className="page dv-page hms-dv-page shadcn-root">
      <PageBack href={client.id ? `/clients/${client.id}/` : "/clients/"} label={t("Back to client")} />

      <DetailCard
        crumbs={[
          { label: t("Clients"), href: "/clients/" },
          client.id ? { label: client.name, href: `/clients/${client.id}/` } : null,
        ].filter(Boolean)}
        kicker={client.name}
        title={t("Finance Statement")}
        sub={date_from || date_to
          ? `${date_from || t("Start")} — ${date_to || t("Now")}`
          : t("All time")
        }
        pill={{
          label: closing_balance > 0 ? t("Client owes") : closing_balance < 0 ? t("Credit") : t("Settled"),
          tone: closing_balance > 0 ? "red" : closing_balance < 0 ? "green" : "gray",
        }}
        actions={
          <>
            <input type="date" className="hms-dv-date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} aria-label={t("From")} />
            <span style={{ color: "var(--muted-foreground)" }}>–</span>
            <input type="date" className="hms-dv-date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} aria-label={t("To")} />
            <button type="button" className="hms-dv-act" onClick={applyRange}>{t("Apply")}</button>
            <a className="hms-dv-act" href={`/clients/${client.id}/statement/pdf/${rangeQs}`} target="_blank" rel="noreferrer">PDF</a>
          </>
        }
      >
        <div style={{ display: "flex", gap: 12, padding: "16px 20px", flexWrap: "wrap" }}>
          <DetailAmount label={t("Closing Balance")} value={closing_balance} currency="SAR" tone={closing_balance > 0 ? "red" : "green"} />
          <DetailAmount label={t("Total Debit")} value={total_debit} currency="SAR" tone="green" />
          <DetailAmount label={t("Total Credit")} value={total_credit} currency="SAR" tone="red" />
        </div>

        <Section label={t("Transactions")} count={transactions.length}>
          <DetailTable columns={columns} rows={transactions} rowKey={(row) => row.entry_number} empty={t("No transactions found for this client.")} />
        </Section>
      </DetailCard>
    </div>
  );
}
