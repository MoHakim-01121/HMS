import { useState } from "react";
import { router } from "@inertiajs/react";
import { DPage, DTop, DHead, DCard, DLines, DLine, DLinesTotal, DA, DC } from "../../components/shadcn/detail-a.jsx";
import { Field, DatePicker, Segmented, Caption, FA } from "../../components/shadcn/form-a.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Checkbox } from "../../components/shadcn/ui/checkbox.jsx";
import { cn } from "@/lib/utils";
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
  const [excluded, setExcluded] = useState([]);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  // preserveState: the unticked expenses and the note survive a change of span.
  const preview = (r) => router.get("/finance/claims/new/", { branch: f.branch, ...r }, { preserveState: true, preserveScroll: true });
  const dates = { date_from: f.date_from, date_to: f.date_to };
  const span = f.span === "all" ? "all"
    : [1, 3, 4].find((n) => { const r = lastMonths(n); return r.date_from === f.date_from && r.date_to === f.date_to; }) ?? "";
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
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <Segmented label={t("Span")} value={span} onChange={(v) => preview(v === "all" ? { span: "all" } : lastMonths(v))}
            options={[[1, t("This month")], [3, t("3 months")], [4, t("4 months")], ["all", t("All time")]]} />
          <Field label={t("From")} className="w-[190px] phone:w-full">
            <DatePicker label={t("From")} value={f.date_from} onChange={(v) => preview({ ...dates, date_from: v })} />
          </Field>
          <Field label={t("To")} className="w-[190px] phone:w-full">
            <DatePicker label={t("To")} value={f.date_to} onChange={(v) => preview({ ...dates, date_to: v })} />
          </Field>
          {branch_choices.length > 1 && (
            <Select value={f.branch || ""} onValueChange={(v) => preview({ ...dates, branch: v })}>
              <SelectTrigger className="w-[180px]"><SelectValue placeholder={t("Branch")} /></SelectTrigger>
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
                title={<span className="flex items-center gap-3"><Checkbox checked={!excluded.includes(e.id)} onCheckedChange={() => toggle(e.id)}
                  aria-label={t("Include {n}", { n: e.expense_number })} />{e.expense_number}</span>}
                sub={[fmtDate(e.expense_date), e.description].filter(Boolean).join(" · ")}
                value={fmt(e.amount)} valueTone={excluded.includes(e.id) ? "text-muted-foreground line-through" : undefined} />
            ))}
            <DLinesTotal label={t("Total")}>{fmt(total)} IDR</DLinesTotal>
          </DLines>
          <div className={DA.scrollWide}>
            <table data-slot="detail-table" className={DA.table}>
              <thead><tr>
                <th className="w-10"><span className="sr-only">{t("Include")}</span></th>
                <th>{t("Expense")}</th><th>{t("Date")}</th><th>{t("Description")}</th><th className={DC.n}>{t("Amount (IDR)")}</th>
              </tr></thead>
              <tbody>
                {expenses.map((e) => (
                  <tr key={e.id} className={excluded.includes(e.id) ? DA.rowVoid : undefined}>
                    <td><Checkbox checked={!excluded.includes(e.id)} onCheckedChange={() => toggle(e.id)}
                      aria-label={t("Include {n}", { n: e.expense_number })} /></td>
                    <td className={DC.mono}>{e.expense_number}</td>
                    <td className={DC.nw}>{fmtDate(e.expense_date)}</td>
                    <td>{e.description}</td>
                    <td className={DC.n}>{fmt(e.amount)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot><tr>
                <td colSpan={4} className="pb-4">{t("Total")}</td>
                <td className={cn(DC.n, "pb-4")}>{fmt(total)} IDR</td>
              </tr></tfoot>
            </table>
          </div>
          </>
        ) : (
          <p className="m-0 px-6 pt-1 pb-5 text-muted-foreground">{t("No paid expenses to claim in this span.")}</p>
        )}
      </DCard>

      <DCard pad>
        <div className="flex flex-col gap-2">
          <Caption optional>{t("Note for head office")}</Caption>
          <textarea className={FA.note} value={note} aria-label={t("Note for head office")} onChange={(e) => setNote(e.target.value)} />
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={() => router.visit("/finance/claims/")}>{t("Cancel")}</Button>
          <Button onClick={save} disabled={!kept.length || saving}>{t("Save draft")}</Button>
        </div>
      </DCard>
    </DPage>
  );
}
