import { useForm } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

const keyOf = (l) => `${l.kind}:${l.id}`;

// Credit note: reduce what an invoice bills, per reservation / service line,
// never beyond what that line still bills. If the client already paid more
// than the invoice will bill afterwards, the excess becomes client deposit.
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
  const over = lines.filter((l) => amountOf(l) > l.available || amountOf(l) < 0);
  const openBefore = Math.max(invoice.remaining, 0);
  const toDeposit = Math.max(total - openBefore, 0);
  const dueAfter = invoice.total - invoice.credited - total;

  const submit = (e) => {
    e.preventDefault();
    form.transform((d) => ({ ...d, amounts: JSON.stringify(d.amounts) }));
    form.post(`/finance/invoices/${invoice.id}/credit-notes/new/`);
  };

  return (
    <div className="form-page shadcn-root">
      <PageBack href={cancel} label={t("Back")} />
      <FormHeader
        kicker={invoice.number}
        title={t("New Credit Note")}
        sub={t("Reduce what {client} is billed on this invoice. The invoice itself stays unchanged.", { client: invoice.client })}
      />
      {error && <div className="alert alert-error" style={{ marginBottom: 12 }}>{t(error)}</div>}
      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label={t("Lines to credit")}>
            <div className="cnf-lines">
              <div className="cnf-h">
                <span>{t("Line")}</span><span className="r">{t("Billed")}</span><span className="r">{t("Can credit")}</span><span className="r">{t("Credit (SAR)")}</span>
              </div>
              {lines.map((l) => {
                const bad = amountOf(l) > l.available || amountOf(l) < 0;
                return (
                  <div className="cnf-r" key={keyOf(l)}>
                    <span className="cnf-lbl">{l.label}</span>
                    <span className="r tab" data-label={t("Billed")}>{fmt(l.billed)}</span>
                    <span className="r tab" data-label={t("Can credit")}>
                      {l.available > 0 ? (
                        <button type="button" className="cnf-full" onClick={() => setAmount(l, String(l.available))} title={t("Credit the full amount")}>
                          {fmt(l.available)}
                        </button>
                      ) : "—"}
                    </span>
                    <Input
                      className="cnf-in" type="number" min="0" max={l.available} inputMode="numeric"
                      disabled={l.available <= 0}
                      aria-label={t("Credit for {line}", { line: l.label })} aria-invalid={bad ? "true" : undefined}
                      value={form.data.amounts[keyOf(l)] ?? ""} onChange={(e) => setAmount(l, e.target.value)}
                    />
                  </div>
                );
              })}
            </div>
            <dl className="cnf-sum">
              <div><dt>{t("Total credit")}</dt><dd>{fmt(total)} SAR</dd></div>
              <div><dt>{t("Invoice will bill")}</dt><dd>{fmt(dueAfter)} SAR</dd></div>
              <div><dt>{t("Already paid")}</dt><dd>{fmt(invoice.paid)} SAR</dd></div>
              {toDeposit > 0 ? (
                <div className="warn"><dt>{t("To client deposit")}</dt><dd>{fmt(toDeposit)} SAR</dd></div>
              ) : null}
            </dl>
            {toDeposit > 0 ? (
              <p className="cnf-note">{t("The client already paid more than the invoice will bill. The excess is kept as client deposit, to refund or move to another booking under Finance → Client Ledger.")}</p>
            ) : null}
          </FormSection>
          <FormSection label={t("Details")}>
            <div className="fg-2">
              <FormField label={t("Date")} name="issued_date" type="date" required value={form.data.issued_date} onChange={(v) => form.setData("issued_date", v)} />
            </div>
            <FormField label={t("Reason")} name="reason" required hint={t("Printed on the credit note, e.g. booking cancelled, rate corrected.")}>
              <Textarea id="reason" rows={2} value={form.data.reason} onChange={(e) => form.setData("reason", e.target.value)} />
            </FormField>
          </FormSection>
          <FormActions
            cancelHref={cancel}
            submitLabel={form.processing ? t("Saving…") : t("Create Credit Note")}
            processing={form.processing || total <= 0 || over.length > 0 || !form.data.reason.trim()}
          />
        </FormPanel>
      </form>
      <style>{CSS}</style>
    </div>
  );
}

const CSS = `
.cnf-lines { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
.cnf-h, .cnf-r { display: grid; grid-template-columns: minmax(0, 1fr) 90px 100px 130px; gap: 10px; align-items: center; padding: 9px 14px; }
.cnf-h { font-size: 12px; font-weight: 500; color: var(--muted-foreground); background: var(--secondary); }
.cnf-r { border-top: 1px solid var(--border); font-size: 13px; }
.cnf-lines .r { text-align: right; }
.cnf-lines .tab { font-variant-numeric: tabular-nums; }
.cnf-lbl { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
.cnf-full { background: none; border: none; padding: 0; font: inherit; color: inherit; cursor: pointer; text-decoration: underline; text-decoration-color: var(--border); text-underline-offset: 3px; }
.cnf-full:hover { text-decoration-color: var(--foreground); }
.cnf-in { text-align: right; height: 34px; }
.cnf-sum { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin: 14px 0 0; }
.cnf-sum > div { padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px; }
.cnf-sum dt { font-size: 12px; color: var(--muted-foreground); }
.cnf-sum dd { margin: 2px 0 0; font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums; }
.cnf-sum .warn dd { color: var(--yellow); }
.cnf-note { margin: 10px 0 0; font-size: 12.5px; color: var(--muted-foreground); }
@media (max-width: 600px) {
  .cnf-h { display: none; }
  .cnf-r { grid-template-columns: 1fr 1fr; }
  .cnf-lbl { grid-column: 1 / -1; }
  .cnf-r [data-label]::before { content: attr(data-label) " "; color: var(--muted-foreground); font-size: 12px; }
  .cnf-in { grid-column: 1 / -1; }
}
`;

export default withStandaloneModal(CreditNoteFormBody, (props) => props.cancel);
