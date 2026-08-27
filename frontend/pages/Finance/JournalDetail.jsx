import PageBack from "../../components/shadcn/page-back.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import {
  Table as ShadcnTable, TableBody, TableCell, TableHead, TableHeader, TableRow, TableFooter,
} from "../../components/shadcn/ui/table.jsx";
import { useI18n } from "../../utils/i18n.jsx";

export default function JournalDetail({ entry = {}, created_by = "", reverses_number = null, lines = [] }) {
  const { t } = useI18n();
  const totalDebit = lines.reduce((s, l) => s + (l.amount_sar > 0 ? l.amount_sar : 0), 0);

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} fallbackHref="/finance/journal/" />

      <div className="page-header">
        <div>
          <div className="page-title">
            {entry.entry_number}
            {entry.is_reversal && <span style={{ marginLeft: 10 }}><StatusPill tone="red" label={t("Reversal")} /></span>}
          </div>
          <div className="page-sub">{entry.description}</div>
        </div>
      </div>

      {/* Meta */}
      <div className="hms-kpi-row" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
        <KpiCard label={t("Type")} value={t(entry.entry_type_display)} />
        <KpiCard label={t("Date")} value={entry.entry_date} />
        <KpiCard label={t("Created By")} value={created_by || "—"} />
        <div className="card p-4">
          <div className="text-xs text-muted-foreground">{t("Reverses")}</div>
          <div className="font-medium mt-1">
            {reverses_number
              ? <a href={`/finance/journal/?q=${reverses_number}`} className="text-blue-600 hover:underline">{reverses_number}</a>
              : "—"}
          </div>
        </div>
      </div>

      {/* Lines */}
      <div className="card">
        <div className="table-wrap hms-table-v2">
          <ShadcnTable>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>{t("Account")}</TableHead>
                <TableHead>{t("Reference")}</TableHead>
                <TableHead>{t("Note")}</TableHead>
                <TableHead className="text-right">{t("Debit")}</TableHead>
                <TableHead className="text-right">{t("Credit")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((l) => (
                <TableRow key={l.id}>
                  <TableCell className="font-medium whitespace-nowrap">{l.account_display}</TableCell>
                  <TableCell className="text-muted-foreground">{l.dim || "—"}</TableCell>
                  <TableCell className="text-muted-foreground">{l.note || "—"}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {l.amount_sar > 0 ? l.amount_sar.toLocaleString() : ""}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {l.amount_sar < 0 ? Math.abs(l.amount_sar).toLocaleString() : ""}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow>
                <TableCell colSpan={3}>{t("Total")}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{totalDebit.toLocaleString()}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{totalDebit.toLocaleString()}</TableCell>
              </TableRow>
            </TableFooter>
          </ShadcnTable>
        </div>
      </div>
    </div>
  );
}
