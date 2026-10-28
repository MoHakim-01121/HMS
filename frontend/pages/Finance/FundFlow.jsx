import { Fragment, useState } from "react";
import { ListPage, Toolbar, Kpis, Kpi, FilterMenu, FilterSection, Check, DateRange, ExportMenu, PickMenu, TableCard, PRow, PBand, Section, usePhone, Empty, fmtN, dLong, useListNav, rowNav, Tr, Th, Td, Note, ToolButton } from "../../components/shadcn/list-a.jsx";
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
  const phone = usePhone();
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

      <Toolbar left={<Note>{range}</Note>}>
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

      <Section title={t("Per currency")} sub={phone ? t("Tap a line to see its transactions.") : t("Click an amount to see its transactions.")} />
      <TableCard cols={[null, ...currencies.map(() => 170)]}
        phone={currencies.map((c) => (
          <Fragment key={c}>
            <PBand label={c} />
            {lineRows.filter((l) => edge(l.key) || l.values[c]).map((l) => {
              const v = l.values[c] || 0;
              const drill = v !== 0 && !edge(l.key);
              return (
                <PRow key={l.key} no={t(l.label)} end={fmtN(v)}
                  amountTone={v < 0 ? "text-danger-text" : !v ? "font-medium text-muted-foreground" : undefined}
                  onClick={drill ? () => setPicked({ line: l.key, currency: c }) : undefined} />
              );
            })}
          </Fragment>
        ))}>
        <thead><Tr><Th>{t("Line")}</Th>{currencies.map((c) => <Th key={c} className="text-right">{c}</Th>)}</Tr></thead>
        <tbody>
          {lineRows.map((l) => (
            <Tr key={l.key} row="static">
              <Td className={edge(l.key) ? "font-medium" : undefined}>{t(l.label)}</Td>
              {currencies.map((c) => {
                const v = l.values[c] || 0;
                const drill = v !== 0 && !edge(l.key);
                return (
                  <Td key={c} className={"text-right" + (v < 0 ? " font-medium text-danger-text" : !v ? " text-muted-foreground" : "") + (drill ? " underline decoration-border underline-offset-3 hover:decoration-foreground" : "")}
                    style={{ fontWeight: l.key === "closing" ? 600 : undefined }}>
                    {drill ? (
                      <button type="button" className="m-0 cursor-pointer rounded-[4px] border-0 bg-transparent p-0 text-inherit [font:inherit] [text-decoration:inherit] [text-underline-offset:inherit] focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-ring" aria-pressed={picked?.line === l.key && picked?.currency === c}
                        aria-label={t("{line} in {currency}: see its transactions", { line: t(l.label), currency: c })}
                        onClick={() => setPicked({ line: l.key, currency: c })}>{fmtN(v)}</button>
                    ) : fmtN(v)}
                  </Td>
                );
              })}
            </Tr>
          ))}
        </tbody>
      </TableCard>

      {picked && (
        <>
          <Section title={`${t(labelOf[picked.line])} · ${picked.currency}`}>
            <ToolButton onClick={() => setPicked(null)}>{t("Close")}</ToolButton>
          </Section>
          <TableCard cols={[120, 220, null, 180]} empty={!shown.length && <Empty title={t("No transactions")} />}
            phone={shown.map((x, i) => (
              <PRow key={`${x.date}-${i}`} href={x.link || undefined} no={x.reference || x.source_type}
                end={`${fmtN(x.amount)} ${x.currency}`} amountTone={x.amount < 0 ? "text-danger-text" : undefined}
                meta={[dLong(x.date), x.account].filter(Boolean).join(" · ")} />
            ))}>
            <thead><Tr><Th>{t("Date")}</Th><Th>{t("Account")}</Th><Th>{t("Reference")}</Th><Th className="text-right">{t("Amount")}</Th></Tr></thead>
            <tbody>
              {shown.map((x, i) => (
                <Tr key={`${x.date}-${i}`} row={x.link ? undefined : "static"} {...(x.link ? rowNav(x.link) : {})}>
                  <Td>{dLong(x.date)}</Td>
                  <Td className="truncate">{x.account}</Td>
                  <Td className="truncate">{x.reference || x.source_type}</Td>
                  <Td className={"text-right" + (x.amount < 0 ? " font-medium text-danger-text" : "")}>{fmtN(x.amount)} <span className="text-muted-foreground">{x.currency}</span></Td>
                </Tr>
              ))}
            </tbody>
          </TableCard>
        </>
      )}

      <Section title={t("Per account")} />
      <TableCard cols={[null, 100, 150, 150, 150, 150]}
        phone={flow.accounts.map((a) => (
          <PRow key={`${a.label}-${a.currency}`} no={a.label} end={`${fmtN(a.closing)} ${a.currency}`}
            amountTone={a.closing < 0 ? "text-danger-text" : undefined}
            meta={`${t("Opening")} ${fmtN(a.opening)} · ${t("In")} ${fmtN(a.inflow)} · ${t("Out")} ${fmtN(a.outflow)}`} />
        ))}>
        <thead><Tr>
          <Th>{t("Account")}</Th><Th>{t("Currency")}</Th><Th className="text-right">{t("Opening")}</Th>
          <Th className="text-right">{t("In")}</Th><Th className="text-right">{t("Out")}</Th><Th className="text-right">{t("Closing")}</Th>
        </Tr></thead>
        <tbody>
          {flow.accounts.map((a) => (
            <Tr key={`${a.label}-${a.currency}`} row="static">
              <Td className="truncate font-medium">{a.label}</Td>
              <Td className="text-muted-foreground">{a.currency}</Td>
              <Td className={"text-right" + (a.opening < 0 ? " font-medium text-danger-text" : "")}>{fmtN(a.opening)}</Td>
              <Td className={"text-right" + (a.inflow ? "" : " text-muted-foreground")}>{fmtN(a.inflow)}</Td>
              <Td className={"text-right" + (a.outflow ? "" : " text-muted-foreground")}>{fmtN(a.outflow)}</Td>
              <Td className={"text-right" + (a.closing < 0 ? " font-medium text-danger-text" : "")}><b>{fmtN(a.closing)}</b></Td>
            </Tr>
          ))}
        </tbody>
      </TableCard>

      <Section title={t("FX profit per transfer")} />
      <TableCard cols={[120, 110, 120, 150, 120, 120, 150]}
        phone={fx.transfers.map((r) => (
          <PRow key={r.id} href={`/remittance/${r.id}/`} mono no={r.remittance_number}
            end={r.profit_idr == null ? t("Not priced") : `${fmtN(r.profit_idr)}${!r.fully_covered ? " *" : ""} IDR`}
            amountTone={r.profit_idr == null ? "font-medium text-muted-foreground" : r.profit_idr < 0 ? "text-danger-text" : undefined}
            meta={[dLong(r.date), `${fmtN(r.sar)} SAR`, r.idr_sent != null ? `${fmtN(r.idr_sent)} IDR` : null].filter(Boolean).join(" · ")}
            note={r.avg_rate != null || r.send_rate != null ? `${r.avg_rate != null ? fmtN(r.avg_rate) : "–"} → ${r.send_rate != null ? fmtN(r.send_rate) : "–"}` : null} />
        ))}
        empty={!fx.transfers.length && <Empty title={t("No transfers to HQ")} sub={t("Transfers in this period show here with what they earned.")} />}>
        <thead><Tr>
          <Th>{t("Transfer")}</Th><Th>{t("Date")}</Th><Th className="text-right">SAR</Th><Th className="text-right">{t("IDR sent")}</Th>
          <Th className="text-right">{t("Average rate")}</Th><Th className="text-right">{t("Send rate")}</Th><Th className="text-right">{t("FX profit (IDR)")}</Th>
        </Tr></thead>
        <tbody>
          {fx.transfers.map((r) => (
            <Tr key={r.id} {...rowNav(`/remittance/${r.id}/`)}>
              <Td><span className="font-mono text-[13px] font-semibold">{r.remittance_number}</span></Td>
              <Td>{dLong(r.date)}</Td>
              <Td className="text-right">{fmtN(r.sar)}</Td>
              <Td className="text-right">{r.idr_sent != null ? fmtN(r.idr_sent) : <span className="text-muted-foreground">–</span>}</Td>
              <Td className="text-right">{r.avg_rate != null ? fmtN(r.avg_rate) : <span className="text-muted-foreground">–</span>}</Td>
              <Td className="text-right">{r.send_rate != null ? fmtN(r.send_rate) : <span className="text-muted-foreground">–</span>}</Td>
              <Td className={"text-right" + (r.profit_idr < 0 ? " font-medium text-danger-text" : "")}>
                {r.profit_idr == null ? <span className="text-muted-foreground" title={t("No IDR amount on this transfer")}>{t("Not priced")}</span>
                  : <b>{fmtN(r.profit_idr)}{!r.fully_covered ? " *" : ""}</b>}
              </Td>
            </Tr>
          ))}
        </tbody>
      </TableCard>
      <p className="m-0 text-[12px] text-muted-foreground">
        {t("Profit = SAR sent × average cost of the client money held − rupiah actually sent (weighted average).")}
        {partial ? " " + t("* The transfer was larger than the client money on record; profit covers only the matched part.") : ""}
      </p>
    </ListPage>
  );
}
