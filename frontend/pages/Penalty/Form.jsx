import { useForm } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField, { FieldGrid } from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { Alert } from "../../components/shadcn/ui/alert.jsx";
import Page from "../../components/shadcn/page.jsx";


function FormBody({ penalty, cl, suggested_number, today, edit, billing, error, errors: serverErrors = {} }) {
  const { t } = useI18n();
  const p = penalty || {};
  const form = useForm({
    penalty_number: p.penalty_number || suggested_number || "",
    cancellation_date: p.cancellation_date || today || "",
    reason: p.reason || "",
    penalty_amount: p.penalty_amount ?? "",
    note: p.note || "",
  });
  const errors = { ...form.errors, ...Object.fromEntries(Object.entries(serverErrors).map(([k, v]) => [k, t(v)])) };
  const set = (k) => (v) => form.setData(k, v);

  const submit = (e) => {
    e.preventDefault();
    const url = edit ? `/penalty/${p.id}/edit/` : `/cl/${cl.id}/penalty/new/`;
    form.post(url, { forceFormData: true });
  };

  return (
    <Page size="form">
      <PageBack href={`/cl/${cl.id}/`} label={t("Back to CL")} />
      <FormHeader
        kicker={t("Cancellation Penalty")}
        title={edit ? t("Edit Penalty") : t("New Penalty Document")}
        sub={<>{cl.guest_name} — {cl.confirmation_number}</>}
      />

      <form method="post" onSubmit={submit}>
        {error && <Alert variant="destructive" className="mb-3">{t(error)}</Alert>}
        <FormPanel>
          <FormSection label={t("Penalty Information")}>
            <FieldGrid className="mb-3">
              <FormField label={t("Penalty Number")} name="penalty_number" value={form.data.penalty_number} onChange={set("penalty_number")} error={errors.penalty_number} />
              <FormField label={t("Cancellation Date")} name="cancellation_date" type="date" value={form.data.cancellation_date} onChange={set("cancellation_date")} />
            </FieldGrid>
            <FormField name="reason" label={t("Reason")}>
              <Textarea name="reason" rows={2} value={form.data.reason} onChange={(e) => form.setData("reason", e.target.value)} placeholder={t("Cancellation reason…")} />
            </FormField>
          </FormSection>

          <FormSection label={t("Amount")}>
            <FormField label={t("Amount (SAR)")} name="penalty_amount" amount required
              value={form.data.penalty_amount} onChange={set("penalty_amount")} error={errors.penalty_amount}
              hint={t("Penalties are always set in SAR. A client paying in another currency is recorded as a payment with its rate.")} />
          </FormSection>

          {/* A penalty is always billed on an invoice and paid through the
              Payment module; this form no longer records payment itself. */}
          <FormSection label={t("Billing")}>
            <div role="note" className="text-[13px] leading-normal text-muted-foreground">
              {billing?.creates_invoice
                ? t("This reservation is not on an invoice yet. Saving will issue a new invoice in the name of {branch} that bills this penalty.", { branch: billing.branch })
                : t("This penalty is billed on invoice {number}, next to its reservation.", { number: billing?.invoice_number || "" })}
              {" "}
              {t("Money already received for this reservation covers the penalty first; record any further payment in Payments.")}
            </div>
          </FormSection>

          <FormSection label={t("Internal Notes")}>
            <FormField name="note">
              <Textarea name="note" rows={3} value={form.data.note} onChange={(e) => form.setData("note", e.target.value)} />
            </FormField>
          </FormSection>

          <FormActions
            cancelHref={edit ? `/penalty/${p.id}/` : `/cl/${cl.id}/`}
            submitLabel={edit ? t("Save Changes") : t("Create Penalty")}
            processing={form.processing} />
        </FormPanel>
      </form>
    </Page>
  );
}

export default withStandaloneModal(FormBody, (p) => (p.edit ? `/penalty/${p.penalty.id}/` : `/cl/${p.cl.id}/`));
