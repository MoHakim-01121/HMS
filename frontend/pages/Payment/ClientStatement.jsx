import PageBack from "../../components/shadcn/page-back.jsx";
import Table from "../../components/shadcn/table.jsx";
import { useI18n } from "../../utils/i18n.jsx";

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

  const columns = [
    {
      header: t("Date"),
      render: (t) => t.date,
    },
    {
      header: t("Entry #"),
      render: (t) => <span className="font-mono text-xs">{t.entry_number}</span>,
    },
    {
      header: t("Type"),
      render: (t) => (
        <span className={`badge ${TYPE_TONE[t.entry_type] || "badge-gray"}`}>
          {t.entry_type_display}
        </span>
      ),
    },
    {
      header: t("Description"),
      render: (t) => t.description,
    },
    {
      header: t("Account"),
      render: (t) => t.account_display,
    },
    {
      header: t("Amount"),
      className: "text-right font-mono",
      render: (t) => (
        <span className={t.amount_sar > 0 ? "text-green-600" : "text-red-600"}>
          {t.amount_sar > 0 ? "+" : ""}{t.amount_sar?.toLocaleString()}
        </span>
      ),
    },
    {
      header: t("Balance"),
      className: "text-right font-mono font-medium",
      render: (t) => (
        <span className={t.balance > 0 ? "text-red-600" : t.balance < 0 ? "text-green-600" : ""}>
          {t.balance?.toLocaleString()}
        </span>
      ),
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack href="/clients/" />
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">{t("Finance Statement")}</h1>
          <p className="text-muted-foreground text-sm">
            {client.name} | {date_from || "Start"} — {date_to || "Now"}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs text-muted-foreground">{t("Closing Balance")}</p>
          <p className={`text-xl font-bold ${closing_balance > 0 ? "text-red-600" : closing_balance < 0 ? "text-green-600" : ""}`}>
            {closing_balance?.toLocaleString()} SAR
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            {t("Debit")}: {total_debit?.toLocaleString()} | {t("Credit")}: {total_credit?.toLocaleString()}
          </p>
        </div>
      </div>

      <Table columns={columns} rows={transactions} rowKey="entry_number" />
    </div>
  );
}
