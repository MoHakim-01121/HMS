import { useState } from "react";
import { Link, router } from "@inertiajs/react";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import {
  ListPage, Kpis, Kpi, Toolbar, MonthNav, SearchTool, FilterMenu, FilterSection, Check, ExportMenu, Primary,
  TableCard, RowMenu, Pill, Amt, Pager, Empty, MONTHS, fmtN, dShort, useListNav, rowNav,
} from "../../components/shadcn/list-a.jsx";
import TrackingPanel from "./TrackingPanel.jsx";
import RecapPanel, { RECAP_CSS } from "./RecapPanel.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

const STATE = { pending: ["amber", "In transit"], partial: ["info-o", "Partially received"], received: ["green", "Received"] };
const monthName = (ym, t) => (ym ? t(MONTHS[+ym.slice(5, 7) - 1]) : "");
const signed = (v) => (v > 0 ? "+" : "") + fmtN(v);

// Remittance to HQ, as on the Record View HMS canvas: what was sent in the
// month, cash in transit (filters the table), what is still due to HQ and the
// FX gain; the table shows IDR sent against SAR received. Tracking and the
// monthly recap stay one click away.
export default function List({ tab = "transfers", remittances = [], filters: f, years = [], counts = {}, account_counts = [],
  kpis, totals, sees_figures, pagination, tracking, monthly }) {
  const { t } = useI18n();
  const perms = usePerms();
  const openForm = useFormModal();
  const [go, loading] = useListNav("/remittance/", f);
  const [draft, setDraft] = useState(f);
  const tog = (key, v) => setDraft((d) => ({ ...d, [key]: d[key].includes(v) ? d[key].filter((x) => x !== v) : [...d[key], v] }));
  const transitOnly = f.status.length === 1 && f.status[0] === "transit";
  const filterCount = (f.status.length ? 1 : 0) + (f.acct.length ? 1 : 0);
  const prevName = kpis ? monthName(kpis.prev_month, t) : "";
  const label = f.month ? monthName(f.month, t) : f.year && f.year !== "all" ? f.year : t("All dates");

  const views = (
    <span className="la-lg" style={{ fontSize: 13 }}>
      {[["transfers", t("Transfers"), "/remittance/"], ["tracking", t("Tracking"), "/remittance/?tab=tracking"], ["recap", t("Monthly recap"), "/remittance/?tab=recap"]].map(([k, l, href]) => (
        k === tab ? <b key={k} style={{ color: "var(--foreground)" }}>{l}</b> : <Link key={k} href={href} style={{ color: "var(--muted-foreground)", fontWeight: 500 }}>{l}</Link>
      ))}
    </span>
  );

  if (tab !== "transfers") {
    return (
      <ListPage title={t("Remittance")} legend={views}>
        <style>{RECAP_CSS}</style>
        {tab === "tracking" && <TrackingPanel tracking={tracking} />}
        {tab === "recap" && <RecapPanel monthly={monthly} t={t} />}
      </ListPage>
    );
  }

  return (
    <ListPage title={t("Remittance")} legend={views} loading={loading}>
      {kpis && (
        <Kpis>
          <Kpi label={t("Remitted to HQ")} value={fmtN(kpis.idr)} unit="IDR"
            delta={kpis.delta && { text: kpis.delta, good: !kpis.delta.startsWith("-"), title: t("{d} vs {m}", { d: kpis.delta, m: prevName }) }}
            foot={t("{v} SAR value, {p} in {m}", { v: fmtN(kpis.sar), p: fmtN(kpis.prev_sar), m: prevName })} />
          <Kpi label={t("Cash in transit")} value={fmtN(kpis.transit_sar)} unit="SAR" tone={kpis.transit_sar ? "warn" : undefined}
            foot={kpis.transit_count ? t("{n} remittances, oldest waiting {d} days", { n: kpis.transit_count, d: kpis.transit_oldest }) : t("Everything sent has arrived")}
            on={transitOnly} onClick={() => go({ status: transitOnly ? [] : ["transit"] })} />
          <Kpi label={t("Due to HQ")} value={fmtN(kpis.due_to_hq)} unit="SAR"
            foot={t("Client money received not yet remitted")} />
          <Kpi label={t("FX gain")} value={signed(kpis.fx_gain)} unit="IDR" tone={kpis.fx_gain > 0 ? "good" : undefined}
            delta={kpis.fx_delta && { text: kpis.fx_delta, good: !kpis.fx_delta.startsWith("-"), title: t("{d} vs {m}", { d: kpis.fx_delta, m: prevName }) }}
            foot={[kpis.avg_send_rate && t("Average sent rate {r}", { r: fmtN(kpis.avg_send_rate) }), kpis.book_rate && t("book rate {r}", { r: fmtN(kpis.book_rate) })].filter(Boolean).join(", ") || t("No transfer this month")} />
        </Kpis>
      )}

      <Toolbar spaced={!!kpis} left={<MonthNav month={f.month} year={f.year} years={years} onChange={(p) => go(p)} />}>
        <SearchTool value={f.q} onSearch={(q) => go({ q })} placeholder={t("Search remittance, reference")} />
        <FilterMenu count={filterCount} onOpen={() => setDraft(f)}
          onReset={() => setDraft({ ...draft, status: [], acct: [] })}
          onApply={() => go({ status: draft.status, acct: draft.acct })}>
          <FilterSection label={t("Status")}>
            <Check on={draft.status.includes("transit")} onClick={() => tog("status", "transit")} label={t("In transit")} count={counts.transit} />
            <Check on={draft.status.includes("partial")} onClick={() => tog("status", "partial")} label={t("Partially received")} count={counts.partial} />
            <Check on={draft.status.includes("received")} onClick={() => tog("status", "received")} label={t("Received")} count={counts.received} />
          </FilterSection>
          {account_counts.length > 1 && (
            <FilterSection label={t("From account")}>
              {account_counts.map((a) => <Check key={a.name} on={draft.acct.includes(a.name)} onClick={() => tog("acct", a.name)} label={a.name} count={a.count} />)}
            </FilterSection>
          )}
        </FilterMenu>
        <ExportMenu items={[
          { label: "CSV", href: "/remittance/export/csv/" },
          f.month && { label: t("FX report"), hint: t("Rate and FX gain per remittance, PDF"), href: `/remittance/export/pdf/?month=${f.month}`, external: true },
        ].filter(Boolean)} />
        {perms.can("remittance", "create") && sees_figures && <Primary label={t("New remittance")} onClick={() => openForm("/remittance/new/")} onPrefetch={() => openForm.prefetch("/remittance/new/")} />}
      </Toolbar>

      <TableCard cols={[92, 64, null, 160, 130, 64, 110, 136, 48]}
        empty={!remittances.length && <Empty title={t("No remittances")} sub={t("Nothing was sent in this period with these filters.")} />}>
        <thead><tr>
          <th>{t("Remittance")}</th><th>{t("Sent")}</th><th>{t("From")}</th>
          <th className="n">{t("Sent")}</th><th className="n">{t("Received at HQ")}</th><th className="n">{t("Rate")}</th>
          <th className="n">{t("FX gain (IDR)")}</th><th>{t("Status")}</th><th className="c">{t("Action")}</th>
        </tr></thead>
        <tbody>
          {remittances.map((r) => {
            const [tone, lbl] = STATE[r.state] || STATE.pending;
            return (
              <tr key={r.id} {...rowNav(`/remittance/${r.id}/`)}>
                <td><span className="mono">{r.remittance_number}</span></td>
                <td>{dShort(r.date)}</td>
                <td className="ell">{r.from}<span className="sub">{t("to {a}", { a: r.to })}</span></td>
                <td className="n"><Amt code={r.currency} value={r.amount_sent} /></td>
                <td className="n">{r.received_sar ? <Amt code="SAR" value={r.received_sar} /> : <span className="mut">0</span>}</td>
                <td className="n">{r.currency === "SAR" ? <span className="mut">—</span> : fmtN(r.rate)}</td>
                <td className="n">{r.state !== "received" && r.fx_gain_idr == null ? <span className="mut">{t("on receipt")}</span>
                  : r.fx_gain_idr == null ? <span className="mut">{t("Not priced")}</span>
                  : <span className={r.fx_gain_idr >= 0 ? "good" : "late"}>{signed(r.fx_gain_idr)}</span>}</td>
                <td><Pill tone={tone}>{t(lbl)}</Pill>{r.state !== "received" && <span className="sub">{t("{n} days", { n: r.days })}</span>}</td>
                <td className="c">
                  <RowMenu label={t("Actions for {n}", { n: r.remittance_number })} items={[
                    r.can_record_receipt && perms.can("remittance", "edit") && { label: t("Record receipt"), onClick: () => router.visit(`/remittance/${r.id}/receipt/`) },
                    r.proof_url && { label: t("View proof"), href: r.proof_url, external: true },
                    perms.can("remittance", "edit") && { label: t("Edit"), onClick: () => openForm(`/remittance/${r.id}/edit/`) },
                    { label: "PDF", href: `/remittance/${r.id}/pdf/`, external: true },
                  ]} />
                </td>
              </tr>
            );
          })}
        </tbody>
        {totals && remittances.length > 0 && (
          <tfoot><tr>
            <td colSpan={3}>{t("{p} total", { p: label })}</td>
            <td className="n"><Amt code="IDR" value={totals.idr} /></td>
            <td className="n"><Amt code="SAR" value={totals.received_sar} /></td>
            <td className="n">{totals.avg_rate ? fmtN(totals.avg_rate) : ""}</td>
            <td className={"n" + (totals.fx_gain_idr > 0 ? " good" : "")}>{signed(totals.fx_gain_idr)}</td>
            <td colSpan={2} className="lbl">{totals.transit_sar ? t("{v} SAR cash in transit", { v: fmtN(totals.transit_sar) }) : ""}</td>
          </tr></tfoot>
        )}
      </TableCard>

      <Pager p={pagination} perPage={f.per} onPage={(page) => go({ page })} onPerPage={(per) => go({ per })} />
    </ListPage>
  );
}
