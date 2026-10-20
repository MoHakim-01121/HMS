import { useForm } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import { FormA, Field, DatePicker, ReadOnly, TextIn, Foot, digitsOf, groupDigits } from "../../components/shadcn/form-a.jsx";
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
      <div className="fa-fields">
        <Field label={t("Client")} required><ReadOnly><span style={{ color: "var(--foreground)", fontWeight: 600 }}>{invoice.client}</span></ReadOnly></Field>
        <Field label={t("Invoice")} required><ReadOnly><span style={{ color: "var(--foreground)", fontWeight: 600 }}>{invoice.number}</span></ReadOnly></Field>
        <Field label={t("Issue date")} required>
          <DatePicker value={form.data.issued_date} onChange={(v) => form.setData("issued_date", v)} label={t("Choose issue date")} />
        </Field>
        <Field label={t("Reason")} required>
          <TextIn value={form.data.reason} onChange={(v) => form.setData("reason", v)} placeholder={t("For example, booking cancelled, rate corrected")} />
        </Field>
      </div>

      <div className="fa-rh">
        <span className="fa-cap">{t("Lines to credit")}</span>
        <span className="fa-mut">{t("Amounts in SAR")}</span>
      </div>
      <div className="fa-box">
        <div className="fa-scroll">
          <div className="cn-row h"><span>{t("Line")}</span><span className="r">{t("Billed")}</span><span className="r">{t("Can credit")}</span><span className="r">{t("Credit")}</span><span /></div>
          {lines.map((l) => {
            const bad = amountOf(l) > l.available;
            return (
              <div className="cn-row" key={keyOf(l)}>
                <span className="cn-lbl">{l.label}</span>
                <span className="r fa-num">{fmt(l.billed)}</span>
                <span className="r fa-num fa-mut">{l.available > 0 ? fmt(l.available) : "—"}</span>
                <label className={"fa-price" + (bad ? " bad" : "")} style={bad ? { borderColor: "var(--danger)" } : undefined}>
                  <input inputMode="numeric" disabled={l.available <= 0} value={groupDigits(form.data.amounts[keyOf(l)])}
                    aria-label={t("Credit for {line}", { line: l.label })} aria-invalid={bad ? "true" : undefined}
                    onChange={(e) => setAmount(l, digitsOf(e.target.value))} />
                  <span className="fa-unit">SAR</span>
                </label>
                <button type="button" className="fa-btn o sm" disabled={l.available <= 0} onClick={() => setAmount(l, String(l.available))}>{t("Full")}</button>
              </div>
            );
          })}
          {!lines.length ? <div className="fa-cnote">{t("Nothing on this invoice can be credited.")}</div> : null}
        </div>
        <div className="fa-ctot"><b>{t("Total credit")}</b><span className="fa-num"><b style={{ fontSize: 17 }}>{fmt(total)}</b><span className="fa-unit">SAR</span></span></div>
      </div>

      <div className="fa-rh"><span className="fa-cap">{t("Effect on {number}", { number: invoice.number })}</span></div>
      <div className="cn-eff">
        <div><span>{t("Invoice total")}</span><span className="fa-num">{fmt(invoice.total)} SAR</span></div>
        {invoice.credited ? <div><span>{t("Earlier credit notes")}</span><span className="fa-num">−{fmt(invoice.credited)} SAR</span></div> : null}
        <div><span>{t("Paid so far")}</span><span className="fa-num">−{fmt(invoice.paid)} SAR</span></div>
        <div><span>{t("This credit note")}</span><span className="fa-num">−{fmt(total)} SAR</span></div>
        <div className="res"><span>{t("Client still owes")}</span><span className="fa-num"><b>{fmt(stillOwes)}</b> SAR</span></div>
        {total > 0 ? (
          <div className="split">
            <div><span>{t("Reduces what the client owes")}</span><span className="fa-num">{fmt(reduces)} SAR</span></div>
            <div className={toDeposit ? "dep" : undefined}><span>{t("Already paid, goes to customer deposit")}</span><span className="fa-num">{fmt(toDeposit)} SAR</span></div>
          </div>
        ) : null}
      </div>

      <Foot why={why} cancelHref={cancel} submitLabel={t("Issue credit note")} processing={form.processing} />
      <style>{CSS}</style>
    </FormA>
  );
}

const CSS = `
.cn-row { display: grid; grid-template-columns: minmax(0,1fr) 100px 100px 140px 64px; align-items: center; gap: 10px; min-height: 52px; padding: 0 8px; font-size: 13.5px; min-width: 580px; }
.cn-row + .cn-row { border-top: 1px solid var(--hairline); }
.cn-row.h { min-height: 34px; font-size: 11.5px; font-weight: 500; color: var(--muted-foreground); }
.cn-row .r { text-align: right; }
.cn-lbl { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
.cn-row .fa-btn:disabled { opacity: .45; cursor: not-allowed; }
.cn-eff { border: 1px solid var(--border); border-radius: 14px; padding: 6px 14px; font-size: 13px; }
.cn-eff > div, .cn-eff .split > div { display: flex; justify-content: space-between; align-items: center; min-height: 30px; color: var(--muted-foreground); }
.cn-eff .res { border-top: 1px solid var(--border); margin-top: 4px; padding-top: 6px; color: var(--foreground); font-weight: 500; }
.cn-eff .res b { font-weight: 700; font-size: 15px; }
.cn-eff .split { display: block; margin: 6px -14px -6px; padding: 6px 14px; background: var(--background); border-radius: 0 0 13px 13px; }
.cn-eff .split .dep { color: var(--warning-text); font-weight: 500; }
`;

export default withStandaloneModal(CreditNoteFormBody, (props) => props.cancel);
