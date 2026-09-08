import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import Table from "../../components/shadcn/table.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import ListPager from "../../components/shadcn/list-pager.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
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
      render: (p) => <span className="col-bold col-nowrap">{p.penalty_number}</span>,
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
        ? <a href={`/cl/${p.cl_id}/`} className="hms-dv-link" onClick={(e) => e.stopPropagation()}>{p.confirmation_number}</a>
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

      <PageHeader
        title={t("Penalties")}
        sub={t("All cancellation penalties across confirmation letters.")}
      />

      <div className="filter-bar">
        <Input
          className="w-64"
          placeholder={t("Search penalty / CL / client...")}
          value={vals.q}
          onChange={(e) => setVal("q", e.target.value)}
        />
        <Select value={vals.status} onValueChange={(v) => setVal("status", v)}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder={t("All Status")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">{t("All Status")}</SelectItem>
            <SelectItem value="paid">{t("Paid")}</SelectItem>
            <SelectItem value="unpaid">{t("Unpaid")}</SelectItem>
          </SelectContent>
        </Select>
        <Button type="button" size="lg" onClick={() => apply()}>{t("Apply")}</Button>
      </div>

      <div className="hms-list-card">
        {penalties.length > 0 ? (
          <>
            <Table
              columns={columns}
              rows={penalties}
              rowKey={(p) => p.id}
              onRowClick={(p) => router.visit(`/penalty/${p.id}/`)}
            />
            <ListPager total={total} unit="penalties" />
          </>
        ) : (
          <EmptyState iconName="invoice" title="No penalties found" sub="No penalties match your filters." />
        )}
      </div>
    </div>
  );
}
