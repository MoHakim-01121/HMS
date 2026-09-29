import { useState } from "react";
import { Link } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import Table from "../../components/shadcn/table.jsx";
import { TableRow, TableCell } from "../../components/shadcn/ui/table.jsx";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";
import { listVisit } from "../../utils/listVisit.js";

const BUCKETS = [
  ["current", "Not yet due"],
  ["1_30", "1–30 days"],
  ["31_60", "31–60 days"],
  ["61_90", "61–90 days"],
  ["90_plus", "> 90 days"],
];
const LATE = ["31_60", "61_90", "90_plus"];

// AR Aging: what every client still owes, grouped by how far past the due
// date it is, as of a chosen day. Click a client for its open invoices.
export default function ArAging({ aging }) {
  const { t } = useI18n();
  const perms = usePerms();
  const [asOf, setAsOf] = useState(aging.as_of);
  const [picked, setPicked] = useState(null);
  const client = picked && aging.clients.find((c) => c.client_id === picked);

  const amount = (v, late) => (v ? <span className="col-nowrap" style={{ color: late ? "var(--red)" : undefined }}>{fmt(v)}</span> : <span className="col-dim">—</span>);

  const clientColumns = [
    { header: t("Client"), className: "col-m-primary", render: (c) => <span className="col-bold">{c.name}</span> },
    ...BUCKETS.map(([key, label]) => ({
      header: t(label), className: "col-m-amount text-right", render: (c) => amount(c.buckets[key], LATE.includes(key)),
    })),
    { header: t("Total (SAR)"), className: "col-m-amount text-right", render: (c) => <span className="col-bold col-nowrap">{fmt(c.total)}</span> },
  ];

  const invoiceColumns = [
    { header: t("Invoice"), className: "col-m-primary", render: (i) => <Link href={`/invoice/${i.id}/`} className="col-bold">{i.invoice_number}</Link> },
    { header: t("Due date"), className: "col-m-meta col-nowrap", render: (i) => i.due_date || "—" },
    { header: t("Days overdue"), className: "col-m-meta text-right", render: (i) => (i.days_overdue ? i.days_overdue : t("Not yet due")) },
    { header: t("Remaining (SAR)"), className: "col-m-amount text-right", render: (i) => amount(i.amount, LATE.includes(i.bucket)) },
  ];

  const late = LATE.reduce((s, k) => s + aging.buckets[k], 0);
  const overdue = aging.total - aging.buckets.current;

  return (
    <div className="page shadcn-root">
      <style>{CSS}</style>
      <PageBack label={t("Back")} />
      <PageHeader
        title={t("AR Aging")}
        sub={t("What every client still owes, by how many days past the due date.")}
        actions={perms.can("statements", "export") ? (
          <Button asChild variant="outline" size="lg"><a href={`/finance/ar-aging/export/csv/?as_of=${aging.as_of}`}>{t("Export CSV")}</a></Button>
        ) : null}
      />

      <div className="filter-bar ag-filters">
        <label className="ag-label" htmlFor="ag-asof">{t("As of")}</label>
        <input id="ag-asof" type="date" className="hms-dv-date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
        <Button variant="outline" onClick={() => listVisit("/finance/ar-aging/", { as_of: asOf })}>{t("Apply")}</Button>
      </div>

      <div className="hms-kpi-row ag-kpis">
        <KpiCard label={t("Total Receivable")} value={fmt(aging.total)} unit="SAR" foot={t("{n} clients owe", { n: aging.clients.length })} />
        <KpiCard label={t("Overdue")} value={fmt(overdue)} unit="SAR" warn={overdue > 0} foot={t("past the due date")} />
        <KpiCard label={t("Over 30 days late")} value={fmt(late)} unit="SAR" warn={late > 0} foot={t("needs follow-up")} />
      </div>

      <div className="hms-list-card">
        <Table
          columns={clientColumns}
          rows={aging.clients}
          rowKey={(c) => c.client_id}
          onRowClick={(c) => setPicked(c.client_id === picked ? null : c.client_id)}
          empty={t("No outstanding receivables.")}
          footer={aging.clients.length ? (
            <TableRow>
              <TableCell className="col-bold">{t("Total")}</TableCell>
              {BUCKETS.map(([key]) => <TableCell key={key} className="text-right col-bold">{fmt(aging.buckets[key])}</TableCell>)}
              <TableCell className="text-right col-bold">{fmt(aging.total)}</TableCell>
            </TableRow>
          ) : undefined}
        />
      </div>

      {client && (
        <>
          <h2 className="ag-h">
            {client.name}
            <Link className="ag-link" href={`/finance/clients/${client.client_id}/statement/`}>{t("Statement")}</Link>
            <button type="button" className="ag-clear" onClick={() => setPicked(null)}>{t("Close")}</button>
          </h2>
          <div className="hms-list-card">
            <Table columns={invoiceColumns} rows={client.invoices} rowKey={(i) => i.id} empty={t("No invoice on record.")} />
          </div>
        </>
      )}
    </div>
  );
}

const CSS = `
.ag-filters { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ag-filters input[type="date"] { width: auto; flex: none; height: 40px; }
.ag-label { font-size: 12.5px; color: var(--muted-foreground); }
.ag-kpis { margin-bottom: 18px; }
.ag-h { display: flex; align-items: center; gap: 10px; margin: 22px 0 10px; font-size: 14px; font-weight: 600; }
.ag-link { font-size: 12.5px; font-weight: 500; }
.ag-clear { margin-left: auto; height: 28px; padding: 0 10px; border-radius: 999px; border: 1px solid var(--border); background: var(--card); font: inherit; font-size: 12px; cursor: pointer; }
`;
