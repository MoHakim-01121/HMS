import { useState } from "react";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import Table from "../../components/shadcn/table.jsx";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import SeasonSelect from "../../components/shadcn/season-select.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/shadcn/ui/select.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";
import { listVisit } from "../../utils/listVisit.js";

// Arus Dana: how much a branch received from clients, exchanged, sent to HQ,
// spent and refunded — per currency, as the banks hold it — and what its
// transfers to HQ earned on the exchange spread (its only income).
export default function FundFlow({ branch, branch_choices = [], date_from, date_to, seasons = [], flow, fx, expenses_idr = 0, net_profit_idr = null }) {
  const { t } = useI18n();
  const perms = usePerms();
  const [from, setFrom] = useState(date_from);
  const [to, setTo] = useState(date_to);
  const [picked, setPicked] = useState(null); // {line, currency} drill-down
  const currencies = flow.currencies;
  const labelOf = Object.fromEntries(flow.lines.map((l) => [l.key, l.label]));

  const go = (over = {}) => listVisit("/finance/fund-flow/", { branch, from, to, ...over });
  const csv = `/finance/fund-flow/export/csv/?branch=${branch}&from=${from}&to=${to}`;

  const lineRows = flow.lines.filter((l) => ["opening", "closing"].includes(l.key) || currencies.some((c) => l.values[c]));
  const lineColumns = [
    {
      header: t("Line"),
      className: "col-m-primary",
      render: (l) => <span className={["opening", "closing"].includes(l.key) ? "col-bold" : undefined}>{t(l.label)}</span>,
    },
    ...currencies.map((c) => ({
      header: c,
      className: "col-m-amount text-right",
      render: (l) => {
        const v = l.values[c] || 0;
        const drillable = v !== 0 && !["opening", "closing"].includes(l.key);
        // Mobile stacks the row into a card without column headers, so the
        // currency rides along with the figure there.
        const text = <span className="col-nowrap" style={{ color: v < 0 ? "var(--red)" : undefined, fontWeight: l.key === "closing" ? 600 : undefined }}>{fmt(v)}<span className="ff-cur"> {c}</span></span>;
        return drillable ? (
          <button type="button" className="ff-cell" onClick={() => setPicked({ line: l.key, currency: c })}>{text}</button>
        ) : text;
      },
    })),
  ];

  const accountColumns = [
    { header: t("Account"), className: "col-m-primary", render: (a) => <span className="col-bold">{a.label}</span> },
    { header: t("Currency"), className: "col-m-meta", render: (a) => a.currency },
    { header: t("Opening"), className: "col-m-amount text-right", render: (a) => fmt(a.opening) },
    { header: t("In"), className: "col-m-amount text-right", render: (a) => fmt(a.inflow) },
    { header: t("Out"), className: "col-m-amount text-right", render: (a) => fmt(a.outflow) },
    { header: t("Closing"), className: "col-m-amount text-right", render: (a) => <span className="col-bold">{fmt(a.closing)}</span> },
  ];

  const transferColumns = [
    { header: t("Transfer"), className: "col-m-primary", render: (r) => <a href={`/remittance/${r.id}/`} className="col-bold">{r.remittance_number}</a> },
    { header: t("Date"), className: "col-m-meta col-nowrap", render: (r) => r.date },
    { header: "SAR", className: "col-m-amount text-right", render: (r) => fmt(r.sar) },
    { header: t("IDR sent"), className: "col-m-amount text-right", render: (r) => (r.idr_sent != null ? fmt(r.idr_sent) : "—") },
    { header: t("Average rate"), className: "col-m-amount text-right", render: (r) => (r.avg_rate != null ? fmt(r.avg_rate) : "—") },
    { header: t("Send rate"), className: "col-m-amount text-right", render: (r) => (r.send_rate != null ? fmt(r.send_rate) : "—") },
    {
      header: t("FX profit (IDR)"),
      className: "col-m-amount text-right",
      render: (r) => r.profit_idr == null ? <span className="col-dim" title={t("No IDR amount on this transfer")}>—</span> : (
        <span className="col-bold" style={{ color: r.profit_idr < 0 ? "var(--red)" : undefined }}>
          {fmt(r.profit_idr)}{!r.fully_covered ? " *" : ""}
        </span>
      ),
    },
  ];

  const shown = picked ? flow.transactions.filter((x) => x.line === picked.line && x.currency === picked.currency) : [];
  const txColumns = [
    { header: t("Date"), className: "col-m-meta col-nowrap", render: (x) => x.date },
    { header: t("Account"), className: "col-m-secondary", render: (x) => x.account },
    { header: t("Reference"), className: "col-m-primary", render: (x) => (x.link ? <a href={x.link}>{x.reference || x.source_type}</a> : (x.reference || x.source_type)) },
    { header: t("Amount"), className: "col-m-amount text-right", render: (x) => <span style={{ color: x.amount < 0 ? "var(--red)" : undefined }}>{fmt(x.amount)} {x.currency}</span> },
  ];

  const heldIdr = fx.client_money_held.IDR?.amount || 0;
  const lineValue = (key, cur) => flow.lines.find((l) => l.key === key)?.values[cur] || 0;
  // Rupiah the branch holds that is not client money awaiting transfer: its
  // own spread (after operations), i.e. what it has actually earned.
  const ownIdr = lineValue("closing", "IDR") - heldIdr;
  const heldUsd = fx.client_money_held.USD?.amount || 0;
  const partial = fx.transfers.some((r) => !r.fully_covered);

  return (
    <div className="page shadcn-root">
      <style>{CSS}</style>
      <PageBack label={t("Back")} />
      <PageHeader
        title={t("Fund Flow")}
        sub={t("Money in and out of the branch, per currency as the banks hold it, and what transfers to HQ earned on the exchange rate.")}
        actions={perms.can("statements", "export") ? (
          <Button asChild variant="outline" size="lg"><a href={csv}>{t("Export CSV")}</a></Button>
        ) : null}
      />

      <div className="filter-bar ff-filters">
        <Select value={branch} onValueChange={(v) => go({ branch: v })}>
          <SelectTrigger className="w-44" style={{ height: 40 }}><SelectValue /></SelectTrigger>
          <SelectContent>
            {branch_choices.map((b) => <SelectItem key={b.value} value={b.value}>{b.label}</SelectItem>)}
          </SelectContent>
        </Select>
        <SeasonSelect seasons={seasons} dateFrom={date_from} dateTo={date_to}
          onPick={(f, tt) => { setFrom(f); setTo(tt); go({ from: f, to: tt }); }} />
        <input type="date" className="hms-dv-date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} aria-label={t("From")} />
        <span style={{ color: "var(--muted-foreground)" }}>–</span>
        <input type="date" className="hms-dv-date" value={to} min={from} onChange={(e) => setTo(e.target.value)} aria-label={t("To")} />
        <Button variant="outline" onClick={() => go()}>{t("Apply")}</Button>
      </div>

      <div className="hms-kpi-row cols-5 ff-kpis">
        <KpiCard label={t("FX profit in period")}
          value={fx.unpriced && fx.unpriced === fx.transfers.length ? "—" : fmt(fx.total_profit_idr)} unit="IDR"
          foot={fx.unpriced
            ? t("{n} transfers to HQ · {u} without original amount, not counted", { n: fx.transfers.length, u: fx.unpriced })
            : t("{n} transfers to HQ", { n: fx.transfers.length })} />
        {/* The branch's profit is what is left after its own costs (business rules 2026-09-29). */}
        <KpiCard label={t("Net branch profit")}
          value={net_profit_idr == null ? "—" : fmt(net_profit_idr)} unit="IDR"
          foot={t("after {n} IDR of expenses paid", { n: fmt(expenses_idr) })} />
        <KpiCard label={t("Sent to HQ")} value={fmt(-lineValue("sent_hq", "IDR"))} unit="IDR" foot={t("in this period")} />
        <KpiCard label={t("Client rupiah not yet sent")} value={fmt(heldIdr)} unit="IDR"
          foot={heldUsd ? t("+ {n} USD not yet exchanged", { n: fmt(heldUsd) }) : t("{n} SAR still owed to HQ", { n: fmt(fx.client_money_held.IDR?.sar || 0) })} />
        <KpiCard label={t("Branch's own rupiah")} value={fmt(ownIdr)} unit="IDR" foot={t("closing rupiah − client money")} />
      </div>

      <h2 className="ff-h">{t("Per currency")}</h2>
      <div className="hms-list-card">
        <Table columns={lineColumns} rows={lineRows} rowKey={(l) => l.key} />
      </div>
      {picked && (
        <>
          <h2 className="ff-h">
            {t(labelOf[picked.line])} · {picked.currency}
            <button type="button" className="ff-clear" onClick={() => setPicked(null)}>{t("Close")}</button>
          </h2>
          <div className="hms-list-card"><Table columns={txColumns} rows={shown} rowKey={(x, i) => `${x.date}-${i}`} /></div>
        </>
      )}

      <h2 className="ff-h">{t("Per account")}</h2>
      <div className="hms-list-card">
        <Table columns={accountColumns} rows={flow.accounts} rowKey={(a) => `${a.label}-${a.currency}`} />
      </div>

      <h2 className="ff-h">{t("FX profit per transfer")}</h2>
      <div className="hms-list-card">
        {fx.transfers.length ? (
          <Table columns={transferColumns} rows={fx.transfers} rowKey={(r) => r.id} />
        ) : (
          <p className="ff-empty">{t("No transfers to HQ in this period.")}</p>
        )}
      </div>
      <p className="ff-note">
        {t("Profit = SAR sent × average cost of the client money held − rupiah actually sent (weighted average).")}
        {partial ? " " + t("* The transfer was larger than the client money on record; profit covers only the matched part.") : ""}
      </p>
    </div>
  );
}

