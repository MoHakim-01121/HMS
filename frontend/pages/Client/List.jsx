import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import Table from "../../components/shadcn/table.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

const STATUS_OPTS = [
  { val: "", label: "All", cls: "c-all" },
  { val: "active", label: "Active", cls: "c-act" },
  { val: "inactive", label: "Inactive", cls: "c-ina" },
];

function riskBadge(risk) {
  if (risk === "high") return ["badge badge-red", "Risk"];
  if (risk === "medium") return ["badge badge-yellow", "Overdue"];
  if (risk === "dormant") return ["badge badge-gray", "Dormant"];
  return null;
}
const needsWaGroup = (c) => c.reminder_target !== "PIC" && !c.wa_group;

function visit(params) {
  router.get("/clients/", params, { preserveState: true, preserveScroll: true, replace: true });
}

export default function List({ clients, q, status }) {
  const { t } = useI18n();
  const [query, setQuery] = useState(q || "");
  const [panelOpen, setPanelOpen] = useState(false);
  const [sel, setSel] = useState(status || "");
  const debounce = useRef(null);
  const first = useRef(true);
  const openForm = useFormModal();
  const perms = usePerms();
  const [confirm, confirmDialog] = useConfirm();

  useEffect(() => {
    if (first.current) { first.current = false; return; }
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => visit({ q: query, status: status || "" }), 300);
    return () => clearTimeout(debounce.current);
  }, [query]);

  const apply = () => { setPanelOpen(false); visit({ q: query, status: sel }); };
  const resetAll = () => { setSel(""); setPanelOpen(false); visit({ q: query, status: "" }); };
  const del = (e, pk, name) => { e.stopPropagation(); confirm({ title: t("Delete client"), message: t("Delete client {name}?", { name }), onConfirm: () => router.post(`/clients/${pk}/delete/`) }); };

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />
      <div className="page-header">
        <div>
          <div className="page-title">{t("Clients")}</div>
          <div className="page-sub">{t("{count} travel agents registered", { count: clients.length })}</div>
        </div>
        <div className="page-actions">
          <a href="/clients/map/" className="btn btn-secondary">
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" /></svg>
            {t("Map")}
          </a>
          {perms.can("clients", "create") && (
            <button type="button" onClick={() => openForm("/clients/new/")} onPointerEnter={() => openForm.prefetch("/clients/new/")} onFocus={() => openForm.prefetch("/clients/new/")} className="btn btn-primary">
              <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
              {t("New client")}
            </button>
          )}
        </div>
      </div>

      <div className="filter-bar">
        <div className="search-wrap">
          <Icon name="search" size={13} />
          <input type="text" value={query} placeholder={t("Search name, city, PIC…")} onChange={(e) => setQuery(e.target.value)} />
          {query && <button type="button" className="sw-clear" title={t("Clear search")} onClick={() => setQuery("")}><Icon name="close" size={11} strokeWidth={2.5} /></button>}
        </div>
        <div className="fbar-actions">
          <div className="filter-panel-wrap" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="fbar-btn" onClick={() => setPanelOpen((v) => !v)}>
              <Icon name="filter" size={13} /> {t("Filter")}
              {status && <span className="fbar-count">1</span>}
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
        {clients.length ? (
          <Table
            columns={[
              {
                header: t("Company Name"),
                className: "col-m-primary",
                render: (c) => {
                  const rb = riskBadge(c.risk_label);
                  return (
                    <>
                      <span style={{ fontWeight: 600 }}>{c.name}</span>
                      {rb && <span className={rb[0]} style={{ marginLeft: 6 }}>{t(rb[1])}</span>}
                    </>
                  );
                },
              },
              { header: t("Brand"), className: "col-muted col-m-hide col-ellipsis-sm", render: (c) => c.brand || <span className="col-dim">—</span> },
              { header: t("City"), className: "col-muted col-m-secondary col-ellipsis", render: (c) => <>{c.city}{c.province ? `, ${c.province}` : ""}</> },
              {
                header: t("PIC / Avg Payment"),
                className: "col-mobile-only col-m-meta",
                render: (c) => (
                  <>
                    <span>{c.pic || ""}</span>
                    {c.avg_days_to_pay != null && <span>{c.avg_days_to_pay}d</span>}
                  </>
                ),
              },
              {
                header: t("PIC / WA"),
                className: "col-m-hide",
                render: (c) => (
                  <>
                    <div style={{ fontSize: 13 }}>{c.pic || "-"}</div>
                    {c.wa && <a href={`https://wa.me/${c.wa}`} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: "var(--green)", textDecoration: "none" }} onClick={(e) => e.stopPropagation()}>{c.wa}</a>}
                    {needsWaGroup(c) && <span className="badge badge-yellow" style={{ fontSize: 9, marginLeft: 6 }}>{t("Group not set")}</span>}
                  </>
                ),
              },
              {
                header: t("Last Order"),
                className: "col-m-amount",
                render: (c) => {
                  const dormant = c.days_since_last_order != null && c.days_since_last_order > 45;
                  const val = c.days_since_last_order != null ? t("{n} days ago", { n: c.days_since_last_order }) : "—";
                  return (
                    <>
                      <span className="m-hide" style={{ color: dormant ? "var(--red)" : undefined }}>{val}</span>
                      <span className="m-only" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--text-3)", fontWeight: 700 }}>{t("Last Order")}</span>
                      <span className="m-only" style={{ color: dormant ? "var(--red)" : undefined }}>{val}</span>
                    </>
                  );
                },
              },
              {
                header: t("Avg Payment"),
                className: "col-m-hide col-num",
                render: (c) => c.avg_days_to_pay != null ? <span className="mono">{c.avg_days_to_pay}d</span> : <span className="col-dim">—</span>,
              },
              { header: t("Status"), className: "col-m-hide", render: (c) => c.is_active ? <span className="badge badge-green">{t("Active")}</span> : <span className="badge badge-gray">{t("Inactive")}</span> },
              {
                header: "",
                className: "col-m-actions",
                render: (c) => <RowActions actions={[
                  perms.can("clients", "edit") && { icon: "edit", label: t("Edit"), onClick: () => openForm(`/clients/${c.id}/edit/`) },
                  perms.can("clients", "delete") && { icon: "trash", label: t("Delete"), variant: "red", onClick: (e) => del(e, c.id, c.name) },
                ]} />,
              },
            ]}
            rows={clients}
            rowKey={(c) => c.id}
            onRowClick={(c) => router.visit(`/clients/${c.id}/`)}
          />
        ) : (
          <div className="empty">
            <Icon name="user" size={36} strokeWidth={1.5} />
            {(q || status) ? (
              <><div className="empty-title">{t("No results")}</div><div className="empty-sub">{t("Try adjusting your search filters")}</div></>
            ) : (
              <><div className="empty-title">{t("No clients yet")}</div><div className="empty-sub">{t("Add your first Umrah travel agent")}</div></>
            )}
          </div>
        )}
      </div>
      {confirmDialog}
    </div>
  );
}
