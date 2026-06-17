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
    form.post(url);
  };

  return (
    <div className="form-page">
      <div className="page-header" style={{ marginBottom: 16 }}>
        <div>
          <div className="page-title">{edit ? "Edit Penalti" : "Dokumen Penalti Baru"}</div>
          <div className="page-sub">{cl.guest_name} — {cl.confirmation_number}</div>
        </div>
      </div>

      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label="Informasi Penalti">
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField label="Nomor Penalti" name="penalty_number" value={form.data.penalty_number} onChange={set("penalty_number")} error={errors.penalty_number} />
              <FormField label="Tanggal Pembatalan" name="cancellation_date" type="date" value={form.data.cancellation_date} onChange={set("cancellation_date")} />
            </div>
            <FormField name="reason" label="Alasan">
              <textarea name="reason" rows={2} value={form.data.reason} onChange={(e) => form.setData("reason", e.target.value)} placeholder="Alasan pembatalan…" />
            </FormField>
          </FormSection>

          <FormSection label="Nilai">
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField label="Jumlah" name="penalty_amount" type="number" step="any" value={form.data.penalty_amount} onChange={set("penalty_amount")} error={errors.penalty_amount} />
              <FormField label="Mata Uang" name="penalty_currency">
                <select name="penalty_currency" value={form.data.penalty_currency} onChange={(e) => form.setData("penalty_currency", e.target.value)}>
                  {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </FormField>
            </div>
            <FormField label="Kurs ke SAR" name="exchange_rate" type="number" step="any" value={form.data.exchange_rate} onChange={set("exchange_rate")} />
          </FormSection>

          <FormSection label="Pembayaran">
            <label className="ff-check">
              <input type="checkbox" checked={form.data.is_paid} onChange={(e) => form.setData("is_paid", e.target.checked)} />
              <span>Sudah dibayar</span>
            </label>
            {form.data.is_paid && (
              <div className="fg-2" style={{ marginTop: 12 }}>
                <FormField label="Tanggal Bayar" name="payment_date" type="date" value={form.data.payment_date} onChange={set("payment_date")} />
                <FormField label="Metode" name="payment_method" value={form.data.payment_method} onChange={set("payment_method")} placeholder="Transfer / Tunai" />
                <FormField span={2} name="payment_note" label="Catatan Bayar">
                  <textarea name="payment_note" rows={2} value={form.data.payment_note} onChange={(e) => form.setData("payment_note", e.target.value)} />
                </FormField>
              </div>
            )}
          </FormSection>

          <FormSection label="Catatan Internal">
            <FormField name="note">
              <textarea name="note" rows={3} value={form.data.note} onChange={(e) => form.setData("note", e.target.value)} />
            </FormField>
          </FormSection>

          <FormActions
            cancelHref={edit ? `/penalty/${p.id}/` : `/cl/${cl.id}/`}
            submitLabel={edit ? "Simpan Perubahan" : "Buat Penalti"}
            processing={form.processing} />
        </FormPanel>
      </form>
    </div>
  );
}
