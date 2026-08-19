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

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

export default function Transfer({ client, reservations, initial, errors: serverErrors }) {
  const { t } = useI18n();
  const i = initial || {};
  const form = useForm({
    from_reservation: i.from_reservation || "",
    to_reservation: i.to_reservation || "",
    amount_sar: i.amount_sar || "",
    note: i.note || "",
  });
  const errors = { ...serverErrors, ...form.errors };

  const submit = (e) => {
    e.preventDefault();
    form.post(`/clients/${client.pk}/transfer/`);
  };

  const opt = (id) => reservations.find((r) => String(r.id) === String(id));

  return (
    <div className="form-page shadcn-root">
      <PageBack href={`/clients/${client.pk}/`} label={t("Back to client")} />
      <FormHeader
        kicker={t("Fund Transfer")}
        title={t("Move Allocation Between Reservations")}
        sub={client.name}
      />

      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label={t("Move Money")}>
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField label={t("From reservation")} name="from_reservation" error={errors.from_reservation}>
                <Select name="from_reservation" value={String(form.data.from_reservation || "")} onValueChange={(v) => form.setData("from_reservation", v)}>
                  <SelectTrigger id="from_reservation" className="w-full">
                    <SelectValue placeholder={t("Choose reservation…")} />
                  </SelectTrigger>
                  <SelectContent>
                    {reservations.map((r) => (
                      <SelectItem key={r.id} value={String(r.id)}>{r.label} ({fmt(r.piutang)} SAR owed)</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </FormField>
              <FormField label={t("To reservation")} name="to_reservation" error={errors.to_reservation}>
                <Select name="to_reservation" value={String(form.data.to_reservation || "")} onValueChange={(v) => form.setData("to_reservation", v)}>
                  <SelectTrigger id="to_reservation" className="w-full">
                    <SelectValue placeholder={t("Choose reservation…")} />
                  </SelectTrigger>
                  <SelectContent>
                    {reservations.map((r) => (
                      <SelectItem key={r.id} value={String(r.id)}>{r.label} ({fmt(r.piutang)} SAR owed)</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </FormField>
            </div>
            <FormField
              label={t("Amount (SAR)")}
              name="amount_sar"
              type="number"
              step="1"
              value={form.data.amount_sar}
              onChange={(v) => form.setData("amount_sar", v)}
              error={errors.amount_sar}
              hint={opt(form.data.from_reservation) ? t("{n} SAR still owed on this reservation", { n: fmt(opt(form.data.from_reservation).piutang) }) : undefined}
            />
            <FormField label={t("Note")} name="note" span={2}>
              <Textarea name="note" rows={2} value={form.data.note} onChange={(e) => form.setData("note", e.target.value)} placeholder={t("Why is this money moving?")} />
            </FormField>
          </FormSection>

          <FormActions
            cancelHref={`/clients/${client.pk}/`}
            submitLabel={t("Move Funds")}
            processing={form.processing}
          />
        </FormPanel>
      </form>
    </div>
  );
}
