import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import Table from "../../components/shadcn/table.jsx";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import useFilterState from "../../hooks/useFilterState.js";
import { TableRow, TableCell } from "../../components/shadcn/ui/table.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

// Neraca Saldo: total debit & kredit tiap akun pada rentang tanggal, satu
// pita per tipe akun, dan baris total sejajar kolom di footer. Angka dalam
// SAR utuh — KPI di atas tabel membawa ringkasan (debit, kredit, selisih)
// supaya status seimbang/tidak terbaca sebelum masuk tabel.
export default function TrialBalance({
  groups = [], total_debit = 0, total_credit = 0, balanced = true, filters = {},
}) {
  const { t } = useI18n();
  const { vals, setVal, apply } = useFilterState(
    { date_from: "", date_to: "", ...filters },
    "/finance/trial-balance/",
  );
  const diff = total_debit - total_credit;
  const range = filters.date_from || filters.date_to ? t("in this period") : t("all time");

  // Accounts per type, for the section band's count.
  const counts = {};
  for (const g of groups) counts[g.type] = (counts[g.type] || 0) + 1;
  const accountsLabel = (n) => t(n === 1 ? "{n} account" : "{n} accounts", { n });
  const sectionOf = (g) => `${t(g.type_display)} · ${accountsLabel(counts[g.type])}`;

  const columns = [
    {
      header: t("Account"),
      className: "col-m-primary",
      render: (g) => <span className="col-bold">{g.account_display}</span>,
    },
    {
      header: t("Debit"),
      className: "col-m-amount text-right",
      render: (g) => <span className="col-nowrap"><span className="tb-ml">{t("Debit")}</span>{fmt(g.debit)}</span>,
    },
    {
      header: t("Credit"),
      className: "col-m-amount text-right",
      render: (g) => <span className="col-nowrap"><span className="tb-ml">{t("Credit")}</span>{fmt(g.credit)}</span>,
    },
    {
      header: t("Net"),
      className: "col-m-amount text-right",
      render: (g) => (
        <span className="col-nowrap" style={{ color: g.net < 0 ? "var(--red)" : undefined }}>
          <span className="tb-ml">{t("Net")}</span>{fmt(g.net)}
        </span>
      ),
    },
  ];

  return (
    <div className="page shadcn-root">
      <style>{CSS}</style>
      <PageBack label={t("Back")} />

      <PageHeader
        title={t("Trial Balance")}
        sub={t("Debit and credit totals per account, based on the journal ledger.")}
        actions={
          <StatusPill tone={balanced ? "green" : "red"} label={balanced ? t("Balanced") : t("Unbalanced")} />
        }
      />

      <div className="filter-bar tb-filters">
        <input
          type="date"
          className="hms-dv-date"
          aria-label={t("From")}
          value={vals.date_from}
          max={vals.date_to || undefined}
          onChange={(e) => setVal("date_from", e.target.value)}
        />
        <span className="tb-dash" aria-hidden="true">–</span>
        <input
          type="date"
          className="hms-dv-date"
          aria-label={t("To")}
          value={vals.date_to}
          min={vals.date_from || undefined}
          onChange={(e) => setVal("date_to", e.target.value)}
        />
        <Button type="button" variant="outline" onClick={() => apply()}>{t("Apply")}</Button>
      </div>

      <div className="hms-kpi-row">
        <KpiCard label={t("Total Debit")} value={fmt(total_debit)} unit="SAR" foot={range} />
        <KpiCard label={t("Total Credit")} value={fmt(total_credit)} unit="SAR" foot={accountsLabel(groups.length)} />
        <KpiCard
          label={t("Difference")}
          value={fmt(diff)}
          unit="SAR"
          warn={!balanced}
          foot={balanced ? t("debits equal credits") : t("debits and credits do not match")}
        />
      </div>

      <div className="hms-list-card">
        {groups.length ? (
          <Table
            columns={columns}
            rows={groups}
            rowKey={(g) => g.account}
            section={sectionOf}
            footer={
              <TableRow>
                <TableCell className="col-bold">{t("Total")}</TableCell>
                <TableCell className="col-bold text-right col-nowrap">{fmt(total_debit)}</TableCell>
                <TableCell className="col-bold text-right col-nowrap">{fmt(total_credit)}</TableCell>
                <TableCell className="col-bold text-right col-nowrap" style={{ color: balanced ? undefined : "var(--red)" }}>
                  {fmt(diff)}
                </TableCell>
              </TableRow>
            }
          />
        ) : (
          <EmptyState iconName="invoice" title={t("No journal data")} sub={t("No entries match your filters.")} />
        )}
      </div>
    </div>
  );
}

const CSS = `
.tb-filters { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.tb-filters input[type="date"] { width: auto; flex: none; height: 40px; }
.tb-dash { color: var(--muted-foreground); }
/* The column header names the figure on desktop; the mobile card has no
   headers, so the label rides along with the number there (FundFlow's
   .ff-cur pattern). */
.tb-ml { display: none; }
@media (max-width: 600px) {
  .tb-filters input[type="date"] { flex: 1 1 0; min-width: 0; }
  .tb-ml {
    display: inline;
    margin-right: 6px;
    font-size: 11.5px;
    font-weight: 500;
    color: var(--muted-foreground);
  }
}
`;
