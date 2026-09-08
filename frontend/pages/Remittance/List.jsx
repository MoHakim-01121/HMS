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

export default function List({ remittances, stats, status_filter, q, total_count, tracking, monthly }) {
  const { t } = useI18n();
  const [tab, setTab] = useState("transfers");
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
      render: (rem) => rem.status === "received" ? <StatusPill tone="green" label={t("Received")} /> : <StatusPill tone="yellow" label={t("Pending")} />,
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
          rem.status === "pending" && perms.can("remittance", "edit") && { icon: "check", label: t("Mark as Received"), variant: "green", strokeWidth: 2.5, onClick: (e) => markReceived(e, rem.id) },
          { icon: "pdf", label: "PDF", href: `/remittance/${rem.id}/pdf/`, variant: "green", external: true },
          perms.can("remittance", "edit") && { icon: "edit", label: t("Edit"), onClick: () => openForm(`/remittance/${rem.id}/edit/`) },
          rem.status === "pending" && perms.can("remittance", "delete") && { icon: "trash", label: t("Delete"), variant: "red", onClick: (e) => del(e, rem.id, rem.date) },
        ]} />
      ),
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack />
      <PageHeader
        title={t("Remittance")}
        sub={tab === "transfers"
          ? t("{count} remittances saved", { count: total_count })
          : tab === "tracking"
            ? t("Per reservation: sent to HQ, remaining idle funds, which RMT covered them")
            : t("Remittance summary per month")}
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
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "transfers" && (
        <>
          <div className="hms-kpi-row cols-5">
            <KpiCard label={t("Total Billed")} value={fmt(stats.total_tagihan)} unit="SAR" icon="invoice" foot={t("all remittances")} />
            <KpiCard label={t("Sent to HQ")} value={fmt(stats.terkirim_ke_pusat)} unit="SAR" icon="remittance" tone="blue" foot={t("transferred to HQ")} />
            <KpiCard
              label={stats.mengendap < 0 ? t("Credit at HQ") : t("Idle Funds")}
              value={fmt(Math.abs(stats.mengendap))}
              unit="SAR"
              icon="clock"
              tone={stats.mengendap > 0 ? "yellow" : stats.mengendap < 0 ? "blue" : "green"}
              foot={stats.mengendap < 0 ? t("HQ sent more than received") : t("pending transfer")}
            />
            {/* Kewajiban kirim & saldo dana klien wajib berdampingan: kewajiban
                kirim negatif tanpa konteks saldo klien bisa salah dibaca sebagai
                kredit murni Surabaya, padahal bisa jadi kelebihan bayar klien. */}
            <KpiCard
              label={stats.kewajiban_kirim < 0 ? t("Credit Owed by HQ") : t("Owed to HQ")}
              value={fmt(Math.abs(stats.kewajiban_kirim))}
              unit="SAR"
              icon="remittance"
              tone={stats.kewajiban_kirim > 0 ? "yellow" : stats.kewajiban_kirim < 0 ? "blue" : "green"}
              foot={t("what Surabaya still owes HQ")}
            />
            <KpiCard
              label={t("Client Fund Balance")}
              value={fmt(stats.saldo_dana_klien)}
              unit="SAR"
              icon="invoice"
              tone={stats.saldo_dana_klien > 0 ? "yellow" : "green"}
              foot={t("client cash not yet allocated")}
            />
          </div>
          {(stats.rupiah_dari_klien > 0 || stats.selisih_kurs !== 0) && (
            <div className="hms-kpi-row cols-3">
              {stats.rupiah_dari_klien > 0 && (
                <KpiCard
                  label={t("Rupiah Idle in Surabaya")}
                  value={fmt(stats.rupiah_dari_klien)}
                  unit="IDR"
                  icon="clock"
                  tone="yellow"
                  foot={t("client rupiah received but not yet sent to HQ")}
                />
              )}
              {stats.selisih_kurs !== 0 && (
                <KpiCard
                  label={stats.selisih_kurs > 0 ? t("Exchange Gain") : t("Exchange Loss")}
                  value={fmt(Math.abs(stats.selisih_kurs))}
                  unit="SAR"
                  icon="invoice"
                  tone={stats.selisih_kurs > 0 ? "green" : "red"}
                  foot={t("this period's FX difference")}
                />
              )}
            </div>
          )}

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

      {tab === "tracking" && <TrackingPanel tracking={tracking} t={t} />}
      {tab === "recap" && <RecapPanel monthly={monthly} t={t} />}

      {confirmDialog}
    </div>
  );
}

