import PageBack from "../../components/shadcn/page-back.jsx";
import Table from "../../components/shadcn/table.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import useFilterState from "../../hooks/useFilterState.js";
import { useI18n } from "../../utils/i18n.jsx";

export default function Journal({
  entries = [], type_choices = [], page_num = 1, num_pages = 1,
  total = 0, filters = {},
}) {
  const { t } = useI18n();
  const { vals, setVal, apply } = useFilterState(
    { type: "", date_from: "", date_to: "", q: "", ...filters },
    "/finance/journal/",
  );

  const gotoPage = (p) => {
    if (p < 1 || p > num_pages) return;
    apply(p);
  };

  const columns = [
    {
      header: t("Entry #"),
      render: (e) => (
        <a href={`/finance/journal/${e.id}/`} className="text-blue-600 hover:underline font-medium">
          {e.entry_number}
        </a>
      ),
    },
    {
      header: t("Type"),
      render: (e) => (
        <span className="inline-flex items-center gap-1">
          {e.entry_type_display}
          {e.is_reversal && <StatusPill tone="red" label="Reversal" />}
        </span>
      ),
    },
    { header: t("Description"), render: (e) => e.description },
    { header: t("Date"), className: "whitespace-nowrap", render: (e) => e.entry_date },
    {
      header: t("Debit"),
      className: "text-right",
      render: (e) => <span className="font-mono tabular-nums">{e.debit.toLocaleString()}</span>,
    },
    {
      header: t("Credit"),
      className: "text-right",
      render: (e) => <span className="font-mono tabular-nums">{e.credit.toLocaleString()}</span>,
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />

      <div className="page-header">
        <div>
          <div className="page-title">{t("Journal Entries")}</div>
          <div className="page-sub">{t("Immutable double-entry ledger. Corrections are made via reversal entries.")}</div>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="filter-bar">
        <input
          className="input w-56" style={{ height: 40 }}
          placeholder={t("Search number or description...")}
          value={vals.q}
          onChange={(e) => setVal("q", e.target.value)}
        />
        <select
          className="input w-40" style={{ height: 40 }}
          value={vals.type}
          onChange={(e) => setVal("type", e.target.value)}
        >
          <option value="">{t("All Types")}</option>
          {type_choices.map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
        <input
          type="date" className="input" style={{ height: 40 }}
          value={vals.date_from}
          onChange={(e) => setVal("date_from", e.target.value)}
        />
        <input
          type="date" className="input" style={{ height: 40 }}
          value={vals.date_to}
          onChange={(e) => setVal("date_to", e.target.value)}
        />
        <button type="button" className="fp-apply" onClick={() => apply()}>{t("Apply")}</button>
      </div>

      {/* Table */}
      <div className="card">
        {entries.length > 0 ? (
          <>
            <Table columns={columns} rows={entries} rowKey={(e) => e.id} />
            <div className="flex items-center justify-between px-4 py-3 border-t border-[var(--border)] text-sm text-muted-foreground">
              <span>{total.toLocaleString()} {t("entries")}</span>
              {num_pages > 1 && (
                <span className="flex items-center gap-2">
                  <button className="btn btn-secondary btn-sm" disabled={page_num <= 1} onClick={() => gotoPage(page_num - 1)}>‹</button>
                  <span>{page_num} / {num_pages}</span>
                  <button className="btn btn-secondary btn-sm" disabled={page_num >= num_pages} onClick={() => gotoPage(page_num + 1)}>›</button>
                </span>
              )}
            </div>
          </>
        ) : (
          <EmptyState title="No journal entries found" sub="No entries match your filters." />
        )}
      </div>
    </div>
  );
}
