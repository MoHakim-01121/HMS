import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import {
  Table as ShadcnTable, TableBody, TableCell, TableHead, TableHeader, TableRow, TableFooter,
} from "../../components/shadcn/ui/table.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmtDate } from "../../utils/format.js";

export default function JournalDetail({ entry = {}, created_by = "", reverses_number = null, lines = [] }) {
  const { t } = useI18n();
  const totalDebit = lines.reduce((s, l) => s + (l.amount_sar > 0 ? l.amount_sar : 0), 0);

  return (
    <div className="page shadcn-root">
      <PageBack href="/finance/journal/" label={t("Back")} />

      <PageHeader
        title={
          <>
            {entry.entry_number}
            {entry.is_reversal && <span style={{ marginLeft: 10 }}><StatusPill tone="red" label={t("Reversal")} /></span>}
          </>
        }
        sub={entry.description}
      />

      {/* Meta */}
      <div className="hms-kpi-row" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
        <KpiCard label={t("Type")} value={t(entry.entry_type_display)} />
        <KpiCard label={t("Date")} value={fmtDate(entry.entry_date) || "—"} />
        <KpiCard label={t("Created By")} value={created_by || "—"} />
        <KpiCard
          label={t("Reverses")}
          value={reverses_number
            ? <a href={`/finance/journal/?q=${reverses_number}`} className="hms-dv-link">{reverses_number}</a>
            : "—"}
        />
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
                    {l.amount_sar > 0 ? l.amount_sar.toLocaleString("en-US") : ""}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {l.amount_sar < 0 ? Math.abs(l.amount_sar).toLocaleString("en-US") : ""}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow>
                <TableCell colSpan={3}>{t("Total")}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{totalDebit.toLocaleString("en-US")}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{totalDebit.toLocaleString("en-US")}</TableCell>
              </TableRow>
            </TableFooter>
          </ShadcnTable>
        </div>
      </div>
    </div>
  );
}
