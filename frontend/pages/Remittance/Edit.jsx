import { useState } from "react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import { useForm } from "@inertiajs/react";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { REM_FORM_CSS } from "./remittanceStyles.js";
import FxPanel, { FX_CSS } from "./FxPanel.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

const num = (v) => Number(String(v ?? "").replace(/,/g, "")) || 0;
const rateText = (amount, sar) => (amount && sar ? (amount / sar).toFixed(2) : "");

// Edit a transfer. A normal transfer's amount and rate stay fixed once HQ has
// recorded a receipt. A legacy transfer (mapped at cutover) keeps its SAR —
// HQ already received it — and the user fills in the rupiah actually sent and
// the rupiah the clients paid for it (original amount); each amount can also
// be entered as its rate.
function EditBody({ rem, fx_pool = null, error = null }) {
  const { t } = useI18n();
  const legacy = rem.is_legacy;
  const sar = rem.expected_sar || 0;
  const amountsLocked = !legacy && rem.has_receipts;
  const [removeProof, setRemoveProof] = useState(false);
  const form = useForm({
    date: rem.date || "",
    receipt_reference: rem.receipt_reference || "",
    note: rem.note || "",
    amount_idr: rem.amount_idr != null ? String(rem.amount_idr) : "",
    exchange_rate: rem.exchange_rate != null ? String(rem.exchange_rate) : "",
    original_amount: rem.original_amount != null ? String(rem.original_amount) : "",
    proof: null,
    remove_proof: "",
  });
  // Rate fields of a legacy transfer are views of its amounts (SAR is fixed).
  const [sentRate, setSentRate] = useState(rateText(num(form.data.amount_idr), sar));
  const [originRate, setOriginRate] = useState(rateText(num(form.data.original_amount), sar));

  const sentIdr = num(form.data.amount_idr);
  const sarNow = legacy ? sar : (sentIdr && num(form.data.exchange_rate) ? Math.round(sentIdr / num(form.data.exchange_rate)) : null);
  const original = legacy && num(form.data.original_amount) ? num(form.data.original_amount) : null;

  const setLegacyAmount = (field, setRate) => (v) => {
    form.setData(field, v);
    setRate(rateText(num(v), sar));
  };
  const setLegacyRate = (field, setRate) => (v) => {
    setRate(v);
    form.setData(field, num(v) && sar ? String(Math.round(num(v) * sar)) : "");
  };

  const submit = (e) => {
    e.preventDefault();
    form.transform((d) => ({ ...d, remove_proof: removeProof ? "1" : "" }));
    form.post(`/remittance/${rem.id}/edit/`, { forceFormData: true });
  };

  return (
    <div className="page rem-form shadcn-root">
      <style>{REM_FORM_CSS + FX_CSS}</style>
      <PageBack href={`/remittance/${rem.id}/`} />
      <FormHeader kicker={t("Remittance")} title={t("Edit {number}", { number: rem.remittance_number })} />

      <form method="post" onSubmit={submit}>
        {error && <div className="alert alert-error" role="alert" style={{ marginBottom: 12 }}>{t(error)}</div>}
        <FormPanel>
          {legacy ? (
            <div className="rem-received-note">
              {t("Legacy transfer from before the system: HQ received {n} SAR. Fill in the rupiah actually sent and what the clients paid to see its FX profit.", { n: fmt(sar) })}
            </div>
          ) : rem.status === "received" && (
            <div className="rem-received-note">
              {t("This transfer has been marked")}{" "}<strong>{t("Received")}</strong>{" "}{t("by HQ. Changes here will alter already-confirmed records.")}
            </div>
          )}

          <FormSection label={t("Transfer Info")}>
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField
                label={t("Transfer Date")} name="date" type="date" required
                value={form.data.date} onChange={(v) => form.setData("date", v)}
              />
              <FormField
                label={t("Bank Reference")} name="receipt_reference"
                value={form.data.receipt_reference} onChange={(v) => form.setData("receipt_reference", v)}
              />
            </div>

            {legacy ? (
              <div className="fg-2">
                <FormField
                  label={t("Rupiah sent")} name="amount_idr" type="number" min="1"
                  value={form.data.amount_idr} onChange={setLegacyAmount("amount_idr", setSentRate)}
                />
                <FormField
                  label={t("Send rate (IDR/SAR)")} name="sent_rate" type="number" step="0.01" min="0.01"
                  value={sentRate} onChange={setLegacyRate("amount_idr", setSentRate)}
                />
                <FormField
                  label={t("Original amount (IDR)")} name="original_amount" type="number" min="1"
                  hint={t("What the clients paid in rupiah for these {n} SAR", { n: fmt(sar) })}
                  value={form.data.original_amount} onChange={setLegacyAmount("original_amount", setOriginRate)}
                />
                <FormField
                  label={t("Original rate (IDR/SAR)")} name="origin_rate" type="number" step="0.01" min="0.01"
                  value={originRate} onChange={setLegacyRate("original_amount", setOriginRate)}
                />
              </div>
            ) : (
              <div className="fg-2">
                <FormField
                  label={t("Amount IDR")} name="amount_idr" type="number" min="1" required
                  value={form.data.amount_idr} onChange={(v) => form.setData("amount_idr", v)}
                  hint={amountsLocked ? t("Fixed: HQ has recorded a receipt for this transfer.") : undefined}
                  disabled={amountsLocked}
                />
                <FormField
                  label={t("Exchange Rate (IDR/SAR)")} name="exchange_rate" type="number" step="0.01" min="0.01" required
                  value={form.data.exchange_rate} onChange={(v) => form.setData("exchange_rate", v)}
                  disabled={amountsLocked}
                />
              </div>
            )}

            <FxPanel pool={fx_pool} sentIdr={sentIdr} sar={sarNow} original={original} legacy={legacy} />

            <div className="fg-2">
              <FormField name="proof" label={t("Receipt")}>
                <Input
                  id="proof" name="proof" type="file" accept="image/*,.pdf"
                  onChange={(e) => form.setData("proof", e.target.files[0] || null)}
                />
              </FormField>
              <FormField
                label={t("Note")} name="note"
                value={form.data.note} onChange={(v) => form.setData("note", v)}
              />
            </div>
            {rem.proof_url && !removeProof && (
              <div style={{ marginTop: 6, display: "flex", gap: 10, fontSize: 12 }}>
                <a href={rem.proof_url} target="_blank" rel="noreferrer" style={{ color: "var(--foreground)", textDecoration: "underline" }}>{t("View receipt")} ↗</a>
                <button type="button" onClick={() => setRemoveProof(true)} style={{ background: "none", border: "none", fontSize: 12, color: "var(--destructive)", cursor: "pointer", padding: 0 }}>{t("Remove")}</button>
              </div>
            )}
            {removeProof && (
              <div style={{ marginTop: 6, fontSize: 12, color: "var(--destructive)" }}>
                {t("Receipt will be removed on save.")} <button type="button" onClick={() => setRemoveProof(false)} style={{ background: "none", border: "none", fontSize: 12, color: "var(--foreground)", textDecoration: "underline", cursor: "pointer", padding: 0 }}>{t("Undo")}</button>
              </div>
            )}
          </FormSection>

          <FormActions
            cancelHref={`/remittance/${rem.id}/`}
            submitLabel={form.processing ? t("Saving…") : t("Save")}
            processing={form.processing}
          />
        </FormPanel>
      </form>
    </div>
  );
}

export default withStandaloneModal(EditBody, (p) => `/remittance/${p.rem.id}/`);
