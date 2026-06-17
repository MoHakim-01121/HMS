import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import PageBack from "../../components/ui/PageBack.jsx";

const STATUS_OPTS = [
  { val: "", label: "Semua", cls: "c-all" },
  { val: "active", label: "Aktif", cls: "c-act" },
  { val: "inactive", label: "Nonaktif", cls: "c-ina" },
];

function riskBadge(risk) {
  if (risk === "high") return ["badge badge-red", "Risiko"];
  if (risk === "medium") return ["badge badge-yellow", "Overdue"];
  if (risk === "dormant") return ["badge badge-gray", "Dormant"];
  return null;
}
const scoreColor = (s) => (s >= 70 ? "var(--green)" : s >= 40 ? "var(--yellow)" : "var(--red)");

function visit(params) {
  router.get("/clients/", params, { preserveState: true, preserveScroll: true, replace: true });
}

export default function List({ clients, q, status }) {
  const [query, setQuery] = useState(q || "");
  const [panelOpen, setPanelOpen] = useState(false);
  const [sel, setSel] = useState(status || "");
  const debounce = useRef(null);
  const first = useRef(true);

  useEffect(() => {
    if (first.current) { first.current = false; return; }
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => visit({ q: query, status: status || "" }), 300);
    return () => clearTimeout(debounce.current);
  }, [query]);

  const apply = () => { setPanelOpen(false); visit({ q: query, status: sel }); };
  const resetAll = () => { setSel(""); setPanelOpen(false); visit({ q: query, status: "" }); };

  return (
    <div className="page">
      <PageBack />
      <div className="page-header">
        <div>
          <div className="page-title">Clients</div>
          <div className="page-sub">{clients.length} agen travel terdaftar</div>
        </div>
        <div className="page-actions">
          <a href="/clients/map/" className="btn btn-secondary">
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" /></svg>
            Peta
          </a>
          <a href="/clients/new/" className="btn btn-primary">
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
            Client baru
          </a>
        </div>
      </div>

      <div className="filter-bar">
        <div className="search-wrap">
          <Icon name="search" size={13} />
          <input type="text" value={query} placeholder="Cari nama, kota, PIC…" onChange={(e) => setQuery(e.target.value)} />
          {query && <button type="button" className="sw-clear" title="Hapus pencarian" onClick={() => setQuery("")}><Icon name="close" size={11} strokeWidth={2.5} /></button>}
        </div>
        <div className="fbar-actions">
          <div className="filter-panel-wrap" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="fbar-btn" onClick={() => setPanelOpen((v) => !v)}>
              <Icon name="filter" size={13} /> Filter
              {status && <span className="fbar-count">1</span>}
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
        {clients.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Nama Agen</th><th>Kota</th><th>PIC / WA</th><th>Invoice</th><th>Outstanding</th><th>Score</th><th>Status</th><th></th></tr>
              </thead>
              <tbody>
                {clients.map((c) => {
                  const rb = riskBadge(c.risk_label);
                  return (
                    <tr key={c.id} style={{ cursor: "pointer" }} onClick={() => router.visit(`/clients/${c.id}/`)}>
                      <td className="col-m-primary">
                        <span style={{ fontWeight: 600 }}>{c.name}</span>
                        {rb && <span className={rb[0]} style={{ marginLeft: 6 }}>{rb[1]}</span>}
                      </td>
                      <td className="col-muted col-m-secondary">{c.city}{c.province ? `, ${c.province}` : ""}</td>
                      <td className="col-m-hide">
                        <div style={{ fontSize: 13 }}>{c.pic || "-"}</div>
                        {c.wa && <a href={`https://wa.me/${c.wa}`} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: "var(--green)", textDecoration: "none" }} onClick={(e) => e.stopPropagation()}>{c.wa}</a>}
                      </td>
                      <td className="col-muted mono col-m-hide">{c.invoices_count}</td>
                      <td className="col-m-amount">{c.outstanding > 0 ? <span className="remaining-unpaid mono">{Math.round(c.outstanding).toLocaleString("en-US")} SAR</span> : <span className="col-dim">—</span>}</td>
                      <td className="col-m-hide">
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <div style={{ flex: 1, height: 4, background: "var(--surface-3)", borderRadius: 2, maxWidth: 48 }}>
                            <div style={{ height: 4, borderRadius: 2, width: `${c.score}%`, background: scoreColor(c.score) }}></div>
                          </div>
                          <span style={{ fontSize: 11, color: "var(--text-3)" }}>{c.score}</span>
                        </div>
                      </td>
                      <td className="col-m-hide">{c.is_active ? <span className="badge badge-green">Aktif</span> : <span className="badge badge-gray">Nonaktif</span>}</td>
                      <td className="col-m-actions" onClick={(e) => e.stopPropagation()}>
                        <a href={`/clients/${c.id}/`} className="btn btn-ghost btn-sm">Detail</a>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty">
            <Icon name="user" size={36} strokeWidth={1.5} />
            {(q || status) ? (
              <><div className="empty-title">Tidak ada hasil</div><div className="empty-sub">Coba ubah filter pencarian</div></>
            ) : (
              <><div className="empty-title">Belum ada client</div><div className="empty-sub">Tambah agen travel Umrah pertama</div></>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
