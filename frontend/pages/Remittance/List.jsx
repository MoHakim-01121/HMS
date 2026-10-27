import { useState } from "react";
import { Link, router } from "@inertiajs/react";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { ListPage, Kpis, Kpi, Toolbar, MonthNav, SearchTool, FilterMenu, FilterSection, Check, ExportMenu, Primary, TableCard, RowMenu, Pill, Amt, Pager, Empty, MONTHS, fmtN, dShort, useListNav, rowNav, Tr, Th, Td } from "../../components/shadcn/list-a.jsx";
import { cn } from "@/lib/utils";
import TrackingPanel from "./TrackingPanel.jsx";
import RecapPanel from "./RecapPanel.jsx";
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
    <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted-foreground">
      {[["transfers", t("Transfers"), "/remittance/"], ["tracking", t("Tracking"), "/remittance/?tab=tracking"], ["recap", t("Monthly recap"), "/remittance/?tab=recap"]].map(([k, l, href]) => (
        k === tab ? <b key={k} className="text-foreground">{l}</b> : <Link key={k} href={href} className="font-medium text-muted-foreground">{l}</Link>
      ))}
    </span>
  );

  if (tab !== "transfers") {
    return (
      <ListPage title={t("Remittance")} legend={views}>
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
        <thead><Tr>
          <Th>{t("Remittance")}</Th><Th>{t("Sent")}</Th><Th>{t("From")}</Th>
          <Th className="text-right">{t("Sent")}</Th><Th className="text-right">{t("Received at HQ")}</Th><Th className="text-right">{t("Rate")}</Th>
          <Th className="text-right">{t("FX gain (IDR)")}</Th><Th>{t("Status")}</Th><Th className="text-center">{t("Action")}</Th>
        </Tr></thead>
        <tbody>
          {remittances.map((r) => {
            const [tone, lbl] = STATE[r.state] || STATE.pending;
            return (
              <Tr key={r.id} {...rowNav(`/remittance/${r.id}/`)}>
                <Td><span className="font-mono text-[13px] font-semibold">{r.remittance_number}</span></Td>
                <Td>{dShort(r.date)}</Td>
                <Td className="truncate">{r.from}<span className="mt-0.5 block overflow-hidden text-ellipsis text-[12px] font-normal text-muted-foreground">{t("to {a}", { a: r.to })}</span></Td>
                <Td className="text-right"><Amt code={r.currency} value={r.amount_sent} /></Td>
                <Td className="text-right">{r.received_sar ? <Amt code="SAR" value={r.received_sar} /> : <span className="text-muted-foreground">0</span>}</Td>
                <Td className="text-right">{r.currency === "SAR" ? <span className="text-muted-foreground">—</span> : fmtN(r.rate)}</Td>
                <Td className="text-right">{r.state !== "received" && r.fx_gain_idr == null ? <span className="text-muted-foreground">{t("on receipt")}</span>
                  : r.fx_gain_idr == null ? <span className="text-muted-foreground">{t("Not priced")}</span>
                  : <span className={cn(r.fx_gain_idr >= 0 ? "text-success-text" : "font-medium text-danger-text")}>{signed(r.fx_gain_idr)}</span>}</Td>
                <Td><Pill tone={tone}>{t(lbl)}</Pill>{r.state !== "received" && <span className="mt-0.5 block overflow-hidden text-ellipsis text-[12px] font-normal text-muted-foreground">{t("{n} days", { n: r.days })}</span>}</Td>
                <Td className="text-center">
                  <RowMenu label={t("Actions for {n}", { n: r.remittance_number })} items={[
                    r.can_record_receipt && perms.can("remittance", "edit") && { label: t("Record receipt"), onClick: () => router.visit(`/remittance/${r.id}/receipt/`) },
                    r.proof_url && { label: t("View proof"), href: r.proof_url, external: true },
                    perms.can("remittance", "edit") && { label: t("Edit"), onClick: () => openForm(`/remittance/${r.id}/edit/`) },
                    { label: "PDF", href: `/remittance/${r.id}/pdf/`, external: true },
                  ]} />
                </Td>
              </Tr>
            );
          })}
        </tbody>
        {totals && remittances.length > 0 && (
          <tfoot><Tr>
            <Td colSpan={3}>{t("{p} total", { p: label })}</Td>
            <Td className="text-right"><Amt code="IDR" value={totals.idr} /></Td>
            <Td className="text-right"><Amt code="SAR" value={totals.received_sar} /></Td>
            <Td className="text-right">{totals.avg_rate ? fmtN(totals.avg_rate) : ""}</Td>
            <Td className={"text-right" + (totals.fx_gain_idr > 0 ? " text-success-text" : "")}>{signed(totals.fx_gain_idr)}</Td>
            <Td colSpan={2} label>{totals.transit_sar ? t("{v} SAR cash in transit", { v: fmtN(totals.transit_sar) }) : ""}</Td>
          </Tr></tfoot>
        )}
      </TableCard>

      <Pager p={pagination} perPage={f.per} onPage={(page) => go({ page })} onPerPage={(per) => go({ per })} />
    </ListPage>
  );
}
