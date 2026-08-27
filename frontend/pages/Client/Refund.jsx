import { useForm } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/shadcn/ui/select.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

const ACCOUNTS = [
  { value: "sby", label: "Surabaya" },
  { value: "pusat", label: "Pusat / HQ" },
];

export default function Refund({ client, initial, errors: serverErrors }) {
  const { t } = useI18n();
  const i = initial || {};
  const form = useForm({
    from_account: i.from_account || "sby",
    amount_sar: i.amount_sar || "",
    note: i.note || "",
    proof: null,
  });
  const errors = { ...serverErrors, ...form.errors };

  const submit = (e) => {
    e.preventDefault();
    form.post(`/clients/${client.pk}/refund/`, { forceFormData: true });
  };

  return (
    <div className="form-page shadcn-root">
      <PageBack href={`/clients/${client.pk}/`} label={t("Back to client")} />
      <FormHeader
        kicker={t("Refund")}
        title={t("Refund to Client")}
        sub={`${client.name} — ${t("Fund balance")}: ${fmt(client.saldo_dana)} SAR`}
      />

      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label={t("Refund Details")}>
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField label={t("Paid from")} name="from_account" error={errors.from_account}>
                <Select name="from_account" value={form.data.from_account} onValueChange={(v) => form.setData("from_account", v)}>
                  <SelectTrigger id="from_account" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ACCOUNTS.map((a) => <SelectItem key={a.value} value={a.value}>{t(a.label)}</SelectItem>)}
                  </SelectContent>
                </Select>
              </FormField>
              <FormField
                label={t("Amount (SAR)")}
                name="amount_sar"
                type="number"
                step="1"
                value={form.data.amount_sar}
                onChange={(v) => form.setData("amount_sar", v)}
                error={errors.amount_sar}
              />
            </div>
            <FormField label={t("Note")} name="note" span={2}>
              <Textarea name="note" rows={2} value={form.data.note} onChange={(e) => form.setData("note", e.target.value)} placeholder={t("Reason for refund…")} />
            </FormField>
            <FormField label={t("Proof")} name="proof" span={2}>
              <input type="file" accept="image/*,.pdf" onChange={(e) => form.setData("proof", e.target.files[0] || null)} />
            </FormField>
          </FormSection>

          <FormActions
            cancelHref={`/clients/${client.pk}/`}
            submitLabel={t("Send Refund")}
            processing={form.processing}
          />
        </FormPanel>
      </form>
    </div>
  );
}
