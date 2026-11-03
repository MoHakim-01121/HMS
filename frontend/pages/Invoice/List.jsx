import { useState } from "react";
import { router } from "@inertiajs/react";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { ListPage, Kpis, Kpi, Toolbar, MonthNav, SearchTool, FilterMenu, FilterSection, Check, DateRange, ExportMenu, Primary, TableCard, PRow, RowMenu, Pill, Pager, Empty, SearchScope, LIcon, MONTHS, fmtN, dShort, useListNav, rowNav, Tr, Th, Td } from "../../components/shadcn/list-a.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

const STATUS = {
  paid: ["green", "Paid"], overpaid: ["green", "Paid"], partial: ["amber-o", "Partial"],
  unpaid: ["amber", "Unpaid"], void: ["gray", "Void"],
};
const monthName = (ym, t) => (ym ? t(MONTHS[+ym.slice(5, 7) - 1]) : "");

// Hotel invoice list, as on the Record View HMS canvas: KPIs for the month
// invoices fall due (Overdue filters the table, Unbilled opens the CLs not
// yet invoiced), the toolbar above the table, and paging.
export default function List({ invoices, filters: f, search_all, years, seasons = [], counts, kpis, export_qs, pagination }) {
  const { t } = useI18n();
  const perms = usePerms();
  const openForm = useFormModal();
  const [confirm, confirmDialog] = useConfirm();
  const [go, loading] = useListNav("/invoice/", f);
  const [draft, setDraft] = useState(f);
  const filterCount = (f.status && f.status !== "overdue" ? 1 : 0) + (f.from || f.to ? 1 : 0);
  const prevName = kpis ? monthName(kpis.prev_month, t) : "";
  const vs = (d) => t("{d} vs {m}", { d, m: prevName });

  const del = (inv) => confirm({ title: t("Delete invoice"), message: t("Delete invoice {number}?", { number: inv.invoice_number }), onConfirm: () => router.post(`/invoice/${inv.id}/delete/`) });

  // The row's actions: the desktop row menu, and the same menu on a phone row.
  const menuFor = (inv) => [
    { label: t("Download PDF"), href: `/invoice/${inv.id}/pdf/`, external: true },
    { label: t("Download detailed PDF"), href: `/invoice/${inv.id}/pdf/?detailed=1`, external: true },
    perms.can("invoice", "edit") && inv.status !== "void" && { label: t("Edit"), onClick: () => openForm(`/invoice/${inv.id}/edit/`) },
    perms.can("invoice", "delete") && { label: t("Delete"), danger: true, onClick: () => del(inv) },
  ];
  return (
    <ListPage title={t("Invoice")} loading={loading}>
      {kpis && (
        <Kpis>
          <Kpi label={t("Invoiced")} value={fmtN(kpis.cur.invoiced)} unit="SAR"
            delta={kpis.invoiced_delta && { text: kpis.invoiced_delta, good: !kpis.invoiced_delta.startsWith("-"), title: vs(kpis.invoiced_delta) }}
            foot={t("{n} invoices, {v} SAR in {m}", { n: kpis.cur.count, v: fmtN(kpis.prev.invoiced), m: prevName })} />
          <Kpi label={t("Collection rate")} value={kpis.cur.rate ?? "—"} unit={kpis.cur.rate != null ? "%" : ""}
            delta={kpis.rate_delta != null && { text: `${kpis.rate_delta >= 0 ? "+" : ""}${kpis.rate_delta} pts`, good: kpis.rate_delta >= 0, title: vs(`${kpis.rate_delta} points`) }}
            foot={t("{v} SAR outstanding", { v: fmtN(kpis.cur.outstanding) }) + (kpis.prev.rate != null ? t(", {p}% in {m}", { p: kpis.prev.rate, m: prevName }) : "")} />
          <Kpi label={t("Overdue")} value={fmtN(kpis.overdue.value)} unit="SAR" tone={kpis.overdue.value ? "warn" : undefined}
            foot={kpis.overdue.count ? t("{n} invoices, oldest {d} days late", { n: kpis.overdue.count, d: kpis.overdue.oldest_days }) : t("Nothing is late")}
            on={f.status === "overdue"} onClick={() => go({ status: f.status === "overdue" ? "" : "overdue" })} />
          <Kpi label={t("Unbilled")} value={fmtN(kpis.unbilled.value)} unit="SAR" tone={kpis.unbilled.value ? "warn" : undefined}
            foot={kpis.unbilled.count ? t("{n} CLs checking in this month, first on {d}", { n: kpis.unbilled.count, d: dShort(kpis.unbilled.first) }) : t("Every CL of the month is invoiced")}
            href={`/cl/?month=${f.month}&inv=no`} />
        </Kpis>
      )}

      <div className="flex flex-col gap-2">
        <Toolbar spaced={!!kpis}
          left={<MonthNav prefix={t("Due")} month={f.month} year={f.year} season={f.season} years={years} seasons={seasons} onChange={(p) => go({ ...p, from: "", to: "" })} />}>
          <SearchTool value={f.q} onSearch={(q) => go({ q })} placeholder={t("Search invoice or client")} />
          <FilterMenu count={filterCount} onOpen={() => setDraft(f)}
            onReset={() => setDraft({ ...draft, status: "", from: "", to: "" })}
            onApply={() => go({ status: draft.status, from: draft.from, to: draft.to, ...(draft.from || draft.to ? { month: "", year: "", season: "" } : {}) })}>
            <FilterSection label={t("Status")}>
              {["paid", "partial", "unpaid", "void"].map((k) => (
                <Check key={k} radio on={draft.status === k} onClick={() => setDraft({ ...draft, status: draft.status === k ? "" : k })} label={t(STATUS[k][1])} count={counts[k]} />
              ))}
            </FilterSection>
            <FilterSection label={t("Due date range")} hint={t("Used instead of the month above.")}>
              <DateRange from={draft.from} to={draft.to} onFrom={(v) => setDraft({ ...draft, from: v })} onTo={(v) => setDraft({ ...draft, to: v })} />
            </FilterSection>
          </FilterMenu>
          <ExportMenu items={[
            { label: "CSV", href: `/invoice/export/csv/${export_qs}` },
            { label: "PDF", href: `/invoice/export/pdf/${export_qs}`, external: true },
          ]} />
          {perms.can("invoice", "create") && <Primary label={t("New invoice")} onClick={() => openForm("/invoice/new/")} onPrefetch={() => openForm.prefetch("/invoice/new/")} />}
        </Toolbar>
        {search_all && <SearchScope />}
      </div>

      <TableCard cols={[110, null, 130, 130, 150, 130, 56]}
        phone={invoices.map((inv) => {
          const [tone, label] = STATUS[inv.status] || STATUS.unpaid;
          const left = inv.remaining_sar > 0 ? t("{v} SAR left", { v: fmtN(inv.remaining_sar) })
            : inv.remaining_sar < 0 ? t("{v} SAR over", { v: fmtN(-inv.remaining_sar) }) : t("Paid in full");
          return (
            <PRow key={inv.id} menu={<RowMenu label={t("Actions for {n}", { n: inv.invoice_number })} items={menuFor(inv)} />} href={`/invoice/${inv.id}/`} mono no={inv.invoice_number} dim={inv.status === "void"}
              tag={<Pill tone={tone} sm>{t(label)}</Pill>}
              title={inv.customer_name} amount={fmtN(inv.total_sar)} unit="SAR"
              meta={<>{t("Due {d}", { d: dShort(inv.due_date) })}{inv.days_late > 0 && <span className="text-danger-text"> · {t("{n} days late", { n: inv.days_late })}</span>}</>}
              note={left} noteTone={inv.remaining_sar > 0 ? "text-danger-text" : inv.remaining_sar < 0 ? "text-success-text" : undefined} />
          );
        })}
        empty={!invoices.length && <Empty title={t("No invoices")} sub={f.status === "overdue" ? t("Nothing is overdue.") : search_all ? t("Nothing matches this search on any date.") : t("Nothing falls due in this period with these filters.")} />}>
        <thead><Tr>
          <Th>{t("Invoice")}</Th><Th>{t("Client")}</Th>
          <Th><button type="button" className="inline-flex items-center gap-1 font-semibold text-foreground" style={{ border: 0, background: "none", padding: 0, font: "inherit", cursor: "pointer" }}
            onClick={() => go({ sort: f.sort === "-due" ? "due" : "-due" })}>{t("Due date")}{f.sort === "-due" ? LIcon.sortUp : LIcon.sortDown}</button></Th>
          <Th className="text-right">{t("Total (SAR)")}</Th><Th className="text-right">{t("Remaining (SAR)")}</Th><Th>{t("Status")}</Th><Th className="text-center">{t("Action")}</Th>
        </Tr></thead>
        <tbody>
          {invoices.map((inv) => {
            const [tone, label] = STATUS[inv.status] || STATUS.unpaid;
            return (
              <Tr key={inv.id} row={inv.status === "void" ? "dim" : undefined} {...rowNav(`/invoice/${inv.id}/`)}>
                <Td><span className="font-mono text-[13px] font-semibold">{inv.invoice_number}</span></Td>
                <Td className="truncate font-medium">{inv.customer_name}</Td>
                <Td>{dShort(inv.due_date)}{inv.days_late > 0 && <span className="mt-0.5 block overflow-hidden text-ellipsis text-[12px] font-medium text-danger-text">{t("{n} days late", { n: inv.days_late })}</span>}</Td>
                <Td className="text-right">{fmtN(inv.total_sar)}</Td>
                <Td className={"text-right" + (inv.days_late > 0 ? " font-medium text-danger-text" : inv.remaining_sar < 0 ? " text-success-text" : "")}>
                  {inv.remaining_sar < 0 ? t("{v} over", { v: fmtN(-inv.remaining_sar) }) : fmtN(inv.remaining_sar)}
                </Td>
                <Td><Pill tone={tone}>{t(label)}</Pill></Td>
                <Td className="text-center">
                  <RowMenu label={t("Actions for {n}", { n: inv.invoice_number })} items={menuFor(inv)} />
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