function TrackingPanel({ tracking, t }) {
  const clients = tracking?.clients || [];
  const totalSisa = tracking?.total_sisa_kirim ?? 0;
  return (
    <>
      {clients.length ? (
        <div className="trk-summary">
          <div className="trk-summary-num">{fmt(totalSisa)}</div>
          <div className="trk-summary-lbl">{t("SAR still idle in Surabaya")}</div>
          <div className="trk-summary-sub">{t("{n} clients, {r} reservations", { n: clients.length, r: clients.reduce((a, c) => a + c.reservations.length, 0) })}</div>
        </div>
      ) : (
        <EmptyState iconName="clock" title={t("Nothing pending transfer")} sub={t("No reservations with idle funds right now")} />
      )}
      {clients.map((c) => (
        <div key={c.client_name} className="trk-group">
          <div className="trk-group-head">
            <span className="trk-group-name">{c.client_name}</span>
            <span className="trk-group-amt">{t("{n} reservations", { n: c.reservations.length })}</span>
          </div>
          <div className="hms-list-card">
            <Table
              columns={[
                {
                  header: t("Reservation"),
                  className: "col-m-primary col-nowrap",
                  render: (x) => (
                    <>
                      <span className="trk-res">{x.linked_number}</span>
                      {x.invoice_number && <span className="trk-res-sub">{x.invoice_number}</span>}
                      {x.rmts.length > 0 && (
                        <span className="trk-rmt-count" title={x.rmts.map((r) => `${r.number} · ${r.date} · ${fmt(r.amount_sar)} SAR`).join("\n")}>{x.rmts.length} RMT</span>
                      )}
                    </>
                  ),
                },
                {
                  header: t("Hotel / Check-in"),
                  className: "col-m-secondary",
                  render: (x) => (
                    <>
                      <span>{x.hotel}</span>
                      {x.check_in && <span className="trk-res-sub">{t("in")} {x.check_in}</span>}
                    </>
                  ),
                },
                {
                  header: t("Sent to HQ"),
                  className: "mono col-m-amount",
                  render: (x) => <span className="trk-sent">{fmt(x.sudah_dikirim)}</span>,
                },
                {
                  header: t("Idle"),
                  className: "mono col-m-amount",
                  style: { fontWeight: 600 },
                  render: (x) =>
                    x.sisa_kirim > 0
                      ? <span className="trk-idle">{fmt(x.sisa_kirim)}</span>
                      : x.mengendap < 0
                        ? <span className="trk-over" title={t("HQ sent more than received for this reservation")}>{fmt(x.mengendap)}</span>
                        : <span className="trk-zero">0</span>,
                },
              ]}
              rows={c.reservations}
              rowKey={(x) => x.linked_number}
            />
          </div>
        </div>
      ))}
    </>
  );
}

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
              {t("Sent")}: {fmt(m.total_sent)} SAR · {t("Received")}: {fmt(m.total_received)} SAR
            </span>
          </div>
          <div className="hms-list-card">
            <Table
              columns={[
                { header: t("Remittance No"), className: "col-m-primary col-nowrap", render: (x) => x.remittance_number },
                {
                  header: t("Status"),
                  className: "col-m-badge",
                  render: (x) => x.status === "received" ? <StatusPill tone="green" label={t("Received")} /> : <StatusPill tone="yellow" label={t("Pending")} />,
                },
                { header: t("Date"), className: "col-m-hide col-nowrap", render: (x) => x.date },
                { header: t("Lines"), className: "col-m-hide", render: (x) => x.lines_count },
                { header: t("Total SAR"), className: "mono col-m-amount", render: (x) => `${fmt(x.total_sar)} SAR` },
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