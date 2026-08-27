import PageBack from "../../components/shadcn/page-back.jsx";
import Table from "../../components/shadcn/table.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import { useI18n } from "../../utils/i18n.jsx";

export default function Statements({ clients = [] }) {
  const { t } = useI18n();

  const columns = [
    {
      header: t("Client"),
      render: (c) => (
        <a href={`/finance/clients/${c.client_id}/statement/`} className="text-blue-600 hover:underline font-medium">
          {c.name}
        </a>
      ),
    },
    {
      header: t("Billed"),
      className: "text-right",
      render: (c) => <span className="font-mono tabular-nums">{c.tagihan.toLocaleString()}</span>,
    },
    {
      header: t("Paid"),
      className: "text-right",
      render: (c) => <span className="font-mono tabular-nums">{c.terbayar.toLocaleString()}</span>,
    },
    {
      header: t("Allocated"),
      className: "text-right",
      render: (c) => <span className="font-mono tabular-nums">{c.allocated.toLocaleString()}</span>,
    },
    {
      header: t("Receivable"),
      className: "text-right",
      render: (c) => (
        <span className={`font-mono tabular-nums font-medium ${c.piutang > 0 ? "text-red-600" : ""}`}>
          {c.piutang.toLocaleString()}
        </span>
      ),
    },
    {
      header: t("Wallet Balance"),
      className: "text-right",
      render: (c) => (
        <span className="font-mono tabular-nums">{c.saldo_dana.toLocaleString()}</span>
      ),
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />

      <div className="page-header">
        <div>
          <div className="page-title">{t("Client Ledger")}</div>
          <div className="page-sub">{t("Balances per client based on the operational ledger. Open a client for the full statement.")}</div>
        </div>
      </div>

      <div className="card">
        {clients.length > 0 ? (
          <Table columns={columns} rows={clients} rowKey={(c) => c.client_id} />
        ) : (
          <EmptyState title="No ledger activity" sub="No clients with charges, payments or allocations yet." />
        )}
      </div>
    </div>
  );
}
