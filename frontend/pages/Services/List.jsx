import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import PageBack from "../../components/ui/PageBack.jsx";
import { useConfirm } from "../../components/ui/ConfirmDialog.jsx";
import Table from "../../components/ui/Table.jsx";
import RowActions from "../../components/ui/RowActions.jsx";

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

  const [confirm, confirmDialog] = useConfirm();
  const del = (e, pk, num) => { e.stopPropagation(); confirm({ title: "Delete invoice", message: `Delete invoice ${num}?`, onConfirm: () => router.post(`/services/${pk}/delete/`) }); };
  const qs = `?q=${encodeURIComponent(q || "")}`;

  return (
    <div className="page">
      <PageBack />
      <div className="page-header">
        <div>
          <div className="page-title">Invoice Services</div>
          <div className="page-sub">{total_count} invoices saved</div>
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
          <a href="/services/new/" className="btn btn-primary">+ Create New</a>
        </div>
      </div>

      <div className="filter-bar">
        <div className="search-wrap">
          <Icon name="search" size={13} />
          <input type="text" value={query} placeholder="Search customer or invoice number…" onChange={(e) => setQuery(e.target.value)} />
          {query && <button type="button" className="sw-clear" title="Clear search" onClick={() => setQuery("")}><Icon name="close" size={11} strokeWidth={2.5} /></button>}
        </div>
      </div>

      <div className="card">
        {invoices.length ? (
          <>
            <Table
              columns={[
                { header: "Invoice #", className: "col-m-primary", render: (inv) => <span className="col-bold col-nowrap">{inv.invoice_number}</span> },
                { header: "Customer", className: "col-m-secondary", render: (inv) => inv.customer_name },
                { header: "Currency", className: "col-m-amount", render: (inv) => <span className="badge badge-gray">{inv.currency}</span> },
                { header: "Issued", className: "col-muted col-nowrap col-m-hide", render: (inv) => inv.issued_date || "—" },
                { header: "Created", className: "col-dim col-nowrap col-m-hide", render: (inv) => inv.created_at },
                {
                  header: "",
                  className: "col-m-actions",
                  render: (inv) => (
                    <RowActions actions={[
                      { icon: "pdf", label: "Download PDF", href: `/services/${inv.id}/pdf/`, variant: "green", external: true },
                      { icon: "edit", label: "Edit", href: `/services/${inv.id}/edit/` },
                      { icon: "trash", label: "Delete", variant: "red", onClick: (e) => del(e, inv.id, inv.invoice_number) },
                    ]} />
                  ),
                },
              ]}
              rows={invoices}
              rowKey={(inv) => inv.id}
              onRowClick={(inv) => router.visit(`/services/${inv.id}/`)}
            />

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
              <><div className="empty-title">No results</div><div className="empty-sub">Try adjusting your search filters</div></>
            ) : (
              <><div className="empty-title">No invoices yet</div><div className="empty-sub">Use the Create New button in the top right</div></>
            )}
          </div>
        )}
      </div>
      {confirmDialog}
    </div>
  );
}
