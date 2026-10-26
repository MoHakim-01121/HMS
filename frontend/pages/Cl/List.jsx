import { useState } from "react";
import { router } from "@inertiajs/react";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { Popover, PopoverTrigger } from "../../components/shadcn/ui/popover.jsx";
import { ListPage, Legend, Kpis, Kpi, Toolbar, MonthNav, SearchTool, FilterMenu, FilterSection, Check, DateRange, ExportMenu, Primary, TableCard, RowMenu, Pill, Pager, Empty, LIcon, MONTHS, fmtN, stay, useListNav, rowNav, Tr, Th, Td, Menu, MenuItem, MenuSep, ToolButton } from "../../components/shadcn/list-a.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

const STATUS = { DEFINITE: ["green", "Definite"], TENTATIVE: ["amber", "Tentative"], CANCELLED: ["gray", "Cancelled"] };
const monthName = (ym, t) => (ym ? t(MONTHS[+ym.slice(5, 7) - 1]) : "");
const X = <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>;

// The Salesperson pick: one click from the toolbar instead of a long section
// in the Filter panel. "My CLs" is the signed-in user's own book; the list
// below is the other salespeople who sold in the period, at their counts.
// Once picked, the value leaves the toolbar and sits in an active chip under
// it (see the list page), so the toolbar stays calm.
function SalespersonMenu({ value, people, mine, unassigned, total, onPick }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const pick = (v) => { setOpen(false); onPick(v); };
  const row = (v, label, count) => (
    <MenuItem key={v || "all"} on={value === v} onClick={() => pick(v)}>
      <span className="flex-1 truncate">{label}</span>
      <span className="ml-2 text-[12px] tabular-nums text-muted-foreground">{count}</span>
    </MenuItem>
  );
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <ToolButton aria-haspopup="menu" className="max-[900px]:w-full">
          {t("Salesperson")}{LIcon.chev}
        </ToolButton>
      </PopoverTrigger>
      <Menu align="start" sideOffset={8} style={{ width: 268 }} className="max-h-[min(60vh,420px)] overflow-y-auto">
        {row("", t("All salespeople"), total)}
        {row("me", t("My CLs"), mine)}
        {(people.length > 0 || unassigned > 0 || value === "none") && <MenuSep />}
        {people.map((sp) => row(String(sp.id), sp.name, sp.count))}
        {(unassigned > 0 || value === "none") && <>{people.length > 0 && <MenuSep />}
          {row("none", t("No salesperson"), unassigned)}</>}
      </Menu>
    </Popover>
  );
}


