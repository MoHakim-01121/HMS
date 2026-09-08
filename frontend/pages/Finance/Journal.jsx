import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import Table from "../../components/shadcn/table.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import ListPager from "../../components/shadcn/list-pager.jsx";
import useFilterState from "../../hooks/useFilterState.js";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
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
      className: "col-m-primary",
      render: (e) => <span className="col-bold col-nowrap">{e.entry_number}</span>,
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

      <PageHeader
        title={t("Journal Entries")}
        sub={t("Immutable double-entry ledger. Corrections are made via reversal entries.")}
      />

      {/* Filter Bar */}
      <div className="filter-bar">
        <Input
          className="w-56"
          placeholder={t("Search number or description...")}
          value={vals.q}
          onChange={(e) => setVal("q", e.target.value)}
        />
        <Select value={vals.type} onValueChange={(v) => setVal("type", v)}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder={t("All Types")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">{t("All Types")}</SelectItem>
            {type_choices.map(([value, label]) => (
              <SelectItem key={value} value={value}>{label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input type="date" value={vals.date_from} onChange={(e) => setVal("date_from", e.target.value)} />
        <Input type="date" value={vals.date_to} onChange={(e) => setVal("date_to", e.target.value)} />
        <Button type="button" size="lg" onClick={() => apply()}>{t("Apply")}</Button>
      </div>

      {/* Table */}
      <div className="hms-list-card">
        {entries.length > 0 ? (
          <>
            <Table
              columns={columns}
              rows={entries}
              rowKey={(e) => e.id}
              onRowClick={(e) => router.visit(`/finance/journal/${e.id}/`)}
            />
            <ListPager page={page_num} numPages={num_pages} total={total} unit="entries" onPage={gotoPage} />
          </>
        ) : (
          <EmptyState iconName="invoice" title="No journal entries found" sub="No entries match your filters." />
        )}
      </div>
    </div>
  );
}
