import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import Table from "../../components/shadcn/table.jsx";
import Pagination from "../../components/shadcn/pagination.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import FilterRadioGroup from "../../components/shadcn/filter-radio-group.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { listVisit } from "../../utils/listVisit.js";

const STATUS_OPTS = [
  { val: "", label: "All", cls: "c-all" },
  { val: "active", label: "Active", cls: "c-act" },
  { val: "inactive", label: "Inactive", cls: "c-ina" },
];

function riskBadge(risk) {
  if (risk === "high") return ["red", "Risk"];
  if (risk === "medium") return ["yellow", "Overdue"];
  if (risk === "dormant") return ["gray", "Dormant"];
  return null;
}
const needsWaGroup = (c) => c.reminder_target !== "PIC" && !c.wa_group;

const visit = (params) => listVisit("/clients/", params);

export default function List({ clients, total_count, q, status, pagination }) {
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
    debounce.current = setTimeout(() => visit({ q: query, status: status || "" }), 350);
    return () => clearTimeout(debounce.current);
  }, [query]);

  const apply = () => { setPanelOpen(false); visit({ q: query, status: sel }); };
  const resetAll = () => { setSel(""); setPanelOpen(false); visit({ q: query, status: "" }); };
  const del = (e, pk, name) => { e.stopPropagation(); confirm({ title: t("Delete client"), message: t("Delete client {name}?", { name }), onConfirm: () => router.post(`/clients/${pk}/delete/`) }); };

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />
      <PageHeader
        title={t("Clients")}
        sub={t("{count} travel agents registered", { count: total_count })}
        actions={
          <>
            <Button variant="outline" size="lg" asChild>
              <a href="/clients/map/">
                <Icon name="map-pin" size={14} />
                {t("Map")}
              </a>
            </Button>
            {perms.can("clients", "create") && (
              <Button type="button" size="lg" onClick={() => openForm("/clients/new/")} onPointerEnter={() => openForm.prefetch("/clients/new/")} onFocus={() => openForm.prefetch("/clients/new/")}>
                + {t("New client")}
              </Button>
            )}
          </>
        }
      />

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
                  <FilterRadioGroup label={t("Status")} options={STATUS_OPTS} value={sel} onChange={setSel} dot />
                </div>
                <div className="fp-footer">
                  <Button type="button" variant="ghost" size="sm" onClick={resetAll}>{t("Reset all")}</Button>
                  <Button type="button" size="sm" onClick={apply}>{t("Apply")}</Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="hms-list-card">
        {clients.length ? (
          <>
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
                      {rb && <span style={{ marginLeft: 6, display: "inline-flex" }}><StatusPill tone={rb[0]} label={t(rb[1])} /></span>}
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
                    {needsWaGroup(c) && <span style={{ fontSize: 9, marginLeft: 6, display: "inline-flex" }}><StatusPill tone="yellow" label={t("Group not set")} /></span>}
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
              { header: t("Status"), className: "col-m-badge", render: (c) => c.is_active ? <StatusPill tone="green" label={t("Active")} /> : <StatusPill tone="gray" label={t("Inactive")} /> },
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
          <Pagination pagination={pagination} unit={t("clients")} onPage={(p) => visit({ q: query, status: status || "", page: p })} />
          </>
        ) : (
          (q || status) ? <EmptyState iconName="user" title="No results" sub="Try adjusting your search filters" /> : <EmptyState iconName="user" title="No clients yet" sub="Add your first Umrah travel agent" />
        )}
      </div>
      {confirmDialog}
    </div>
  );
}
