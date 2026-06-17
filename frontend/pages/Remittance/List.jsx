import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");
const STATUS_OPTS = [
  { val: "", label: "Semua", cls: "c-all" },
  { val: "pending", label: "Pending", cls: "c-pen" },
  { val: "received", label: "Received", cls: "c-rec" },
];

function visit(params) {
  router.get("/remittance/", params, { preserveState: true, preserveScroll: true, replace: true });
}

export default function List({ remittances, stats, status_filter, q, total_count }) {
  const [query, setQuery] = useState(q || "");
  const [panelOpen, setPanelOpen] = useState(false);
  const [sel, setSel] = useState(status_filter || "");
  const debounce = useRef(null);
  const first = useRef(true);

  useEffect(() => {
    if (first.current) { first.current = false; return; }
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => visit({ q: query, status: status_filter || "" }), 300);
    return () => clearTimeout(debounce.current);
  }, [query]);

  const apply = () => { setPanelOpen(false); visit({ q: query, status: sel }); };
  const resetAll = () => { setSel(""); setPanelOpen(false); visit({ q: query, status: "" }); };
  const markReceived = (e, pk) => { e.stopPropagation(); router.post(`/remittance/${pk}/mark-received/`); };
  const del = (e, pk, label) => { e.stopPropagation(); if (confirm(`Hapus remittance ${label}?`)) router.post(`/remittance/${pk}/delete/`); };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">Remittance</div>
          <div className="page-sub">{total_count} remittance tersimpan</div>
        </div>
        <div className="page-actions">
          <a href="/remittance/recap/" className="btn btn-secondary" style={{ height: 32, padding: "0 12px", fontSize: 13 }}>Rekap</a>
          <a href="/remittance/export/csv/" className="btn btn-secondary">Export CSV</a>
          <a href="/remittance/new/" className="btn btn-primary">+ Kirim Baru</a>
        </div>
      </div>

      <div className="rem-stats">
        <div className="rem-stat"><div className="rem-stat-label">Total Tagihan</div><div className="rem-stat-value">{fmt(stats.total_tagihan)}<span className="unit">SAR</span></div></div>
        <div className="rem-stat"><div className="rem-stat-label">Terkirim ke Pusat</div><div className="rem-stat-value blue">{fmt(stats.terkirim_ke_pusat)}<span className="unit">SAR</span></div></div>
        <div className="rem-stat"><div className="rem-stat-label">Uang Mengendap</div><div className={"rem-stat-value " + (stats.mengendap > 0 ? "yellow" : "green")}>{fmt(stats.mengendap)}<span className="unit">SAR</span></div></div>
      </div>

      <div className="filter-bar">
        <div className="search-wrap">
          <Icon name="search" size={13} />
          <input type="text" value={query} placeholder="Cari nomor remittance atau referensi…" onChange={(e) => setQuery(e.target.value)} />
          {query && <button type="button" className="sw-clear" title="Hapus pencarian" onClick={() => setQuery("")}><Icon name="close" size={11} strokeWidth={2.5} /></button>}
        </div>
        <div className="fbar-actions">
          <div className="filter-panel-wrap" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="fbar-btn" onClick={() => setPanelOpen((v) => !v)}>
              <Icon name="filter" size={13} /> Filter
              {status_filter && <span className="fbar-count">1</span>}
            </button>
            {panelOpen && (
              <div className="filter-panel open">
                <div className="fp-head"><span className="fp-title">Filter</span></div>
                <div className="fp-section">
                  <div className="fp-section-head"><span className="fp-section-label">Status</span><button type="button" className="fp-reset" onClick={() => setSel("")}>Reset</button></div>
                  <div className="fp-status-group">
                    {STATUS_OPTS.map((o) => (
                      <div key={o.val} className={`fp-status-opt ${o.cls}${sel === o.val ? " selected" : ""}`} onClick={() => setSel(o.val)}>
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
        {remittances.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>No Remittance</th><th>Tanggal</th><th>Total SAR</th><th>Status</th><th className="col-m-hide">Bukti</th><th></th></tr>
              </thead>
              <tbody>
                {remittances.map((rem) => (
                  <tr key={rem.id} style={{ cursor: "pointer" }} onClick={() => router.visit(`/remittance/${rem.id}/`)}>
                    <td className="col-m-primary col-nowrap" style={{ fontFamily: "monospace", fontWeight: 600 }}>{rem.remittance_number}</td>
                    <td className="col-m-secondary col-nowrap">{rem.date}</td>
                    <td className="mono col-m-amount" style={{ fontWeight: 600 }}>{fmt(rem.total_sar)} SAR</td>
                    <td className="col-m-hide">{rem.status === "received" ? <span className="badge badge-green">Received</span> : <span className="badge badge-yellow">Pending</span>}</td>
                    <td className="col-m-hide" onClick={(e) => e.stopPropagation()}>
                      {rem.proof_url ? <a href={rem.proof_url} target="_blank" rel="noreferrer" style={{ color: "var(--accent-2)", fontSize: 12, textDecoration: "none" }}>Lihat ↗</a> : "—"}
                    </td>
                    <td className="col-m-actions" onClick={(e) => e.stopPropagation()}>
                      <div className="row-actions">
                        {rem.status === "pending" && (
                          <button type="button" className="btn btn-ghost btn-icon btn-icon-green" title="Mark as Received" onClick={(e) => markReceived(e, rem.id)}>
                            <Icon name="check" size={14} strokeWidth={2.5} />
                          </button>
                        )}
                        <a href={`/remittance/${rem.id}/pdf/`} target="_blank" rel="noreferrer" className="btn btn-ghost btn-icon btn-icon-green" title="PDF"><Icon name="pdf" size={14} /></a>
                        {rem.status === "pending" && (
                          <>
                            <a href={`/remittance/${rem.id}/edit/`} className="btn btn-ghost btn-icon" title="Edit"><Icon name="edit" size={14} /></a>
                            <button type="button" className="btn btn-ghost btn-icon btn-icon-red" title="Hapus" onClick={(e) => del(e, rem.id, rem.date)}><Icon name="trash" size={14} /></button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty">
            <Icon name="invoice" size={36} strokeWidth={1.5} />
            {(q || status_filter) ? (
              <><div className="empty-title">Tidak ada hasil</div><div className="empty-sub">Coba ubah filter pencarian</div></>
            ) : (
              <><div className="empty-title">Belum ada remittance</div><div className="empty-sub">Klik "+ Kirim Baru" untuk mencatat pengiriman ke Pusat</div></>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
