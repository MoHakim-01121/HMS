import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import Table from "../../components/shadcn/table.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

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
  const { t } = useI18n();
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
  const del = (e, pk, label) => { e.stopPropagation(); confirm({ title: t("Delete remittance"), message: t("Delete remittance {label}?", { label }), onConfirm: () => router.post(`/remittance/${pk}/delete/`) }); };
  const openForm = useFormModal();
  const perms = usePerms();

  return (
    <div className="page shadcn-root">
      <PageBack />
      <div className="page-header">
        <div>
          <div className="page-title">{t("Remittance")}</div>
          <div className="page-sub">{t("{count} remittances saved", { count: total_count })}</div>
        </div>
        <div className="page-actions">
          <a href="/remittance/recap/" className="btn btn-secondary" style={{ height: 32, padding: "0 12px", fontSize: 13 }}>{t("Recap")}</a>
          <a href="/remittance/export/ledger/" target="_blank" rel="noreferrer" className="btn btn-secondary">{t("Ledger PDF")}</a>
          <a href="/remittance/export/csv/" className="btn btn-secondary">{t("Export CSV")}</a>
          {perms.can("remittance", "create") && (
            <button type="button" onClick={() => openForm("/remittance/new/")} onPointerEnter={() => openForm.prefetch("/remittance/new/")} onFocus={() => openForm.prefetch("/remittance/new/")} className="btn btn-primary">{t("+ New Transfer")}</button>
          )}
        </div>
      </div>

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
      {stats.selisih_kurs !== 0 && (
        <div className="hms-kpi-row cols-5">
          <KpiCard
            label={stats.selisih_kurs > 0 ? t("Exchange Gain") : t("Exchange Loss")}
            value={fmt(Math.abs(stats.selisih_kurs))}
            unit="SAR"
            icon="invoice"
            tone={stats.selisih_kurs > 0 ? "green" : "red"}
            foot={t("this period's FX difference")}
          />
        </div>
      )}

      <div className="filter-bar">
        <div className="search-wrap">
          <Icon name="search" size={13} />
          <input type="text" value={query} placeholder={t("Search remittance number or reference…")} onChange={(e) => setQuery(e.target.value)} />
          {query && <button type="button" className="sw-clear" title={t("Clear search")} onClick={() => setQuery("")}><Icon name="close" size={11} strokeWidth={2.5} /></button>}
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
                  <div className="fp-section-head"><span className="fp-section-label">{t("Status")}</span><button type="button" className="fp-reset" onClick={() => setSel("")}>{t("Reset")}</button></div>
                  <div className="fp-status-group" role="radiogroup" aria-label={t("Status")}>
                    {STATUS_OPTS.map((o) => (
                      <div key={o.val} className={`fp-status-opt ${o.cls}${sel === o.val ? " selected" : ""}`}
                        role="radio" aria-checked={sel === o.val} tabIndex={0}
                        onClick={() => setSel(o.val)}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSel(o.val); } }}>
                        <span className="fp-status-dot"></span><span className="fp-status-opt-label">{t(o.label)}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="fp-footer">
                  <button type="button" className="btn btn-ghost" style={{ fontSize: 12 }} onClick={resetAll}>{t("Reset all")}</button>
                  <button type="button" className="fp-apply" onClick={apply}>{t("Apply")}</button>
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
              { header: t("Remittance No"), className: "col-m-primary col-nowrap", render: (rem) => rem.remittance_number },
              {
                header: t("Status"),
                className: "col-m-badge",
                render: (rem) => rem.status === "received" ? <span className="badge badge-green">{t("Received")}</span> : <span className="badge badge-yellow">{t("Pending")}</span>,
              },
              { header: t("Date"), className: "col-m-secondary col-nowrap", render: (rem) => rem.date },
              {
                header: t("Proof"),
                headerClassName: "col-m-hide",
                className: "col-m-meta",
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
            ]}
            rows={remittances}
            rowKey={(rem) => rem.id}
            onRowClick={(rem) => router.visit(`/remittance/${rem.id}/`)}
          />
        ) : (
          <div className="empty">
            <Icon name="invoice" size={36} strokeWidth={1.5} />
            {(q || status_filter) ? (
              <><div className="empty-title">{t("No results")}</div><div className="empty-sub">{t("Try adjusting your search filters")}</div></>
            ) : (
              <><div className="empty-title">{t("No remittances yet")}</div><div className="empty-sub">{t('Click "+ New Transfer" to record a transfer to HQ')}</div></>
            )}
          </div>
        )}
      </div>
      {confirmDialog}
    </div>
  );
}
