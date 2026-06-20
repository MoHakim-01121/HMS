import { useForm } from "@inertiajs/react";
import FormPanel from "../../components/form/FormPanel.jsx";
import FormSection from "../../components/form/FormSection.jsx";
import FormField from "../../components/form/FormField.jsx";
import FormActions from "../../components/form/FormActions.jsx";

const CURRENCIES = ["SAR", "IDR", "USD"];

export default function Form({ penalty, cl, suggested_number, today, edit, errors: serverErrors }) {
  const p = penalty || {};
  const form = useForm({
    penalty_number: p.penalty_number || suggested_number || "",
    cancellation_date: p.cancellation_date || today || "",
    reason: p.reason || "",
    penalty_amount: p.penalty_amount ?? "",
    penalty_currency: p.penalty_currency || "SAR",
    exchange_rate: p.exchange_rate ?? 1,
    is_paid: edit ? !!p.is_paid : false,
    payment_date: p.payment_date || "",
    payment_method: p.payment_method || "",
    payment_note: p.payment_note || "",
    note: p.note || "",
  });
  const errors = { ...serverErrors, ...form.errors };
  const set = (k) => (v) => form.setData(k, v);

  const submit = (e) => {
    e.preventDefault();
    form.transform((d) => ({ ...d, is_paid: d.is_paid ? "on" : "" }));
    const url = edit ? `/penalty/${p.id}/edit/` : `/cl/${cl.id}/penalty/new/`;
    form.post(url, { forceFormData: true });
  };

  return (
    <div className="form-page">
      <div className="page-header" style={{ marginBottom: 16 }}>
        <div>
          <div className="page-title">{edit ? "Edit Penalty" : "New Penalty Document"}</div>
          <div className="page-sub">{cl.guest_name} — {cl.confirmation_number}</div>
        </div>
      </div>

      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label="Penalty Information">
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField label="Penalty Number" name="penalty_number" value={form.data.penalty_number} onChange={set("penalty_number")} error={errors.penalty_number} />
              <FormField label="Cancellation Date" name="cancellation_date" type="date" value={form.data.cancellation_date} onChange={set("cancellation_date")} />
            </div>
            <FormField name="reason" label="Reason">
              <textarea name="reason" rows={2} value={form.data.reason} onChange={(e) => form.setData("reason", e.target.value)} placeholder="Cancellation reason…" />
            </FormField>
          </FormSection>

          <FormSection label="Amount">
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField label="Amount" name="penalty_amount" type="number" step="any" value={form.data.penalty_amount} onChange={set("penalty_amount")} error={errors.penalty_amount} />
              <FormField label="Currency" name="penalty_currency">
                <select name="penalty_currency" value={form.data.penalty_currency} onChange={(e) => form.setData("penalty_currency", e.target.value)}>
                  {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </FormField>
            </div>
            <FormField label="Exchange Rate to SAR" name="exchange_rate" type="number" step="any" value={form.data.exchange_rate} onChange={set("exchange_rate")} />
          </FormSection>

          <FormSection label="Payment">
            <label className="ff-check">
              <input type="checkbox" checked={form.data.is_paid} onChange={(e) => form.setData("is_paid", e.target.checked)} />
              <span>Already paid</span>
            </label>
            {form.data.is_paid && (
              <div className="fg-2" style={{ marginTop: 12 }}>
                <FormField label="Payment Date" name="payment_date" type="date" value={form.data.payment_date} onChange={set("payment_date")} />
                <FormField label="Method" name="payment_method" value={form.data.payment_method} onChange={set("payment_method")} placeholder="Transfer / Cash" />
                <FormField span={2} name="payment_note" label="Payment Note">
                  <textarea name="payment_note" rows={2} value={form.data.payment_note} onChange={(e) => form.setData("payment_note", e.target.value)} />
                </FormField>
              </div>
            )}
          </FormSection>

          <FormSection label="Internal Notes">
            <FormField name="note">
              <textarea name="note" rows={3} value={form.data.note} onChange={(e) => form.setData("note", e.target.value)} />
            </FormField>
          </FormSection>

          <FormActions
            cancelHref={edit ? `/penalty/${p.id}/` : `/cl/${cl.id}/`}
            submitLabel={edit ? "Save Changes" : "Create Penalty"}
            processing={form.processing} />
        </FormPanel>
      </form>
    </div>
  );
}
