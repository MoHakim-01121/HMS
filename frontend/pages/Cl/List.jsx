import { useState } from "react";
import { router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import ListCard from "../../components/shadcn/list-card.jsx";
import SearchBox from "../../components/shadcn/search-box.jsx";
import FilterPanel from "../../components/shadcn/filter-panel.jsx";
import FilterChips from "../../components/shadcn/filter-chips.jsx";
import ExportMenu from "../../components/shadcn/export-menu.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import useDebouncedSearch from "../../hooks/useDebouncedSearch.js";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmtDateShort } from "../../utils/format.js";

const STATUS_OPTS = [
  { val: "definite", label: "Definite", cls: "c-def", countKey: "definite" },
  { val: "tentative", label: "Tentative", cls: "c-ten", countKey: "tentative" },
  { val: "cancelled", label: "Cancelled", cls: "c-can", countKey: "cancelled" },
];

function statusBadge(s) {
  if (s === "DEFINITE") return ["green", "Definite"];
  if (s === "CANCELLED") return ["red", "Cancelled"];
  return ["yellow", "Tentative"];
}

// Mobile card only: "12/08/2026" -> "12 Aug" so the stay line stays short
// enough to leave room for the hotel name above it.
const shortDate = (dmy) => fmtDateShort(dmy) || "?";

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
  const { t } = useI18n();
  const [panelOpen, setPanelOpen] = useState(false);
  const [sortOpen, setSortOpen] = useState(false);
  const [sel, setSel] = useState(status_list || []);
  const [from, setFrom] = useState(date_from || "");
  const [to, setTo] = useState(date_to || "");
  const { query, setQuery } = useDebouncedSearch(q, (qq) => go({ q: qq }));

  const go = (extra = {}) =>
    router.get(buildQuery({ q: query, status: status_list, date_from, date_to, sort, ...extra }), {}, { preserveState: true, preserveScroll: true, replace: true });

  const toggleStatus = (val) => setSel((prev) => prev.includes(val) ? prev.filter((s) => s !== val) : [...prev, val]);
  const applyFilters = () => { setPanelOpen(false); go({ status: sel, date_from: from, date_to: to }); };
  const resetAll = () => { setSel([]); setFrom(""); setTo(""); setPanelOpen(false); go({ q: "", status: [], date_from: "", date_to: "" }); setQuery(""); };
  const appliedList = status_list || [];
  const dirty = sel.slice().sort().join() !== appliedList.slice().sort().join() || from !== (date_from || "") || to !== (date_to || "");

  const [confirm, confirmDialog] = useConfirm();

  const statusOptByVal = Object.fromEntries(STATUS_OPTS.map((o) => [o.val, o]));
  const chips = [
    ...(q ? [{ key: "q", label: t('Keyword "{q}"', { q }), onRemove: () => { setQuery(""); go({ q: "" }); } }] : []),
    ...((date_from || date_to) ? [{ key: "date", label: t("Check-in {from} to {to}", { from: date_from || "…", to: date_to || "…" }), onRemove: () => { setFrom(""); setTo(""); go({ date_from: "", date_to: "" }); } }] : []),
    ...appliedList.map((val) => ({
      key: "status-" + val,
      label: t("Status {status}", { status: t(statusOptByVal[val]?.label || val) }),
      onRemove: () => { const next = appliedList.filter((s) => s !== val); setSel(next); go({ status: next }); },
    })),
  ];
  const del = (e, pk, number) => { e.stopPropagation(); confirm({ title: t("Delete CL"), message: t("Delete CL {number}?", { number }), onConfirm: () => router.post(`/cl/${pk}/delete/`) }); };
  const openForm = useFormModal();
  const perms = usePerms();

  const exportQs = buildQuery({ q, status: status_list, date_from, date_to, sort }).replace("/cl/", "");

  const columns = [
    {
      header: t("No CL"),
      className: "col-m-primary",
      render: (cl) => (
        <>
          <span className="col-bold col-nowrap">{cl.confirmation_number}</span>
          {cl.has_invoice && <span className="m-hide" style={{ fontSize: 10, color: "var(--accent-2)", marginLeft: 5 }} title={t("Already invoiced: {number}", { number: cl.invoice_number })}>● INV</span>}
          {cl.has_invoice && <span className="m-only" style={{ marginLeft: 5 }} title={t("Already invoiced: {number}", { number: cl.invoice_number })}><StatusPill small outline label="INV" /></span>}
        </>
      ),
    },
    {
      header: t("Status"),
      className: "col-m-badge",
      render: (cl) => {
        const [tone, blabel] = statusBadge(cl.reservation_status);
        return <StatusPill tone={tone} label={t(blabel)} />;
      },
    },
    { header: t("Client/Travel"), className: "col-m-secondary col-ellipsis", render: (cl) => (cl.guest_name || "").trim().replace(/^-$/, "") || <span className="col-dim">—</span> },
    {
      header: t("Hotel"),
      className: "col-ellipsis-sm col-muted col-m-meta",
      render: (cl) => (
        <>
          <span className="m-hide">{cl.hotel_name}</span>
          <span className="m-only m-card-hotelstay">
            <span className="m-card-hotel-row">
              <Icon name="hotels" size={11} />
              <span className="m-card-hotel-name">{cl.hotel_name}</span>
            </span>
            {(cl.check_in || cl.check_out) && (
              <span className="m-card-stay-row">
                <Icon name="calendar" size={11} />
                <span className="m-card-stay-dates">{shortDate(cl.check_in)} – {shortDate(cl.check_out)}</span>
                {!!cl.num_nights && <span className="m-card-nights">{t("{n} nights", { n: cl.num_nights })}</span>}
              </span>
            )}
          </span>
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
          {!!cl.total_rooms && <span className="m-only m-card-rooms">{cl.total_rooms} {t(cl.total_rooms === 1 ? "room" : "rooms")}</span>}
          <span className="m-only m-card-total-group">
            <span style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--text-3)", fontWeight: 700 }}>{t("Total")}</span>
            <span>{cl.total_price ? `${cl.total_price.toLocaleString("en-US")} SAR` : <span style={{ color: "var(--text-3)" }}>—</span>}</span>
          </span>
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
  ];

  return (
    <div className="page shadcn-root">
      <PageBack />
      <PageHeader
        title={t("Confirmation Letter")}
        sub={t("{count} documents saved", { count: total_count })}
        actions={
          <>
            <ExportMenu
              items={[
                { href: `/cl/export/csv/${exportQs}`, label: "CSV", icon: "invoice" },
                { href: `/cl/export/pdf/${exportQs}`, label: "PDF", icon: "cl", external: true },
                { href: `/cl/export/pdf-v2/${exportQs}`, label: "PDF v2", icon: "cl", external: true },
              ]}
            />
            {perms.can("cl", "create") && (
              <Button type="button" size="lg" onClick={() => openForm("/cl/new/")} onPointerEnter={() => openForm.prefetch("/cl/new/")} onFocus={() => openForm.prefetch("/cl/new/")}>{t("+ Create New")}</Button>
            )}
          </>
        }
      />

      <div className="filter-bar">
        <SearchBox value={query} onChange={setQuery} placeholder="Search guest, hotel, confirmation number…" />

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

          <FilterPanel
            count={active_filters}
            open={panelOpen}
            onToggle={() => { setPanelOpen((v) => !v); setSortOpen(false); }}
            dirty={dirty}
            onApply={applyFilters}
            onResetAll={resetAll}
          >
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
              <div className="fp-status-group" data-multi role="group" aria-label={t("Status")}>
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
          </FilterPanel>
        </div>
      </div>

      <FilterChips chips={chips} onClearAll={resetAll} />

      <ListCard
        columns={columns}
        rows={letters}
        rowKey={(cl) => cl.id}
        onRowClick={(cl) => router.visit(`/cl/${cl.id}/`)}
        empty={{
          icon: "cl",
          title: "No documents yet",
          sub: "Use the Create New button in the top right",
          filteredTitle: "No results",
          filteredSub: "Try adjusting your search filters",
        }}
        hasFilter={!!q}
        pagination={pagination}
        unit={t("documents")}
        onPage={(p) => go({ page: p })}
      />
      {confirmDialog}
    </div>
  );
}