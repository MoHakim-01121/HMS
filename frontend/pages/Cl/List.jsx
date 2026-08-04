import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import Table from "../../components/shadcn/table.jsx";
import Pagination from "../../components/shadcn/pagination.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

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

  const [confirm, confirmDialog] = useConfirm();
  const { t } = useI18n();
  const del = (e, pk, number) => { e.stopPropagation(); confirm({ title: t("Delete CL"), message: t("Delete CL {number}?", { number }), onConfirm: () => router.post(`/cl/${pk}/delete/`) }); };
  const openForm = useFormModal();
  const perms = usePerms();

  const exportQs = buildQuery({ q, status: status_list, date_from, date_to, sort }).replace("/cl/", "");

  return (
    <div className="page shadcn-root">
      <PageBack />
      <div className="page-header">
        <div>
          <div className="page-title">{t("Confirmation Letter")}</div>
          <div className="page-sub">{t("{count} documents saved", { count: total_count })}</div>
        </div>
        <div className="page-actions">
          <div className="export-dropdown" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="btn btn-secondary export-btn" onClick={() => setExportOpen((v) => !v)}>{t("Export")} ▾</button>
            {exportOpen && (
              <div className="export-menu" style={{ display: "block" }}>
                <a href={`/cl/export/csv/${exportQs}`}><Icon name="invoice" size={13} /> CSV</a>
                <a href={`/cl/export/pdf/${exportQs}`} target="_blank" rel="noreferrer"><Icon name="cl" size={13} /> PDF</a>
                <a href={`/cl/export/pdf-v2/${exportQs}`} target="_blank" rel="noreferrer"><Icon name="cl" size={13} /> PDF v2</a>
              </div>
            )}
          </div>
          {perms.can("cl", "create") && (
            <button type="button" onClick={() => openForm("/cl/new/")} onPointerEnter={() => openForm.prefetch("/cl/new/")} onFocus={() => openForm.prefetch("/cl/new/")} className="btn btn-primary">{t("+ Create New")}</button>
          )}
        </div>
      </div>

      <div className="filter-bar">
        <div className="search-wrap">
          <Icon name="search" size={13} />
          <input type="text" value={query} placeholder={t("Search guest, hotel, confirmation number…")} onChange={(e) => setQuery(e.target.value)} />
          {query && <button type="button" className="sw-clear" title={t("Clear search")} onClick={() => setQuery("")}><Icon name="close" size={11} strokeWidth={2.5} /></button>}
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
              <Icon name="filter" size={13} /> {t("Filter")}
              {active_filters > 0 && <span className="fbar-count">{active_filters}</span>}
            </button>
            {panelOpen && (
              <div className="filter-panel open">
                <div className="fp-head"><span className="fp-title">{t("Filter")}</span></div>
                <div className="fp-section">
                  <div className="fp-section-head">
                    <span className="fp-section-label">{t("Check-in")}</span>
                    <button type="button" className="fp-reset" onClick={() => { setFrom(""); setTo(""); }}>{t("Reset")}</button>
                  </div>
                  <div className="fp-date-row">
                    <div className="fp-date-field"><label>{t("From")}</label><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></div>
                    <div className="fp-date-field"><label>{t("To")}</label><input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></div>
                  </div>
                </div>
                <div className="fp-section">
                  <div className="fp-section-head">
                    <span className="fp-section-label">{t("Status")}</span>
                    <button type="button" className="fp-reset" onClick={() => setSel([])}>{t("Reset")}</button>
                  </div>
                  <div className="fp-status-group" role="group" aria-label={t("Status")}>
                    {STATUS_OPTS.map((o) => (
                      <div key={o.val} className={`fp-status-opt ${o.cls}${sel.includes(o.val) ? " selected" : ""}`}
                        role="checkbox" aria-checked={sel.includes(o.val)} tabIndex={0}
                        onClick={() => toggleStatus(o.val)}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleStatus(o.val); } }}>
                        <span className="fp-status-dot"></span>
                        <span className="fp-status-opt-label">{t(o.label)}</span>
                        <span className="fp-status-count">{counts[o.countKey]}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="fp-footer">
                  <button type="button" className="btn btn-ghost" style={{ fontSize: 12 }} onClick={resetAll}>{t("Reset all")}</button>
                  <button type="button" className="fp-apply" onClick={applyFilters}>{t("Apply")}</button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        {letters.length ? (
          <>
            <Table
              columns={[
                {
                  header: t("No CL"),
                  className: "col-m-primary",
                  render: (cl) => (
                    <>
                      <span className="col-bold col-nowrap">{cl.confirmation_number}</span>
                      {cl.has_invoice && <span className="m-hide" style={{ fontSize: 10, color: "var(--accent-2)", marginLeft: 5 }} title={t("Already invoiced: {number}", { number: cl.invoice_number })}>● INV</span>}
                      {cl.has_invoice && <span className="badge badge-blue m-only" style={{ fontSize: 9, marginLeft: 5 }} title={t("Already invoiced: {number}", { number: cl.invoice_number })}>INV</span>}
                    </>
                  ),
                },
                {
                  header: t("Status"),
                  className: "col-m-badge",
                  render: (cl) => {
                    const [bcls, blabel] = statusBadge(cl.reservation_status);
                    return <span className={bcls}>{t(blabel)}</span>;
                  },
                },
                { header: t("Client/Travel"), className: "col-m-secondary col-ellipsis", render: (cl) => cl.guest_name },
                {
                  header: t("Hotel"),
                  className: "col-ellipsis-sm col-muted col-m-meta",
                  render: (cl) => (
                    <>
                      <span>{cl.hotel_name}</span>
                      {(cl.check_in || cl.check_out) && (
                        <span className="m-only" style={{ fontVariantNumeric: "tabular-nums" }}>{cl.check_in || "?"} - {cl.check_out || "?"}</span>
                      )}
                    </>
                  ),
                },
                { header: t("Check-in"), className: "col-muted col-nowrap col-m-hide", render: (cl) => cl.check_in || "—" },
                { header: t("Check-out"), className: "col-muted col-nowrap col-m-hide", render: (cl) => cl.check_out || "—" },
                {
                  header: t("Total"),
                  className: "mono col-nowrap col-m-amount",
                  render: (cl) => (
                    <>
                      <span className="m-hide">{cl.total_price ? cl.total_price.toLocaleString("en-US") + " SAR" : <span className="col-dim">—</span>}</span>
                      <span className="m-only" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--text-3)", fontWeight: 700 }}>{t("Total")}</span>
                      <span className="m-only">{cl.total_price ? `${cl.total_price.toLocaleString("en-US")} SAR` : <span style={{ color: "var(--text-3)" }}>—</span>}</span>
                    </>
                  ),
                },
                {
                  header: "",
                  className: "col-m-actions",
                  render: (cl) => (
                    <RowActions actions={[
                      { icon: "pdf", label: t("Download PDF"), href: `/cl/${cl.id}/pdf/`, variant: "green", external: true },
                      perms.can("cl", "edit") && { icon: "edit", label: t("Edit"), onClick: () => openForm(`/cl/${cl.id}/edit/`) },
                      perms.can("cl", "delete") && { icon: "trash", label: t("Delete"), variant: "red", onClick: (e) => del(e, cl.id, cl.confirmation_number) },
                    ]} />
                  ),
                },
              ]}
              rows={letters}
              rowKey={(cl) => cl.id}
              onRowClick={(cl) => router.visit(`/cl/${cl.id}/`)}
            />

            <Pagination pagination={pagination} unit={t("documents")} onPage={(p) => go({ page: p })} />
          </>
        ) : (
          <div className="empty">
            <Icon name="cl" size={36} strokeWidth={1.5} />
            {q ? (
              <><div className="empty-title">{t("No results")}</div><div className="empty-sub">{t("Try adjusting your search filters")}</div></>
            ) : (
              <><div className="empty-title">{t("No documents yet")}</div><div className="empty-sub">{t("Use the Create New button in the top right")}</div></>
            )}
          </div>
        )}
      </div>
      {confirmDialog}
    </div>
  );
}
