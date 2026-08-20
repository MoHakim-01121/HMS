import PageBack from "../../components/shadcn/page-back.jsx";
import DetailCard from "../../components/shadcn/detail-card.jsx";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import DetailAmount from "../../components/shadcn/detail-amount.jsx";
import Section from "../../components/shadcn/section.jsx";
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
      render: (row) => row.date,
    },
    {
      header: t("Entry #"),
      render: (row) => <span className="font-mono text-xs">{row.entry_number}</span>,
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
        <span className={row.amount_sar > 0 ? "text-green-600 font-mono" : "text-red-600 font-mono"}>
          {row.amount_sar > 0 ? "+" : ""}{row.amount_sar?.toLocaleString()}
        </span>
      ),
    },
    {
      header: t("Balance"),
      align: "right",
      strong: true,
      render: (row) => (
        <span className={`font-mono ${row.balance > 0 ? "text-red-600" : row.balance < 0 ? "text-green-600" : ""}`}>
          {row.balance?.toLocaleString()}
        </span>
      ),
    },
  ];

  return (
    <div className="page dv-page hms-dv-page shadcn-root">
      <PageBack href="/clients/" label={t("Back")} />

      <DetailCard
        crumbs={[{ label: t("Clients"), href: "/clients/" }]}
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
      >
        <div style={{ display: "flex", gap: 12, padding: "16px 20px", flexWrap: "wrap" }}>
          <DetailAmount label={t("Closing Balance")} value={closing_balance} currency="SAR" tone={closing_balance > 0 ? "red" : "green"} />
          <DetailAmount label={t("Total Debit")} value={total_debit} currency="SAR" tone="green" />
          <DetailAmount label={t("Total Credit")} value={total_credit} currency="SAR" tone="red" />
        </div>

        <Section label={t("Transactions")} count={transactions.length}>
          <DetailTable columns={columns} rows={transactions} rowKey="entry_number" empty={t("No transactions found for this client.")} />
        </Section>
      </DetailCard>
    </div>
  );
}
