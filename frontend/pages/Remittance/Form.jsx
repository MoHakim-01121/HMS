import { useForm } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import { FormA, Field, Picker, DatePicker, AmountIn, TextIn, FileDrop, NoteField, Foot, FA } from "../../components/shadcn/form-a.jsx";
import { cn } from "@/lib/utils";
import { showToast } from "../../components/shadcn/toast.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtDec } from "../../utils/format.js";
import { fxFigures } from "./FxPanel.jsx";
import PlanTable from "./PlanTable.jsx";

// Send to HQ, the "Remittance Form" artboard on the Record View HMS canvas: a
// lump sum of rupiah leaves a branch account at a rate. The book rate (what
// clients paid in rupiah, on average) beside it gives the FX result before
// saving. Reservations picked on the Tracking tab come along as a plan; they
// are allocated when HQ records the receipt (Receipt.jsx), which starts from
// the plan.
function FormBody({ plan = [], open_transfers = [], today, error, from_accounts = [], to_accounts = [], fx_pool = null }) {
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
    plan: plan.map((r) => ({ ...r, amount_sar: String(r.amount_sar) })),
  });
  const d = form.data;
  const set = (k) => (v) => form.setData(k, v);

  const idr = Number(d.amount_idr) || 0;
  const rate = Number(d.exchange_rate) || 0;
  const sar = idr > 0 && rate > 0 ? Math.round(idr / rate) : null;
  const fx = fxFigures({ pool: fx_pool, sentIdr: idr, sar });
  const pending = open_transfers.reduce((sum, r) => sum + r.in_transit + r.received_unallocated, 0);
  const from = from_accounts.find((a) => a.value === d.from_bank_account);
  const planSar = d.plan.reduce((sum, r) => sum + (Number(r.amount_sar) || 0), 0);
  const planBad = d.plan.some((r) => !(Number(r.amount_sar) > 0) || Number(r.amount_sar) > r.plannable);
  const setPlan = (id, v) => form.setData("plan", d.plan.map((r) => (r.invoice_line_id === id ? { ...r, amount_sar: v.replace(/\D/g, "") } : r)));
  const dropPlan = (id) => form.setData("plan", d.plan.filter((r) => r.invoice_line_id !== id));

  const why = !d.from_bank_account ? t("Choose the account the money left.")
    : !d.to_account ? t("Add an HQ SAR account in Bank Balances first.")
      : !idr ? t("Enter the amount sent.")
        : !rate ? t("Enter the exchange rate.")
          : planBad ? t("Check the planned amounts.")
            : "";

  const submit = (e) => {
    e.preventDefault();
    if (why) return;
    form.transform((data) => ({
      ...data,
      plan: JSON.stringify(data.plan.map((r) => ({ invoice_line_id: r.invoice_line_id, amount_sar: Number(r.amount_sar) || 0 }))),
    }));
    form.post("/remittance/new/", { forceFormData: true });
  };

  const profit = fx?.profit;
  return (
    <FormA title={t("Send to HQ")} onSubmit={submit} error={error ? t(error) : null}>
      {pending > 0 ? (
        <div className={cn(FA.alertTop, "text-warning-text")} role="status">
          {t("{n} SAR from {list} is still in transit or not yet allocated. Make sure this is not the same transfer.", {
            n: fmt(pending), list: open_transfers.map((r) => r.remittance_number).join(", "),
          })}
        </div>
      ) : null}
      <div className={FA.fields}>
        <Field label={t("From account")} required>
          <Picker searchable={false} value={d.from_bank_account} placeholder={t("Choose IDR account")} heading={t("From account")}
            options={from_accounts.map((a) => ({ value: a.value, label: a.name || a.label, meta: a.label }))}
            onPick={(o) => form.setData("from_bank_account", o.value)}
            extra={from ? <span className={FA.meta}>IDR</span> : null} />
        </Field>
        <Field label={t("Send to")} required>
          <Picker searchable={false} value={d.to_account} placeholder={t("Choose HQ account")} heading={t("Send to")}
            options={to_accounts.map((a) => ({ value: a.value, label: a.label, meta: a.number || "" }))}
            onPick={(o) => form.setData("to_account", o.value)}
            extra={<span className={FA.meta}>SAR</span>} />
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
            icon={<span className={FA.meta}>1 SAR =</span>} suffix={<span className={FA.meta}>IDR</span>} />
        </Field>
        <Field label={t("Book rate")}>
          <div className={cn(FA.control, FA.readOnly)}>
            <span className={cn(FA.text, FA.num, "font-semibold text-foreground")}>
              {fx_pool?.rate ? `1 SAR = ${fmt(fx_pool.rate)} IDR` : t("No client rupiah yet")}
            </span>
            <span className={FA.meta}>{t("Average of client payments")}</span>
          </div>
        </Field>
        <Field label={t("FX result")}>
          <div className={cn(FA.control, FA.readOnly)}>
            <span className={cn(FA.text, FA.num, profit > 0 && "font-semibold text-success-text", profit < 0 && "font-semibold text-danger-text")}>
              {profit == null ? t("Enter the amount and rate")
                : profit === 0 ? t("No gain or loss")
                  : t(profit > 0 ? "{n} IDR gain" : "{n} IDR loss", { n: fmt(Math.abs(profit)) })}
            </span>
            {fx?.originRate ? <span className={FA.meta}>{t("sent at {r}", { r: fmtDec(idr / sar, 2) })}</span> : null}
          </div>
        </Field>
      </div>
      {fx && fx.uncovered > 0 ? (
        <div className={cn(FA.alert, "text-warning-text")} role="status">
          {t("{n} SAR of this transfer has no client rupiah behind it, so no original rate.", { n: fmt(fx.uncovered) })}
        </div>
      ) : null}

      {d.plan.length ? (
        <>
          <div className={FA.sectionHead}>
            <span className={FA.caption}>{t("Planned reservations")}</span>
            {rate > 0 && (
              <button type="button" className="cursor-pointer border-0 bg-transparent p-0 text-[13px] font-semibold text-foreground hover:underline"
                onClick={() => form.setData("amount_idr", String(Math.round(planSar * rate)))}>
                {t("Use {n} IDR as amount", { n: fmt(Math.round(planSar * rate)) })}
              </button>
            )}
          </div>
          <PlanTable rows={d.plan} onChange={setPlan} onRemove={dropPlan} />
          {sar && sar !== planSar ? (
            <div className={cn(FA.alert, "text-muted-foreground")} role="status">
              {t("This transfer is {sar} SAR and the plan {plan} SAR. HQ allocates what arrives when it records the receipt.", { sar: fmt(sar), plan: fmt(planSar) })}
            </div>
          ) : null}
        </>
      ) : null}

      <NoteField label={t("Transfer proof")} optional>
        <FileDrop file={d.proof} onFile={set("proof")} title={t("Upload the bank transfer slip")}
          onTooBig={() => showToast(t("File too large. Maximum upload size is 3 MB."), "error")} />
      </NoteField>
      <NoteField label={t("Note")} value={d.note} onChange={set("note")} placeholder={t("Anything HQ should know about this transfer")} />

      <Foot why={why} cancelHref="/remittance/" submitLabel={t("Save remittance")} processing={form.processing} />
    </FormA>
  );
}

export default withStandaloneModal(FormBody, "/remittance/");
