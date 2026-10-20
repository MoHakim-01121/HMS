import { useState } from "react";
import { router } from "@inertiajs/react";
import { DPage, DTop, DHead, DBanner, DBtn, DCard, DPill } from "../../components/shadcn/detail-a.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { Checkbox } from "../../components/shadcn/ui/checkbox.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";
import { fmt, fmtDate } from "../../utils/format.js";

// One bank statement against the account's cash book, in the account's own
// currency, in the detail-page language of the Record View HMS canvas (no
// artboard of its own). The system suggests a partner for a line (same amount
// and direction, a few days apart) but a person always does the matching.
export default function Detail({ statement = {} }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canEdit = perms.can("bank", "edit");
  const [picks, setPicks] = useState({});
  const [forceLine, setForceLine] = useState({});
  const cur = statement.currency;
  const lines = statement.lines || [];

  const txLabel = (c) => `${c.transaction_date} · ${c.reference || `${c.source_type} #${c.source_id}`} · ${c.direction === "in" ? "+" : "−"}${fmt(c.amount)}`;
  const post = (url, data = {}) => router.post(url, data, { preserveScroll: true });
  const doMatch = (line, txId) => {
    if (!txId) return;
    post(`/finance/reconciliation/lines/${line.id}/match/`, { transaction_id: txId, force: forceLine[line.id] ? "1" : "" });
  };

  const agrees = statement.difference === 0;
  const allMatched = statement.lines_total > 0 && statement.lines_matched === statement.lines_total;

  const matchCell = (l) => {
    if (l.matched_transaction) {
      const m = l.matched_transaction;
      const ref = m.reference || `${m.source_type} #${m.source_id}`;
      return (
        <span className="rd-match">
          <DPill sm tone="green">{t("Matched")}</DPill>
          {m.link ? <a href={m.link}>{ref}</a> : <span className="rd-ref">{ref}</span>}
          {canEdit ? <button type="button" className="rd-lnk danger" onClick={() => post(`/finance/reconciliation/lines/${l.id}/unmatch/`)}>{t("Unmatch")}</button> : null}
        </span>
      );
    }
    if (!canEdit) return <DPill sm tone="amber">{t("Unmatched")}</DPill>;
    if (l.suggested && !picks[l.id]) {
      return (
        <span className="rd-match">
          <DPill sm tone="info">{t("Suggested")}</DPill>
          <span className="rd-ref">{txLabel(l.suggested)}</span>
          <button type="button" className="da-btn primary" style={{ height: 30 }} onClick={() => doMatch(l, l.suggested.id)}>{t("Match")}</button>
          <button type="button" className="rd-lnk" onClick={() => setPicks({ ...picks, [l.id]: "other" })}>{t("Other…")}</button>
        </span>
      );
    }
    const pick = picks[l.id] === "other" ? "" : picks[l.id] || "";
    return (
      <span className="rd-match">
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
        <button type="button" className="da-btn primary" style={{ height: 30 }} disabled={!pick} onClick={() => doMatch(l, pick)}>{t("Match")}</button>
      </span>
    );
  };

  return (
    <DPage>
      <style>{CSS}</style>
      <DTop href="/finance/reconciliation/" />

      {statement.statement_gap !== 0 ? (
        <DBanner tone="danger">
          {t("Opening balance plus the lines doesn't reach the closing balance ({gap} {cur} apart). A line is missing or a balance was mistyped.", { gap: fmt(statement.statement_gap), cur })}
        </DBanner>
      ) : canEdit && statement.suggested_count > 0 ? (
        <DBanner actions={<DBtn primary onClick={() => post(`/finance/reconciliation/${statement.id}/match-suggested/`)}>{t("Match {n} suggested", { n: statement.suggested_count })}</DBtn>}>
          <b>{statement.suggested_count}</b> {t("lines have a suggested partner in the cash book.")}
        </DBanner>
      ) : null}

      <DHead
        title={statement.account_label}
        badge={agrees && allMatched ? { label: t("Reconciled"), tone: "green" } : agrees ? { label: t("Balanced"), tone: "green" } : { label: t("Difference"), tone: "amber" }}
        facts={[
          { k: t("Period"), v: t("{start} to {end}", { start: fmtDate(statement.period_start), end: fmtDate(statement.period_end) }) },
          { k: t("Book balance"), v: `${fmt(statement.book_balance)} ${cur}` },
          { k: t("Statement closing"), v: `${fmt(statement.closing_balance)} ${cur}` },
          { k: t("Difference"), v: `${fmt(statement.difference)} ${cur}`, strong: true, tone: agrees ? "success" : "warning" },
          { k: t("Matched lines"), v: `${statement.lines_matched}/${statement.lines_total}` },
          statement.source_filename && { k: t("Imported from"), v: statement.source_filename },
        ]}
        note={statement.note ? { text: statement.note } : null}
      />

      <DCard title={t("Statement lines")} count={lines.length || null} meta={agrees ? t("Bank and books agree") : t("Bank vs books: find the missing entry")}>
        {lines.length ? (
          <div className="da-scroll">
            <table className="da-t">
              <thead><tr><th className="d">{t("Date")}</th><th>{t("Description")}</th><th className="n">{t("Amount ({cur})", { cur })}</th><th>{t("Match")}</th></tr></thead>
              <tbody>
                {lines.map((l) => (
                  <tr key={l.id}>
                    <td className="d">{fmtDate(l.line_date)}</td>
                    <td>{l.description || l.reference || ""}{l.description && l.reference ? <span className="sub">{l.reference}</span> : null}</td>
                    <td className="n" style={{ color: l.direction === "in" ? "var(--success-text)" : undefined }}>{l.direction === "in" ? "+" : "−"}{fmt(l.amount)}</td>
                    <td>{matchCell(l)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div className="da-empty">{t("This statement has no lines.")}</div>}
      </DCard>
    </DPage>
  );
}

const CSS = `
.rd-match { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.rd-ref { font-size: 12px; color: var(--muted-foreground); }
.rd-force { display: flex; align-items: center; gap: 4px; font-size: 11.5px; color: var(--muted-foreground); }
.rd-lnk { padding: 0; border: 0; background: none; font: 600 12.5px var(--font-sans); color: var(--muted-foreground); cursor: pointer; }
.rd-lnk:hover { color: var(--foreground); }
.rd-lnk.danger { color: var(--danger-text); }
`;
