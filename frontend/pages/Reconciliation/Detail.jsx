import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { Checkbox } from "../../components/shadcn/ui/checkbox.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";
import { fmt } from "../../utils/format.js";

// One bank statement against the account's cash book, in the account's own
// currency. The system suggests a partner for a line (same amount and
// direction, a few days apart) but a person always does the matching.
export default function Detail({ statement = {} }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canEdit = perms.can("payments", "edit");
  const [picks, setPicks] = useState({});
  const [forceLine, setForceLine] = useState({});
  const cur = statement.currency;

  const txLabel = (c) => `${c.transaction_date} · ${c.reference || `${c.source_type} #${c.source_id}`} · ${c.direction === "in" ? "+" : "−"}${fmt(c.amount)}`;
  const post = (url, data = {}) => router.post(url, data, { preserveScroll: true });
  const doMatch = (line, txId) => {
    if (!txId) return;
    post(`/finance/reconciliation/lines/${line.id}/match/`, { transaction_id: txId, force: forceLine[line.id] ? "1" : "" });
  };

  const columns = [
    { header: t("Date"), render: (l) => <span className="col-nowrap">{l.line_date}</span> },
    {
      header: t("Description"),
      render: (l) => (
        <>
          <div>{l.description || l.reference || "—"}</div>
          {l.description && l.reference ? <div style={{ fontSize: 11.5, color: "var(--muted-foreground)" }}>{l.reference}</div> : null}
        </>
      ),
    },
    {
      header: t("Amount ({cur})", { cur }), align: "right",
      render: (l) => (
        <span className="col-nowrap" style={{ color: l.direction === "in" ? "var(--green)" : "var(--red)" }}>
          {l.direction === "in" ? "+" : "−"}{fmt(l.amount)}
        </span>
      ),
    },
    {
      header: t("Match"),
      render: (l) => {
        if (l.matched_transaction) {
          const m = l.matched_transaction;
          return (
            <div className="rd-match">
              <StatusPill small tone="green" label={t("Matched")} />
              {m.link ? <a href={m.link} className="rd-ref">{m.reference || `${m.source_type} #${m.source_id}`}</a>
                : <span className="rd-ref">{m.reference || `${m.source_type} #${m.source_id}`}</span>}
              {canEdit && (
                <button type="button" className="hms-dv-act" style={{ color: "var(--red)" }} onClick={() => post(`/finance/reconciliation/lines/${l.id}/unmatch/`)}>
                  {t("Unmatch")}
                </button>
              )}
            </div>
          );
        }
        if (!canEdit) return <StatusPill small tone="yellow" label={t("Unmatched")} />;
        if (l.suggested && !picks[l.id]) {
          return (
            <div className="rd-match">
              <StatusPill small tone="blue" label={t("Suggested")} />
              <span className="rd-ref">{txLabel(l.suggested)}</span>
              <Button size="sm" onClick={() => doMatch(l, l.suggested.id)}>{t("Match")}</Button>
              <button type="button" className="hms-dv-act" onClick={() => setPicks({ ...picks, [l.id]: "other" })}>{t("Other…")}</button>
            </div>
          );
        }
        const pick = picks[l.id] === "other" ? "" : picks[l.id] || "";
        return (
          <div className="rd-match">
            <Select value={pick} onValueChange={(v) => v && setPicks({ ...picks, [l.id]: v })}>
              <SelectTrigger className="w-72"><SelectValue placeholder={t("Select transaction...")} /></SelectTrigger>
              <SelectContent>
                {l.candidates.length === 0 ? (
                  <div style={{ padding: "6px 12px", fontSize: 12, color: "var(--muted-foreground)" }}>{t("No candidates")}</div>
                ) : l.candidates.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>{txLabel(c)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <label className="rd-force">
              <Checkbox checked={!!forceLine[l.id]} onCheckedChange={(v) => setForceLine({ ...forceLine, [l.id]: !!v })} />
              {t("Force match")}
            </label>
            <Button size="sm" disabled={!pick} onClick={() => doMatch(l, pick)}>{t("Match")}</Button>
          </div>
        );
      },
    },
  ];

  return (
    <div className="page shadcn-root">
      <style>{CSS}</style>
      <PageBack href="/finance/reconciliation/" label={t("Back")} />

      <PageHeader
        title={statement.account_label}
        sub={[
          t("{start} to {end}", { start: statement.period_start, end: statement.period_end }),
          statement.source_filename ? t("imported from {file}", { file: statement.source_filename }) : null,
        ].filter(Boolean).join(" · ")}
        actions={canEdit && statement.suggested_count > 0 ? (
          <Button size="lg" onClick={() => post(`/finance/reconciliation/${statement.id}/match-suggested/`)}>
            {t("Match {n} suggested", { n: statement.suggested_count })}
          </Button>
        ) : null}
      />

      <div className="hms-kpi-row">
        <KpiCard label={t("Book Balance")} value={fmt(statement.book_balance)} unit={cur} foot={t("cash book on {date}", { date: statement.period_end })} />
        <KpiCard label={t("Statement Closing")} value={fmt(statement.closing_balance)} unit={cur} />
        <KpiCard label={t("Difference")} value={fmt(statement.difference)} unit={cur} tone={statement.difference !== 0 ? "yellow" : "green"}
          foot={statement.difference !== 0 ? t("bank vs books — find the missing entry") : t("bank and books agree")} />
        <KpiCard label={t("Matched Lines")} value={`${statement.lines_matched}/${statement.lines_total}`} />
      </div>

      {statement.statement_gap !== 0 ? (
        <div className="alert alert-warning rd-gap" role="status">
          {t("Opening balance plus the lines doesn't reach the closing balance ({gap} {cur} apart). A line is missing or a balance was mistyped.", { gap: fmt(statement.statement_gap), cur })}
        </div>
      ) : null}
      {statement.note ? <p className="rd-note">{statement.note}</p> : null}

      <div className="hms-list-card">
        <DetailTable columns={columns} rows={statement.lines || []} rowKey={(l) => l.id} />
      </div>
    </div>
  );
}

const CSS = `
.rd-match { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.rd-ref { font-size: 12px; color: var(--muted-foreground); }
.rd-force { display: flex; align-items: center; gap: 4px; font-size: 11px; }
.rd-gap { margin: 0 0 14px; }
.rd-note { margin: 0 0 14px; font-size: 12.5px; color: var(--muted-foreground); white-space: pre-line; }
`;
