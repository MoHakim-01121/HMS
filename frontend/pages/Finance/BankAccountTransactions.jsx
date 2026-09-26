import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import Table from "../../components/shadcn/table.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import useFilterState from "../../hooks/useFilterState.js";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { useI18n } from "../../utils/i18n.jsx";

export default function BankAccountTransactions({ account, rows = [], filters = {} }) {
  const { t } = useI18n();
  const { vals, setVal, apply } = useFilterState(
    { date_from: "", date_to: "", ...filters },
    `/finance/bank-accounts/${account.kind}/${account.id}/`,
  );

  const columns = [
    { header: t("Date"), className: "col-m-primary whitespace-nowrap", render: (r) => r.transaction_date },
    {
      header: t("Direction"),
      className: "col-m-badge",
      render: (r) => (
        <StatusPill
          tone={r.direction === "in" ? "green" : "red"}
          label={r.direction === "in" ? t("Money In") : t("Money Out")}
        />
      ),
    },
    { header: t("Source"), className: "col-m-meta", render: (r) => `${r.source_type} #${r.source_id}` },
    { header: t("Reference"), className: "col-m-meta", render: (r) => r.reference || "—" },
    {
      header: t("Status"),
      className: "col-m-badge",
      render: (r) => (
        <StatusPill
          tone={r.matched ? "blue" : "gray"}
          label={r.matched ? t("Reconciled") : t("Unmatched")}
        />
      ),
    },
    {
      header: t("Amount"),
      className: "col-m-amount",
      style: { textAlign: "right" },
      render: (r) => (
        <span className="col-nowrap font-mono tabular-nums" style={{ color: r.direction === "in" ? "var(--green)" : "var(--red)" }}>
          {r.direction === "in" ? "+" : "-"}{r.amount_sar.toLocaleString("en-US")}
        </span>
      ),
    },
    {
      header: t("Running Balance"),
      className: "col-m-amount",
      style: { textAlign: "right" },
      render: (r) => (
        <span className="col-nowrap font-mono tabular-nums" style={r.running_balance_sar < 0 ? { color: "var(--red)" } : undefined}>
          {r.running_balance_sar.toLocaleString("en-US")}
        </span>
      ),
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />

      <PageHeader
        title={account.name}
        sub={t("Transaction history for this account — running balance is a cumulative sum of these records, not the journal-derived book balance.")}
      />

      <div className="filter-bar">
        <Input type="date" value={vals.date_from} onChange={(e) => setVal("date_from", e.target.value)} />
        <Input type="date" value={vals.date_to} onChange={(e) => setVal("date_to", e.target.value)} />
        <Button type="button" size="lg" onClick={() => apply()}>{t("Apply")}</Button>
      </div>

      <div className="hms-list-card">
        {rows.length > 0 ? (
          <Table columns={columns} rows={rows} rowKey={(r) => r.id} />
        ) : (
          <EmptyState iconName="wallet" title={t("No transactions found")} sub={t("No bank transactions recorded for this account yet.")} />
        )}
      </div>
    </div>
  );
}
