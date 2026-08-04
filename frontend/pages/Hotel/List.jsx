import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import Table from "../../components/shadcn/table.jsx";
import Pagination from "../../components/shadcn/pagination.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
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
  if (d < 500) return "badge badge-green";
  if (d < 1500) return "badge badge-yellow";
  return "badge badge-red";
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
    debounce.current = setTimeout(() => go({ q: query }), 300);
    return () => clearTimeout(debounce.current);
  }, [query]);

  const apply = () => { setPanelOpen(false); go({ city, stars }); };
  const resetAll = () => { setCity(""); setStars(""); setPanelOpen(false); go({ city: "", stars: "" }); };
  const [confirm, confirmDialog] = useConfirm();
  const del = (e, pk, name) => { e.stopPropagation(); confirm({ title: t("Delete hotel"), message: t("Delete hotel {name}?", { name }), onConfirm: () => router.post(`/hotels/${pk}/delete/`) }); };
  const openForm = useFormModal();
  const perms = usePerms();

  const filterCount = (city_filter ? 1 : 0) + (stars_filter ? 1 : 0);

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />
      <div className="page-header">
        <div>
          <div className="page-title">{t("Hotels")}</div>
          <div className="page-sub">{t("{count} hotels registered", { count: total_count })}</div>
        </div>
        <div className="page-actions">
          <a href="/hotels/map/" className="btn btn-secondary">
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" /></svg>
            {t("Map")}
          </a>
          {perms.can("hotels", "create") && (
            <button type="button" onClick={() => openForm("/hotels/new/")} onPointerEnter={() => openForm.prefetch("/hotels/new/")} onFocus={() => openForm.prefetch("/hotels/new/")} className="btn btn-primary">
              <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
              {t("New hotel")}
            </button>
          )}
        </div>
      </div>

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
                  <div className="fp-status-group" role="radiogroup" aria-label={t("City")}>
                    {CITY_OPTS.map((o) => (
                      <div key={o.val} className={`fp-status-opt ${o.cls}${city === o.val ? " selected" : ""}`}
                        role="radio" aria-checked={city === o.val} tabIndex={0}
                        onClick={() => setCity(o.val)}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setCity(o.val); } }}>
                        <span className="fp-status-dot"></span><span className="fp-status-opt-label">{t(o.label)}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="fp-section">
                  <div className="fp-section-head"><span className="fp-section-label">{t("Stars")}</span><button type="button" className="fp-reset" onClick={() => setStars("")}>{t("Reset")}</button></div>
                  <div className="fp-status-group" role="radiogroup" aria-label={t("Stars")}>
                    {STAR_OPTS.map((o) => (
                      <div key={o.val} className={`fp-status-opt ${o.cls}${stars === o.val ? " selected" : ""}`}
                        role="radio" aria-checked={stars === o.val} tabIndex={0}
                        onClick={() => setStars(o.val)}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setStars(o.val); } }}>
                        <span className="fp-status-dot"></span><span className="fp-status-opt-label">{t(o.label)}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="fp-footer">
                  <button type="button" className="btn btn-ghost" style={{ fontSize: 12 }} onClick={resetAll}>{t("Reset all")}</button>
                  <button type="button" className="fp-apply" onClick={apply}>{t("Apply")}</button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        {hotels.length ? (
          <>
            <Table
              columns={[
                { header: t("Hotel Name"), className: "col-m-primary", render: (h) => <span style={{ fontWeight: 600 }}>{h.name}</span> },
                {
                  header: t("Status"),
                  className: "col-m-badge",
                  render: (h) => h.is_active ? <span className="badge badge-green">{t("Active")}</span> : <span className="badge badge-gray">{t("Inactive")}</span>,
                },
                {
                  header: t("City"),
                  className: "col-m-secondary",
                  render: (h) => (
                    <>
                      <span className={"badge " + (h.city === "makkah" ? "badge-blue" : "badge-green")}>{h.city_display}</span>
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
                      <span className="m-hide">{h.distance !== null ? <span className={distBadge(h.distance)}>{h.distance_label}</span> : <span className="col-dim">—</span>}</span>
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
          <div className="empty">
            <Icon name="hotels" size={36} strokeWidth={1.5} />
            {(q || city_filter || area_filter || stars_filter) ? (
              <><div className="empty-title">{t("No matching hotels")}</div><div className="empty-sub"><a href="/hotels/" style={{ color: "var(--accent-2)" }}>{t("Reset filter")}</a></div></>
            ) : (
              <><div className="empty-title">{t("No hotels yet")}</div><div className="empty-sub">{t("Add your first Makkah hotel")}</div></>
            )}
          </div>
        )}
      </div>
      {confirmDialog}
    </div>
  );
}