// Confirmation Letter list, as on the Record View HMS canvas: four KPIs for
// the CLs sold in the month (by the day each was made) with a small trend against the month before
// (Cancelled filters the table), the toolbar above the table, and paging.
export default function List({ letters, filters: f, years, counts, salespeople = [], kpis, export_qs, pagination }) {
  const { t } = useI18n();
  const perms = usePerms();
  const openForm = useFormModal();
  const [confirm, confirmDialog] = useConfirm();
  const [go, loading] = useListNav("/cl/", f);
  const [draft, setDraft] = useState(f);

  const filterCount = (f.status.length ? 1 : 0) + (f.inv ? 1 : 0) + (f.from || f.to ? 1 : 0);
  const salesperson = f.salesperson === "me" ? t("My CLs") : f.salesperson === "none" ? t("No salesperson")
    : salespeople.find((sp) => String(sp.id) === f.salesperson)?.name || f.salesperson;
  const toggle = (v) => setDraft((d) => ({ ...d, status: d.status.includes(v) ? d.status.filter((x) => x !== v) : [...d.status, v] }));
  const onlyCancelled = f.status.length === 1 && f.status[0] === "cancelled";

  const cur = kpis?.cur, prev = kpis?.prev;
  const prevName = kpis ? monthName(kpis.prev_month, t) : "";

  const del = (cl) => confirm({ title: t("Delete CL"), message: t("Delete CL {number}?", { number: cl.confirmation_number }), onConfirm: () => router.post(`/cl/${cl.id}/delete/`) });

  return (
    <ListPage title={t("Confirmation Letter")} loading={loading}
      legend={kpis && <Legend current={monthName(f.month, t)} previous={prevName} note={t("by sale date")} />}>
      {kpis && (
        <Kpis>
          <Kpi label={t("Reservations")} value={fmtN(cur.count)} foot={`${prevName} ${fmtN(prev.count)}`}
            delta={{ text: kpis.delta.count, good: cur.count >= prev.count, title: t("{d} vs {m}", { d: kpis.delta.count, m: prevName }) }} />
          <Kpi label={t("Room nights")} value={fmtN(cur.nights)} foot={`${prevName} ${fmtN(prev.nights)}`}
            delta={kpis.delta.nights && { text: kpis.delta.nights, good: cur.nights >= prev.nights, title: t("{d} vs {m}", { d: kpis.delta.nights, m: prevName }) }} />
          <Kpi label={t("Total value")} value={fmtN(cur.value)} unit="SAR" foot={`${prevName} ${fmtN(prev.value)} SAR`}
            delta={kpis.delta.value && { text: kpis.delta.value, good: cur.value >= prev.value, title: t("{d} vs {m}", { d: kpis.delta.value, m: prevName }) }} />
          <Kpi label={t("Cancelled")} value={fmtN(cur.cancelled)} tone={cur.cancelled ? "warn" : undefined}
            foot={t("{v} SAR lost, {n} in {m}", { v: fmtN(cur.cancelled_value), n: prev.cancelled, m: prevName })}
            delta={{ text: kpis.delta.cancelled, good: cur.cancelled <= prev.cancelled, title: t("{d} vs {m}", { d: kpis.delta.cancelled, m: prevName }) }}
            on={onlyCancelled} onClick={() => go({ status: onlyCancelled ? [] : ["cancelled"] })} />
        </Kpis>
      )}

      <div className="flex flex-col gap-2">
        <Toolbar spaced={!!kpis}
          left={<MonthNav month={f.month} year={f.year} years={years} onChange={(p) => go({ ...p, from: "", to: "" })} />}>
          <SearchTool value={f.q} onSearch={(q) => go({ q })} placeholder={t("Search client, hotel, CL number")} />
          <SalespersonMenu value={f.salesperson} people={salespeople} mine={counts.mine} unassigned={counts.unassigned} total={counts.all}
            onPick={(salesperson) => go({ salesperson })} />
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
        {f.salesperson && salesperson && (
          <div className="flex flex-wrap items-center gap-2">
            <span data-slot="active-filter" className="inline-flex h-7 items-center gap-1.5 rounded-full border border-border bg-card pr-1 pl-2.5 text-[12.5px] leading-none font-medium">
              <span className="text-muted-foreground">{t("Salesperson")}</span>
              <span className="max-w-[240px] truncate font-semibold">{salesperson}</span>
              <button type="button" onClick={() => go({ salesperson: "" })}
                aria-label={t("Clear salesperson filter")} title={t("Clear salesperson filter")}
                className="grid size-5 cursor-pointer place-content-center rounded-full border-0 bg-transparent text-muted-foreground transition-colors duration-150 ease-[ease] hover:bg-secondary hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid">
                {X}
              </button>
            </span>
          </div>
        )}
      </div>

      <TableCard cols={[76, null, null, 130, 64, 64, 96, 100, 104, 56]}
        empty={!letters.length && <Empty title={t("No confirmation letters")}
          sub={salesperson
            ? <>{t("No CLs for {name} in this period.", { name: salesperson })} <button type="button" onClick={() => go({ salesperson: "" })}
              className="cursor-pointer border-0 bg-transparent p-0 font-medium text-foreground underline underline-offset-2">{t("Show all salespeople")}</button></>
            : t("Nothing matches this month and these filters.")} />}>
        <thead><Tr>
          <Th>CL</Th><Th>{t("Client")}</Th><Th>{t("Hotel")}</Th>
          <Th><button type="button" className="inline-flex items-center gap-1 font-semibold text-foreground" style={{ border: 0, background: "none", padding: 0, font: "inherit", cursor: "pointer" }}
            onClick={() => go({ sort: f.sort === "-check_in" ? "check_in" : "-check_in" })}>{t("Stay")}{f.sort === "-check_in" ? LIcon.sortUp : LIcon.sortDown}</button></Th>
          <Th className="text-right">{t("Nights")}</Th><Th className="text-right">{t("Rooms")}</Th><Th>{t("Invoice")}</Th>
          <Th className="text-right">{t("Total (SAR)")}</Th><Th>{t("Status")}</Th><Th className="text-center">{t("Action")}</Th>
        </Tr></thead>
        <tbody>
          {letters.map((cl) => {
            const [tone, label] = STATUS[cl.reservation_status] || STATUS.TENTATIVE;
            return (
              <Tr key={cl.id} row={cl.reservation_status === "CANCELLED" ? "dim" : undefined} {...rowNav(`/cl/${cl.id}/`)}>
                <Td><span className="font-mono text-[13px] font-semibold">{cl.confirmation_number}</span></Td>
                <Td className="truncate font-medium">{cl.guest_name}</Td>
                <Td className="truncate">{cl.hotel_name}</Td>
                <Td>{stay(cl.check_in, cl.check_out, t)}</Td>
                <Td className="text-right">{cl.num_nights}</Td>
                <Td className="text-right">{cl.total_rooms}</Td>
                <Td>{cl.invoice_number ? <span className="font-mono text-[13px] font-semibold">{cl.invoice_number}</span> : <span className="text-muted-foreground">{t("Not invoiced")}</span>}</Td>
                <Td className="text-right">{fmtN(cl.total_price)}</Td>
                <Td><Pill tone={tone}>{t(label)}</Pill></Td>
                <Td className="text-center">
                  <RowMenu label={t("Actions for {n}", { n: cl.confirmation_number })} items={[
                    { label: t("Download PDF"), href: `/cl/${cl.id}/pdf/`, external: true },
                    perms.can("cl", "edit") && { label: t("Edit"), onClick: () => openForm(`/cl/${cl.id}/edit/`) },
                    perms.can("cl", "delete") && { label: t("Delete"), danger: true, onClick: () => del(cl) },
                  ]} />
                </Td>
              </Tr>
            );
          })}
        </tbody>
      </TableCard>

      <Pager p={pagination} perPage={f.per} onPage={(page) => go({ page })} onPerPage={(per) => go({ per })} />
      {confirmDialog}
    </ListPage>
  );
}
