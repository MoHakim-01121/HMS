import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import PageBack from "../../components/ui/PageBack.jsx";

const CITY_OPTS = [
  { val: "", label: "Semua Kota", cls: "c-all" },
  { val: "makkah", label: "Makkah", cls: "c-mak" },
  { val: "madinah", label: "Madinah", cls: "c-mad" },
];
const STAR_OPTS = [
  { val: "", label: "Semua ★", cls: "c-all" },
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
  const del = (e, pk, name) => { e.stopPropagation(); if (confirm(`Hapus hotel ${name}?`)) router.post(`/hotels/${pk}/delete/`); };

  const filterCount = (city_filter ? 1 : 0) + (stars_filter ? 1 : 0);

  return (
    <div className="page">
      <PageBack />
      <div className="page-header">
        <div>
          <div className="page-title">Hotels</div>
          <div className="page-sub">{total_count} hotel terdaftar</div>
        </div>
        <div className="page-actions">
          <a href="/hotels/map/" className="btn btn-secondary">
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" /></svg>
            Peta
          </a>
          <a href="/hotels/new/" className="btn btn-primary">
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
            Hotel baru
          </a>
        </div>
      </div>

      <div className="filter-bar">
        <div className="search-wrap">
          <Icon name="search" size={13} />
          <input type="text" value={query} placeholder="Cari nama atau area…" onChange={(e) => setQuery(e.target.value)} />
          {query && <button type="button" className="sw-clear" title="Hapus pencarian" onClick={() => setQuery("")}><Icon name="close" size={11} strokeWidth={2.5} /></button>}
        </div>
        <div className="fbar-actions">
          <div className="filter-panel-wrap" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="fbar-btn" onClick={() => setPanelOpen((v) => !v)}>
              <Icon name="filter" size={13} /> Filter
              {filterCount > 0 && <span className="fbar-count">{filterCount}</span>}
            </button>
            {panelOpen && (
              <div className="filter-panel open">
                <div className="fp-head"><span className="fp-title">Filter</span></div>
                <div className="fp-section">
                  <div className="fp-section-head"><span className="fp-section-label">Kota</span><button type="button" className="fp-reset" onClick={() => setCity("")}>Reset</button></div>
                  <div className="fp-status-group">
                    {CITY_OPTS.map((o) => (
                      <div key={o.val} className={`fp-status-opt ${o.cls}${city === o.val ? " selected" : ""}`} onClick={() => setCity(o.val)}>
                        <span className="fp-status-dot"></span><span className="fp-status-opt-label">{o.label}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="fp-section">
                  <div className="fp-section-head"><span className="fp-section-label">Bintang</span><button type="button" className="fp-reset" onClick={() => setStars("")}>Reset</button></div>
                  <div className="fp-status-group">
                    {STAR_OPTS.map((o) => (
                      <div key={o.val} className={`fp-status-opt ${o.cls}${stars === o.val ? " selected" : ""}`} onClick={() => setStars(o.val)}>
                        <span className="fp-status-dot"></span><span className="fp-status-opt-label">{o.label}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="fp-footer">
                  <button type="button" className="btn btn-ghost" style={{ fontSize: 12 }} onClick={resetAll}>Reset semua</button>
                  <button type="button" className="fp-apply" onClick={apply}>Terapkan</button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        {hotels.length ? (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Nama Hotel</th><th>Kota</th><th>Area</th><th>Bintang</th><th>Jarak ke Masjid</th><th>Avg</th><th>Status</th><th></th></tr>
                </thead>
                <tbody>
                  {hotels.map((h) => (
                    <tr key={h.id} className="row-link" style={{ cursor: "pointer" }} onClick={() => router.visit(`/hotels/${h.id}/`)}>
                      <td className="col-m-primary"><span style={{ fontWeight: 600 }}>{h.name}</span></td>
                      <td className="col-m-secondary"><span className={"badge " + (h.city === "makkah" ? "badge-blue" : "badge-green")}>{h.city_display}</span></td>
                      <td className="col-muted col-m-hide">{h.area || "—"}</td>
                      <td className="col-m-amount"><span style={{ color: "var(--yellow)", fontSize: 12, fontWeight: 600 }}>{h.stars}★</span></td>
                      <td className="col-m-hide">
                        {h.distance !== null ? <span className={distBadge(h.distance)}>{h.distance_label}</span> : <span className="col-dim">—</span>}
                      </td>
                      <td className="mono col-m-hide">{h.avg_occupancy ? h.avg_occupancy : <span className="col-dim">—</span>}</td>
                      <td className="col-m-hide">{h.is_active ? <span className="badge badge-green">Aktif</span> : <span className="badge badge-gray">Nonaktif</span>}</td>
                      <td className="col-m-actions">
                        <div className="row-actions" onClick={(e) => e.stopPropagation()}>
                          <a href={`/hotels/${h.id}/edit/`} className="btn btn-ghost btn-icon" title="Edit"><Icon name="edit" size={14} /></a>
                          <button type="button" className="btn btn-ghost btn-icon btn-icon-red" title="Hapus" onClick={(e) => del(e, h.id, h.name)}><Icon name="trash" size={14} /></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {pagination.has_other_pages && (
              <div className="pagination">
                {pagination.has_previous ? <button className="pag-btn" onClick={() => go({ page: pagination.previous_page_number })}>‹</button> : <span className="pag-btn pag-disabled">‹</span>}
                {pagination.range.map((p, i) =>
                  p === null ? <span key={i} className="pag-ellipsis">…</span>
                    : p === pagination.number ? <span key={i} className="pag-btn pag-active">{p}</span>
                      : <button key={i} className="pag-btn" onClick={() => go({ page: p })}>{p}</button>
                )}
                {pagination.has_next ? <button className="pag-btn" onClick={() => go({ page: pagination.next_page_number })}>›</button> : <span className="pag-btn pag-disabled">›</span>}
              </div>
            )}
          </>
        ) : (
          <div className="empty">
            <Icon name="hotels" size={36} strokeWidth={1.5} />
            {(q || city_filter || area_filter || stars_filter) ? (
              <><div className="empty-title">Tidak ada hotel yang cocok</div><div className="empty-sub"><a href="/hotels/" style={{ color: "var(--accent-2)" }}>Reset filter</a></div></>
            ) : (
              <><div className="empty-title">Belum ada hotel</div><div className="empty-sub">Tambah hotel Makkah pertama</div></>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
