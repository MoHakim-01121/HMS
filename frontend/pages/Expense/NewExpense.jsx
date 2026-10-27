import { useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { Popover, PopoverContent, PopoverTrigger } from "../../components/shadcn/ui/popover.jsx";
import {
  FaDialog, Field, Picker, CellPicker, DatePicker, TextIn, NoteField, Foot, fileSize, groupDigits, digitsOf, todayIso, FA, Caption,
} from "../../components/shadcn/form-a.jsx";
import { cn } from "@/lib/utils";
import { showToast } from "../../components/shadcn/toast.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

// New Expense, the "Expense Form" artboard on the Record View HMS canvas: who
// spent it and with what (their advance, or the office pays after approval),
// one row per cost with its own receipt (or a reason there is none), and,
// when paid from an advance, what the advance holds after it. Each photo
// dropped on "Upload receipts" becomes a line.

const MAX = 3 * 1024 * 1024;
const blank = () => ({ category: "", description: "", amount: "", files: [], noReceipt: false, reason: "" });

const I = {
  clip: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M15.17 7l-6.59 6.59a2 2 0 102.83 2.82l6.41-6.58a4 4 0 10-5.66-5.66l-6.41 6.59a6 6 0 108.49 8.48L20.5 13" /></svg>,
  ok: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M5 12l5 5 9-10" /></svg>,
  warn: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path strokeLinecap="round" d="M12 8v5m0 3.5v.5" /><circle cx="12" cy="12" r="9" /></svg>,
  trash: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>,
  plus: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path strokeLinecap="round" d="M12 5v14M5 12h14" /></svg>,
  up: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M12 16V4m0 0l-4 4m4-4l4 4M5 20h14" /></svg>,
};

// A cost line: category, description, amount, receipt, remove.
const ROW = "grid min-h-[52px] min-w-[640px] grid-cols-[156px_minmax(0,1fr)_140px_132px_28px] items-center gap-2.5 px-2 text-[14px]";
// A typed cell: a bordered box around a bare input.
const CELL_IN = "box-border flex h-[34px] items-center gap-1.5 rounded-[10px] border-[1.5px] border-input bg-card px-2.5 transition-[border-color] duration-[120ms] ease-[ease] hover:border-[color:color-mix(in_oklch,var(--foreground)_45%,var(--input))] focus-within:border-foreground [&>svg]:flex-none [&>svg]:text-warning-text";
const BARE_IN = "h-full min-w-0 flex-1 rounded-none border-0 bg-transparent p-0 font-sans text-[14px] font-medium text-foreground shadow-none outline-none";
const RCP = "box-border flex h-[34px] w-full cursor-pointer items-center gap-1.5 rounded-[10px] py-0 pr-2 pl-2.5 text-left font-sans text-[13px] leading-[normal] font-medium";
const RCP_TONE = {
  ok: "border-[1.5px] border-input bg-card text-foreground [&>svg]:flex-none [&>svg]:text-success-text",
  nr: "border-[1.5px] border-[color:color-mix(in_oklch,var(--warning)_45%,var(--input))] bg-warning-tint text-warning-text",
  miss: "border-[1.5px] border-dashed border-input bg-transparent text-muted-foreground hover:border-foreground hover:text-foreground",
};
const FN = "min-w-0 flex-1 truncate";
const SET_ROW = "flex min-h-[30px] items-center justify-between text-muted-foreground [&_b]:font-semibold [&_b]:text-foreground";
const SET_RES = "mt-1 border-t border-border pt-1.5 font-medium text-foreground";

// The receipt cell: what is attached, and a menu to add files or say there is none.
function Receipt({ line, onChange }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const add = (files) => {
    const ok = [...files].filter((f) => f.size <= MAX);
    if (ok.length < files.length) showToast(t("File too large. Maximum upload size is 3 MB."), "error");
    if (ok.length) onChange({ files: [...line.files, ...ok], noReceipt: false, reason: "" });
  };
  const has = line.files.length > 0;
  const btn = has
    ? <button type="button" className={cn(RCP, RCP_TONE.ok)} aria-haspopup="dialog">{I.ok}<span className={FN}>{line.files.length === 1 ? line.files[0].name : t("{n} files", { n: line.files.length })}</span></button>
    : line.noReceipt
      ? <button type="button" className={cn(RCP, RCP_TONE.nr)} aria-haspopup="dialog">{I.warn}<span className={FN}>{t("No receipt")}</span></button>
      : <button type="button" className={cn(RCP, RCP_TONE.miss)} aria-haspopup="dialog">{I.clip}<span className={FN}>{t("Attach")}</span></button>;
  return (
    <>
      <input ref={ref} type="file" accept="image/*,.pdf" multiple hidden onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>{btn}</PopoverTrigger>
        <PopoverContent align="end" sideOffset={6} className={cn(FA.popover, "w-[280px]")}>
          {line.files.map((f, i) => (
            <div key={i} className="flex items-center gap-2.5 rounded-[8px] py-1.5 pr-1.5 pl-2.5 text-[13px] hover:bg-secondary">
              <span className={cn(FN, "font-medium")}>{f.name}<br /><small className="text-[12px] text-muted-foreground">{fileSize(f.size)}</small></span>
              <button type="button" className={FA.trash} aria-label={t("Remove file")}
                onClick={() => onChange({ files: line.files.filter((_, j) => j !== i) })}>{I.trash}</button>
            </div>
          ))}
          <button type="button" className={FA.option} onClick={() => { setOpen(false); ref.current?.click(); }}>
            {I.plus}<span className="t">{has ? t("Add another file") : t("Attach receipt")}<small>{t("Photo or PDF, up to 3 MB each")}</small></span>
          </button>
          {!has && !line.noReceipt ? (
            <>
              <div className={FA.popSep} />
              <button type="button" className={FA.option} onClick={() => { setOpen(false); onChange({ noReceipt: true }); }}>
                {I.warn}<span className="t">{t("No receipt for this cost")}<small>{t("Give a reason, the approver will check it")}</small></span>
              </button>
            </>
          ) : null}
          {line.noReceipt && !has ? (
            <>
              <div className={FA.popSep} />
              <button type="button" className={FA.option} onClick={() => { setOpen(false); onChange({ noReceipt: false, reason: "" }); }}>
                <span className="t">{t("There is a receipt after all")}</span>
              </button>
            </>
          ) : null}
        </PopoverContent>
      </Popover>
    </>
  );
}

export default function NewExpense({ onClose, branch_choices = [], category_choices = [], staff_choices = [], vendor_choices = [], me, defaultBranch }) {
  const { t } = useI18n();
  const [branch, setBranch] = useState(defaultBranch || (branch_choices.length === 1 ? branch_choices[0].value : ""));
  const staffHere = staff_choices.filter((s) => !branch || s.branch === branch);
  const mine = staffHere.find((s) => s.value === String(me));
  const [spentBy, setSpentBy] = useState(mine ? mine.value : "");
  const staff = staffHere.find((s) => s.value === spentBy);
  const [payAdv, setPayAdv] = useState(!!(mine && mine.advance && mine.balance > 0));
  const [description, setDescription] = useState("");
  const [vendor, setVendor] = useState("");
  const [date, setDate] = useState(todayIso());
  const [note, setNote] = useState("");
  const [lines, setLines] = useState([blank()]);
  const [busy, setBusy] = useState(false);
  const bulkRef = useRef(null);

  const first = staff ? staff.label.split(" ")[0] : "";
  const canAdv = !!(staff && staff.advance && staff.balance > 0);
  const useAdv = canAdv && payAdv;
  const total = lines.reduce((s, l) => s + (Number(l.amount) || 0), 0);
  const setLine = (i, patch) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)));

  const pickStaff = (o) => {
    setSpentBy(o.value);
    const s = staffHere.find((x) => x.value === o.value);
    setPayAdv(!!(s && s.advance && s.balance > 0));
  };
  const bulk = (files) => {
    const ok = [...files].filter((f) => f.size <= MAX);
    if (ok.length < files.length) showToast(t("File too large. Maximum upload size is 3 MB."), "error");
    // Fill an untouched first row before adding new ones.
    setLines((ls) => {
      const rest = ls.length === 1 && !ls[0].category && !ls[0].amount && !ls[0].files.length ? [] : ls;
      return [...rest, ...ok.map((f) => ({ ...blank(), files: [f] }))];
    });
  };

  const why = !description.trim() ? t("Describe what the expense was for.")
    : !branch ? t("Choose the branch.")
      : !staff ? t("Choose who spent it.")
        : !lines.length ? t("Add at least one line.")
          : lines.some((l) => !l.category) ? t("Every line needs a category.")
            : lines.some((l) => !(Number(l.amount) > 0)) ? t("Every line needs an amount.")
              : lines.some((l) => !l.files.length && !l.noReceipt) ? t("Every line needs its own receipt.")
                : lines.some((l) => l.noReceipt && !l.files.length && !l.reason.trim()) ? t("Give a reason for each cost without a receipt.")
                  : "";

  const submit = (e) => {
    e.preventDefault();
    if (why || busy) return;
    const fd = new FormData();
    fd.append("branch", branch);
    fd.append("expense_date", date);
    fd.append("description", description.trim());
    fd.append("vendor", vendor);
    fd.append("note", note);
    fd.append("spent_by", spentBy);
    fd.append("paid_with", useAdv ? staff.advance : "office");
    fd.append("lines", JSON.stringify(lines.map((l) => ({
      category: l.category, description: l.description, amount: l.amount,
      no_receipt_reason: l.files.length ? "" : l.reason.trim(),
    }))));
    lines.forEach((l, i) => l.files.forEach((f) => fd.append(`receipts_${i}`, f)));
    setBusy(true);
    router.post("/finance/expenses/record/", fd, { onFinish: () => setBusy(false), onSuccess: onClose });
  };

  const catOpts = category_choices.map((c) => ({ value: c.value, label: c.label }));

  return (
    <FaDialog title={t("New Expense")} onClose={onClose}>
      <form method="post" onSubmit={submit} noValidate>
        <div className={FA.fields}>
          <Field label={t("Description")} required className={branch_choices.length > 1 ? undefined : FA.wide}>
            <TextIn value={description} onChange={setDescription} placeholder={t("For example, Sales team visit to Malang")} autoFocus />
          </Field>
          {branch_choices.length > 1 ? (
            <Field label={t("Branch")} required>
              <Picker searchable={false} value={branch} placeholder={t("Choose branch")}
                options={branch_choices.map((b) => ({ value: b.value, label: b.label }))}
                onPick={(o) => { setBranch(o.value); setSpentBy(""); setPayAdv(false); }} />
            </Field>
          ) : null}
          <Field label={t("Spent by")} required>
            <Picker value={spentBy} placeholder={t("Choose staff")} heading={t("Staff")} onPick={pickStaff}
              options={staffHere.map((s) => ({
                value: s.value, label: s.label,
                meta: [s.value === String(me) ? t("you") : null, s.advance ? t("holds {n} IDR", { n: fmt(s.balance) }) : null].filter(Boolean).join(", "),
              }))}
              extra={staff && staff.value === String(me) ? <span className={FA.meta}>{t("You")}</span> : null} />
          </Field>
          <Field label={t("Paid with")} required>
            <Picker searchable={false} value={useAdv ? "adv" : "office"} heading={t("Paid with")}
              placeholder={t("Choose who spent it first")}
              options={staff ? [
                ...(canAdv ? [{ value: "adv", label: t("Advance held by {name}", { name: first }), meta: t("Balance {n} IDR", { n: fmt(staff.balance) }) }] : []),
                { value: "office", label: t("Paid by the office after approval"), meta: t("Reimburses {name}, or pays the vendor", { name: first }) },
              ] : []}
              onPick={(o) => setPayAdv(o.value === "adv")} />
          </Field>
          <Field label={t("Expense date")} required>
            <DatePicker value={date} onChange={setDate} label={t("Choose expense date")} />
          </Field>
          <Field label={t("Vendor")} optional>
            <TextIn value={vendor} onChange={setVendor} placeholder={t("Shop or supplier")} list="exp-vendors" />
            <datalist id="exp-vendors">{vendor_choices.map((v) => <option key={v} value={v} />)}</datalist>
          </Field>
        </div>

        <div className={FA.sectionHead}>
          <Caption>{t("Lines")}</Caption>
          <span className={FA.muted}>{t(lines.length === 1 ? "1 line" : "{n} lines", { n: lines.length })}</span>
        </div>
        <div className={FA.box}>
          <div className={FA.scroll}>
            <div className={cn(ROW, "min-h-[34px] text-[12px] font-medium text-muted-foreground")}><span>{t("Category")}</span><span>{t("Description")}</span><span className="text-right">{t("Amount")}</span><span>{t("Receipt")}</span><span /></div>
            {lines.map((l, i) => (
              <div key={i} className="border-hairline not-first:border-t">
                <div className={ROW}>
                  <CellPicker value={l.category} options={catOpts} placeholder={t("Category")} label={t("Category")}
                    onPick={(o) => setLine(i, { category: o.value })} />
                  <label className={CELL_IN}><input className={BARE_IN} placeholder={t("What was it")} value={l.description} onChange={(e) => setLine(i, { description: e.target.value })} /></label>
                  <label className={CELL_IN}><span className="text-[11px] font-semibold text-muted-foreground">IDR</span><input className={cn(BARE_IN, "text-right font-semibold", FA.num)} inputMode="numeric" value={groupDigits(l.amount)}
                    onChange={(e) => setLine(i, { amount: digitsOf(e.target.value) })} aria-label={t("Amount")} /></label>
                  <Receipt line={l} onChange={(patch) => setLine(i, patch)} />
                  <button type="button" className={FA.trash} aria-label={t("Remove line")} onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))}>{I.trash}</button>
                </div>
                {l.noReceipt && !l.files.length ? (
                  <div className="-mt-1 flex pr-[46px] pb-3 pl-[174px] max-[640px]:px-2">
                    <label className={cn(CELL_IN, "flex-1")}>{I.warn}<input className={BARE_IN} placeholder={t("Why there is no receipt")} value={l.reason} onChange={(e) => setLine(i, { reason: e.target.value })} /></label>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
          {!lines.length ? <div className={FA.noteEmpty}>{t("No lines yet. Add the first cost.")}</div> : null}
          <div className="mt-0.5 flex items-center justify-between border-0 border-t border-dashed border-border">
            <button type="button" className={cn(FA.addRow, "mt-0 w-auto border-t-0")} onClick={() => setLines((ls) => [...ls, blank()])}>{I.plus}{t("Add line")}</button>
            <input ref={bulkRef} type="file" accept="image/*,.pdf" multiple hidden onChange={(e) => { bulk(e.target.files); e.target.value = ""; }} />
            <button type="button" className="mr-1 flex h-8 cursor-pointer items-center gap-2 rounded-[10px] border-[1.5px] border-input bg-card px-3 font-sans text-[13px] leading-[normal] font-medium text-foreground hover:border-foreground" onClick={() => bulkRef.current?.click()}>{I.up}{t("Upload receipts")}<small className="text-[12px] font-normal text-muted-foreground max-[640px]:hidden">{t("each photo becomes a line")}</small></button>
          </div>
          <div className={cn(FA.checkTotal, useAdv && "rounded-none")}><b>{t("Total")}</b><span className={FA.num}><b className="text-[17px]">{fmt(total)}</b><span className={FA.unit}>IDR</span></span></div>
          {useAdv ? (
            <div className="-mx-1.5 rounded-b-[13px] bg-background px-3.5 pt-1 pb-2.5 text-[13px]">
              <div className={SET_ROW}><span>{t("Advance held by {name}", { name: first })}</span><span className={FA.num}><b>{fmt(staff.balance)}</b> IDR</span></div>
              <div className={SET_ROW}><span>{t("This expense")}</span><span className={FA.num}><b>−{fmt(total)}</b> IDR</span></div>
              {total <= staff.balance
                ? <div className={cn(SET_ROW, SET_RES)}><span>{t("Still with {name} after this", { name: first })}</span><span className={FA.num}><b>{fmt(staff.balance - total)}</b> IDR</span></div>
                : <div className={cn(SET_ROW, SET_RES, "[&_b]:text-warning-text")}><span>{t("Over the advance, owed to {name}", { name: first })}</span><span className={FA.num}><b>{fmt(total - staff.balance)}</b> IDR</span></div>}
            </div>
          ) : null}
        </div>

        <NoteField label={t("Note")} value={note} onChange={setNote} placeholder={t("Anything the approver should know")} />

        <Foot why={why} onCancel={onClose} submitLabel={t("Submit for approval")} processing={busy} />
      </form>
    </FaDialog>
  );
}

