import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import PageBack from "../../components/ui/PageBack.jsx";

function visit(params) {
  router.get("/services/", params, { preserveState: true, preserveScroll: true, replace: true });
}

export default function List({ invoices, total_count, q, pagination }) {
  const [query, setQuery] = useState(q || "");
  const [exportOpen, setExportOpen] = useState(false);
  const debounce = useRef(null);
  const first = useRef(true);

  useEffect(() => {
    if (first.current) { first.current = false; return; }
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => visit({ q: query }), 300);
    return () => clearTimeout(debounce.current);
  }, [query]);

  const del = (e, pk, num) => { e.stopPropagation(); if (confirm(`Hapus invoice ${num}?`)) router.post(`/services/${pk}/delete/`); };
  const qs = `?q=${encodeURIComponent(q || "")}`;

  return (
    <div className="page">
      <PageBack />
      <div className="page-header">
        <div>
          <div className="page-title">Invoice Services</div>
          <div className="page-sub">{total_count} invoice tersimpan</div>
        </div>
        <div className="page-actions">
          <div className="export-dropdown" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="btn btn-secondary export-btn" onClick={() => setExportOpen((v) => !v)}>Export ▾</button>
            {exportOpen && (
              <div className="export-menu" style={{ display: "block" }}>
                <a href={`/services/export/csv/${qs}`}><Icon name="invoice" size={13} /> CSV</a>
                <a href={`/services/export/pdf/${qs}`} target="_blank" rel="noreferrer"><Icon name="cl" size={13} /> PDF</a>
              </div>
            )}
          </div>
          <a href="/services/new/" className="btn btn-primary">+ Buat Baru</a>
        </div>
      </div>

      <div className="filter-bar">
        <div className="search-wrap">
          <Icon name="search" size={13} />
          <input type="text" value={query} placeholder="Cari customer atau nomor invoice…" onChange={(e) => setQuery(e.target.value)} />
          {query && <button type="button" className="sw-clear" title="Hapus pencarian" onClick={() => setQuery("")}><Icon name="close" size={11} strokeWidth={2.5} /></button>}
        </div>
      </div>

      <div className="card">
        {invoices.length ? (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Invoice #</th><th>Customer</th><th>Currency</th><th>Issued</th><th>Dibuat</th><th></th></tr>
                </thead>
                <tbody>
                  {invoices.map((inv) => (
                    <tr key={inv.id} style={{ cursor: "pointer" }} onClick={() => router.visit(`/services/${inv.id}/`)}>
                      <td className="col-m-primary"><span className="col-bold col-nowrap">{inv.invoice_number}</span></td>
                      <td className="col-m-secondary">{inv.customer_name}</td>
                      <td className="col-m-amount"><span className="badge badge-gray">{inv.currency}</span></td>
                      <td className="col-muted col-nowrap col-m-hide">{inv.issued_date || "—"}</td>
                      <td className="col-dim col-nowrap col-m-hide">{inv.created_at}</td>
                      <td className="col-m-actions" onClick={(e) => e.stopPropagation()}>
                        <div className="row-actions">
                          <a href={`/services/${inv.id}/pdf/`} className="btn btn-ghost btn-icon btn-icon-green" title="Download PDF" target="_blank" rel="noreferrer"><Icon name="pdf" size={14} /></a>
                          <a href={`/services/${inv.id}/edit/`} className="btn btn-ghost btn-icon" title="Edit"><Icon name="edit" size={14} /></a>
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
                {pagination.has_previous ? <button className="pag-btn" onClick={() => visit({ q: query, page: pagination.previous_page_number })}>‹</button> : <span className="pag-btn pag-disabled">‹</span>}
                {pagination.range.map((p, i) =>
                  p === null ? <span key={i} className="pag-ellipsis">…</span>
                    : p === pagination.number ? <span key={i} className="pag-btn pag-active">{p}</span>
                      : <button key={i} className="pag-btn" onClick={() => visit({ q: query, page: p })}>{p}</button>
                )}
                {pagination.has_next ? <button className="pag-btn" onClick={() => visit({ q: query, page: pagination.next_page_number })}>›</button> : <span className="pag-btn pag-disabled">›</span>}
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
    </div>
  );
}
