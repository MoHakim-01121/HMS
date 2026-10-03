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
import { Icon } from "../../components/icons.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";
import FxPanel, { FX_CSS } from "./FxPanel.jsx";

// Transfer ke Pusat = lump-sum (IDR + kurs). Reservasi tidak dipilih di sini:
// alokasi dilakukan saat Pusat mencatat penerimaan (Receipt.jsx), karena baru
// saat itu jelas uang reservasi mana yang didahulukan.
function FormBody({ open_transfers = [], today, error, from_accounts = [], fx_pool = null }) {
  const { t } = useI18n();
  const form = useForm({
    date: today || "",
    // One IDR account → nothing to choose.
    from_bank_account: from_accounts.length === 1 ? from_accounts[0].value : "",
    amount_idr: "",
    exchange_rate: "",
    receipt_reference: "",
    note: "",
    proof: null,
  });

  const idr = Number(form.data.amount_idr) || 0;
  const rate = Number(form.data.exchange_rate) || 0;
  const estimate = idr > 0 && rate > 0 ? Math.round(idr / rate) : null;
  const pending = open_transfers.reduce((sum, r) => sum + r.in_transit + r.received_unallocated, 0);

  const submit = (e) => {
    e.preventDefault();
    form.post("/remittance/new/", { forceFormData: true });
  };

  return (
    <div className="page rem-form shadcn-root">
      <style>{CSS + FX_CSS}</style>
      <PageBack href="/remittance/" />
      <FormHeader
        kicker={t("Remittance")}
        title={t("Send to HQ")}
        sub={t("Money leaving Surabaya. Allocation to reservations happens when HQ records the receipt.")}
      />

      {error && <div className="alert alert-error" style={{ marginBottom: 12 }}>{t(error)}</div>}

      {pending > 0 && (
        <div className="rem-open-note" role="status">
          <Icon name="alert-circle" size={15} />
          <span>
            {t("{n} SAR from {list} is still in transit or not yet allocated. Make sure this is not the same transfer.", {
              n: fmt(pending),
              list: open_transfers.map((r) => r.remittance_number).join(", "),
            })}
          </span>
        </div>
      )}

      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label={t("Transfer Info")}>
            <div className="fg-2">
              <FormField
                label={t("Transfer Date")} name="date" type="date" required
                value={form.data.date} onChange={(v) => form.setData("date", v)}
              />
              <FormField
                label={t("Bank Reference")} name="receipt_reference"
                value={form.data.receipt_reference} onChange={(v) => form.setData("receipt_reference", v)}
              />
              <FormField label={t("From Account")} name="from_bank_account" required span={2}>
                <Select value={form.data.from_bank_account} onValueChange={(v) => form.setData("from_bank_account", v)}>
                  <SelectTrigger id="from_bank_account" className="w-full"><SelectValue placeholder={t("Choose IDR account")} /></SelectTrigger>
                  <SelectContent>
                    {from_accounts.map((a) => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </FormField>
              <FormField
                label={t("Amount IDR")} name="amount_idr" type="number" min="1" required
                value={form.data.amount_idr} onChange={(v) => form.setData("amount_idr", v)}
                placeholder="240000000"
              />
              <FormField
                label={t("Exchange Rate (IDR/SAR)")} name="exchange_rate" type="number" step="0.01" min="0.01" required
                value={form.data.exchange_rate} onChange={(v) => form.setData("exchange_rate", v)}
                placeholder="4800"
              />
            </div>
            <p className={"rem-estimate" + (estimate == null ? " is-hint" : "")} aria-live="polite">
              {estimate != null ? t("≈ {n} SAR", { n: fmt(estimate) }) : t("Enter the IDR amount and rate to see the SAR estimate.")}
            </p>
            <FxPanel pool={fx_pool} sentIdr={idr} sar={estimate} />
            <div className="fg-2">
              <FormField
                name="proof" label={t("Receipt")} hint={t("Optional — image or PDF")}
              >
                <Input
                  id="proof" name="proof" type="file" accept="image/*,.pdf"
                  onChange={(e) => form.setData("proof", e.target.files[0] || null)}
                />
              </FormField>
              <FormField
                label={t("Note")} name="note"
                value={form.data.note} onChange={(v) => form.setData("note", v)}
                placeholder={t("Transfer BCA 01/06")}
              />
            </div>
          </FormSection>

          <FormActions
            cancelHref="/remittance/"
            submitLabel={form.processing ? t("Saving…") : t("Save Remittance")}
            processing={form.processing}
          />
        </FormPanel>
      </form>
    </div>
  );
}

const CSS = `
.rem-open-note {
  display: flex; align-items: flex-start; gap: 8px; margin-bottom: 14px;
  padding: 10px 12px; border-radius: 12px; font-size: 12.5px; line-height: 1.5;
  background: color-mix(in oklch, var(--muted) 55%, var(--card)); border: 1px solid var(--border);
}
.rem-open-note svg { flex: none; margin-top: 2px; color: var(--yellow); }
.rem-estimate { margin: 6px 0 14px; font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums; }
.rem-estimate.is-hint { font-weight: 400; color: var(--muted-foreground); }
`;

export default withStandaloneModal(FormBody, "/remittance/");
