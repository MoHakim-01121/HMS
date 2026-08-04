import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import StatusBadge from "../../components/ui/StatusBadge.jsx";
import { Icon } from "../../components/icons.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import Table from "../../components/shadcn/table.jsx";
import Pagination from "../../components/shadcn/pagination.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

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
  const { t } = useI18n();
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
  const openForm = useFormModal();
  const perms = usePerms();
  const del = (e, pk, number) => {
    e.stopPropagation();
    confirm({ title: t("Delete invoice"), message: t("Delete invoice {number}?", { number }), onConfirm: () => router.post(`/invoice/${pk}/delete/`) });
  };

  const qs = `?q=${encodeURIComponent(q || "")}&status=${status_filter || ""}`;

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />
      <div className="page-header">
        <div>
          <div className="page-title">{t("Invoice Hotel")}</div>
          <div className="page-sub">{t("{count} invoices saved", { count: total_count })}</div>
        </div>
        <div className="page-actions">
          <div className="export-dropdown" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="btn btn-secondary export-btn" onClick={() => setExportOpen((v) => !v)}>{t("Export")} ▾</button>
            {exportOpen && (
              <div className="export-menu" style={{ display: "block" }}>
                <a href={`/invoice/export/csv/${qs}`}><Icon name="invoice" size={13} /> CSV</a>
                <a href={`/invoice/export/pdf/${qs}`} target="_blank" rel="noreferrer"><Icon name="cl" size={13} /> PDF</a>
              </div>
            )}
          </div>
          {perms.can("invoice", "create") && (
            <button type="button" onClick={() => openForm("/invoice/new/")} onPointerEnter={() => openForm.prefetch("/invoice/new/")} onFocus={() => openForm.prefetch("/invoice/new/")} className="btn btn-primary">+ {t("Create New")}</button>
          )}
        </div>
      </div>

      {remit_stats && (
        <div className="hms-kpi-row cols-5">
          <KpiCard label={t("Total Billed")} value={fmt(remit_stats.total_tagihan)} unit="SAR" icon="invoice" foot={t("all invoices")} />
          <KpiCard
            label={t("Unpaid")}
            value={fmt(remit_stats.belum_terbayar)}
            unit="SAR"
            icon="alert-circle"
            tone={remit_stats.belum_terbayar > 0 ? "red" : "green"}
            foot={t("outstanding balance")}
          />
          <KpiCard label={t("Paid in Surabaya")} value={fmt(remit_stats.terbayar_surabaya)} unit="SAR" icon="check" tone="green" foot={t("collected locally")} />
          <KpiCard label={t("Sent to HQ")} value={fmt(remit_stats.terbayar_pusat)} unit="SAR" icon="remittance" tone="blue" foot={t("transferred to HQ")} />
          <KpiCard
            label={t("Idle Funds")}
            value={fmt(remit_stats.mengendap)}
            unit="SAR"
            icon="clock"
            tone={remit_stats.mengendap > 0 ? "yellow" : "green"}
            foot={t("awaiting transfer")}
          />
        </div>
      )}

      <div className="filter-bar">
        <div className="search-wrap">
          <Icon name="search" size={13} />
          <input type="text" value={query} placeholder={t("Search customer or invoice number…")} onChange={(e) => setQuery(e.target.value)} />
          {query && (
            <button type="button" className="sw-clear" title={t("Clear search")} onClick={() => setQuery("")}>
              <Icon name="close" size={11} strokeWidth={2.5} />
            </button>
          )}
        </div>
        <div className="fbar-actions">
          <div className="filter-panel-wrap" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="fbar-btn" onClick={() => setPanelOpen((v) => !v)}>
              <Icon name="filter" size={13} /> {t("Filter")}
              {status_filter && <span className="fbar-count">1</span>}
            </button>
            {panelOpen && (
              <div className="filter-panel open">
                <div className="fp-head"><span className="fp-title">{t("Filter")}</span></div>
                <div className="fp-section">
                  <div className="fp-section-head">
                    <span className="fp-section-label">{t("Status")}</span>
                    <button type="button" className="fp-reset" onClick={() => setSel("")}>{t("Reset")}</button>
                  </div>
                  <div className="fp-status-group" role="radiogroup" aria-label={t("Status")}>
                    {STATUS_OPTS.map((o) => (
                      <div key={o.val} className={`fp-status-opt ${o.cls}${sel === o.val ? " selected" : ""}`}
                        role="radio" aria-checked={sel === o.val} tabIndex={0}
                        onClick={() => setSel(o.val)}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSel(o.val); } }}>
                        <span className="fp-status-dot"></span>
                        <span className="fp-status-opt-label">{t(o.label)}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="fp-footer">
                  <button type="button" className="btn btn-ghost" style={{ fontSize: 12 }} onClick={resetAll}>{t("Reset all")}</button>
                  <button type="button" className="fp-apply" onClick={applyStatus}>{t("Apply")}</button>
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
                { header: t("Invoice #"), className: "col-m-primary", render: (inv) => <span className="col-bold col-nowrap">{inv.invoice_number}</span> },
                { header: t("Customer"), className: "col-m-secondary", render: (inv) => inv.customer_name },
                {
                  header: t("Issued"),
                  className: "col-muted col-nowrap col-m-meta",
                  render: (inv) => (
                    <>
                      <span className="m-hide">{inv.issued_date || "—"}</span>
                      {inv.issued_date && <span className="m-only">{t("issued {date}", { date: inv.issued_date })}</span>}
                      <span className="m-only" style={{ fontVariantNumeric: "tabular-nums" }}>{inv.total_sar.toLocaleString("en-US")} SAR</span>
                    </>
                  ),
                },
                { header: t("Total"), className: "mono col-nowrap col-m-hide", render: (inv) => `${inv.total_sar.toLocaleString("en-US")} SAR` },
                {
                  header: t("Remaining"),
                  className: (inv) => "mono col-nowrap col-m-amount " + (inv.remaining_sar === 0 ? "remaining-paid" : inv.remaining_sar > 0 ? "remaining-unpaid" : ""),
                  render: (inv) => (
                    <>
                      <span className="m-hide">{inv.remaining_sar.toLocaleString("en-US")} SAR</span>
                      <span className="m-only" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--text-3)", fontWeight: 700 }}>{t("Remaining")}</span>
                      <span className="m-only">{inv.remaining_sar.toLocaleString("en-US")} SAR</span>
                    </>
                  ),
                },
                { header: t("Status"), className: "col-m-badge", render: (inv) => <StatusBadge status={inv.status} /> },
                { header: t("Created"), className: "col-dim col-nowrap col-m-hide", render: (inv) => inv.created_at },
                {
                  header: "",
                  className: "col-m-actions",
                  render: (inv) => (
                    <RowActions actions={[
                      { icon: "pdf", label: t("Download PDF"), href: `/invoice/${inv.id}/pdf/`, variant: "green", external: true },
                      perms.can("invoice", "edit") && { icon: "edit", label: t("Edit"), onClick: () => openForm(`/invoice/${inv.id}/edit/`) },
                      perms.can("invoice", "delete") && { icon: "trash", label: t("Delete"), variant: "red", onClick: (e) => del(e, inv.id, inv.invoice_number) },
                    ]} />
                  ),
                },
              ]}
              rows={invoices}
              rowKey={(inv) => inv.id}
              onRowClick={(inv) => router.visit(`/invoice/${inv.id}/`)}
            />

            <Pagination
              pagination={pagination}
              unit={t("invoices")}
              onPage={(p) => visit({ q: query, status: status_filter || "", page: p })}
            />
          </>
        ) : (
          <div className="empty">
            <Icon name="invoice" size={36} strokeWidth={1.5} />
            {q ? (
              <><div className="empty-title">{t("No results")}</div><div className="empty-sub">{t("Try adjusting your search filters")}</div></>
            ) : (
              <><div className="empty-title">{t("No invoices yet")}</div><div className="empty-sub">{t("Use the Create New button in the top right")}</div></>
            )}
          </div>
        )}
      </div>
      {confirmDialog}
    </div>
  );
}
