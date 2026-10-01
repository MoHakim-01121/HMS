import { useForm } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
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

function DepositTransferBody({ client, clients, initial, errors: serverErrors }) {
  const { t } = useI18n();
  const i = initial || {};
  const form = useForm({ to_client: i.to_client || "", amount_sar: i.amount_sar || "", note: i.note || "" });
  const errors = { ...serverErrors, ...form.errors };

  const submit = (e) => {
    e.preventDefault();
    form.post(`/finance/clients/${client.pk}/deposit-transfer/`);
  };

  return (
    <div className="form-page shadcn-root">
      <PageBack href={`/finance/clients/${client.pk}/statement/`} label={t("Back")} />
      <FormHeader kicker={t("Deposit Transfer")} title={t("Move Deposit to Another Client")} sub={client.name} />

      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label={t("Move Money")}>
            <FormField label={t("To client")} name="to_client" error={errors.to_client}>
              <Select name="to_client" value={String(form.data.to_client || "")} onValueChange={(v) => form.setData("to_client", v)}>
                <SelectTrigger id="to_client" className="w-full">
                  <SelectValue placeholder={t("Choose client…")} />
                </SelectTrigger>
                <SelectContent>
                  {clients.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </FormField>
            <FormField
              label={t("Amount (SAR)")} name="amount_sar" type="number" step="1"
              value={form.data.amount_sar} onChange={(v) => form.setData("amount_sar", v)} error={errors.amount_sar}
              hint={t("Deposit available: {n} SAR", { n: fmt(client.saldo_dana) })}
            />
            <FormField label={t("Note")} name="note" span={2}>
              <Textarea name="note" rows={2} value={form.data.note} onChange={(e) => form.setData("note", e.target.value)} placeholder={t("Why is this money moving?")} />
            </FormField>
          </FormSection>
          <FormActions cancelHref={`/finance/clients/${client.pk}/statement/`} submitLabel={t("Move Deposit")} processing={form.processing} />
        </FormPanel>
      </form>
    </div>
  );
}

export default withStandaloneModal(DepositTransferBody, (p) => `/finance/clients/${p.client.pk}/statement/`);
