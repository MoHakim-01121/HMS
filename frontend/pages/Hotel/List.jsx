import { useState } from "react";
import { Link, router } from "@inertiajs/react";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { ListPage, Toolbar, SearchTool, FilterMenu, FilterSection, Check, ExportMenu, Primary, TableCard, RowMenu, Pill, Pager, Empty, LIcon, useListNav, rowNav, Tr, Th, Td, Note, ToolButton } from "../../components/shadcn/list-a.jsx";
import { cn } from "@/lib/utils";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

const Star = () => <svg width="13" height="13" viewBox="0 0 24 24" aria-hidden="true" style={{ fill: "var(--ring)" }}><path d="M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4l-5.9 3.1 1.2-6.5-4.8-4.6 6.6-.9z" /></svg>;
const Pin = () => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 21s-7-6.2-7-12a7 7 0 0114 0c0 5.8-7 12-7 12z" /><circle cx="12" cy="9" r="2.5" /></svg>;

// Every filter of the list, one per column it narrows. The keys match
// _hotel_list_qs in hw/views/hotel_views.py.
const KEYS = ["city", "stars", "allotment", "status", "location"];

// Hotel list, as on the Record View HMS canvas: no KPIs; the filters live in
// Filter; the map, export and New hotel sit beside the search.
export default function List({ hotels, total, filters: f, counts, pagination }) {
  const { t } = useI18n();
  const perms = usePerms();
  const openForm = useFormModal();
  const [confirm, confirmDialog] = useConfirm();
  const [go, loading] = useListNav("/hotels/", f);
  const [draft, setDraft] = useState(f);
  const tog = (key, v) => setDraft((d) => ({ ...d, [key]: d[key].includes(v) ? d[key].filter((x) => x !== v) : [...d[key], v] }));
  const filterCount = KEYS.filter((k) => f[k].length).length;
  const qs = new URLSearchParams({ ...(f.q && { q: f.q }), ...Object.fromEntries(KEYS.filter((k) => f[k].length).map((k) => [k, f[k].join(",")])) }).toString();
  // A section of yes/no style options: "All" plus one check per value.
  const section = (key, label, allLabel, opts) => (
    <FilterSection label={label}>
      <Check radio on={!draft[key].length} onClick={() => setDraft({ ...draft, [key]: [] })} label={allLabel} count={counts.all} />
      {opts.map(([v, l]) => <Check key={v} on={draft[key].includes(v)} onClick={() => tog(key, v)} label={l} count={counts[key]?.[v] || 0} />)}
    </FilterSection>
  );

  const del = (h) => confirm({ title: t("Delete hotel"), message: t("Delete hotel {name}?", { name: h.name }), onConfirm: () => router.post(`/hotels/${h.id}/delete/`) });

  return (
    <ListPage title={t("Hotels")} loading={loading}>
      <Toolbar left={<Note>{t("{n} hotels registered", { n: total })}</Note>}>
        <SearchTool value={f.q} onSearch={(q) => go({ q })} placeholder={t("Search name or area")} />
        <FilterMenu count={filterCount} onOpen={() => setDraft(f)}
          onReset={() => setDraft({ ...draft, ...Object.fromEntries(KEYS.map((k) => [k, []])) })}
          onApply={() => go(Object.fromEntries(KEYS.map((k) => [k, draft[k]])))}>
          {section("city", t("City"), t("All cities"), [["makkah", "Makkah"], ["madinah", "Madinah"]])}
          {section("stars", t("Stars"), t("All stars"), ["5", "4", "3", "2", "1"].map((s) => [s, s === "1" ? t("1 star") : t("{n} stars", { n: s })]))}
          {section("allotment", t("Allotment"), t("All hotels"), [["yes", t("Allotment")], ["no", t("No allotment")]])}
          {section("status", t("Status"), t("All statuses"), [["active", t("Active")], ["inactive", t("Inactive")]])}
          {section("location", t("Location"), t("All hotels"), [["set", t("Has coordinates")], ["missing", t("No location")]])}
        </FilterMenu>
        <ToolButton as={Link} href="/hotels/map/">{t("Map")}<Pin /></ToolButton>
        {perms.can("hotels", "export") && <ExportMenu items={[{ label: "CSV", href: `/hotels/export/csv/${qs ? "?" + qs : ""}` }]} />}
        {perms.can("hotels", "create") && <Primary label={t("New hotel")} onClick={() => openForm("/hotels/new/")} onPrefetch={() => openForm.prefetch("/hotels/new/")} />}
      </Toolbar>

      <TableCard cols={[null, 92, 140, 64, 124, 76, 132, 96, 56]}
        empty={!hotels.length && <Empty title={t("No hotels")} sub={t("Nothing matches this search and these filters.")} />}>
        <thead><Tr>
          <Th><button type="button" className="inline-flex items-center gap-1 font-semibold text-foreground" style={{ border: 0, background: "none", padding: 0, font: "inherit", cursor: "pointer" }}
            onClick={() => go({ sort: f.sort === "-name" ? "name" : "-name" })}>{t("Hotel")}{f.sort === "-name" ? LIcon.sortUp : LIcon.sortDown}</button></Th>
          <Th>{t("City")}</Th><Th>{t("Area")}</Th><Th>{t("Stars")}</Th><Th>{t("Allotment")}</Th>
          <Th className="text-right" title={t("Average pax per room")}>{t("Avg pax")}</Th><Th>{t("Distance to mosque")}</Th><Th>{t("Status")}</Th><Th className="text-center">{t("Action")}</Th>
        </Tr></thead>
        <tbody>
          {hotels.map((h) => (
            <Tr key={h.id} row={h.is_active ? undefined : "dim"} {...rowNav(`/hotels/${h.id}/`)}>
              <Td className="truncate font-medium">{h.name}</Td>
              <Td>{h.city_display}</Td>
              <Td className="truncate">{h.area || <span className="text-muted-foreground">—</span>}</Td>
              <Td><span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontWeight: 500 }}><Star />{h.stars}</span></Td>
              <Td><span className={"hl-al" + (h.has_allotment ? "" : " no")}>{h.has_allotment ? t("Allotment") : t("No allotment")}</span></Td>
              <Td className="text-right">{h.avg_occupancy != null ? h.avg_occupancy.toFixed(1) : <span className="text-muted-foreground">—</span>}</Td>
              <Td>{h.distance == null ? <span className="text-muted-foreground">{t("No location")}</span>
                : <span className={cn(h.distance <= 500 ? "text-success-text" : h.distance <= 1500 ? "text-warning-text" : "font-medium text-danger-text")} style={{ fontWeight: 600 }}>{h.distance_label}</span>}</Td>
              <Td><Pill tone={h.is_active ? "green" : "gray"}>{h.is_active ? t("Active") : t("Inactive")}</Pill></Td>
              <Td className="text-center">
                <RowMenu label={t("Actions for {n}", { n: h.name })} items={[
                  perms.can("hotels", "edit") && { label: t("Edit"), onClick: () => openForm(`/hotels/${h.id}/edit/`) },
                  perms.can("hotels", "delete") && { label: t("Delete"), danger: true, onClick: () => del(h) },
                ]} />
              </Td>
            </Tr>
          ))}
        </tbody>
      </TableCard>

      <Pager p={pagination} perPage={f.per} onPage={(page) => go({ page })} onPerPage={(per) => go({ per })} />
      {confirmDialog}
      <style>{`.hl-al { display: inline-flex; align-items: center; height: 22px; padding: 0 9px; border-radius: 9999px; background: var(--success-tint); color: var(--success-text); font-size: 12px; font-weight: 600; white-space: nowrap; }
.hl-al.no { background: var(--warning-tint); color: var(--warning-text); }`}</style>
    </ListPage>
  );
}
