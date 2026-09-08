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
import FilterPanel, { FilterSection } from "../../components/shadcn/filter-panel.jsx";
import FilterRadioGroup from "../../components/shadcn/filter-radio-group.jsx";
import FilterChips from "../../components/shadcn/filter-chips.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import useDebouncedSearch from "../../hooks/useDebouncedSearch.js";
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
  const [sel, setSel] = useState(status || "");
  const [panelOpen, setPanelOpen] = useState(false);
  const { query, setQuery } = useDebouncedSearch(q, (query) => visit({ q: query, status: status || "" }));
  const openForm = useFormModal();
  const perms = usePerms();
  const [confirm, confirmDialog] = useConfirm();

  const apply = () => { setPanelOpen(false); visit({ q: query, status: sel }); };
  const resetAll = () => { setQuery(""); setSel(""); setPanelOpen(false); visit({ q: "", status: "" }); };
  const del = (e, pk, name) => { e.stopPropagation(); confirm({ title: t("Delete client"), message: t("Delete client {name}?", { name }), onConfirm: () => router.post(`/clients/${pk}/delete/`) }); };
  const dirty = sel !== (status || "");
  const statusLabelOf = (v) => STATUS_OPTS.find((o) => o.val === v)?.label || v;
  const chips = [
    ...(q ? [{ key: "q", label: t('Keyword "{q}"', { q }), onRemove: () => { setQuery(""); visit({ q: "", status: status || "" }); } }] : []),
    ...(status ? [{ key: "status", label: t("Status {status}", { status: t(statusLabelOf(status)) }), onRemove: () => { setSel(""); visit({ q: query, status: "" }); } }] : []),
  ];

  const columns = [
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
  ];

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
        <SearchBox value={query} onChange={setQuery} placeholder="Search name, city, PIC…" />
        <div className="fbar-actions">
          <FilterPanel
            count={status ? 1 : 0}
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
        rows={clients}
        rowKey={(c) => c.id}
        onRowClick={(c) => router.visit(`/clients/${c.id}/`)}
        empty={{
          icon: "user",
          title: "No clients yet",
          sub: "Add your first Umrah travel agent",
          filteredTitle: "No results",
          filteredSub: "Try adjusting your search filters",
        }}
        hasFilter={!!(q || status)}
        pagination={pagination}
        unit={t("clients")}
        onPage={(p) => visit({ q: query, status: status || "", page: p })}
      />
      {confirmDialog}
    </div>
  );
}