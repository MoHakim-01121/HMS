import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";

const STATUS_OPTS = [
  { val: "definite", label: "Definite", cls: "c-def", countKey: "definite" },
  { val: "tentative", label: "Tentative", cls: "c-ten", countKey: "tentative" },
  { val: "cancelled", label: "Cancelled", cls: "c-can", countKey: "cancelled" },
];

function statusBadge(s) {
  if (s === "DEFINITE") return ["badge badge-green", "Definite"];
  if (s === "CANCELLED") return ["badge badge-red", "Cancelled"];
  return ["badge badge-yellow", "Tentative"];
}

// Django reads ?status=a&status=b (repeated), so build the query string by hand.
function buildQuery({ q, status, date_from, date_to, sort, page }) {
  const p = new URLSearchParams();
  if (q) p.append("q", q);
  (status || []).forEach((s) => p.append("status", s));
  if (date_from) p.append("date_from", date_from);
  if (date_to) p.append("date_to", date_to);
  if (sort) p.append("sort", sort);
  if (page) p.append("page", page);
  return "/cl/?" + p.toString();
}

export default function List({ letters, total_count, q, status_list, date_from, date_to, sort, sort_label, sort_labels, active_filters, counts, pagination }) {
  const [query, setQuery] = useState(q || "");
  const [panelOpen, setPanelOpen] = useState(false);
  const [sortOpen, setSortOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [sel, setSel] = useState(status_list || []);
  const [from, setFrom] = useState(date_from || "");
  const [to, setTo] = useState(date_to || "");
  const debounce = useRef(null);
  const first = useRef(true);

  const go = (extra = {}) =>
    router.get(buildQuery({ q: query, status: status_list, date_from, date_to, sort, ...extra }), {}, { preserveState: true, preserveScroll: true, replace: true });

  useEffect(() => {
    if (first.current) { first.current = false; return; }
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => go({ q: query }), 300);
    return () => clearTimeout(debounce.current);
  }, [query]);

  const toggleStatus = (val) => setSel((prev) => prev.includes(val) ? prev.filter((s) => s !== val) : [...prev, val]);
  const applyFilters = () => { setPanelOpen(false); go({ status: sel, date_from: from, date_to: to }); };
  const resetAll = () => { setSel([]); setFrom(""); setTo(""); setPanelOpen(false); go({ status: [], date_from: "", date_to: "" }); };

  const del = (e, pk, number) => { e.stopPropagation(); if (confirm(`Hapus CL ${number}?`)) router.post(`/cl/${pk}/delete/`); };

  const exportQs = buildQuery({ q, status: status_list, date_from, date_to, sort }).replace("/cl/", "");

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">Confirmation Letter</div>
          <div className="page-sub">{total_count} dokumen tersimpan</div>
        </div>
        <div className="page-actions">
          <div className="export-dropdown" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="btn btn-secondary export-btn" onClick={() => setExportOpen((v) => !v)}>Export ▾</button>
            {exportOpen && (
              <div className="export-menu" style={{ display: "block" }}>
                <a href={`/cl/export/csv/${exportQs}`}><Icon name="invoice" size={13} /> CSV</a>
                <a href={`/cl/export/pdf/${exportQs}`} target="_blank" rel="noreferrer"><Icon name="cl" size={13} /> PDF</a>
              </div>
            )}
          </div>
          <a href="/cl/new/" className="btn btn-primary">+ Buat Baru</a>
        </div>
      </div>

      <div className="filter-bar">
        <div className="search-wrap">
          <Icon name="search" size={13} />
          <input type="text" value={query} placeholder="Cari tamu, hotel, nomor konfirmasi…" onChange={(e) => setQuery(e.target.value)} />
          {query && <button type="button" className="sw-clear" title="Hapus pencarian" onClick={() => setQuery("")}><Icon name="close" size={11} strokeWidth={2.5} /></button>}
        </div>

        <div className="fbar-actions">
          <div className="sort-wrap" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="fbar-btn" onClick={() => { setSortOpen((v) => !v); setPanelOpen(false); }}>
              <Icon name="sort" size={13} /> {sort_label}
            </button>
            {sortOpen && (
              <div className="sort-menu open">
                {Object.entries(sort_labels).map(([val, label]) => (
                  <a key={val} className={"sort-opt" + (sort === val ? " active" : "")} onClick={() => { setSortOpen(false); go({ sort: val }); }}>{label}</a>
                ))}
              </div>
            )}
          </div>

          <div className="filter-panel-wrap" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="fbar-btn" onClick={() => { setPanelOpen((v) => !v); setSortOpen(false); }}>
              <Icon name="filter" size={13} /> Filter
              {active_filters > 0 && <span className="fbar-count">{active_filters}</span>}
            </button>
            {panelOpen && (
              <div className="filter-panel open">
                <div className="fp-head"><span className="fp-title">Filter</span></div>
                <div className="fp-section">
                  <div className="fp-section-head">
                    <span className="fp-section-label">Check-in</span>
                    <button type="button" className="fp-reset" onClick={() => { setFrom(""); setTo(""); }}>Reset</button>
                  </div>
                  <div className="fp-date-row">
                    <div className="fp-date-field"><label>Dari</label><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></div>
                    <div className="fp-date-field"><label>Sampai</label><input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></div>
                  </div>
                </div>
                <div className="fp-section">
                  <div className="fp-section-head">
                    <span className="fp-section-label">Status</span>
                    <button type="button" className="fp-reset" onClick={() => setSel([])}>Reset</button>
                  </div>
                  <div className="fp-status-group">
                    {STATUS_OPTS.map((o) => (
                      <div key={o.val} className={`fp-status-opt ${o.cls}${sel.includes(o.val) ? " selected" : ""}`} onClick={() => toggleStatus(o.val)}>
                        <span className="fp-status-dot"></span>
                        <span className="fp-status-opt-label">{o.label}</span>
                        <span className="fp-status-count">{counts[o.countKey]}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="fp-footer">
                  <button type="button" className="btn btn-ghost" style={{ fontSize: 12 }} onClick={resetAll}>Reset semua</button>
                  <button type="button" className="fp-apply" onClick={applyFilters}>Terapkan</button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        {letters.length ? (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>No CL</th><th>Status</th><th>Client/Travel</th><th>Hotel</th><th>Check-in</th><th>Check-out</th><th>Total</th><th></th></tr>
                </thead>
                <tbody>
                  {letters.map((cl) => {
                    const [bcls, blabel] = statusBadge(cl.reservation_status);
                    return (
                      <tr key={cl.id} style={{ cursor: "pointer" }} onClick={() => router.visit(`/cl/${cl.id}/`)}>
                        <td className="col-m-primary">
                          <span className="col-bold col-nowrap">{cl.confirmation_number}</span>
                          {cl.has_invoice && <span style={{ fontSize: 10, color: "var(--accent-2)", marginLeft: 5 }} title={`Sudah ditagih: ${cl.invoice_number}`}>● INV</span>}
                        </td>
                        <td className="col-m-hide"><span className={bcls}>{blabel}</span></td>
                        <td className="col-m-secondary col-ellipsis">{cl.guest_name}</td>
                        <td className="col-ellipsis-sm col-muted col-m-hide">{cl.hotel_name}</td>
                        <td className="col-muted col-nowrap col-m-hide">{cl.check_in || "—"}</td>
                        <td className="col-muted col-nowrap col-m-hide">{cl.check_out || "—"}</td>
                        <td className="mono col-nowrap col-m-amount">{cl.total_price ? cl.total_price.toLocaleString("en-US") + " SAR" : "—"}</td>
                        <td className="col-m-actions" onClick={(e) => e.stopPropagation()}>
                          <div className="row-actions">
                            <a href={`/cl/${cl.id}/pdf/`} className="btn btn-ghost btn-icon btn-icon-green" title="Download PDF" target="_blank" rel="noreferrer"><Icon name="pdf" size={14} /></a>
                            <a href={`/cl/${cl.id}/edit/`} className="btn btn-ghost btn-icon" title="Edit"><Icon name="edit" size={14} /></a>
                            <button type="button" className="btn btn-ghost btn-icon btn-icon-red" title="Hapus" onClick={(e) => del(e, cl.id, cl.confirmation_number)}><Icon name="trash" size={14} /></button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {pagination.has_other_pages && (
              <div className="pagination">
                {pagination.has_previous
                  ? <button className="pag-btn" onClick={() => go({ page: pagination.previous_page_number })}>‹</button>
                  : <span className="pag-btn pag-disabled">‹</span>}
                {pagination.range.map((p, i) =>
                  p === null ? <span key={i} className="pag-ellipsis">…</span>
                    : p === pagination.number ? <span key={i} className="pag-btn pag-active">{p}</span>
                      : <button key={i} className="pag-btn" onClick={() => go({ page: p })}>{p}</button>
                )}
                {pagination.has_next
                  ? <button className="pag-btn" onClick={() => go({ page: pagination.next_page_number })}>›</button>
                  : <span className="pag-btn pag-disabled">›</span>}
              </div>
            )}
          </>
        ) : (
          <div className="empty">
            <Icon name="cl" size={36} strokeWidth={1.5} />
            {q ? (
              <><div className="empty-title">Tidak ada hasil</div><div className="empty-sub">Coba ubah filter pencarian</div></>
            ) : (
              <><div className="empty-title">Belum ada dokumen</div><div className="empty-sub">Gunakan tombol Buat Baru di pojok kanan atas</div></>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
