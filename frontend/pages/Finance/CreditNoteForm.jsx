import { useForm } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import { FormA, Field, DatePicker, ReadOnly, TextIn, Foot, digitsOf, groupDigits, FA, Caption, btnClass } from "../../components/shadcn/form-a.jsx";
import { cn } from "@/lib/utils";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

const keyOf = (l) => `${l.kind}:${l.id}`;

// New Credit Note, the "Credit Note Form" artboard on the Record View HMS
// canvas: reduce what an invoice bills, per line, never beyond what that line
// still bills, and see the effect on the invoice before issuing. If the
// client already paid more than the invoice will bill afterwards, the excess
// becomes customer deposit. Opened from an invoice, so client and invoice are
// fixed.
function CreditNoteFormBody({ invoice, lines = [], cancel, form: initial = {}, error }) {
  const { t } = useI18n();
  const form = useForm({
    issued_date: initial.issued_date || "",
    reason: initial.reason || "",
    amounts: initial.amounts || {},
  });
  const amountOf = (l) => Number(form.data.amounts[keyOf(l)]) || 0;
  const setAmount = (l, v) => form.setData("amounts", { ...form.data.amounts, [keyOf(l)]: v });

  const total = lines.reduce((s, l) => s + amountOf(l), 0);
  const over = lines.some((l) => amountOf(l) > l.available);
  const owes = Math.max(invoice.remaining, 0);
  const reduces = Math.min(total, owes);
  const toDeposit = Math.max(total - owes, 0);
  const stillOwes = owes - reduces;

  const why = over ? t("A line is credited more than it can be.")
    : !total ? t("Enter the amount to credit on at least one line.")
      : !form.data.reason.trim() ? t("Give the reason; it is printed on the credit note.")
        : "";

  const submit = (e) => {
    e.preventDefault();
    if (why) return;
    form.transform((d) => ({ ...d, amounts: JSON.stringify(d.amounts) }));
    form.post(`/finance/invoices/${invoice.id}/credit-notes/new/`);
  };

  return (
    <FormA title={t("New Credit Note")} onSubmit={submit} error={error ? t(error) : null}>
      <div className={FA.fields}>
        <Field label={t("Client")} required><ReadOnly><span style={{ color: "var(--foreground)", fontWeight: 600 }}>{invoice.client}</span></ReadOnly></Field>
        <Field label={t("Invoice")} required><ReadOnly><span style={{ color: "var(--foreground)", fontWeight: 600 }}>{invoice.number}</span></ReadOnly></Field>
        <Field label={t("Issue date")} required>
          <DatePicker value={form.data.issued_date} onChange={(v) => form.setData("issued_date", v)} label={t("Choose issue date")} />
        </Field>
        <Field label={t("Reason")} required>
          <TextIn value={form.data.reason} onChange={(v) => form.setData("reason", v)} placeholder={t("For example, booking cancelled, rate corrected")} />
        </Field>
      </div>

      <div className={FA.sectionHead}>
        <Caption>{t("Lines to credit")}</Caption>
        <span className={FA.muted}>{t("Amounts in SAR")}</span>
      </div>
      <div className={FA.box}>
        <div className={FA.scroll}>
          <div data-row className={cn(ROW, "min-h-[34px] text-[12px] font-medium text-muted-foreground")}><span>{t("Line")}</span><span className="text-right">{t("Billed")}</span><span className="text-right">{t("Can credit")}</span><span className="text-right">{t("Credit")}</span><span /></div>
          {lines.map((l) => {
            const bad = amountOf(l) > l.available;
            return (
              <div data-row className={ROW} key={keyOf(l)}>
                <span className="min-w-0 truncate font-medium">{l.label}</span>
                <span className="text-right tabular-nums">{fmt(l.billed)}</span>
                <span className={cn("text-right tabular-nums", FA.muted)}>{l.available > 0 ? fmt(l.available) : "—"}</span>
                <label className={cn(FA.price, bad && "border-danger hover:border-danger focus-within:border-danger")}>
                  <input className={FA.priceInput} inputMode="numeric" disabled={l.available <= 0} value={groupDigits(form.data.amounts[keyOf(l)])}
                    aria-label={t("Credit for {line}", { line: l.label })} aria-invalid={bad ? "true" : undefined}
                    onChange={(e) => setAmount(l, digitsOf(e.target.value))} />
                  <span className={FA.unit}>SAR</span>
                </label>
                <button type="button" className={cn(btnClass("o", true), "disabled:cursor-not-allowed disabled:opacity-45")} disabled={l.available <= 0} onClick={() => setAmount(l, String(l.available))}>{t("Full")}</button>
              </div>
            );
          })}
          {!lines.length ? <div className={FA.checkNote}>{t("Nothing on this invoice can be credited.")}</div> : null}
        </div>
        <div className={FA.checkTotal}><b>{t("Total credit")}</b><span className={FA.num}><b className="text-[17px]">{fmt(total)}</b><span className={FA.unit}>SAR</span></span></div>
      </div>

      <div className={FA.sectionHead}><Caption>{t("Effect on {number}", { number: invoice.number })}</Caption></div>
      <div className="rounded-[14px] border border-border px-3.5 py-1.5 text-[13px]">
        <div className={LINE}><span>{t("Invoice total")}</span><span className={FA.num}>{fmt(invoice.total)} SAR</span></div>
        {invoice.credited ? <div className={LINE}><span>{t("Earlier credit notes")}</span><span className={FA.num}>−{fmt(invoice.credited)} SAR</span></div> : null}
        <div className={LINE}><span>{t("Paid so far")}</span><span className={FA.num}>−{fmt(invoice.paid)} SAR</span></div>
        <div className={LINE}><span>{t("This credit note")}</span><span className={FA.num}>−{fmt(total)} SAR</span></div>
        <div className={cn(LINE, "mt-1 border-t border-border pt-1.5 font-medium text-foreground [&_b]:text-[16px] [&_b]:font-bold")}><span>{t("Client still owes")}</span><span className={FA.num}><b>{fmt(stillOwes)}</b> SAR</span></div>
        {total > 0 ? (
          <div className="-mx-3.5 mt-1.5 -mb-1.5 rounded-b-[13px] bg-background px-3.5 py-1.5">
            <div className={LINE}><span>{t("Reduces what the client owes")}</span><span className={FA.num}>{fmt(reduces)} SAR</span></div>
            <div className={cn(LINE, toDeposit && "font-medium text-warning-text")}><span>{t("Already paid, goes to customer deposit")}</span><span className={FA.num}>{fmt(toDeposit)} SAR</span></div>
          </div>
        ) : null}
      </div>

      <Foot why={why} cancelHref={cancel} submitLabel={t("Issue credit note")} processing={form.processing} />
    </FormA>
  );
}

// A credit line: label, billed, still creditable, the amount, "Full".
const ROW = "grid min-h-[52px] min-w-[580px] grid-cols-[minmax(0,1fr)_100px_100px_140px_64px] items-center gap-2.5 px-2 text-[14px] [[data-row]+&]:border-t [[data-row]+&]:border-hairline";
// A line of the effect summary under the table.
const LINE = "flex min-h-[30px] items-center justify-between text-muted-foreground";

export default withStandaloneModal(CreditNoteFormBody, (props) => props.cancel);
