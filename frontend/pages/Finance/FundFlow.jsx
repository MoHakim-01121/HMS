import { useState } from "react";
import {
  ListPage, Toolbar, Kpis, Kpi, FilterMenu, FilterSection, Check, DateRange, ExportMenu, PickMenu,
  TableCard, Section, Empty, fmtN, dLong, useListNav, rowNav,
} from "../../components/shadcn/list-a.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

// Arus Dana: how much a branch received from clients, exchanged, sent to HQ,
// spent and refunded — per currency, as the banks hold it — and what its
// transfers to HQ earned on the exchange spread (its only income).
export default function FundFlow({ branch, branch_choices = [], date_from, date_to, seasons = [], flow, fx, expenses_idr = 0, net_profit_idr = null }) {
  const { t } = useI18n();
  const perms = usePerms();
  const cur = { branch, from: date_from, to: date_to };
  const [go, loading] = useListNav("/finance/fund-flow/", cur);
  const [draft, setDraft] = useState(cur);
  const [picked, setPicked] = useState(null); // {line, currency} drill-down
  const currencies = flow.currencies;
  const labelOf = Object.fromEntries(flow.lines.map((l) => [l.key, l.label]));
  const csv = `/finance/fund-flow/export/csv/?branch=${branch}&from=${date_from}&to=${date_to}`;
  const season = seasons.find((s) => s.date_from === date_from && s.date_to === date_to);
  const range = season ? t("Season {s}", { s: season.name }) : `${dLong(date_from)} – ${dLong(date_to)}`;

  const edge = (k) => ["opening", "closing"].includes(k);
  const lineRows = flow.lines.filter((l) => edge(l.key) || currencies.some((c) => l.values[c]));
  const shown = picked ? flow.transactions.filter((x) => x.line === picked.line && x.currency === picked.currency) : [];

  const heldIdr = fx.client_money_held.IDR?.amount || 0;
  const lineValue = (key, c) => flow.lines.find((l) => l.key === key)?.values[c] || 0;
  // Rupiah the branch holds that is not client money awaiting transfer: its
  // own spread (after operations), i.e. what it has actually earned.
  const ownIdr = lineValue("closing", "IDR") - heldIdr;
  const heldUsd = fx.client_money_held.USD?.amount || 0;
  const partial = fx.transfers.some((r) => !r.fully_covered);
  const noFx = fx.unpriced && fx.unpriced === fx.transfers.length;

  return (
    <ListPage title={t("Fund Flow")} loading={loading}>
      <Kpis dense>
        <Kpi label={t("FX profit in period")} value={noFx ? t("Not priced yet") : fmtN(fx.total_profit_idr)} unit={noFx ? "" : "IDR"} tone={noFx ? "none" : undefined}
          foot={fx.unpriced
            ? t("{n} transfers to HQ · {u} without original amount, not counted", { n: fx.transfers.length, u: fx.unpriced })
            : t("{n} transfers to HQ", { n: fx.transfers.length })} />
        {/* Branch profit is the FX gain only; expenses are claimed back from HQ, never deducted. */}
        <Kpi label={t("Branch profit")} value={net_profit_idr == null ? t("No FX gain yet") : fmtN(net_profit_idr)} unit={net_profit_idr == null ? "" : "IDR"}
          tone={net_profit_idr == null ? "none" : net_profit_idr < 0 ? "warn" : undefined}
          foot={t("Expenses {n} IDR, claimed back from HQ", { n: fmtN(expenses_idr) })} />
        <Kpi label={t("Sent to HQ")} value={fmtN(-lineValue("sent_hq", "IDR"))} unit="IDR" foot={t("in this period")} />
        <Kpi label={t("Client rupiah not yet sent")} value={fmtN(heldIdr)} unit="IDR"
          foot={heldUsd ? t("+ {n} USD not yet exchanged", { n: fmtN(heldUsd) }) : t("{n} SAR still owed to HQ", { n: fmtN(fx.client_money_held.IDR?.sar || 0) })} />
        <Kpi label={t("Branch's own rupiah")} value={fmtN(ownIdr)} unit="IDR" tone={ownIdr < 0 ? "warn" : undefined} foot={t("closing rupiah − client money")} />
      </Kpis>

      <Toolbar left={<span className="la-note">{range}</span>}>
        {branch_choices.length > 1 && (
          <PickMenu value={branch} options={branch_choices} onPick={(b) => go({ branch: b })} label={t("Branch")} />
        )}
        <FilterMenu count={season ? 1 : 0} onOpen={() => setDraft(cur)} onReset={() => setDraft({ ...draft, from: "", to: "" })}
          onApply={() => go({ from: draft.from, to: draft.to })}>
          {seasons.length > 0 && (
            <FilterSection label={t("Season")}>
              {seasons.map((s) => (
                <Check radio key={s.id} label={s.name} on={draft.from === s.date_from && draft.to === s.date_to}
                  onClick={() => setDraft({ ...draft, from: s.date_from, to: s.date_to })} />
              ))}
            </FilterSection>
          )}
          <FilterSection label={t("Date")} hint={t("Empty: this month so far.")}>
            <DateRange from={draft.from} to={draft.to} onFrom={(v) => setDraft({ ...draft, from: v })} onTo={(v) => setDraft({ ...draft, to: v })} />
          </FilterSection>
        </FilterMenu>
        {perms.can("statements", "export") && <ExportMenu items={[{ label: "CSV", href: csv }]} />}
      </Toolbar>

      <Section title={t("Per currency")} sub={t("Click an amount to see its transactions.")} />
      <TableCard cols={[null, ...currencies.map(() => 170)]}>
        <thead><tr><th>{t("Line")}</th>{currencies.map((c) => <th key={c} className="n">{c}</th>)}</tr></thead>
        <tbody>
          {lineRows.map((l) => (
            <tr key={l.key} className="static">
              <td className={edge(l.key) ? "strong" : undefined}>{t(l.label)}</td>
              {currencies.map((c) => {
                const v = l.values[c] || 0;
                const drill = v !== 0 && !edge(l.key);
                return (
                  <td key={c} className={"n" + (v < 0 ? " late" : !v ? " zero" : "") + (drill ? " lnk" : "")}
                    style={{ fontWeight: l.key === "closing" ? 600 : undefined }}>
                    {drill ? (
                      <button type="button" className="la-drill" aria-pressed={picked?.line === l.key && picked?.currency === c}
                        aria-label={t("{line} in {currency}: see its transactions", { line: t(l.label), currency: c })}
                        onClick={() => setPicked({ line: l.key, currency: c })}>{fmtN(v)}</button>
                    ) : fmtN(v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </TableCard>

      {picked && (
        <>
          <Section title={`${t(labelOf[picked.line])} · ${picked.currency}`}>
            <button type="button" className="la-tool" onClick={() => setPicked(null)}>{t("Close")}</button>
          </Section>
          <TableCard cols={[120, 220, null, 180]} empty={!shown.length && <Empty title={t("No transactions")} />}>
            <thead><tr><th>{t("Date")}</th><th>{t("Account")}</th><th>{t("Reference")}</th><th className="n">{t("Amount")}</th></tr></thead>
            <tbody>
              {shown.map((x, i) => (
                <tr key={`${x.date}-${i}`} className={x.link ? "" : "static"} {...(x.link ? rowNav(x.link) : {})}>
                  <td>{dLong(x.date)}</td>
                  <td className="ell">{x.account}</td>
                  <td className="ell">{x.reference || x.source_type}</td>
                  <td className={"n" + (x.amount < 0 ? " late" : "")}>{fmtN(x.amount)} <span className="mut">{x.currency}</span></td>
                </tr>
              ))}
            </tbody>
          </TableCard>
        </>
      )}

      <Section title={t("Per account")} />
      <TableCard cols={[null, 100, 150, 150, 150, 150]}>
        <thead><tr>
          <th>{t("Account")}</th><th>{t("Currency")}</th><th className="n">{t("Opening")}</th>
          <th className="n">{t("In")}</th><th className="n">{t("Out")}</th><th className="n">{t("Closing")}</th>
        </tr></thead>
        <tbody>
          {flow.accounts.map((a) => (
            <tr key={`${a.label}-${a.currency}`} className="static">
              <td className="ell strong">{a.label}</td>
              <td className="mut">{a.currency}</td>
              <td className={"n" + (a.opening < 0 ? " late" : "")}>{fmtN(a.opening)}</td>
              <td className={"n" + (a.inflow ? "" : " zero")}>{fmtN(a.inflow)}</td>
              <td className={"n" + (a.outflow ? "" : " zero")}>{fmtN(a.outflow)}</td>
              <td className={"n" + (a.closing < 0 ? " late" : "")}><b>{fmtN(a.closing)}</b></td>
            </tr>
          ))}
        </tbody>
      </TableCard>

      <Section title={t("FX profit per transfer")} />
      <TableCard cols={[120, 110, 120, 150, 120, 120, 150]}
        empty={!fx.transfers.length && <Empty title={t("No transfers to HQ")} sub={t("Transfers in this period show here with what they earned.")} />}>
        <thead><tr>
          <th>{t("Transfer")}</th><th>{t("Date")}</th><th className="n">SAR</th><th className="n">{t("IDR sent")}</th>
          <th className="n">{t("Average rate")}</th><th className="n">{t("Send rate")}</th><th className="n">{t("FX profit (IDR)")}</th>
        </tr></thead>
        <tbody>
          {fx.transfers.map((r) => (
            <tr key={r.id} {...rowNav(`/remittance/${r.id}/`)}>
              <td><span className="mono">{r.remittance_number}</span></td>
              <td>{dLong(r.date)}</td>
              <td className="n">{fmtN(r.sar)}</td>
              <td className="n">{r.idr_sent != null ? fmtN(r.idr_sent) : <span className="mut">–</span>}</td>
              <td className="n">{r.avg_rate != null ? fmtN(r.avg_rate) : <span className="mut">–</span>}</td>
              <td className="n">{r.send_rate != null ? fmtN(r.send_rate) : <span className="mut">–</span>}</td>
              <td className={"n" + (r.profit_idr < 0 ? " late" : "")}>
                {r.profit_idr == null ? <span className="mut" title={t("No IDR amount on this transfer")}>{t("Not priced")}</span>
                  : <b>{fmtN(r.profit_idr)}{!r.fully_covered ? " *" : ""}</b>}
              </td>
            </tr>
          ))}
        </tbody>
      </TableCard>
      <p className="la-fnote">
        {t("Profit = SAR sent × average cost of the client money held − rupiah actually sent (weighted average).")}
        {partial ? " " + t("* The transfer was larger than the client money on record; profit covers only the matched part.") : ""}
      </p>
    </ListPage>
  );
}