const CSS = `
.shadcn-root .ff-filters { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ff-filters input[type="date"] { width: auto; flex: none; height: 40px; }
.ff-cur { display: none; font-size: 11px; font-weight: 500; color: var(--muted-foreground); }
@media (max-width: 640px) {
  .shadcn-root .ff-filters > :first-child { flex: 1 1 100%; width: 100%; }
  .ff-filters input[type="date"] { flex: 1 1 0; min-width: 0; }
  .ff-cur { display: inline; }
}
.ff-kpis { margin-bottom: 18px; }
.ff-h { display: flex; align-items: center; gap: 10px; margin: 22px 0 10px; font-size: 14px; font-weight: 600; }
.ff-cell { background: none; border: none; padding: 0; font: inherit; cursor: pointer; text-decoration: underline; text-decoration-color: var(--border); text-underline-offset: 3px; }
.ff-cell:hover { text-decoration-color: var(--foreground); }
.ff-clear { margin-left: auto; height: 28px; padding: 0 10px; border-radius: 999px; border: 1px solid var(--border); background: var(--card); font: inherit; font-size: 12px; cursor: pointer; }
.ff-empty { padding: 18px; margin: 0; font-size: 12.5px; color: var(--muted-foreground); text-align: center; }
.ff-note { margin: 10px 2px 0; font-size: 12px; color: var(--muted-foreground); }
`;
