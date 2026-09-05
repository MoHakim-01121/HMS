import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import Table from "../../components/shadcn/table.jsx";
import Pagination from "../../components/shadcn/pagination.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import FilterRadioGroup from "../../components/shadcn/filter-radio-group.jsx";
import FilterChips from "../../components/shadcn/filter-chips.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
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
  const [query, setQuery] = useState(q || "");
  const [panelOpen, setPanelOpen] = useState(false);
  const [city, setCity] = useState(city_filter || "");
  const [stars, setStars] = useState(stars_filter || "");
  const debounce = useRef(null);
  const first = useRef(true);

  const go = (extra = {}) =>
    router.get(buildQuery({ q: query, city: city_filter, stars: stars_filter, area: area_filter, ...extra }), {}, { preserveState: true, preserveScroll: true, replace: true });

  useEffect(() => {
    if (first.current) { first.current = false; return; }
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => go({ q: query }), 350);
    return () => clearTimeout(debounce.current);
  }, [query]);

  const apply = () => { setPanelOpen(false); go({ city, stars }); };
  const resetAll = () => { setQuery(""); setCity(""); setStars(""); setPanelOpen(false); go({ q: "", city: "", stars: "" }); };
  const [confirm, confirmDialog] = useConfirm();
  const del = (e, pk, name) => { e.stopPropagation(); confirm({ title: t("Delete hotel"), message: t("Delete hotel {name}?", { name }), onConfirm: () => router.post(`/hotels/${pk}/delete/`) }); };
  const openForm = useFormModal();
  const perms = usePerms();

  const filterCount = (city_filter ? 1 : 0) + (stars_filter ? 1 : 0);
  const dirty = city !== (city_filter || "") || stars !== (stars_filter || "");
  const cityLabelOf = (v) => CITY_OPTS.find((o) => o.val === v)?.label || v;
  const starLabelOf = (v) => STAR_OPTS.find((o) => o.val === v)?.label || v;
  const chips = [
    ...(q ? [{ key: "q", label: t('Keyword "{q}"', { q }), onRemove: () => { setQuery(""); go({ q: "" }); } }] : []),
    ...(city_filter ? [{ key: "city", label: t(cityLabelOf(city_filter)), onRemove: () => { setCity(""); go({ city: "" }); } }] : []),
    ...(stars_filter ? [{ key: "stars", label: t(starLabelOf(stars_filter)), onRemove: () => { setStars(""); go({ stars: "" }); } }] : []),
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
        <div className="search-wrap">
          <Icon name="search" size={13} />
          <input type="text" value={query} placeholder={t("Search name or area…")} onChange={(e) => setQuery(e.target.value)} />
          {query && <button type="button" className="sw-clear" title={t("Clear search")} onClick={() => setQuery("")}><Icon name="close" size={11} strokeWidth={2.5} /></button>}
        </div>
        <div className="fbar-actions">
          <div className="filter-panel-wrap" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="fbar-btn" onClick={() => setPanelOpen((v) => !v)}>
              <Icon name="filter" size={13} /> {t("Filter")}
              {filterCount > 0 && <span className="fbar-count">{filterCount}</span>}
            </button>
            {panelOpen && (
              <div className="filter-panel open">
                <div className="fp-head"><span className="fp-title">{t("Filter")}</span></div>
                <div className="fp-section">
                  <div className="fp-section-head"><span className="fp-section-label">{t("City")}</span><button type="button" className="fp-reset" onClick={() => setCity("")}>{t("Reset")}</button></div>
                  <FilterRadioGroup label={t("City")} options={CITY_OPTS} value={city} onChange={setCity} dot />
                </div>
                <div className="fp-section">
                  <div className="fp-section-head"><span className="fp-section-label">{t("Stars")}</span><button type="button" className="fp-reset" onClick={() => setStars("")}>{t("Reset")}</button></div>
                  <FilterRadioGroup label={t("Stars")} options={STAR_OPTS} value={stars} onChange={setStars} dot />
                </div>
                <div className="fp-footer">
                  <Button type="button" variant="ghost" size="sm" onClick={resetAll}>{t("Reset all")}</Button>
                  <Button type="button" size="sm" onClick={apply}>{dirty ? t("Apply changes") : t("Apply")}</Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <FilterChips chips={chips} onClearAll={resetAll} />

      <div className="hms-list-card">
        {hotels.length ? (
          <>
            <Table
              columns={[
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
              ]}
              rows={hotels}
              rowKey={(h) => h.id}
              onRowClick={(h) => router.visit(`/hotels/${h.id}/`)}
            />

            <Pagination pagination={pagination} unit={t("hotels")} onPage={(p) => go({ page: p })} />
          </>
        ) : (
          (q || city_filter || area_filter || stars_filter) ? <EmptyState iconName="hotels" title="No matching hotels" sub="Reset filter" /> : <EmptyState iconName="hotels" title="No hotels yet" sub="Add your first Makkah hotel" />
        )}
      </div>
      {confirmDialog}
    </div>
  );
}
