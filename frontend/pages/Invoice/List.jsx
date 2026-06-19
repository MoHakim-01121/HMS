import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import StatusBadge from "../../components/ui/StatusBadge.jsx";
import { Icon } from "../../components/icons.jsx";
import PageBack from "../../components/ui/PageBack.jsx";
import { useConfirm } from "../../components/ui/ConfirmDialog.jsx";

const STATUS_OPTS = [
  { val: "", label: "Semua", cls: "c-all" },
  { val: "lunas", label: "Lunas", cls: "c-lun" },
  { val: "partial", label: "Partial", cls: "c-par" },
  { val: "belum", label: "Belum Bayar", cls: "c-bel" },
];

function visit(params) {
  router.get("/invoice/", params, { preserveState: true, preserveScroll: true, replace: true });
}

export default function List({ invoices, total_count, q, status_filter, remit_stats, pagination }) {
  const [query, setQuery] = useState(q || "");
  const [panelOpen, setPanelOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [sel, setSel] = useState(status_filter || "");
  const debounce = useRef(null);
  const first = useRef(true);

  // Debounced search; auto-resets when emptied (matches the old behaviour).
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => visit({ q: query, status: status_filter || "" }), 300);
    return () => clearTimeout(debounce.current);
  }, [query]);

  const applyStatus = () => { setPanelOpen(false); visit({ q: query, status: sel }); };
  const resetAll = () => { setSel(""); setPanelOpen(false); visit({ q: query, status: "" }); };

  const [confirm, confirmDialog] = useConfirm();
  const del = (e, pk, number) => {
    e.stopPropagation();
    confirm({ title: "Delete invoice", message: `Delete invoice ${number}?`, onConfirm: () => router.post(`/invoice/${pk}/delete/`) });
  };

  const qs = `?q=${encodeURIComponent(q || "")}&status=${status_filter || ""}`;

  return (
    <div className="page">
      <PageBack />
      <div className="page-header">
        <div>
          <div className="page-title">Invoice Hotel</div>
          <div className="page-sub">{total_count} invoice tersimpan</div>
        </div>
        <div className="page-actions">
          <div className="export-dropdown" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="btn btn-secondary export-btn" onClick={() => setExportOpen((v) => !v)}>Export ▾</button>
            {exportOpen && (
              <div className="export-menu" style={{ display: "block" }}>
                <a href={`/invoice/export/csv/${qs}`}><Icon name="invoice" size={13} /> CSV</a>
                <a href={`/invoice/export/pdf/${qs}`} target="_blank" rel="noreferrer"><Icon name="cl" size={13} /> PDF</a>
              </div>
            )}
          </div>
          <a href="/invoice/new/" className="btn btn-primary">+ Buat Baru</a>
        </div>
      </div>

      {remit_stats && (
        <div className="rs-grid">
          <Stat label="Total Tagihan" value={remit_stats.total_tagihan} />
          <Stat label="Belum Terbayar" value={remit_stats.belum_terbayar} cls={remit_stats.belum_terbayar > 0 ? "red" : "green"} />
          <Stat label="Terbayar Sby" value={remit_stats.terbayar_surabaya} cls="green" />
          <Stat label="Terkirim Pusat" value={remit_stats.terbayar_pusat} cls="blue" />
          <Stat label="Mengendap" value={remit_stats.mengendap} cls={remit_stats.mengendap > 0 ? "yellow" : "green"} />
        </div>
      )}

      <div className="filter-bar">
        <div className="search-wrap">
          <Icon name="search" size={13} />
          <input type="text" value={query} placeholder="Cari customer atau nomor invoice…" onChange={(e) => setQuery(e.target.value)} />
          {query && (
            <button type="button" className="sw-clear" title="Hapus pencarian" onClick={() => setQuery("")}>
              <Icon name="close" size={11} strokeWidth={2.5} />
            </button>
          )}
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
                  <div className="fp-section-head">
                    <span className="fp-section-label">Status</span>
                    <button type="button" className="fp-reset" onClick={() => setSel("")}>Reset</button>
                  </div>
                  <div className="fp-status-group">
                    {STATUS_OPTS.map((o) => (
                      <div key={o.val} className={`fp-status-opt ${o.cls}${sel === o.val ? " selected" : ""}`} onClick={() => setSel(o.val)}>
                        <span className="fp-status-dot"></span>
                        <span className="fp-status-opt-label">{o.label}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="fp-footer">
                  <button type="button" className="btn btn-ghost" style={{ fontSize: 12 }} onClick={resetAll}>Reset semua</button>
                  <button type="button" className="fp-apply" onClick={applyStatus}>Terapkan</button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        {invoices.length ? (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Invoice #</th><th>Customer</th><th>Issued</th><th>Total</th>
                    <th>Sisa</th><th>Status</th><th>Dibuat</th><th></th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((inv) => (
                    <tr key={inv.id} style={{ cursor: "pointer" }} onClick={() => router.visit(`/invoice/${inv.id}/`)}>
                      <td className="col-m-primary"><span className="col-bold col-nowrap">{inv.invoice_number}</span></td>
                      <td className="col-m-secondary">{inv.customer_name}</td>
                      <td className="col-muted col-nowrap col-m-hide">{inv.issued_date || "—"}</td>
                      <td className="mono col-nowrap col-m-hide">{inv.total_sar.toLocaleString("en-US")} SAR</td>
                      <td className={"mono col-nowrap col-m-amount " + (inv.remaining_sar === 0 ? "remaining-paid" : inv.remaining_sar > 0 ? "remaining-unpaid" : "")}>
                        {inv.remaining_sar.toLocaleString("en-US")} SAR
                      </td>
                      <td><StatusBadge status={inv.status} /></td>
                      <td className="col-dim col-nowrap col-m-hide">{inv.created_at}</td>
                      <td className="col-m-actions" onClick={(e) => e.stopPropagation()}>
                        <div className="row-actions">
                          <a href={`/invoice/${inv.id}/pdf/`} className="btn btn-ghost btn-icon btn-icon-green" title="Download PDF" target="_blank" rel="noreferrer"><Icon name="pdf" size={14} /></a>
                          <a href={`/invoice/${inv.id}/edit/`} className="btn btn-ghost btn-icon" title="Edit"><Icon name="edit" size={14} /></a>
                          <button type="button" className="btn btn-ghost btn-icon btn-icon-red" title="Hapus" onClick={(e) => del(e, inv.id, inv.invoice_number)}><Icon name="trash" size={14} /></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {pagination.has_other_pages && (
              <div className="pagination">
                {pagination.has_previous
                  ? <button className="pag-btn" onClick={() => visit({ q: query, status: status_filter || "", page: pagination.previous_page_number })}>‹</button>
                  : <span className="pag-btn pag-disabled">‹</span>}
                {pagination.range.map((p, i) =>
                  p === null ? <span key={i} className="pag-ellipsis">…</span>
                    : p === pagination.number ? <span key={i} className="pag-btn pag-active">{p}</span>
                      : <button key={i} className="pag-btn" onClick={() => visit({ q: query, status: status_filter || "", page: p })}>{p}</button>
                )}
                {pagination.has_next
                  ? <button className="pag-btn" onClick={() => visit({ q: query, status: status_filter || "", page: pagination.next_page_number })}>›</button>
                  : <span className="pag-btn pag-disabled">›</span>}
              </div>
            )}
          </>
        ) : (
          <div className="empty">
            <Icon name="invoice" size={36} strokeWidth={1.5} />
            {q ? (
              <><div className="empty-title">Tidak ada hasil</div><div className="empty-sub">Coba ubah filter pencarian</div></>
            ) : (
              <><div className="empty-title">Belum ada invoice</div><div className="empty-sub">Gunakan tombol Buat Baru di pojok kanan atas</div></>
            )}
          </div>
        )}
      </div>
      {confirmDialog}
    </div>
  );
}

function Stat({ label, value, cls }) {
  return (
    <div className="rs-card">
      <div className="rs-label">{label}</div>
      <div className={"rs-val" + (cls ? " " + cls : "")}>{value.toLocaleString("en-US")} <span className="rs-unit">SAR</span></div>
    </div>
  );
}
