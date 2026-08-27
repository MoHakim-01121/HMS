import PageBack from "../../components/shadcn/page-back.jsx";
import Table from "../../components/shadcn/table.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import useFilterState from "../../hooks/useFilterState.js";
import { useI18n } from "../../utils/i18n.jsx";

export default function List({ penalties = [], total = 0, filters = {} }) {
  const { t } = useI18n();
  const { vals, setVal, apply } = useFilterState(
    { q: "", status: "", ...filters },
    "/finance/penalties/",
  );

  const columns = [
    {
      header: t("Penalty #"),
      className: "col-m-primary",
      render: (p) => (
        <a href={`/penalty/${p.id}/`} className="text-blue-600 hover:underline font-medium">
          {p.penalty_number}
        </a>
      ),
    },
    {
      header: t("Status"),
      className: "col-m-badge",
      render: (p) => (
        <StatusPill tone={p.is_paid ? "green" : "yellow"} label={p.is_paid ? t("Paid") : t("Unpaid")} />
      ),
    },
    {
      header: t("Client"),
      className: "col-m-secondary",
      render: (p) => p.client_name || "—",
    },
    {
      header: t("Conf Letter"),
      className: "col-m-hide",
      render: (p) => p.cl_id
        ? <a href={`/cl/${p.cl_id}/`} className="text-blue-600 hover:underline">{p.confirmation_number}</a>
        : "—",
    },
    {
      header: t("Cancellation Date"),
      className: "col-m-meta",
      render: (p) => p.cancellation_date,
    },
    {
      header: t("Amount"),
      className: "mono col-nowrap col-m-amount",
      render: (p) => (
        <>
          <span className="m-hide">{p.amount_sar.toLocaleString()} SAR</span>
          <span className="m-only" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--text-3)", fontWeight: 700 }}>{t("Amount")}</span>
          <span className="m-only">{p.amount_sar.toLocaleString()} SAR</span>
        </>
      ),
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />

      <div className="page-header">
        <div>
          <div className="page-title">{t("Penalties")}</div>
          <div className="page-sub">{t("All cancellation penalties across confirmation letters.")}</div>
        </div>
      </div>

      <div className="filter-bar">
        <input
          className="input w-64" style={{ height: 40 }}
          placeholder={t("Search penalty / CL / client...")}
          value={vals.q}
          onChange={(e) => setVal("q", e.target.value)}
        />
        <select
          className="input w-36" style={{ height: 40 }}
          value={vals.status}
          onChange={(e) => setVal("status", e.target.value)}
        >
          <option value="">{t("All Status")}</option>
          <option value="paid">{t("Paid")}</option>
          <option value="unpaid">{t("Unpaid")}</option>
        </select>
        <button type="button" className="fp-apply" onClick={() => apply()}>{t("Apply")}</button>
      </div>

      <div className="card">
        {penalties.length > 0 ? (
          <>
            <Table columns={columns} rows={penalties} rowKey={(p) => p.id} />
            <div className="px-4 py-3 border-t border-[var(--border)] text-sm text-muted-foreground">
              {total.toLocaleString()} {t("penalties")}
            </div>
          </>
        ) : (
          <EmptyState title="No penalties found" sub="No penalties match your filters." />
        )}
      </div>
    </div>
  );
}
