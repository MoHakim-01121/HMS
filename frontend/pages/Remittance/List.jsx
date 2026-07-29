import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import PageBack from "../../components/ui/PageBack.jsx";
import { useConfirm } from "../../components/ui/ConfirmDialog.jsx";
import Table from "../../components/ui/Table.jsx";
import RowActions from "../../components/ui/RowActions.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");
const STATUS_OPTS = [
  { val: "", label: "All", cls: "c-all" },
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
  const [confirm, confirmDialog] = useConfirm();
  const del = (e, pk, label) => { e.stopPropagation(); confirm({ title: "Delete remittance", message: `Delete remittance ${label}?`, onConfirm: () => router.post(`/remittance/${pk}/delete/`) }); };

  return (
    <div className="page">
      <PageBack />
      <div className="page-header">
        <div>
          <div className="page-title">Remittance</div>
          <div className="page-sub">{total_count} remittances saved</div>
        </div>
        <div className="page-actions">
          <a href="/remittance/recap/" className="btn btn-secondary" style={{ height: 32, padding: "0 12px", fontSize: 13 }}>Recap</a>
          <a href="/remittance/export/ledger/" target="_blank" rel="noreferrer" className="btn btn-secondary">Ledger PDF</a>
          <a href="/remittance/export/csv/" className="btn btn-secondary">Export CSV</a>
          <a href="/remittance/new/" className="btn btn-primary">+ New Transfer</a>
        </div>
      </div>

      <div className="rem-stats">
        <div className="rem-stat"><div className="rem-stat-label">Total Billed</div><div className="rem-stat-value">{fmt(stats.total_tagihan)}<span className="unit">SAR</span></div></div>
        <div className="rem-stat"><div className="rem-stat-label">Sent to HQ</div><div className="rem-stat-value blue">{fmt(stats.terkirim_ke_pusat)}<span className="unit">SAR</span></div></div>
        <div className="rem-stat"><div className="rem-stat-label">Idle Funds</div><div className={"rem-stat-value " + (stats.mengendap > 0 ? "yellow" : "green")}>{fmt(stats.mengendap)}<span className="unit">SAR</span></div></div>
      </div>

      <div className="filter-bar">
        <div className="search-wrap">
          <Icon name="search" size={13} />
          <input type="text" value={query} placeholder="Search remittance number or reference…" onChange={(e) => setQuery(e.target.value)} />
          {query && <button type="button" className="sw-clear" title="Clear search" onClick={() => setQuery("")}><Icon name="close" size={11} strokeWidth={2.5} /></button>}
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
                  <button type="button" className="btn btn-ghost" style={{ fontSize: 12 }} onClick={resetAll}>Reset all</button>
                  <button type="button" className="fp-apply" onClick={apply}>Apply</button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        {remittances.length ? (
          <Table
            columns={[
              { header: "Remittance No", className: "col-m-primary col-nowrap", style: { fontFamily: "'JetBrains Mono', monospace", fontWeight: 600 }, render: (rem) => rem.remittance_number },
              { header: "Date", className: "col-m-secondary col-nowrap", render: (rem) => rem.date },
              { header: "Total SAR", className: "mono col-m-amount", style: { fontWeight: 600 }, render: (rem) => `${fmt(rem.total_sar)} SAR` },
              { header: "Status", className: "col-m-hide", render: (rem) => rem.status === "received" ? <span className="badge badge-green">Received</span> : <span className="badge badge-yellow">Pending</span> },
              {
                header: "Proof",
                headerClassName: "col-m-hide",
                className: "col-m-hide",
                render: (rem) => rem.proof_url
                  ? <a href={rem.proof_url} target="_blank" rel="noreferrer" style={{ color: "var(--accent-2)", fontSize: 12, textDecoration: "none" }} onClick={(e) => e.stopPropagation()}>View ↗</a>
                  : "—",
              },
              {
                header: "",
                className: "col-m-actions",
                render: (rem) => (
                  <RowActions actions={[
                    rem.status === "pending" && { icon: "check", label: "Mark as Received", variant: "green", strokeWidth: 2.5, onClick: (e) => markReceived(e, rem.id) },
                    { icon: "pdf", label: "PDF", href: `/remittance/${rem.id}/pdf/`, variant: "green", external: true },
                    rem.status === "pending" && { icon: "edit", label: "Edit", href: `/remittance/${rem.id}/edit/` },
                    rem.status === "pending" && { icon: "trash", label: "Delete", variant: "red", onClick: (e) => del(e, rem.id, rem.date) },
                  ]} />
                ),
              },
            ]}
            rows={remittances}
            rowKey={(rem) => rem.id}
            onRowClick={(rem) => router.visit(`/remittance/${rem.id}/`)}
          />
        ) : (
          <div className="empty">
            <Icon name="invoice" size={36} strokeWidth={1.5} />
            {(q || status_filter) ? (
              <><div className="empty-title">No results</div><div className="empty-sub">Try adjusting your search filters</div></>
            ) : (
              <><div className="empty-title">No remittances yet</div><div className="empty-sub">Click "+ New Transfer" to record a transfer to HQ</div></>
            )}
          </div>
        )}
      </div>
      {confirmDialog}
    </div>
  );
}
