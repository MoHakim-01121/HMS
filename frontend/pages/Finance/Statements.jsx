import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import Table from "../../components/shadcn/table.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import { useI18n } from "../../utils/i18n.jsx";

export default function Statements({ clients = [] }) {
  const { t } = useI18n();

  const columns = [
    {
      header: t("Client"),
      className: "col-m-primary",
      render: (c) => <span className="col-bold col-nowrap">{c.name}</span>,
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
        <span className="font-mono tabular-nums font-medium" style={c.piutang > 0 ? { color: "var(--red)" } : undefined}>
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

      <PageHeader
        title={t("Client Ledger")}
        sub={t("Balances per client based on the operational ledger. Open a client for the full statement.")}
      />

      <div className="hms-list-card">
        {clients.length > 0 ? (
          <Table
            columns={columns}
            rows={clients}
            rowKey={(c) => c.client_id}
            onRowClick={(c) => router.visit(`/finance/clients/${c.client_id}/statement/`)}
          />
        ) : (
          <EmptyState iconName="wallet" title="No ledger activity" sub="No clients with charges, payments or allocations yet." />
        )}
      </div>
    </div>
  );
}
