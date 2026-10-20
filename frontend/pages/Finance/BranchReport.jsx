import { useEffect, useState } from "react";
import { router, usePage } from "@inertiajs/react";
import {
  ListPage, Kpis, Kpi, Toolbar, TableCard, Empty, ExportMenu, DateRange, LIcon, fmtN,
} from "../../components/shadcn/list-a.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";

const KINDS = [["month", "Month"], ["quarter", "Quarter"], ["year", "Year"], ["season", "Season"], ["range", "Date range"]];
const pad = (n) => String(n).padStart(2, "0");
const rate = (r) => (r == null ? "—" : r.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));

// Step a month, quarter or year value back or forward.
function shift(kind, value, d) {
  if (kind === "month") {
    const [y, m] = value.split("-").map(Number);
    const dt = new Date(y, m - 1 + d, 1);
    return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}`;
  }
  if (kind === "quarter") {
    const [y, q] = value.split("-Q").map(Number);
    const n = y * 4 + (q - 1) + d;
    return `${Math.floor(n / 4)}-Q${(n % 4) + 1}`;
  }
  return String(Number(value) + d);
}

// Period names in the UI's language (the server only sends the dates).
function periodName(p, kind, loc) {
  if (!p) return "";
  const d = (iso) => { const [y, m, dd] = iso.split("-").map(Number); return new Date(y, m - 1, dd); };
  const a = d(p.date_from), b = d(p.date_to);
  if (kind === "month") return a.toLocaleDateString(loc, { month: "long", year: "numeric" });
  if (kind === "quarter") return `Q${Math.floor(a.getMonth() / 3) + 1} ${a.getFullYear()}`;
  if (kind === "year") return String(a.getFullYear());
  if (kind === "range") return `${shortDate(p.date_from, loc)} – ${shortDate(p.date_to, loc)}`;
  return p.label;
}
const shortDate = (iso, loc) => {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(loc, { day: "2-digit", month: "short", year: "numeric" });
};
const dayMonth = (iso, loc) => {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(loc, { day: "numeric", month: "short" });
};

// Branch report (2026-10-19): the branch's profit is its FX profit on
// transfers to head office; operating expenses are fronted by the branch and
// paid back by head office, so they show on their own with their claim
// status; the position is read on the last day of the period.
export default function BranchReport({
  branch, branch_choices = [], period = {}, seasons = [], report = {}, previous = null, profit_delta = null,
}) {
  const { t } = useI18n();
  const perms = usePerms();
  const loc = usePage().props.locale === "id" ? "id-ID" : "en-GB";
  const [range, setRange] = useState(period.kind === "range" ? { from: period.date_from, to: period.date_to } : { from: "", to: "" });
  // Inertia keeps this component mounted across visits: refill the range
  // inputs from the period the server settled on.
  useEffect(() => {
    if (period.kind === "range") setRange({ from: period.date_from, to: period.date_to });
  }, [period.kind, period.value]);
  const go = (p) => router.get("/finance/branch-report/", { branch, kind: period.kind, value: period.value, ...p }, { preserveScroll: true });
  const profit = report.profit || {};
  const exp = report.expenses || {};
  const pos = report.position || {};
  const prevLabel = periodName(period.prev, period.kind, loc);
  const qs = new URLSearchParams({ branch, kind: period.kind, value: period.value }).toString();

  const kindPicker = (
    <Select value={period.kind} onValueChange={(k) => go({ kind: k, value: "" })}>
      <SelectTrigger style={{ width: 130 }}><SelectValue /></SelectTrigger>
      <SelectContent>{KINDS.map(([k, l]) => <SelectItem key={k} value={k}>{t(l)}</SelectItem>)}</SelectContent>
    </Select>
  );
  let valuePicker;
  if (period.kind === "season") {
    valuePicker = seasons.length ? (
      <Select value={period.value} onValueChange={(v) => go({ value: v })}>
        <SelectTrigger style={{ width: 180 }}><SelectValue /></SelectTrigger>
        <SelectContent>{seasons.map((s) => <SelectItem key={s.id} value={String(s.id)}>{s.name}</SelectItem>)}</SelectContent>
      </Select>
    ) : <span className="mut">{t("No seasons yet")}</span>;
  } else if (period.kind === "range") {
    valuePicker = (
      <>
        <DateRange from={range.from} to={range.to} onFrom={(v) => setRange({ ...range, from: v })} onTo={(v) => setRange({ ...range, to: v })} />
        <button type="button" className="la-tool" disabled={!range.from || !range.to} onClick={() => go({ value: `${range.from}..${range.to}` })}>{t("Show")}</button>
      </>
    );
  } else {
    valuePicker = (
      <>
        <span className="la-month">{periodName(period, period.kind, loc)}</span>
        <button type="button" className="la-icon" aria-label={t("Previous")} onClick={() => go({ value: shift(period.kind, period.value, -1) })}>{LIcon.prev}</button>
        <button type="button" className="la-icon" aria-label={t("Next")} onClick={() => go({ value: shift(period.kind, period.value, 1) })}>{LIcon.next}</button>
      </>
    );
  }

  const profitValue = profit.fx_idr == null ? "—" : fmtN(profit.fx_idr);
  const transfers = profit.transfers || [];

  return (
    <ListPage title={t("Branch report")}>
      <style>{CSS}</style>
      <Toolbar left={<>{kindPicker}{valuePicker}</>}>
        {branch_choices.length > 1 && (
          <Select value={branch} onValueChange={(b) => go({ branch: b })}>
            <SelectTrigger style={{ width: 160 }}><SelectValue /></SelectTrigger>
            <SelectContent>{branch_choices.map((b) => <SelectItem key={b.value} value={b.value}>{b.label}</SelectItem>)}</SelectContent>
          </Select>
        )}
        {perms.can("statements", "export") && <ExportMenu items={[{ label: "CSV", href: `/finance/branch-report/export/csv/?${qs}` }]} />}
      </Toolbar>

      <Kpis>
        <Kpi label={t("Branch profit")} value={profitValue} unit="IDR"
          delta={profit_delta && { text: profit_delta, good: !profit_delta.startsWith("-"), title: t("{d} vs {m}", { d: profit_delta, m: prevLabel }) }}
          foot={profit.unpriced ? t("{n} transfers without a priced FX profit", { n: profit.unpriced })
            : previous ? t("FX profit on transfers to head office. {m}: {v} IDR", { m: prevLabel, v: previous.fx_idr == null ? "—" : fmtN(previous.fx_idr) })
            : t("FX profit on transfers to head office")} />
        <Kpi label={t("Operating expenses")} value={fmtN(exp.total)} unit="IDR"
          foot={previous ? t("{m}: {v} IDR. Paid back by head office, not deducted.", { m: prevLabel, v: fmtN(previous.expenses) }) : t("Paid back by head office, not deducted.")} />
        <Kpi label={t("Owed by head office")} value={fmtN(pos.owed_by_hq_idr)} unit="IDR" tone={pos.owed_by_hq_idr ? "warn" : undefined}
          href="/finance/claims/" foot={t("Expenses not reimbursed yet, as of {d}", { d: dayMonth(pos.as_of, loc) })} />
        <Kpi label={t("Rupiah cash")} value={fmtN(pos.cash_idr)} unit="IDR" foot={t("Bank and cash accounts, as of {d}", { d: dayMonth(pos.as_of, loc) })} />
      </Kpis>

      <h2 className="br-h2">{t("FX profit per transfer")}</h2>
      <TableCard cols={[110, 76, 110, 140, 96, 96, 130]}
        empty={!transfers.length && <Empty title={t("No transfers to head office")} sub={t("The branch earns its FX profit when it sends money to head office.")} />}>
        <thead><tr>
          <th>{t("Transfer")}</th><th>{t("Date")}</th><th className="n">SAR</th><th className="n">{t("IDR sent")}</th>
          <th className="n">{t("Average rate")}</th><th className="n">{t("Send rate")}</th><th className="n">{t("FX profit (IDR)")}</th>
        </tr></thead>
        <tbody>
          {transfers.map((x) => (
            <tr key={x.id} onClick={() => router.visit(`/remittance/${x.id}/`)}>
              <td><span className="mono">{x.remittance_number}</span></td>
              <td>{dayMonth(x.date, loc)}</td>
              <td className="n">{fmtN(x.sar)}</td>
              <td className="n">{fmtN(x.idr_sent)}</td>
              <td className="n">{rate(x.avg_rate)}</td>
              <td className="n">{rate(x.send_rate)}</td>
              <td className="n">{x.profit_idr == null ? <span className="mut">{t("Not priced")}</span> : fmtN(x.profit_idr)}</td>
            </tr>
          ))}
        </tbody>
      </TableCard>

      <h2 className="br-h2">{t("Operating expenses")}</h2>
      <TableCard cols={[null, 160]}
        empty={!exp.by_category?.length && <Empty title={t("No expenses paid")} sub={t("Nothing was paid in this period.")} />}>
        <thead><tr><th>{t("Category")}</th><th className="n">{t("Amount (IDR)")}</th></tr></thead>
        <tbody>
          {(exp.by_category || []).map((c) => <tr key={c.name}><td>{c.name}</td><td className="n">{fmtN(c.amount)}</td></tr>)}
          {exp.by_category?.length ? (<>
            <tr><td><span className="strong">{t("Total")}</span></td><td className="n"><span className="strong">{fmtN(exp.total)}</span></td></tr>
            <tr><td className="mut">{t("Reimbursed")}</td><td className="n">{fmtN(exp.paid_back)}</td></tr>
            <tr><td className="mut">{t("Claimed, waiting")}</td><td className="n">{fmtN(exp.claimed)}</td></tr>
            <tr><td className="mut">{t("Not claimed yet")}</td><td className="n">{fmtN(exp.unclaimed)}</td></tr>
          </>) : null}
        </tbody>
      </TableCard>

      <h2 className="br-h2">{t("Position as of {d}", { d: dayMonth(pos.as_of, loc) })}</h2>
      <TableCard cols={[null, 90, 160]}>
        <thead><tr><th>{t("Account")}</th><th>{t("Currency")}</th><th className="n">{t("Balance")}</th></tr></thead>
        <tbody>
          {(pos.accounts || []).map((a) => (
            <tr key={a.name}><td>{a.name}{a.kind === "staff" && <span className="sub">{t("Staff advance")}</span>}</td>
              <td>{a.currency}</td><td className="n">{fmtN(a.native)}</td></tr>
          ))}
          <tr><td>{t("Client receivables")}</td><td>SAR</td><td className="n">{fmtN(pos.receivable_sar)}</td></tr>
          <tr><td>{t("Client deposits")}</td><td>SAR</td><td className="n">{fmtN(pos.deposits_sar)}</td></tr>
          <tr><td>{t("Owed by head office")}</td><td>IDR</td><td className="n">{fmtN(pos.owed_by_hq_idr)}</td></tr>
        </tbody>
      </TableCard>
    </ListPage>
  );
}

// Section headings between the tables; the list pages have none of their own.
const CSS = `
.br-h2 { font-size: 15px; font-weight: 600; margin: 32px 0 12px; color: var(--foreground); }
`;
