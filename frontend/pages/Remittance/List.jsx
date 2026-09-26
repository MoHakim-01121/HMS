import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import Table from "../../components/shadcn/table.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import ListCard from "../../components/shadcn/list-card.jsx";
import SearchBox from "../../components/shadcn/search-box.jsx";
import FilterPanel, { FilterSection } from "../../components/shadcn/filter-panel.jsx";
import FilterRadioGroup from "../../components/shadcn/filter-radio-group.jsx";
import FilterChips from "../../components/shadcn/filter-chips.jsx";
import ExportMenu from "../../components/shadcn/export-menu.jsx";
import TrackingPanel from "./TrackingPanel.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import useDebouncedSearch from "../../hooks/useDebouncedSearch.js";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { listVisit } from "../../utils/listVisit.js";
import { fmt } from "../../utils/format.js";

const STATUS_OPTS = [
  { val: "", label: "All", cls: "c-all" },
  { val: "pending", label: "Pending", cls: "c-pen" },
  { val: "received", label: "Received", cls: "c-rec" },
];

const visit = (params) => listVisit("/remittance/", params);

export default function List({ tab = "transfers", remittances, stats, status_filter, q, total_count, tracking, monthly }) {
  const { t } = useI18n();
  const [panelOpen, setPanelOpen] = useState(false);
  const [sel, setSel] = useState(status_filter || "");
  const { query, setQuery } = useDebouncedSearch(q, (qq) => visit({ q: qq, status: status_filter || "" }));

  const apply = () => { setPanelOpen(false); visit({ q: query, status: sel }); };
  const resetAll = () => { setQuery(""); setSel(""); setPanelOpen(false); visit({ q: "", status: "" }); };
  const dirty = sel !== (status_filter || "");
  const statusLabelOf = (v) => STATUS_OPTS.find((o) => o.val === v)?.label || v;
  const chips = [
    ...(q ? [{ key: "q", label: t('Keyword "{q}"', { q }), onRemove: () => { setQuery(""); visit({ q: "", status: status_filter || "" }); } }] : []),
    ...(status_filter ? [{ key: "status", label: t("Status {status}", { status: t(statusLabelOf(status_filter)) }), onRemove: () => { setSel(""); visit({ q: query, status: "" }); } }] : []),
  ];
  const markReceived = (e, pk) => { e.stopPropagation(); router.post(`/remittance/${pk}/mark-received/`); };
  const [confirm, confirmDialog] = useConfirm();
  const del = (e, pk, label) => { e.stopPropagation(); confirm({ title: t("Delete remittance"), message: t("Delete remittance {label}?", { label }), onConfirm: () => router.post(`/remittance/${pk}/delete/`) }); };
  const openForm = useFormModal();
  const perms = usePerms();
  const receiptUrl = (rem) => `/remittance/${rem.id}/receipt/?next=/remittance/`;

  const TABS = [
    { key: "transfers", label: t("Transfers") },
    { key: "tracking", label: t("Tracking") },
    { key: "recap", label: t("Recap") },
  ];

  const columns = [
    { header: t("Remittance No"), className: "col-m-primary col-nowrap", render: (rem) => rem.remittance_number },
    {
      header: t("Status"),
      className: "col-m-badge",
      render: (rem) => rem.status === "received" ? <StatusPill tone="green" label={t("Received")} />
        : rem.settled_sar > 0 ? <StatusPill tone="blue" label={t("Partially received")} />
          : <StatusPill tone="yellow" label={t("Pending")} />,
    },
    { header: t("Date"), className: "col-m-secondary col-nowrap", render: (rem) => rem.date },
    {
      header: t("Proof"),
      className: "col-m-hide",
      render: (rem) => (
        <>
          <span className="m-hide">
            {rem.proof_url
              ? <a href={rem.proof_url} target="_blank" rel="noreferrer" style={{ color: "var(--accent-2)", fontSize: 12, textDecoration: "none" }} onClick={(e) => e.stopPropagation()}>{t("View")} ↗</a>
              : "—"}
          </span>
          {rem.proof_url && <a href={rem.proof_url} target="_blank" rel="noreferrer" className="dv-link m-only" onClick={(e) => e.stopPropagation()}>{t("Proof")}</a>}
        </>
      ),
    },
    {
      header: t("Received"),
      className: "mono col-m-hide col-nowrap",
      render: (rem) => (rem.settled_sar ? fmt(rem.settled_sar) : "—"),
    },
    {
      header: t("Allocated"),
      className: "mono col-m-hide col-nowrap",
      render: (rem) => (rem.expected_sar != null ? fmt(rem.allocated_sar) : "—"),
    },
    {
      header: t("Total SAR"),
      className: "mono col-m-amount",
      style: { fontWeight: 600 },
      render: (rem) => (
        <>
          <span className="m-hide">{fmt(rem.total_sar)} SAR</span>
          <span className="m-only" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--text-3)", fontWeight: 700 }}>{t("Total")}</span>
          <span className="m-only">{fmt(rem.total_sar)} SAR</span>
        </>
      ),
    },
    {
      header: "",
      className: "col-m-actions",
      render: (rem) => (
        <RowActions actions={[
          rem.can_record_receipt && perms.can("remittance", "edit") && { icon: "check", label: t("Record Receipt"), variant: "green", strokeWidth: 2.5, onClick: () => openForm(receiptUrl(rem)) },
          rem.can_mark_received && perms.can("remittance", "edit") && { icon: "check", label: t("Mark as Received"), variant: "green", strokeWidth: 2.5, onClick: (e) => markReceived(e, rem.id) },
          { icon: "pdf", label: "PDF", href: `/remittance/${rem.id}/pdf/`, variant: "green", external: true },
          perms.can("remittance", "edit") && { icon: "edit", label: t("Edit"), onClick: () => openForm(`/remittance/${rem.id}/edit/`) },
          rem.status === "pending" && !rem.settled_sar && perms.can("remittance", "delete") && { icon: "trash", label: t("Delete"), variant: "red", onClick: (e) => del(e, rem.id, rem.date) },
        ]} />
      ),
    },
  ];

  return (
    <div className="page shadcn-root">
      <style>{LIST_CSS}</style>
      <PageBack />
      <PageHeader
        title={t("Remittance")}
        sub={tab === "transfers"
          ? t("{count} remittances saved", { count: total_count })
          : tab === "tracking"
            ? t("Client money in Surabaya not yet allocated to what HQ received")
            : t("Per transfer month — received is what actually reached HQ")}
        actions={
          <>
            <ExportMenu
              items={[
                { href: "/remittance/export/ledger/", label: t("Ledger PDF"), icon: "invoice", external: true },
                { href: "/remittance/export/csv/", label: t("Export CSV"), icon: "invoice" },
              ]}
            />
            {perms.can("remittance", "create") && (
              <Button type="button" size="lg" onClick={() => openForm("/remittance/new/")} onPointerEnter={() => openForm.prefetch("/remittance/new/")} onFocus={() => openForm.prefetch("/remittance/new/")}>{t("+ New Transfer")}</Button>
            )}
          </>
        }
      />

      <div className="rmt-tabs" role="tablist">
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            className={`rmt-tab${tab === key ? " active" : ""}`}
            onClick={() => key !== tab && visit({ tab: key === "transfers" ? "" : key })}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "transfers" && (
        <>
          <div className="hms-kpi-row">
            <KpiCard label={t("Sent")} value={fmt(stats.sent)} unit="SAR" foot={t("all transfers")} />
            <KpiCard label={t("Received at HQ")} value={fmt(stats.received)} unit="SAR" foot={t("actually reached HQ")} />
            <KpiCard label={t("In transit")} value={fmt(stats.in_transit)} unit="SAR" foot={t("sent, not received yet")} />
            <KpiCard
              label={t("Received, not allocated")}
              value={fmt(stats.received_unallocated)}
              unit="SAR"
              warn={stats.received_unallocated > 0}
              foot={stats.received_unallocated > 0 ? (
                <button type="button" className="rmt-kpi-link" onClick={() => visit({ tab: "tracking" })}>
                  {t("Allocate in Tracking")} →
                </button>
              ) : t("nothing waiting")}
            />
          </div>

          {/* Posisi kas: angka yang tidak ada di tab lain. Kewajiban ke Pusat dan
              saldo dana klien sengaja berdampingan -- kewajiban negatif tanpa
              konteks saldo klien bisa salah dibaca sebagai kredit murni Surabaya. */}
          <dl className="rmt-cash" aria-label={t("Cash position")}>
            <div>
              <dt>{stats.kewajiban_kirim < 0 ? t("Credit Owed by HQ") : t("Owed to HQ")}</dt>
              <dd>{fmt(Math.abs(stats.kewajiban_kirim))} SAR</dd>
            </div>
            <div>
              <dt>{t("Client Fund Balance")}</dt>
              <dd>{fmt(stats.saldo_dana_klien)} SAR</dd>
            </div>
            <div>
              <dt>{t("Rupiah not yet sent")}</dt>
              <dd>{fmt(stats.rupiah_dari_klien)} IDR</dd>
            </div>
            <div>
              <dt>{stats.selisih_kurs < 0 ? t("Exchange Loss") : t("Exchange Gain")}</dt>
              <dd>{fmt(Math.abs(stats.selisih_kurs))} SAR</dd>
            </div>
          </dl>

          <div className="filter-bar">
            <SearchBox value={query} onChange={setQuery} placeholder="Search remittance number or reference…" />
            <div className="fbar-actions">
              <FilterPanel
                count={status_filter ? 1 : 0}
                open={panelOpen}
                onToggle={() => setPanelOpen((v) => !v)}
                dirty={dirty}
                onApply={apply}
                onResetAll={resetAll}
              >
                <FilterSection label={t("Status")} onReset={() => setSel("")}>
                  <FilterRadioGroup label={t("Status")} options={STATUS_OPTS} value={sel} onChange={setSel} dot />
                </FilterSection>
              </FilterPanel>
            </div>
          </div>

          <FilterChips chips={chips} onClearAll={resetAll} />

          <ListCard
            columns={columns}
            rows={remittances}
            rowKey={(rem) => rem.id}
            onRowClick={(rem) => router.visit(`/remittance/${rem.id}/`)}
            empty={{
              icon: "invoice",
              title: "No remittances yet",
              sub: 'Click "+ New Transfer" to record a transfer to HQ',
              filteredTitle: "No results",
              filteredSub: "Try adjusting your search filters",
            }}
            hasFilter={!!(q || status_filter)}
          />
        </>
      )}

      {tab === "tracking" && <TrackingPanel tracking={tracking} />}
      {tab === "recap" && <RecapPanel monthly={monthly} t={t} />}

      {confirmDialog}
    </div>
  );
}

