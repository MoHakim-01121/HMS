import { useState } from "react";
import { Link } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import Table from "../../components/shadcn/table.jsx";
import { TableRow, TableCell } from "../../components/shadcn/ui/table.jsx";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";
import { listVisit } from "../../utils/listVisit.js";

// Service Margin: what each sold Services line earned (SAR billed, from the
// journal) against the vendor cost booked on it, plus what is still owed to
// each vendor.
export default function ServiceMargin({ margins, payables = [], branch_choices = [], filters = {} }) {
  const { t } = useI18n();
  const [branch, setBranch] = useState(filters.branch || "all");
  const [from, setFrom] = useState(filters.date_from || "");
  const [to, setTo] = useState(filters.date_to || "");

  const apply = () => listVisit("/finance/service-margin/", {
    ...(branch !== "all" ? { branch } : {}),
    ...(from ? { date_from: from } : {}),
    ...(to ? { date_to: to } : {}),
  });

  const dim = <span className="col-dim">—</span>;
  const lineColumns = [
    { header: t("Invoice"), className: "col-m-primary", render: (r) => <Link href={`/services/${r.invoice_id}/`} className="col-bold">{r.invoice_number}</Link> },
    { header: t("Client"), className: "col-m-meta", render: (r) => r.client || "—" },
    { header: t("Service"), className: "col-m-meta", render: (r) => r.description },
    { header: t("Qty"), className: "col-m-meta text-right", render: (r) => r.quantity },
    { header: t("Billed (SAR)"), className: "col-m-amount text-right", render: (r) => fmt(r.revenue_sar) },
    { header: `${t("Vendor cost")} (SAR)`, className: "col-m-amount text-right", render: (r) => (r.has_cost ? fmt(r.cost_sar) : dim) },
    {
      header: t("Margin"), className: "col-m-amount text-right",
      render: (r) => (r.has_cost
        ? <span className="col-nowrap" style={{ color: r.margin_sar < 0 ? "var(--red)" : undefined }}>
            {fmt(r.margin_sar)}{r.margin_pct !== null ? ` · ${r.margin_pct}%` : ""}
          </span>
        : dim),
    },
  ];
  const vendorColumns = [
    { header: t("Vendor"), className: "col-m-primary", render: (v) => <span className="col-bold">{v.vendor}</span> },
    { header: t("Billed (SAR)"), className: "col-m-amount text-right", render: (v) => fmt(v.billed_sar) },
    { header: t("Paid (SAR)"), className: "col-m-amount text-right", render: (v) => fmt(v.paid_sar) },
    {
      header: t("Outstanding (SAR)"), className: "col-m-amount text-right",
      render: (v) => <span className="col-bold" style={{ color: v.outstanding_sar > 0 ? "var(--red)" : undefined }}>{fmt(v.outstanding_sar)}</span>,
    },
  ];
  const owed = payables.reduce((s, v) => s + v.outstanding_sar, 0);

  return (
    <div className="page shadcn-root">
      <style>{CSS}</style>
      <PageBack label={t("Back")} />
      <PageHeader
        title={t("Service Margin")}
        sub={t("What each Services line earned against its vendor cost, and what is still owed to vendors.")}
      />

      <div className="filter-bar sm-filters">
        <Select value={branch} onValueChange={setBranch}>
          <SelectTrigger className="sm-branch"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("All branches")}</SelectItem>
            {branch_choices.map((b) => <SelectItem key={b.value} value={b.value}>{b.label}</SelectItem>)}
          </SelectContent>
        </Select>
        <input type="date" className="hms-dv-date" aria-label={t("From")} value={from} onChange={(e) => setFrom(e.target.value)} />
        <input type="date" className="hms-dv-date" aria-label={t("To")} value={to} onChange={(e) => setTo(e.target.value)} />
        <Button variant="outline" onClick={apply}>{t("Apply")}</Button>
      </div>

      <div className="hms-kpi-row sm-kpis">
        <KpiCard label={t("Billed")} value={fmt(margins.revenue_sar)} unit="SAR" foot={t("{n} Services lines", { n: margins.rows.length })} />
        <KpiCard label={t("Vendor cost")} value={fmt(margins.cost_sar)} unit="SAR"
          foot={margins.without_cost ? t("{n} lines without a vendor cost", { n: margins.without_cost }) : t("every line has a cost")}
          warn={margins.without_cost > 0} />
        <KpiCard label={t("Margin")} value={fmt(margins.margin_sar)} unit="SAR" warn={margins.margin_sar < 0} foot={t("billed − vendor cost")} />
      </div>

      <div className="hms-list-card">
        <Table
          columns={lineColumns}
          rows={margins.rows}
          rowKey={(r) => r.line_id}
          empty={t("No Services lines in this range.")}
          footer={margins.rows.length ? (
            <TableRow>
              <TableCell className="col-bold" colSpan={4}>{t("Total")}</TableCell>
              <TableCell className="text-right col-bold">{fmt(margins.revenue_sar)}</TableCell>
              <TableCell className="text-right col-bold">{fmt(margins.cost_sar)}</TableCell>
              <TableCell className="text-right col-bold">{fmt(margins.margin_sar)}</TableCell>
            </TableRow>
          ) : undefined}
        />
      </div>

      <h2 className="sm-h">{t("Vendor payables")} <span className="sm-sub">{fmt(owed)} SAR</span></h2>
      <div className="hms-list-card">
        <Table columns={vendorColumns} rows={payables} rowKey={(v) => v.vendor_id ?? "none"} empty={t("No posted vendor expenses.")} />
      </div>
    </div>
  );
}

const CSS = `
.sm-filters { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.sm-filters input[type="date"] { width: auto; flex: none; height: 40px; }
.sm-branch { width: 180px; }
.sm-kpis { margin-bottom: 18px; }
.sm-h { display: flex; align-items: baseline; gap: 10px; margin: 22px 0 10px; font-size: 14px; font-weight: 600; }
.sm-sub { font-size: 12.5px; font-weight: 500; color: var(--muted-foreground); }
`;
