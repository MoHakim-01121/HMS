import PageBack from "../../components/shadcn/page-back.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import useFilterState from "../../hooks/useFilterState.js";
import {
  Table as ShadcnTable, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "../../components/shadcn/ui/table.jsx";
import { useI18n } from "../../utils/i18n.jsx";

export default function TrialBalance({
  groups = [], total_debit = 0, total_credit = 0, balanced = true, filters = {},
}) {
  const { t } = useI18n();
  const { vals, setVal, apply } = useFilterState(
    { date_from: "", date_to: "", ...filters },
    "/finance/trial-balance/",
  );

  // Group rows by account type with section headers
  const sections = [];
  let currentType = null;
  for (const g of groups) {
    if (g.type !== currentType) {
      currentType = g.type;
      sections.push({ kind: "header", label: g.type_display, key: `h-${g.type}` });
    }
    sections.push({ kind: "row", ...g, key: g.account });
  }

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />

      <div className="page-header">
        <div>
          <div className="page-title">{t("Trial Balance")}</div>
          <div className="page-sub">{t("Debit and credit totals per account, based on the journal ledger.")}</div>
        </div>
        <div className="page-actions">
          <StatusPill tone={balanced ? "green" : "red"} label={balanced ? t("Balanced") : t("Unbalanced")} />
        </div>
      </div>

      <div className="filter-bar">
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

      <div className="card">
        {groups.length > 0 ? (
          <div className="table-wrap hms-table-v2">
            <ShadcnTable>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>{t("Account")}</TableHead>
                  <TableHead className="text-right">{t("Debit")}</TableHead>
                  <TableHead className="text-right">{t("Credit")}</TableHead>
                  <TableHead className="text-right">{t("Net")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sections.map((s) => s.kind === "header" ? (
                  <TableRow key={s.key} className="hover:bg-[var(--muted)]">
                    <TableCell colSpan={4} className="text-xs font-semibold uppercase tracking-wide text-muted-foreground py-2">
                      {t(s.label)}
                    </TableCell>
                  </TableRow>
                ) : (
                  <TableRow key={s.key}>
                    <TableCell className="font-medium whitespace-nowrap">{s.account_display}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums">{s.debit.toLocaleString()}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums">{s.credit.toLocaleString()}</TableCell>
                    <TableCell className={`text-right font-mono tabular-nums font-medium ${s.net < 0 ? "text-red-600" : ""}`}>
                      {s.net.toLocaleString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </ShadcnTable>
            <div className="flex items-center justify-between px-4 py-3 border-t border-[var(--border)] text-sm font-semibold">
              <span>{t("Total")}</span>
              <span className="flex gap-6 font-mono tabular-nums">
                <span>{total_debit.toLocaleString()}</span>
                <span>{total_credit.toLocaleString()}</span>
                <span>{(total_debit - total_credit).toLocaleString()}</span>
              </span>
            </div>
          </div>
        ) : (
          <EmptyState title="No journal data" sub="No entries match your filters." />
        )}
      </div>
    </div>
  );
}
