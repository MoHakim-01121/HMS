import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import StatusBadge from "../../components/ui/StatusBadge.jsx";
import { Icon } from "../../components/icons.jsx";
import PageBack from "../../components/ui/PageBack.jsx";
import { useConfirm } from "../../components/ui/ConfirmDialog.jsx";
import Table from "../../components/ui/Table.jsx";
import RowActions from "../../components/ui/RowActions.jsx";

const STATUS_OPTS = [
  { val: "", label: "All", cls: "c-all" },
  { val: "lunas", label: "Paid", cls: "c-lun" },
  { val: "partial", label: "Partial", cls: "c-par" },
  { val: "belum", label: "Unpaid", cls: "c-bel" },
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
          <div className="page-sub">{total_count} invoices saved</div>
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
          <a href="/invoice/new/" className="btn btn-primary">+ Create New</a>
        </div>
      </div>

      {remit_stats && (
        <div className="rs-grid">
          <Stat label="Total Billed" value={remit_stats.total_tagihan} />
          <Stat label="Unpaid" value={remit_stats.belum_terbayar} cls={remit_stats.belum_terbayar > 0 ? "red" : "green"} />
          <Stat label="Paid in Surabaya" value={remit_stats.terbayar_surabaya} cls="green" />
          <Stat label="Sent to HQ" value={remit_stats.terbayar_pusat} cls="blue" />
          <Stat label="Idle Funds" value={remit_stats.mengendap} cls={remit_stats.mengendap > 0 ? "yellow" : "green"} />
        </div>
      )}

      <div className="filter-bar">
        <div className="search-wrap">
          <Icon name="search" size={13} />
          <input type="text" value={query} placeholder="Search customer or invoice number…" onChange={(e) => setQuery(e.target.value)} />
          {query && (
            <button type="button" className="sw-clear" title="Clear search" onClick={() => setQuery("")}>
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
                  <button type="button" className="btn btn-ghost" style={{ fontSize: 12 }} onClick={resetAll}>Reset all</button>
                  <button type="button" className="fp-apply" onClick={applyStatus}>Apply</button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        {invoices.length ? (
          <>
            <Table
              columns={[
                { header: "Invoice #", className: "col-m-primary", render: (inv) => <span className="col-bold col-nowrap">{inv.invoice_number}</span> },
                { header: "Customer", className: "col-m-secondary", render: (inv) => inv.customer_name },
                { header: "Issued", className: "col-muted col-nowrap col-m-meta", render: (inv) => inv.issued_date || "—" },
                { header: "Total", className: "mono col-nowrap col-m-meta", render: (inv) => `${inv.total_sar.toLocaleString("en-US")} SAR` },
                {
                  header: "Remaining",
                  className: (inv) => "mono col-nowrap col-m-amount " + (inv.remaining_sar === 0 ? "remaining-paid" : inv.remaining_sar > 0 ? "remaining-unpaid" : ""),
                  render: (inv) => `${inv.remaining_sar.toLocaleString("en-US")} SAR`,
                },
                { header: "Status", className: "col-m-badge", render: (inv) => <StatusBadge status={inv.status} /> },
                { header: "Created", className: "col-dim col-nowrap col-m-hide", render: (inv) => inv.created_at },
                {
                  header: "",
                  className: "col-m-actions",
                  render: (inv) => (
                    <RowActions actions={[
                      { icon: "pdf", label: "Download PDF", href: `/invoice/${inv.id}/pdf/`, variant: "green", external: true },
                      { icon: "edit", label: "Edit", href: `/invoice/${inv.id}/edit/` },
                      { icon: "trash", label: "Delete", variant: "red", onClick: (e) => del(e, inv.id, inv.invoice_number) },
                    ]} />
                  ),
                },
              ]}
              rows={invoices}
              rowKey={(inv) => inv.id}
              onRowClick={(inv) => router.visit(`/invoice/${inv.id}/`)}
            />

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

function Stat({ label, value, cls }) {
  return (
    <div className="rs-card">
      <div className="rs-label">{label}</div>
      <div className={"rs-val" + (cls ? " " + cls : "")}>{value.toLocaleString("en-US")} <span className="rs-unit">SAR</span></div>
    </div>
  );
}
