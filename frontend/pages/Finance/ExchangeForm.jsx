import { useForm } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/shadcn/ui/select.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Same currency: one amount, a plain transfer. Different currencies: enter the
// two real amounts from the bank (out and in); the rate is derived, never
// typed, and flagged when it strays from the last exchange of the pair.
function ExchangeFormBody({ account_choices = [], last_rates = {}, warning_pct = 3, form: initial = {}, error }) {
  const { t } = useI18n();
  const form = useForm({
    exchange_date: initial.exchange_date || "",
    from_account: initial.from_account || "",
    amount_out: initial.amount_out || "",
    to_account: initial.to_account || "",
    amount_in: initial.amount_in || "",
    reference: initial.reference || "",
    note: initial.note || "",
    proof: null,
  });
  const set = (k) => (v) => form.setData(k, v);

  const from = account_choices.find((a) => a.value === form.data.from_account);
  const to = account_choices.find((a) => a.value === form.data.to_account);
  const out = Number(form.data.amount_out) || 0;
  const inn = Number(form.data.amount_in) || 0;
  const sameCurrency = from && to && from.currency === to.currency;
  const rate = from && to && !sameCurrency && out > 0 && inn > 0 ? inn / out : null;
  const prev = rate ? last_rates[`${from.currency}>${to.currency}`] : null;
  const deviation = rate && prev ? (Math.abs(rate - prev) / prev) * 100 : null;

  const submit = (e) => {
    e.preventDefault();
    form.post("/finance/exchanges/new/", { forceFormData: true });
  };

  const accountSelect = (key, placeholder) => (
    <Select value={form.data[key]} onValueChange={set(key)}>
      <SelectTrigger id={key} className="w-full"><SelectValue placeholder={placeholder} /></SelectTrigger>
      <SelectContent>
        {account_choices.map((a) => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}
      </SelectContent>
    </Select>
  );

  return (
    <div className="form-page shadcn-root">
      <PageBack href="/finance/exchanges/" label={t("Back")} />
      <FormHeader
        kicker={t("Transfer & Exchange")}
        title={t("New Transfer")}
        sub={sameCurrency
          ? t("Enter the amount exactly as the bank shows it.")
          : t("Enter the two amounts exactly as the bank shows them. The rate is calculated.")}
      />
      {error && <div className="alert alert-error" style={{ marginBottom: 12 }}>{t(error)}</div>}
      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label={t("Details")}>
            <div className="fg-2">
              <FormField label={t("From Account")} name="from_account" required>{accountSelect("from_account", t("Choose account"))}</FormField>
              <FormField
                label={from ? t("Amount out ({currency})", { currency: from.currency }) : t("Amount out")}
                name="amount_out" type="number" min="1" required autoFocus
                value={form.data.amount_out} onChange={set("amount_out")}
              />
              <FormField label={t("To Account")} name="to_account" required>{accountSelect("to_account", t("Choose account"))}</FormField>
              {!sameCurrency && (
                <FormField
                  label={to ? t("Amount in ({currency})", { currency: to.currency }) : t("Amount in")}
                  name="amount_in" type="number" min="1" required
                  value={form.data.amount_in} onChange={set("amount_in")}
                />
              )}
            </div>
            <p className="fx-rate" aria-live="polite">
              {sameCurrency
                ? t("Both accounts are in {currency} — a plain transfer, no rate.", { currency: from.currency })
                : rate
                  ? t("Rate: {rate} {to} per {from}", { rate: rate.toLocaleString("en-US", { maximumFractionDigits: 4 }), to: to.currency, from: from.currency })
                  : t("Choose both accounts and enter both amounts to see the rate.")}
            </p>
            {deviation != null && deviation > warning_pct && (
              <p className="fx-warn" role="status">
                {t("This rate is {pct}% away from the last {from}→{to} exchange ({prev}). Check both amounts.", {
                  pct: deviation.toFixed(1), from: from.currency, to: to.currency,
                  prev: prev.toLocaleString("en-US", { maximumFractionDigits: 4 }),
                })}
              </p>
            )}
            <div className="fg-2">
              <FormField label={t("Date")} name="exchange_date" type="date" required value={form.data.exchange_date} onChange={set("exchange_date")} />
              <FormField label={t("Bank Reference")} name="reference" value={form.data.reference} onChange={set("reference")} />
              <FormField name="proof" label={t("Receipt")} hint={t("Optional — image or PDF")}>
                <Input id="proof" name="proof" type="file" accept="image/*,.pdf" onChange={(e) => form.setData("proof", e.target.files[0] || null)} />
              </FormField>
              <FormField label={t("Note")} name="note" value={form.data.note} onChange={set("note")} />
            </div>
          </FormSection>
          <FormActions
            cancelHref="/finance/exchanges/"
            submitLabel={form.processing ? t("Saving…") : t("Save Transfer")}
            processing={form.processing}
          />
        </FormPanel>
      </form>
      <style>{`
.fx-rate { margin: 6px 0 14px; font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums; }
.fx-warn { margin: -6px 0 14px; font-size: 12.5px; color: var(--yellow); }
`}</style>
    </div>
  );
}

export default withStandaloneModal(ExchangeFormBody, "/finance/exchanges/");
