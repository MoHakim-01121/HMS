import { useState } from "react";
import { router } from "@inertiajs/react";
import { DPage, DTop, DHead, DCard, DLines, DLine, DLinesTotal, DA, DC } from "../../components/shadcn/detail-a.jsx";
import { DateRange } from "../../components/shadcn/list-a.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtDate } from "../../utils/format.js";

const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
// The span a branch claims: this month, or this month and the ones before it.
const lastMonths = (n) => {
  const now = new Date();
  return { date_from: iso(new Date(now.getFullYear(), now.getMonth() - (n - 1), 1)), date_to: iso(now) };
};

// New claim: pick the span, check the paid expenses it picked up (untick any
// that should wait), and save it as a draft to submit from its page.
export default function ClaimForm({ expenses = [], filters: f = {}, branch_choices = [] }) {
  const { t } = useI18n();
  const [range, setRange] = useState({ date_from: f.date_from, date_to: f.date_to });
  const [excluded, setExcluded] = useState([]);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const preview = (r) => router.get("/finance/claims/new/", { ...r, branch: f.branch }, { preserveState: false });
  const kept = expenses.filter((e) => !excluded.includes(e.id));
  const total = kept.reduce((s, e) => s + e.amount, 0);
  const toggle = (id) => setExcluded((x) => (x.includes(id) ? x.filter((y) => y !== id) : [...x, id]));
  const save = () => {
    setSaving(true);
    // preserveState: a refused save redirects back here (same range), and the
    // unticked expenses and the note must survive it.
    router.post("/finance/claims/new/", { date_from: f.date_from, date_to: f.date_to, branch: f.branch, exclude: excluded, note }, { preserveState: true, onFinish: () => setSaving(false) });
  };

  return (
    <DPage>
      <DTop href="/finance/claims/" />
      <DHead title={t("New claim")} cols={3} facts={[
        { k: t("Expenses dated"), v: `${fmtDate(f.date_from)} – ${fmtDate(f.date_to)}` },
        { k: t("Expenses"), v: String(kept.length) },
        { k: t("To claim"), v: `${fmt(total)} IDR`, strong: true },
      ]} />

      <DCard title={t("Span")} pad>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          {[[1, t("This month")], [3, t("3 months")], [4, t("4 months")]].map(([n, label]) => (
            <Button key={n} type="button" variant="outline" onClick={() => preview(lastMonths(n))}>{label}</Button>
          ))}
          <DateRange from={range.date_from} to={range.date_to}
            onFrom={(v) => setRange({ ...range, date_from: v })} onTo={(v) => setRange({ ...range, date_to: v })} />
          <Button type="button" variant="outline" onClick={() => preview(range)}>{t("Show")}</Button>
          {branch_choices.length > 1 && (
            <Select value={f.branch || ""} onValueChange={(v) => router.get("/finance/claims/new/", { ...range, branch: v })}>
              <SelectTrigger style={{ width: 180 }}><SelectValue placeholder={t("Branch")} /></SelectTrigger>
              <SelectContent>{branch_choices.map((b) => <SelectItem key={b.value} value={b.value}>{b.label}</SelectItem>)}</SelectContent>
            </Select>
          )}
        </div>
      </DCard>

      <DCard title={t("Paid expenses not claimed yet")} count={expenses.length}>
        {expenses.length ? (
          <>
          <DLines>
            {expenses.map((e) => (
              <DLine key={e.id} mono
                title={<label className="flex items-center gap-3"><input type="checkbox" className="size-4 accent-foreground" checked={!excluded.includes(e.id)} onChange={() => toggle(e.id)}
                  aria-label={t("Include {n}", { n: e.expense_number })} />{e.expense_number}</label>}
                sub={[fmtDate(e.expense_date), e.description].filter(Boolean).join(" · ")}
                value={fmt(e.amount)} valueTone={excluded.includes(e.id) ? "text-muted-foreground line-through" : undefined} />
            ))}
            <DLinesTotal label={t("Total")}>{fmt(total)} IDR</DLinesTotal>
          </DLines>
          <div className={DA.scrollWide}>
            <table data-slot="detail-table" className={DA.table}>
              <thead><tr>
                <th style={{ width: 40 }}><span className="sr-only">{t("Include")}</span></th>
                <th>{t("Expense")}</th><th>{t("Date")}</th><th>{t("Description")}</th><th className={DC.n}>{t("Amount (IDR)")}</th>
              </tr></thead>
              <tbody>
                {expenses.map((e) => (
                  <tr key={e.id} className={excluded.includes(e.id) ? DA.rowVoid : undefined}>
                    <td><input type="checkbox" className="accent-foreground" checked={!excluded.includes(e.id)} onChange={() => toggle(e.id)}
                      aria-label={t("Include {n}", { n: e.expense_number })} /></td>
                    <td className={DC.mono}>{e.expense_number}</td>
                    <td className={DC.nw}>{fmtDate(e.expense_date)}</td>
                    <td>{e.description}</td>
                    <td className={DC.n}>{fmt(e.amount)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot><tr>
                <td colSpan={4} style={{ paddingBottom: 16 }}>{t("Total")}</td>
                <td className={DC.n} style={{ paddingBottom: 16 }}>{fmt(total)} IDR</td>
              </tr></tfoot>
            </table>
          </div>
          </>
        ) : (
          <p className="mut" style={{ padding: "4px 24px 20px", margin: 0 }}>{t("No paid expenses to claim in this span.")}</p>
        )}
      </DCard>

      <DCard title={t("Note for head office")} pad>
        <Textarea rows={2} value={note} aria-label={t("Note for head office")} onChange={(e) => setNote(e.target.value)} />
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
          <Button variant="outline" onClick={() => router.visit("/finance/claims/")}>{t("Cancel")}</Button>
          <Button onClick={save} disabled={!kept.length || saving || range.date_from !== f.date_from || range.date_to !== f.date_to}>{t("Save draft")}</Button>
        </div>
      </DCard>
    </DPage>
  );
}
