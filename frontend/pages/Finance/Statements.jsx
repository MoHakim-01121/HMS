import { useState } from "react";
import { router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import Table from "../../components/shadcn/table.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import Pagination from "../../components/shadcn/pagination.jsx";
import SearchBox from "../../components/shadcn/search-box.jsx";
import FilterPanel, { FilterSection } from "../../components/shadcn/filter-panel.jsx";
import FilterRadioGroup from "../../components/shadcn/filter-radio-group.jsx";
import FilterChips from "../../components/shadcn/filter-chips.jsx";
import { TableRow, TableCell } from "../../components/shadcn/ui/table.jsx";
import useDebouncedSearch from "../../hooks/useDebouncedSearch.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";
import { listVisit } from "../../utils/listVisit.js";

const visit = (params) => listVisit("/finance/statements/", params);

// Server owns the ordering — the list is paginated, so sorting the current
// page in the browser would only reorder a slice of the result.
const SORTS = [
  ["receivable", "Receivable"],
  ["billed", "Billed"],
  ["paid", "Paid"],
  ["credit", "Wallet Balance"],
  ["name", "Client"],
];

// [row key, column label, sort field]. The journal is SAR-only, so every
// money column says so in its header rather than repeating the unit per cell.
const MONEY = [
  ["tagihan", "Billed (SAR)", "billed"],
  ["terbayar", "Paid (SAR)", "paid"],
  ["piutang", "Receivable (SAR)", "receivable"],
  ["saldo_dana", "Wallet Balance (SAR)", "credit"],
];

export default function Statements({
  clients = [], totals = {}, total_count = 0, pagination = null,
  q = "", outstanding = false, sort = "receivable",
}) {
  const { t } = useI18n();
  const [panelOpen, setPanelOpen] = useState(false);
  const [draftSort, setDraftSort] = useState(sort);
  const [draftOutstanding, setDraftOutstanding] = useState(outstanding);
  const { query, setQuery } = useDebouncedSearch(
    q, (qq) => visit({ q: qq, outstanding: outstanding ? "1" : "", sort }),
  );

  const go = (params) => visit({ q: query, outstanding: outstanding ? "1" : "", sort, ...params });
  const apply = () => { setPanelOpen(false); go({ q: query, sort: draftSort, outstanding: draftOutstanding ? "1" : "" }); };
  const resetAll = () => { setQuery(""); setDraftSort("receivable"); setDraftOutstanding(false); setPanelOpen(false); visit({}); };
  const dirty = draftSort !== sort || draftOutstanding !== outstanding;

  const chips = [
    ...(q ? [{ key: "q", label: t('Keyword "{q}"', { q }), onRemove: () => { setQuery(""); visit({ outstanding: outstanding ? "1" : "", sort }); } }] : []),
    ...(outstanding ? [{ key: "outstanding", label: t("Outstanding only"), onRemove: () => { setDraftOutstanding(false); go({ outstanding: "" }); } }] : []),
    ...(sort !== "receivable" ? [{ key: "sort", label: t("Sorted by {field}", { field: t(SORTS.find(([k]) => k === sort)[1]) }), onRemove: () => { setDraftSort("receivable"); go({ sort: "" }); } }] : []),
  ];

  // Sorts are numeric-only in the panel; `name` sorts A→Z and is reachable
  // from the Client column header.
  const SortHeader = ({ field, label, children }) => {
    const active = sort === field;
    return (
      <button
        type="button"
        className="sh-sortbtn"
        // `label` is the plain translated string; `children` is a node, which
        // would interpolate as "[object Object]" into the tooltip.
        title={active ? t("Clear sort") : t("Sort by {field}", { field: label })}
        onClick={() => go({ sort: active ? "" : field })}
      >
        {children}
        <Icon
          name="chevron"
          size={12}
          style={{ transform: active ? "none" : "rotate(-90deg)", opacity: active ? 1 : 0.3 }}
        />
      </button>
    );
  };

  const columns = [
    {
      header: <SortHeader field="name" label={t("Client")}>{t("Client")}</SortHeader>,
      className: "col-m-primary",
      render: (c) => <span className="col-bold col-nowrap">{c.name}</span>,
    },
    ...MONEY.map(([key, label, sortField]) => ({
      header: <SortHeader field={sortField} label={t(label)}>{t(label)}</SortHeader>,
      className: "col-m-amount text-right",
      render: (c) => (
        <span
          className="col-nowrap font-mono tabular-nums"
          style={key === "piutang" && c.piutang > 0 ? { color: "var(--red)" } : undefined}
        >
          {fmt(c[key])}
        </span>
      ),
    })),
  ];

  return (
    <div className="page shadcn-root">
      <style>{CSS}</style>
      <PageBack label={t("Back")} />

      <PageHeader
        title={t("Client Ledger")}
        sub={t("{count} clients with ledger activity. Open a client for the full statement.", { count: total_count })}
      />

      <div className="filter-bar">
        <SearchBox value={query} onChange={setQuery} placeholder={t("Search client.")} />
        <div className="fbar-actions">
          <FilterPanel
            count={(outstanding ? 1 : 0) + (sort !== "receivable" ? 1 : 0)}
            open={panelOpen}
            onToggle={() => setPanelOpen((v) => !v)}
            dirty={dirty}
            onApply={apply}
            onResetAll={resetAll}
          >
            <FilterSection label="Balance" onReset={() => { setDraftOutstanding(false); setDraftSort("receivable"); }}>
              <FilterRadioGroup
                label={t("Balance")}
                options={[{ val: "all", label: "All", cls: "c-all" }, { val: "outstanding", label: "Outstanding", cls: "c-ina" }]}
                value={draftOutstanding ? "outstanding" : "all"}
                onChange={(v) => setDraftOutstanding(v === "outstanding")}
                dot
              />
            </FilterSection>
            <FilterSection label="Sort by">
              <FilterRadioGroup
                label={t("Sort by")}
                options={SORTS.map(([val, label]) => ({ val, label, cls: val === "name" ? "c-all" : "c-act" }))}
                value={draftSort}
                onChange={setDraftSort}
                dot
              />
            </FilterSection>
          </FilterPanel>
        </div>
      </div>

      <FilterChips chips={chips} onClearAll={resetAll} />

      <div className="hms-list-card">
        {clients.length > 0 ? (
          <>
            <Table
              columns={columns}
              rows={clients}
              rowKey={(c) => c.client_id}
              onRowClick={(c) => router.visit(`/finance/clients/${c.client_id}/statement/`)}
              footer={(
                <TableRow>
                  <TableCell className="col-bold">{t("Total")}</TableCell>
                  {MONEY.map(([key]) => (
                    <TableCell key={key} className="text-right col-bold col-nowrap">
                      {fmt(totals[key])}
                    </TableCell>
                  ))}
                </TableRow>
              )}
            />
            <Pagination pagination={pagination} unit={t("clients")} onPage={(p) => go({ page: p })} />
          </>
        ) : (
          <EmptyState
            iconName="wallet"
            title={q || outstanding ? t("No results") : t("No ledger activity")}
            sub={q || outstanding ? t("Try adjusting your search filters") : t("No clients with charges, payments or allocations yet.")}
          />
        )}
      </div>
    </div>
  );
}

const CSS = `
.sh-sortbtn {
  display: inline-flex; align-items: center; gap: 3px;
  background: none; border: 0; padding: 0; margin: 0;
  font: inherit; color: inherit; cursor: pointer;
}

`;