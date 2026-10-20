import { useForm } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import {
  FormA, Field, Picker, DatePicker, AmountIn, TextIn, FileDrop, NoteField, Foot,
} from "../../components/shadcn/form-a.jsx";
import { showToast } from "../../components/shadcn/toast.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtDec } from "../../utils/format.js";
import { fxFigures } from "./FxPanel.jsx";

// Send to HQ, the "Remittance Form" artboard on the Record View HMS canvas: a
// lump sum of rupiah leaves a branch account at a rate. The book rate (what
// clients paid in rupiah, on average) beside it gives the FX result before
// saving. Reservations are not chosen here: they are allocated when HQ records
// the receipt (Receipt.jsx), once it is clear whose money came first.
function FormBody({ open_transfers = [], today, error, from_accounts = [], to_accounts = [], fx_pool = null }) {
  const { t } = useI18n();
  const form = useForm({
    date: today || "",
    // One IDR account → nothing to choose.
    from_bank_account: from_accounts.length === 1 ? from_accounts[0].value : "",
    to_account: (to_accounts.find((a) => a.is_default) || to_accounts[0])?.value || "",
    amount_idr: "",
    exchange_rate: "",
    receipt_reference: "",
    note: "",
    proof: null,
  });
  const d = form.data;
  const set = (k) => (v) => form.setData(k, v);

  const idr = Number(d.amount_idr) || 0;
  const rate = Number(d.exchange_rate) || 0;
  const sar = idr > 0 && rate > 0 ? Math.round(idr / rate) : null;
  const fx = fxFigures({ pool: fx_pool, sentIdr: idr, sar });
  const pending = open_transfers.reduce((sum, r) => sum + r.in_transit + r.received_unallocated, 0);
  const from = from_accounts.find((a) => a.value === d.from_bank_account);

  const why = !d.from_bank_account ? t("Choose the account the money left.")
    : !d.to_account ? t("Add an HQ SAR account in Bank Balances first.")
      : !idr ? t("Enter the amount sent.")
        : !rate ? t("Enter the exchange rate.")
          : "";

  const submit = (e) => {
    e.preventDefault();
    if (why) return;
    form.post("/remittance/new/", { forceFormData: true });
  };

  const profit = fx?.profit;
  return (
    <FormA title={t("Send to HQ")} onSubmit={submit} error={error ? t(error) : null}>
      {pending > 0 ? (
        <div className="fa-alert fa-alert-top" role="status" style={{ color: "var(--warning-text)" }}>
          {t("{n} SAR from {list} is still in transit or not yet allocated. Make sure this is not the same transfer.", {
            n: fmt(pending), list: open_transfers.map((r) => r.remittance_number).join(", "),
          })}
        </div>
      ) : null}
      <div className="fa-fields">
        <Field label={t("From account")} required>
          <Picker searchable={false} value={d.from_bank_account} placeholder={t("Choose IDR account")} heading={t("From account")}
            options={from_accounts.map((a) => ({ value: a.value, label: a.name || a.label, meta: a.label }))}
            onPick={(o) => form.setData("from_bank_account", o.value)}
            extra={from ? <span className="fa-om">IDR</span> : null} />
        </Field>
        <Field label={t("Send to")} required>
          <Picker searchable={false} value={d.to_account} placeholder={t("Choose HQ account")} heading={t("Send to")}
            options={to_accounts.map((a) => ({ value: a.value, label: a.label, meta: a.number || "" }))}
            onPick={(o) => form.setData("to_account", o.value)}
            extra={<span className="fa-om">SAR</span>} />
        </Field>
        <Field label={t("Transfer date")} required>
          <DatePicker value={d.date} onChange={set("date")} label={t("Choose transfer date")} />
        </Field>
        <Field label={t("Bank reference")} optional>
          <TextIn value={d.receipt_reference} onChange={set("receipt_reference")} placeholder={t("From the transfer slip")} />
        </Field>
        <Field label={t("Amount sent")} required>
          <AmountIn ccy="IDR" value={d.amount_idr} onChange={set("amount_idr")} hint={sar ? `${fmt(sar)} SAR` : null} />
        </Field>
        <Field label={t("Exchange rate")} required>
          <TextIn value={d.exchange_rate} onChange={(v) => form.setData("exchange_rate", v.replace(/[^\d.]/g, ""))} inputMode="decimal"
            icon={<span className="fa-om">1 SAR =</span>} suffix={<span className="fa-om">IDR</span>} />
        </Field>
        <Field label={t("Book rate")}>
          <div className="fa-oi fa-ro">
            <span className="fa-ot fa-num" style={{ color: "var(--foreground)", fontWeight: 600 }}>
              {fx_pool?.rate ? `1 SAR = ${fmt(fx_pool.rate)} IDR` : t("No client rupiah yet")}
            </span>
            <span className="fa-om">{t("Average of client payments")}</span>
          </div>
        </Field>
        <Field label={t("FX result")}>
          <div className={"fa-oi fa-ro" + (profit > 0 ? " rm-gain" : profit < 0 ? " rm-loss" : "")}>
            <span className="fa-ot fa-num">
              {profit == null ? t("Enter the amount and rate")
                : profit === 0 ? t("No gain or loss")
                  : t(profit > 0 ? "{n} IDR gain" : "{n} IDR loss", { n: fmt(Math.abs(profit)) })}
            </span>
            {fx?.originRate ? <span className="fa-om">{t("sent at {r}", { r: fmtDec(idr / sar, 2) })}</span> : null}
          </div>
        </Field>
      </div>
      {fx && fx.uncovered > 0 ? (
        <div className="fa-alert" role="status" style={{ color: "var(--warning-text)" }}>
          {t("{n} SAR of this transfer has no client rupiah behind it, so no original rate.", { n: fmt(fx.uncovered) })}
        </div>
      ) : null}

      <NoteField label={t("Transfer proof")} optional>
        <FileDrop file={d.proof} onFile={set("proof")} title={t("Upload the bank transfer slip")}
          onTooBig={() => showToast(t("File too large. Maximum upload size is 3 MB."), "error")} />
      </NoteField>
      <NoteField label={t("Note")} value={d.note} onChange={set("note")} placeholder={t("Anything HQ should know about this transfer")} />

      <Foot why={why} cancelHref="/remittance/" submitLabel={t("Save remittance")} processing={form.processing} />
      <style>{`
.rm-gain .fa-ot { color: var(--success-text) !important; font-weight: 600 !important; }
.rm-loss .fa-ot { color: var(--danger-text) !important; font-weight: 600 !important; }
`}</style>
    </FormA>
  );
}

export default withStandaloneModal(FormBody, "/remittance/");
