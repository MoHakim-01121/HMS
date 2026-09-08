import { useState } from "react";
import { router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import ListCard from "../../components/shadcn/list-card.jsx";
import SearchBox from "../../components/shadcn/search-box.jsx";
import FilterPanel, { FilterSection } from "../../components/shadcn/filter-panel.jsx";
import FilterRadioGroup from "../../components/shadcn/filter-radio-group.jsx";
import FilterChips from "../../components/shadcn/filter-chips.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import useDebouncedSearch from "../../hooks/useDebouncedSearch.js";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

const CITY_OPTS = [
  { val: "", label: "All Cities", cls: "c-all" },
  { val: "makkah", label: "Makkah", cls: "c-mak" },
  { val: "madinah", label: "Madinah", cls: "c-mad" },
];
const STAR_OPTS = [
  { val: "", label: "All ★", cls: "c-all" },
  { val: "3", label: "3★", cls: "c-star" },
  { val: "4", label: "4★", cls: "c-star" },
  { val: "5", label: "5★", cls: "c-star" },
];

function distBadge(d) {
  if (d === null || d === undefined) return null;
  if (d < 500) return "green";
  if (d < 1500) return "yellow";
  return "red";
}

function buildQuery({ q, city, stars, area, page }) {
  const p = new URLSearchParams();
  if (q) p.append("q", q);
  if (city) p.append("city", city);
  if (stars) p.append("stars", stars);
  if (area) p.append("area", area);
  if (page) p.append("page", page);
  return "/hotels/?" + p.toString();
}

export default function List({ hotels, total_count, q, city_filter, stars_filter, area_filter, pagination }) {
  const { t } = useI18n();
  const [city, setCity] = useState(city_filter || "");
  const [stars, setStars] = useState(stars_filter || "");
  const [panelOpen, setPanelOpen] = useState(false);
  const { query, setQuery } = useDebouncedSearch(q, (query) => go({ q: query }));
  const [confirm, confirmDialog] = useConfirm();
  const openForm = useFormModal();
  const perms = usePerms();

  const go = (extra = {}) =>
    router.get(buildQuery({ q: query, city: city_filter, stars: stars_filter, area: area_filter, ...extra }), {}, { preserveState: true, preserveScroll: true, replace: true });

  const apply = () => { setPanelOpen(false); go({ city, stars }); };
  const resetAll = () => { setQuery(""); setCity(""); setStars(""); setPanelOpen(false); go({ q: "", city: "", stars: "" }); };
  const del = (e, pk, name) => { e.stopPropagation(); confirm({ title: t("Delete hotel"), message: t("Delete hotel {name}?", { name }), onConfirm: () => router.post(`/hotels/${pk}/delete/`) }); };

  const filterCount = (city_filter ? 1 : 0) + (stars_filter ? 1 : 0);
  const dirty = city !== (city_filter || "") || stars !== (stars_filter || "");
  const cityLabelOf = (v) => CITY_OPTS.find((o) => o.val === v)?.label || v;
  const starLabelOf = (v) => STAR_OPTS.find((o) => o.val === v)?.label || v;
  const chips = [
    ...(q ? [{ key: "q", label: t('Keyword "{q}"', { q }), onRemove: () => { setQuery(""); go({ q: "" }); } }] : []),
    ...(city_filter ? [{ key: "city", label: t(cityLabelOf(city_filter)), onRemove: () => { setCity(""); go({ city: "" }); } }] : []),
    ...(stars_filter ? [{ key: "stars", label: t(starLabelOf(stars_filter)), onRemove: () => { setStars(""); go({ stars: "" }); } }] : []),
  ];

  const columns = [
    { header: t("Hotel Name"), className: "col-m-primary", render: (h) => <span style={{ fontWeight: 600 }}>{h.name}</span> },
    {
      header: t("Status"),
      className: "col-m-badge",
      render: (h) => h.is_active ? <StatusPill tone="green" label={t("Active")} /> : <StatusPill tone="gray" label={t("Inactive")} />,
    },
    {
      header: t("City"),
      className: "col-m-secondary",
      render: (h) => (
        <>
          <StatusPill tone={h.city === "makkah" ? "blue" : "green"} label={h.city_display} />
          {h.area && <span className="m-only" style={{ marginLeft: 6, color: "var(--text-3)" }}>{h.area}</span>}
        </>
      ),
    },
    { header: t("Area"), className: "col-muted col-m-hide", render: (h) => h.area || "—" },
    {
      header: t("Stars"),
      className: "col-m-hide",
      render: (h) => <span style={{ color: "var(--yellow)", fontSize: 12, fontWeight: 600 }}>{h.stars}★</span>,
    },
    {
      header: t("Avg"),
      className: "col-m-meta",
      render: (h) => (
        <>
          <span className="m-hide">{h.avg_occupancy ? h.avg_occupancy : <span className="col-dim">—</span>}</span>
          <span className="m-only">{h.stars}★ {t("hotel")}</span>
          {h.avg_occupancy ? <span className="m-only">{t("Avg {avg} pax/room", { avg: h.avg_occupancy })}</span> : null}
        </>
      ),
    },
    {
      header: t("Distance to Mosque"),
      className: "col-m-amount",
      render: (h) => (
        <>
          <span className="m-hide">{h.distance !== null ? <StatusPill tone={distBadge(h.distance)} label={h.distance_label} /> : <span className="col-dim">—</span>}</span>
          <span className="m-only" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--text-3)", fontWeight: 700 }}>{t("Distance")}</span>
          {h.distance !== null ? <span className="m-only" style={h.distance < 500 ? { color: "var(--green)" } : h.distance < 1500 ? { color: "var(--yellow)" } : { color: "var(--red)" }}>{h.distance_label}</span> : <span className="m-only" style={{ color: "var(--text-3)" }}>—</span>}
        </>
      ),
    },
    {
      header: "",
      className: "col-m-actions",
      render: (h) => (
        <RowActions actions={[
          perms.can("hotels", "edit") && { icon: "edit", label: t("Edit"), onClick: () => openForm(`/hotels/${h.id}/edit/`) },
          perms.can("hotels", "delete") && { icon: "trash", label: t("Delete"), variant: "red", onClick: (e) => del(e, h.id, h.name) },
        ]} />
      ),
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />
      <PageHeader
        title={t("Hotels")}
        sub={t("{count} hotels registered", { count: total_count })}
        actions={
          <>
            <Button variant="outline" size="lg" asChild>
              <a href="/hotels/map/">
                <Icon name="map-pin" size={14} />
                {t("Map")}
              </a>
            </Button>
            {perms.can("hotels", "create") && (
              <Button type="button" size="lg" onClick={() => openForm("/hotels/new/")} onPointerEnter={() => openForm.prefetch("/hotels/new/")} onFocus={() => openForm.prefetch("/hotels/new/")}>
                + {t("New hotel")}
              </Button>
            )}
          </>
        }
      />

      <div className="filter-bar">
        <SearchBox value={query} onChange={setQuery} placeholder="Search name or area…" />
        <div className="fbar-actions">
          <FilterPanel
            count={filterCount}
            open={panelOpen}
            onToggle={() => setPanelOpen((v) => !v)}
            dirty={dirty}
            onApply={apply}
            onResetAll={resetAll}
          >
            <FilterSection label={t("City")} onReset={() => setCity("")}>
              <FilterRadioGroup label={t("City")} options={CITY_OPTS} value={city} onChange={setCity} dot />
            </FilterSection>
            <FilterSection label={t("Stars")} onReset={() => setStars("")}>
              <FilterRadioGroup label={t("Stars")} options={STAR_OPTS} value={stars} onChange={setStars} dot />
            </FilterSection>
          </FilterPanel>
        </div>
      </div>

      <FilterChips chips={chips} onClearAll={resetAll} />

      <ListCard
        columns={columns}
        rows={hotels}
        rowKey={(h) => h.id}
        onRowClick={(h) => router.visit(`/hotels/${h.id}/`)}
        empty={{
          icon: "hotels",
          title: "No hotels yet",
          sub: "Add your first Makkah hotel",
          filteredTitle: "No matching hotels",
          filteredSub: "Reset filter",
        }}
        hasFilter={!!(q || city_filter || area_filter || stars_filter)}
        pagination={pagination}
        unit={t("hotels")}
        onPage={(p) => go({ page: p })}
      />
      {confirmDialog}
    </div>
  );
}