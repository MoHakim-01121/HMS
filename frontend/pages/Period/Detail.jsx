import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import DetailCard from "../../components/shadcn/detail-card.jsx";
import DetailGrid from "../../components/shadcn/detail-grid.jsx";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import Section from "../../components/shadcn/section.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { useI18n } from "../../utils/i18n.jsx";

const STATUS_TONE = {
  pending: "yellow",
  confirmed: "blue",
  allocated: "green",
  rejected: "red",
  reversed: "gray",
};

const ENTRY_TYPE_TONE = {
  charge: "badge-blue",
  payment: "badge-green",
  allocate: "badge-yellow",
  transfer: "badge-purple",
  refund: "badge-orange",
  penalty: "badge-red",
  reversal: "badge-gray",
};

export default function Detail({ period = {}, entries = [], payments = [], account_balances = [], total_debit = 0, total_credit = 0 }) {
  const { t } = useI18n();
  const [confirm, confirmDialog] = useConfirm();

  const closePeriod = () => {
    confirm({
      title: t("Close Period"),
      message: t("Close this period? No more journal entries will be allowed."),
      onConfirm: () => router.post(`/finance/periods/${period.id}/close/`),
    });
  };

  const lockPeriod = () => {
    confirm({
      title: t("Lock Period"),
      message: t("Lock this period? This is IRREVERSIBLE."),
      danger: true,
      onConfirm: () => router.post(`/finance/periods/${period.id}/lock/`),
    });
  };

  const pill = {
    open: { label: t("Open"), tone: "green" },
    soft_close: { label: t("Soft Close"), tone: "yellow" },
    closed: { label: t("Closed"), tone: "orange" },
    locked: { label: t("Locked"), tone: "gray" },
  }[period.status] || { label: period.status_display, tone: "gray" };

  const metaActions = [];
  if (period.is_postable) {
    metaActions.push(
      <button key="close" className="hms-dv-act" onClick={closePeriod}>{t("Close Period")}</button>,
    );
  }
  if (period.status === "closed") {
    metaActions.push(
      <button key="lock" className="hms-dv-act" onClick={lockPeriod} style={{ color: "var(--red)" }}>{t("Lock Period")}</button>,
    );
  }

  const entryColumns = [
    { header: t("Entry #"), render: (e) => <span className="font-mono text-xs">{e.entry_number}</span> },
    { header: t("Type"), render: (e) => (
      <span className={`badge ${ENTRY_TYPE_TONE[e.entry_type] || "badge-gray"}`}>
        {e.entry_type_display}
      </span>
    )},
    { header: t("Description"), render: (e) => e.description },
    { header: t("Date"), render: (e) => e.entry_date },
    { header: t("Debit"), align: "right", render: (e) => <span className="font-mono">{e.total_debit?.toLocaleString()}</span> },
    { header: t("Credit"), align: "right", render: (e) => <span className="font-mono">{e.total_credit?.toLocaleString()}</span> },
    { header: t("Balanced"), align: "center", render: (e) => e.is_balanced ? <span style={{ color: "var(--green)" }}>✓</span> : <span style={{ color: "var(--red)" }}>✗</span> },
  ];

  const paymentColumns = [
    { header: t("Payment #"), render: (p) => (
      <a href={`/finance/payments/${p.id}/`} className="text-blue-600 hover:underline">{p.payment_number}</a>
    )},
    { header: t("Client"), render: (p) => p.client_name || "—" },
    { header: t("Amount"), align: "right", render: (p) => <span className="font-mono">{p.amount_sar?.toLocaleString()} SAR</span> },
    { header: t("Status"), render: (p) => (
      <StatusPill tone={STATUS_TONE[p.status] || "gray"} label={p.status_display} />
    )},
    { header: t("Date"), render: (p) => p.payment_date || "—" },
  ];

  return (
    <div className="page dv-page hms-dv-page shadcn-root">
      <PageBack href="/finance/periods/" label={t("Back")} />

      <DetailCard
        crumbs={[{ label: t("Periods"), href: "/finance/periods/" }]}
        kicker={period.name}
        title={t("Financial Period")}
        sub={`${period.date_from} — ${period.date_to}`}
        pill={pill}
        actions={metaActions}
      >
        {account_balances.length > 0 && (
          <Section label={t("Account Balances")} icon="wallet" count={account_balances.length}>
            <div style={{ display: "flex", gap: 12, padding: "0 20px 16px", flexWrap: "wrap" }}>
              {account_balances.map((ab) => (
                <div key={ab.account} className="card" style={{ padding: "12px 20px", flex: "1 1 180px", minWidth: 180 }}>
                  <div style={{ fontSize: 12, color: "var(--muted-foreground)" }}>{ab.label}</div>
                  <div className={`font-mono font-bold ${ab.balance > 0 ? "text-green-600" : "text-red-600"}`} style={{ fontSize: 20, marginTop: 4 }}>
                    {ab.balance?.toLocaleString()} <span style={{ fontSize: 12, fontWeight: 400 }}>SAR</span>
                  </div>
                </div>
              ))}
            </div>
          </Section>
        )}

        <Section label={t("Summary")} icon="wallet">
          <DetailGrid
            rows={[
              { label: t("Total Debit"), icon: "wallet", value: `${total_debit?.toLocaleString()} SAR`, color: "var(--green)" },
              { label: t("Total Credit"), icon: "wallet", value: `${total_credit?.toLocaleString()} SAR`, color: "var(--red)" },
              { label: t("Journal Entries"), value: entries.length },
              { label: t("Payments"), value: payments.length },
              period.closed_by ? { label: t("Closed by"), value: period.closed_by } : null,
              period.closed_at ? { label: t("Closed at"), value: period.closed_at } : null,
              period.locked_by ? { label: t("Locked by"), value: period.locked_by } : null,
              period.locked_at ? { label: t("Locked at"), value: period.locked_at } : null,
            ].filter(Boolean)}
          />
        </Section>

        <Section label={t("Journal Entries")} icon="invoice" count={entries.length}>
          <DetailTable columns={entryColumns} rows={entries} rowKey="id" empty={t("No journal entries in this period.")} />
        </Section>

        <Section label={t("Payments")} icon="wallet" count={payments.length}>
          <DetailTable columns={paymentColumns} rows={payments} rowKey="id" empty={t("No payments in this period.")} />
        </Section>
      </DetailCard>

      {confirmDialog}
    </div>
  );
}