const RECAP_PILL = {
  received: { tone: "green", label: "Received" },
  partial: { tone: "blue", label: "Partially received" },
  pending: { tone: "yellow", label: "Pending" },
};

function RecapPanel({ monthly, t }) {
  if (!monthly || !monthly.length) {
    return <EmptyState iconName="invoice" title={t("No remittances yet")} sub={t("Nothing recorded")} />;
  }
  return (
    <div className="recap-list">
      {monthly.map((m) => (
        <div key={m.period} className="recap-group">
          <div className="recap-group-head">
            <span className="recap-group-label">{m.label}</span>
            <span className="recap-group-stats">
              {t("Sent")} {fmt(m.total_sent)} · {t("Received")} {fmt(m.total_received)}
              {m.total_outstanding ? ` · ${t("In transit")} ${fmt(m.total_outstanding)}` : ""}
              {m.total_difference ? ` · ${t("Difference")} ${fmt(m.total_difference)}` : ""} SAR
              <a className="recap-pdf" href={`/remittance/export/pdf/?month=${m.period}`} target="_blank" rel="noreferrer">PDF</a>
            </span>
          </div>
          <div className="hms-list-card">
            <Table
              columns={[
                { header: t("Remittance No"), className: "col-m-primary col-nowrap", render: (x) => x.remittance_number },
                {
                  header: t("Status"),
                  className: "col-m-badge",
                  render: (x) => <StatusPill tone={RECAP_PILL[x.state].tone} label={t(RECAP_PILL[x.state].label)} />,
                },
                { header: t("Date"), className: "col-m-hide col-nowrap", render: (x) => x.date },
                { header: t("Lines"), className: "col-m-hide", render: (x) => x.lines_count },
                { header: t("Sent"), className: "mono col-m-hide col-nowrap", render: (x) => fmt(x.sent) },
                {
                  header: t("Received"),
                  className: "mono col-m-amount",
                  render: (x) => (
                    <>
                      <span className="m-only recap-m-label">{t("Received")}</span>
                      {x.received ? `${fmt(x.received)} SAR` : "—"}
                      {x.difference ? <span className="recap-diff">{t("difference")} {fmt(x.difference)}</span> : null}
                    </>
                  ),
                },
                {
                  header: "",
                  className: "col-m-actions",
                  render: (x) => (
                    <RowActions
                      actions={[
                        { icon: "pdf", label: "PDF", href: `/remittance/${x.id}/pdf/`, variant: "green", external: true },
                        { icon: "arrow-up-right", label: t("Open"), href: `/remittance/${x.id}/`, variant: "green" },
                      ]}
                    />
                  ),
                },
              ]}
              rows={m.remittances}
              rowKey={(x) => x.id}
              onRowClick={(x) => router.visit(`/remittance/${x.id}/`)}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

// Posisi kas + link KPI (tab Transfer) dan detail Recap.
const LIST_CSS = `
.recap-pdf { margin-left: 10px; font-weight: 600; color: var(--foreground); text-decoration: none; }
.recap-pdf:hover { text-decoration: underline; }
.recap-m-label { margin-right: 6px; font-size: 10px; font-weight: 700; letter-spacing: .5px; text-transform: uppercase; color: var(--text-3); }
.recap-diff { display: block; font-size: 11px; font-weight: 400; color: var(--muted-foreground); }
.rmt-kpi-link { border: none; background: none; padding: 0; font: inherit; font-weight: 600; color: var(--foreground); cursor: pointer; }
.rmt-kpi-link:hover { text-decoration: underline; }
.rmt-cash { display: flex; flex-wrap: wrap; gap: 6px 22px; margin: -4px 2px 16px; font-size: 12.5px; }
.rmt-cash > div { display: flex; gap: 6px; }
.rmt-cash dt { color: var(--muted-foreground); }
.rmt-cash dd { margin: 0; font-weight: 600; font-variant-numeric: tabular-nums; }
`;
