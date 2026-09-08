import { useState } from "react";
import { router } from "@inertiajs/react";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import FilterRadioGroup from "../../components/shadcn/filter-radio-group.jsx";
import FilterChips from "../../components/shadcn/filter-chips.jsx";
import ListCard from "../../components/shadcn/list-card.jsx";
import SearchBox from "../../components/shadcn/search-box.jsx";
import FilterPanel from "../../components/shadcn/filter-panel.jsx";
import ExportMenu from "../../components/shadcn/export-menu.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import useDebouncedSearch from "../../hooks/useDebouncedSearch.js";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { listVisit } from "../../utils/listVisit.js";
import { fmt } from "../../utils/format.js";

const STATUS_OPTS = [
  { val: "", label: "All", cls: "c-all" },
  { val: "lunas", label: "Paid", cls: "c-lun" },
  { val: "partial", label: "Partial", cls: "c-par" },
  { val: "belum", label: "Unpaid", cls: "c-bel" },
];

const visit = (params) => listVisit("/invoice/", params);

function buildQuery({ q, status, date_from, date_to } = {}) {
  const p = new URLSearchParams();
  if (q) p.set("q", q);
  if (status) p.set("status", status);
  if (date_from) p.set("date_from", date_from);
  if (date_to) p.set("date_to", date_to);
  const s = p.toString();
  return s ? `/invoice/?${s}` : "/invoice/";
}

export default function List({ invoices, total_count, q, status_filter, date_from, date_to, remit_stats, pagination }) {
  const { t } = useI18n();
  const [sel, setSel] = useState(status_filter || "");
  const [from, setFrom] = useState(date_from || "");
  const [to, setTo] = useState(date_to || "");
  const [panelOpen, setPanelOpen] = useState(false);
  const { query, setQuery } = useDebouncedSearch(q, (qq) => visit({ q: qq }));
  const [confirm, confirmDialog] = useConfirm();
  const openForm = useFormModal();
  const perms = usePerms();

  const applyFilters = () => { setPanelOpen(false); visit({ status: sel, date_from: from, date_to: to }); };
  const resetAll = () => { setQuery(""); setSel(""); setFrom(""); setTo(""); setPanelOpen(false); visit({ q: "", status: "", date_from: "", date_to: "" }); };
  const dirty = sel !== (status_filter || "") || from !== (date_from || "") || to !== (date_to || "");
  const activeGroups = (status_filter ? 1 : 0) + ((date_from || date_to) ? 1 : 0);

  const statusLabelOf = (v) => STATUS_OPTS.find((o) => o.val === v)?.label || v;
  const chips = [
    ...(q ? [{ key: "q", label: t('Keyword "{q}"', { q }), onRemove: () => { setQuery(""); visit({ q: "" }); } }] : []),
    ...((date_from || date_to) ? [{ key: "date", label: t("Due {from} to {to}", { from: date_from || "…", to: date_to || "…" }), onRemove: () => { setFrom(""); setTo(""); visit({ date_from: "", date_to: "" }); } }] : []),
    ...(status_filter ? [{ key: "status", label: t("Status {status}", { status: t(statusLabelOf(status_filter)) }), onRemove: () => { setSel(""); visit({ status: "" }); } }] : []),
  ];
  const del = (e, pk, number) => {
    e.stopPropagation();
    confirm({ title: t("Delete invoice"), message: t("Delete invoice {number}?", { number }), onConfirm: () => router.post(`/invoice/${pk}/delete/`) });
  };

  const exportQs = buildQuery({ q, status: status_filter, date_from, date_to }).replace("/invoice/", "");

  const columns = [
    { header: t("Invoice #"), className: "col-m-primary", render: (inv) => <span className="col-bold col-nowrap">{inv.invoice_number}</span> },
    { header: t("Customer"), className: "col-m-secondary", render: (inv) => inv.customer_name },
    {
      header: t("Due Date"),
      className: "col-muted col-nowrap col-m-meta",
      render: (inv) => (
        <>
          <span className="m-hide">{inv.due_date || "—"}</span>
          {inv.due_date && <span className="m-only">{t("due {date}", { date: inv.due_date })}</span>}
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
    { header: t("Status"), className: "col-m-badge", render: (inv) => (
      <StatusPill tone={
        inv.status === "overpaid" ? "green" :
        inv.status === "paid" ? "green" :
        inv.status === "partial" ? "yellow" : "red"
      } label={t({
        overpaid: "Overpaid",
        paid: "Paid",
        partial: "Partial",
        unpaid: "Unpaid",
      }[inv.status] || "Unpaid")} />
    ) },
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
  ];

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />
      <PageHeader
        title={t("Invoice Hotel")}
        sub={t("{count} invoices saved", { count: total_count })}
        actions={
          <>
            <ExportMenu
              items={[
                { href: `/invoice/export/csv/${exportQs}`, label: "CSV", icon: "invoice" },
                { href: `/invoice/export/pdf/${exportQs}`, label: "PDF", icon: "cl", external: true },
              ]}
            />
            {perms.can("invoice", "create") && (
              <Button type="button" size="lg" onClick={() => openForm("/invoice/new/")} onPointerEnter={() => openForm.prefetch("/invoice/new/")} onFocus={() => openForm.prefetch("/invoice/new/")}>+ {t("Create New")}</Button>
            )}
          </>
        }
      />

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
            label={remit_stats.mengendap < 0 ? t("Credit at HQ") : t("Idle Funds")}
            value={fmt(Math.abs(remit_stats.mengendap))}
            unit="SAR"
            icon="clock"
            tone={remit_stats.mengendap > 0 ? "yellow" : remit_stats.mengendap < 0 ? "blue" : "green"}
            foot={remit_stats.mengendap < 0 ? t("HQ sent more than received") : t("awaiting transfer")}
          />
        </div>
      )}

      <div className="filter-bar">
        <SearchBox value={query} onChange={setQuery} placeholder="Search customer or invoice number…" />
        <div className="fbar-actions">
          <FilterPanel
            count={activeGroups}
            open={panelOpen}
            onToggle={() => setPanelOpen((v) => !v)}
            dirty={dirty}
            onApply={applyFilters}
            onResetAll={resetAll}
          >
            <div className="fp-section">
              <div className="fp-section-head">
                <span className="fp-section-label">{t("Due Date")}</span>
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
                <button type="button" className="fp-reset" onClick={() => setSel("")}>{t("Reset")}</button>
              </div>
              <FilterRadioGroup label={t("Status")} options={STATUS_OPTS} value={sel} onChange={setSel} dot />
            </div>
          </FilterPanel>
        </div>
      </div>

      <FilterChips chips={chips} onClearAll={resetAll} />

      <ListCard
        columns={columns}
        rows={invoices}
        rowKey={(inv) => inv.id}
        onRowClick={(inv) => router.visit(`/invoice/${inv.id}/`)}
        empty={{
          icon: "invoice",
          title: "No invoices yet",
          sub: "Use the Create New button in the top right",
          filteredTitle: "No results",
          filteredSub: "Try adjusting your search filters",
        }}
        hasFilter={!!q}
        pagination={pagination}
        unit={t("invoices")}
        onPage={(p) => visit({ page: p })}
      />
      {confirmDialog}
    </div>
  );
}