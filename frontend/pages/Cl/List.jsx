import { useState } from "react";
import { router } from "@inertiajs/react";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import {
  ListPage, Legend, Kpis, Kpi, Spark, Toolbar, MonthNav, SearchTool, FilterMenu, FilterSection, Check, DateRange,
  ExportMenu, Primary, TableCard, RowMenu, Pill, Pager, Empty, LIcon, MONTHS, fmtN, stay, useListNav, rowNav,
} from "../../components/shadcn/list-a.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

const STATUS = { DEFINITE: ["green", "Definite"], TENTATIVE: ["amber", "Tentative"], CANCELLED: ["gray", "Cancelled"] };
const monthName = (ym, t) => (ym ? t(MONTHS[+ym.slice(5, 7) - 1]) : "");

// Confirmation Letter list, as on the Record View HMS canvas: four KPIs for
// the CLs sold in the month (by the day each was made) with a small trend against the month before
// (Cancelled filters the table), the toolbar above the table, and paging.
export default function List({ letters, filters: f, years, counts, kpis, export_qs, pagination }) {
  const { t } = useI18n();
  const perms = usePerms();
  const openForm = useFormModal();
  const [confirm, confirmDialog] = useConfirm();
  const [go, loading] = useListNav("/cl/", f);
  const [draft, setDraft] = useState(f);

  const filterCount = (f.status.length ? 1 : 0) + (f.inv ? 1 : 0) + (f.from || f.to ? 1 : 0);
  const toggle = (v) => setDraft((d) => ({ ...d, status: d.status.includes(v) ? d.status.filter((x) => x !== v) : [...d.status, v] }));
  const onlyCancelled = f.status.length === 1 && f.status[0] === "cancelled";

  const cur = kpis?.cur, prev = kpis?.prev;
  const prevName = kpis ? monthName(kpis.prev_month, t) : "";
  const sparkLabel = (what, a, b) => t("{what}, cumulative by sale day. {cur}: {a}. {prev}: {b}", { what, cur: monthName(f.month, t), prev: prevName, a: a.join(", "), b: b.join(", ") });

  const del = (cl) => confirm({ title: t("Delete CL"), message: t("Delete CL {number}?", { number: cl.confirmation_number }), onConfirm: () => router.post(`/cl/${cl.id}/delete/`) });

  return (
    <ListPage title={t("Confirmation Letter")} loading={loading}
      legend={kpis && <Legend current={monthName(f.month, t)} previous={prevName} note={t("by sale date")} />}>
      {kpis && (
        <Kpis>
          <Kpi label={t("Reservations")} value={fmtN(cur.count)} foot={`${prevName} ${fmtN(prev.count)}`}
            delta={{ text: kpis.delta.count, good: cur.count >= prev.count, title: t("{d} vs {m}", { d: kpis.delta.count, m: prevName }) }}
            spark={<Spark cur={cur.spark_count} prev={prev.spark_count} label={sparkLabel(t("Reservations"), cur.spark_count, prev.spark_count)} />} />
          <Kpi label={t("Room nights")} value={fmtN(cur.nights)} foot={`${prevName} ${fmtN(prev.nights)}`}
            delta={kpis.delta.nights && { text: kpis.delta.nights, good: cur.nights >= prev.nights, title: t("{d} vs {m}", { d: kpis.delta.nights, m: prevName }) }}
            spark={<Spark cur={cur.spark_nights} prev={prev.spark_nights} label={sparkLabel(t("Room nights"), cur.spark_nights, prev.spark_nights)} />} />
          <Kpi label={t("Total value")} value={fmtN(cur.value)} unit="SAR" foot={`${prevName} ${fmtN(prev.value)} SAR`}
            delta={kpis.delta.value && { text: kpis.delta.value, good: cur.value >= prev.value, title: t("{d} vs {m}", { d: kpis.delta.value, m: prevName }) }}
            spark={<Spark cur={cur.spark_value} prev={prev.spark_value} label={sparkLabel(t("Total value in thousand SAR"), cur.spark_value, prev.spark_value)} />} />
          <Kpi label={t("Cancelled")} value={fmtN(cur.cancelled)} tone={cur.cancelled ? "warn" : undefined}
            foot={t("{v} SAR lost, {n} in {m}", { v: fmtN(cur.cancelled_value), n: prev.cancelled, m: prevName })}
            delta={{ text: kpis.delta.cancelled, good: cur.cancelled <= prev.cancelled, title: t("{d} vs {m}", { d: kpis.delta.cancelled, m: prevName }) }}
            on={onlyCancelled} onClick={() => go({ status: onlyCancelled ? [] : ["cancelled"] })} />
        </Kpis>
      )}

      <Toolbar spaced={!!kpis}
        left={<MonthNav month={f.month} year={f.year} years={years} onChange={(p) => go({ ...p, from: "", to: "" })} />}>
        <SearchTool value={f.q} onSearch={(q) => go({ q })} placeholder={t("Search client, hotel, CL number")} />
        <FilterMenu count={filterCount} onOpen={() => setDraft(f)}
          onReset={() => setDraft({ ...draft, status: [], inv: "", from: "", to: "" })}
          onApply={() => go({ status: draft.status, inv: draft.inv, from: draft.from, to: draft.to, ...(draft.from || draft.to ? { month: "", year: "" } : {}) })}>
          <FilterSection label={t("Status")}>
            <Check on={draft.status.includes("definite")} onClick={() => toggle("definite")} label={t("Definite")} count={counts.definite} />
            <Check on={draft.status.includes("tentative")} onClick={() => toggle("tentative")} label={t("Tentative")} count={counts.tentative} />
            <Check on={draft.status.includes("cancelled")} onClick={() => toggle("cancelled")} label={t("Cancelled")} count={counts.cancelled} />
          </FilterSection>
          <FilterSection label={t("Invoice")}>
            <Check radio on={!draft.inv} onClick={() => setDraft({ ...draft, inv: "" })} label={t("All")} count={counts.all} />
            <Check radio on={draft.inv === "yes"} onClick={() => setDraft({ ...draft, inv: "yes" })} label={t("Invoiced")} count={counts.invoiced} />
            <Check radio on={draft.inv === "no"} onClick={() => setDraft({ ...draft, inv: "no" })} label={t("Not invoiced")} count={counts.not_invoiced} />
          </FilterSection>
          <FilterSection label={t("Check-in range")} hint={t("Used instead of the month above.")}>
            <DateRange from={draft.from} to={draft.to} onFrom={(v) => setDraft({ ...draft, from: v })} onTo={(v) => setDraft({ ...draft, to: v })} />
          </FilterSection>
        </FilterMenu>
        <ExportMenu items={[
          { label: "CSV", href: `/cl/export/csv/${export_qs}` },
          { label: t("Payment check"), hint: t("Total, paid and remaining per reservation"), href: `/cl/export/pdf/${export_qs}`, external: true },
          { label: t("Room formation"), hint: t("Room types and meals per reservation"), href: `/cl/export/pdf-v2/${export_qs}`, external: true },
        ]} />
        {perms.can("cl", "create") && <Primary label={t("New CL")} onClick={() => openForm("/cl/new/")} onPrefetch={() => openForm.prefetch("/cl/new/")} />}
      </Toolbar>

      <TableCard cols={[76, null, null, 130, 64, 64, 96, 100, 104, 56]}
        empty={!letters.length && <Empty title={t("No confirmation letters")} sub={t("Nothing matches this month and these filters.")} />}>
        <thead><tr>
          <th>CL</th><th>{t("Client")}</th><th>{t("Hotel")}</th>
          <th><button type="button" className="srt" style={{ border: 0, background: "none", padding: 0, font: "inherit", cursor: "pointer" }}
            onClick={() => go({ sort: f.sort === "-check_in" ? "check_in" : "-check_in" })}>{t("Stay")}{f.sort === "-check_in" ? LIcon.sortUp : LIcon.sortDown}</button></th>
          <th className="n">{t("Nights")}</th><th className="n">{t("Rooms")}</th><th>{t("Invoice")}</th>
          <th className="n">{t("Total (SAR)")}</th><th>{t("Status")}</th><th className="c">{t("Action")}</th>
        </tr></thead>
        <tbody>
          {letters.map((cl) => {
            const [tone, label] = STATUS[cl.reservation_status] || STATUS.TENTATIVE;
            return (
              <tr key={cl.id} className={cl.reservation_status === "CANCELLED" ? "dim" : ""} {...rowNav(`/cl/${cl.id}/`)}>
                <td><span className="mono">{cl.confirmation_number}</span></td>
                <td className="ell strong">{cl.guest_name}</td>
                <td className="ell">{cl.hotel_name}</td>
                <td>{stay(cl.check_in, cl.check_out, t)}</td>
                <td className="n">{cl.num_nights}</td>
                <td className="n">{cl.total_rooms}</td>
                <td>{cl.invoice_number ? <span className="mono">{cl.invoice_number}</span> : <span className="mut">{t("Not invoiced")}</span>}</td>
                <td className="n">{fmtN(cl.total_price)}</td>
                <td><Pill tone={tone}>{t(label)}</Pill></td>
                <td className="c">
                  <RowMenu label={t("Actions for {n}", { n: cl.confirmation_number })} items={[
                    { label: t("Download PDF"), href: `/cl/${cl.id}/pdf/`, external: true },
                    perms.can("cl", "edit") && { label: t("Edit"), onClick: () => openForm(`/cl/${cl.id}/edit/`) },
                    perms.can("cl", "delete") && { label: t("Delete"), danger: true, onClick: () => del(cl) },
                  ]} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </TableCard>

      <Pager p={pagination} perPage={f.per} onPage={(page) => go({ page })} onPerPage={(per) => go({ per })} />
      {confirmDialog}
    </ListPage>
  );
}
