import { useState } from "react";
import { cn } from "@/lib/utils";
import { router } from "@inertiajs/react";
import { DPage, DTop, DHead, DBanner, DBtn, DCard, DPill, DLines, DLine, DA, DC, dBtnClass } from "../../components/shadcn/detail-a.jsx";
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
// Ticking lines joins them into one match with one or more cash-book rows:
// a transfer that paid two invoices, or salaries and their fees as one row.
export default function Detail({ statement = {} }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canEdit = perms.can("bank", "edit");
  const [picks, setPicks] = useState({});
  const [forceLine, setForceLine] = useState({});
  const [sel, setSel] = useState([]);
  const [selTx, setSelTx] = useState([]);
  const [groupForce, setGroupForce] = useState(false);
  const cur = statement.currency;
  const lines = statement.lines || [];

  const txLabel = (c) => `${c.transaction_date} · ${c.reference || `${c.source_type} #${c.source_id}`} · ${c.direction === "in" ? "+" : "−"}${fmt(c.amount)}`;
  const post = (url, data = {}, opts = {}) => router.post(url, data, { preserveScroll: true, ...opts });
  const doMatch = (line, txId) => {
    if (!txId) return;
    post(`/finance/reconciliation/lines/${line.id}/match/`, { transaction_id: txId, force: forceLine[line.id] ? "1" : "" });
  };

  const signed = (x) => (x.direction === "in" ? x.amount : -x.amount);
  const toggle = (list, set, id) => set(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  const picked = lines.filter((l) => sel.includes(l.id));
  const pool = [];
  for (const l of picked) for (const c of l.candidates) if (!pool.some((p) => p.id === c.id)) pool.push(c);
  pool.sort((a, b) => a.transaction_date.localeCompare(b.transaction_date) || a.id - b.id);
  const pickedTx = pool.filter((c) => selTx.includes(c.id));
  const bankTotal = picked.reduce((n, l) => n + signed(l), 0);
  const bookTotal = pickedTx.reduce((n, c) => n + signed(c), 0);
  const signedFmt = (n) => `${n < 0 ? "−" : "+"}${fmt(Math.abs(n))}`;
  const matchGroup = () => post(`/finance/reconciliation/${statement.id}/match-group/`, {
    line_ids: sel, transaction_ids: pickedTx.map((c) => c.id), force: groupForce ? "1" : "",
  }, { onSuccess: () => { setSel([]); setSelTx([]); setGroupForce(false); } });

  const agrees = statement.difference === 0;
  const allMatched = statement.lines_total > 0 && statement.lines_matched === statement.lines_total;

  const matchCell = (l) => {
    if (l.match) {
      const others = l.match.other_lines.length;
      return (
        <span className="flex flex-wrap items-center gap-2">
          <DPill sm tone="green">{t("Matched")}</DPill>
          {l.match.transactions.map((m) => {
            const ref = m.reference || `${m.source_type} #${m.source_id}`;
            return m.link ? <a key={m.id} href={m.link}>{ref}</a> : <span key={m.id} className="text-[12px] text-muted-foreground">{ref}</span>;
          })}
          {others ? <span className="text-[12px] text-muted-foreground">{t("with {n} other lines", { n: others })}</span> : null}
          {canEdit ? <button type="button" className="cursor-pointer border-0 bg-transparent p-0 font-sans text-[13px] leading-[normal] font-semibold text-danger-text" onClick={() => post(`/finance/reconciliation/lines/${l.id}/unmatch/`)}>{t("Unmatch")}</button> : null}
        </span>
      );
    }
    if (!canEdit) return <DPill sm tone="amber">{t("Unmatched")}</DPill>;
    const tick = (
      <label className="flex items-center gap-1 text-[12px] font-medium text-muted-foreground">
        <Checkbox checked={sel.includes(l.id)} onCheckedChange={() => toggle(sel, setSel, l.id)} />
        {t("Group")}
      </label>
    );
    if (sel.length) return tick;
    if (l.suggested && !picks[l.id]) {
      return (
        <span className="flex flex-wrap items-center gap-2">
          <DPill sm tone="info">{t("Suggested")}</DPill>
          <span className="text-[12px] text-muted-foreground">{txLabel(l.suggested)}</span>
          <button type="button" className={cn(dBtnClass({ primary: true }), "h-[30px]")} onClick={() => doMatch(l, l.suggested.id)}>{t("Match")}</button>
          <button type="button" className="cursor-pointer border-0 bg-transparent p-0 font-sans text-[13px] leading-[normal] font-semibold text-muted-foreground hover:text-foreground" onClick={() => setPicks({ ...picks, [l.id]: "other" })}>{t("Other…")}</button>
          {tick}
        </span>
      );
    }
    const pick = picks[l.id] === "other" ? "" : picks[l.id] || "";
    return (
      <span className="flex flex-wrap items-center gap-2">
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
        <label className="flex items-center gap-1 text-[12px] font-medium text-muted-foreground">
          <Checkbox checked={!!forceLine[l.id]} onCheckedChange={(v) => setForceLine({ ...forceLine, [l.id]: !!v })} />
          {t("Force match")}
        </label>
        <button type="button" className={cn(dBtnClass({ primary: true }), "h-[30px]")} disabled={!pick} onClick={() => doMatch(l, pick)}>{t("Match")}</button>
        {tick}
      </span>
    );
  };

  return (
    <DPage>
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

      {sel.length ? (
        <DCard title={t("Match as one group")}
          meta={t("Bank {bank} · books {book} · difference {diff} {cur}", { bank: signedFmt(bankTotal), book: signedFmt(bookTotal), diff: fmt(bankTotal - bookTotal), cur })}
          actions={<>
            <DBtn onClick={() => { setSel([]); setSelTx([]); setGroupForce(false); }}>{t("Cancel")}</DBtn>
            <DBtn primary disabled={!pickedTx.length || (bankTotal !== bookTotal && !groupForce)} onClick={matchGroup}>{t("Match group")}</DBtn>
          </>}>
          <div className={DA.scrollWide}>
            <table data-slot="detail-table" className={DA.table}>
              <thead><tr><th className="w-8" /><th className={DC.date}>{t("Date")}</th><th>{t("Cash book")}</th><th className={DC.n}>{t("Amount ({cur})", { cur })}</th></tr></thead>
              <tbody>
                {pool.length === 0 ? (
                  <tr><td colSpan={4} className="text-muted-foreground">{t("No candidates")}</td></tr>
                ) : pool.map((c) => (
                  <tr key={c.id}>
                    <td><Checkbox checked={selTx.includes(c.id)} onCheckedChange={() => toggle(selTx, setSelTx, c.id)} aria-label={txLabel(c)} /></td>
                    <td className={DC.date}>{fmtDate(c.transaction_date)}</td>
                    <td>{c.link ? <a href={c.link}>{c.reference || `${c.source_type} #${c.source_id}`}</a> : (c.reference || `${c.source_type} #${c.source_id}`)}</td>
                    <td className={DC.n}>{signedFmt(signed(c))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {bankTotal !== bookTotal ? (
            <label className="mt-3 flex items-center gap-1 text-[12px] font-medium text-muted-foreground">
              <Checkbox checked={groupForce} onCheckedChange={(v) => setGroupForce(!!v)} />
              {t("Force match")}
            </label>
          ) : null}
        </DCard>
      ) : null}

      <DCard title={t("Statement lines")} count={lines.length || null} meta={agrees ? t("Bank and books agree") : t("Bank vs books: find the missing entry")}>
        {lines.length ? (
          <>
          <DLines>
            {lines.map((l) => (
              <DLine key={l.id} title={l.description || l.reference || ""}
                sub={[fmtDate(l.line_date), l.description ? l.reference : null].filter(Boolean).join(" · ")}
                value={`${l.direction === "in" ? "+" : "−"}${fmt(l.amount)}`} valueTone={l.direction === "in" ? "text-success-text" : undefined}>
                {matchCell(l)}
              </DLine>
            ))}
          </DLines>
          <div className={DA.scrollWide}>
            <table data-slot="detail-table" className={DA.table}>
              <thead><tr><th className={DC.date}>{t("Date")}</th><th>{t("Description")}</th><th className={DC.n}>{t("Amount ({cur})", { cur })}</th><th>{t("Match")}</th></tr></thead>
              <tbody>
                {lines.map((l) => (
                  <tr key={l.id}>
                    <td className={DC.date}>{fmtDate(l.line_date)}</td>
                    <td>{l.description || l.reference || ""}{l.description && l.reference ? <span className={DC.sub}>{l.reference}</span> : null}</td>
                    <td className={DC.n} style={{ color: l.direction === "in" ? "var(--success-text)" : undefined }}>{l.direction === "in" ? "+" : "−"}{fmt(l.amount)}</td>
                    <td>{matchCell(l)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </>
        ) : <div className={DA.empty}>{t("This statement has no lines.")}</div>}
      </DCard>
    </DPage>
  );
}
