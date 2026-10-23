import { useForm } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import { FormA, Field, Picker, DatePicker, AmountIn, ReadOnly, TextIn, FileDrop, NoteField, Foot, todayIso, FA, Caption, btnClass } from "../../components/shadcn/form-a.jsx";
import { cn } from "@/lib/utils";
import { showToast } from "../../components/shadcn/toast.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

// Refund to Client, the "Refund Form" artboard on the Record View HMS canvas.
// Two amounts: the SAR taken from the client's deposit (journal) and what the
// account actually paid in its own currency (cash book); the same number for
// a SAR account. Another user approves it before anything is posted.
function RefundBody({ client, accounts = [], initial, errors: serverErrors }) {
  const { t } = useI18n();
  const i = initial || {};
  const form = useForm({
    from_account: i.from_account || "",
    amount_sar: i.amount_sar || "",
    amount_paid: i.amount_paid || "",
    refund_date: i.refund_date || todayIso(),
    reason: i.reason || "",
    note: i.note || "",
    proof: null,
  });
  const d = form.data;
  const set = (k) => (v) => form.setData(k, v);
  const errors = { ...serverErrors, ...form.errors };
  const back = `/finance/clients/${client.pk}/statement/`;

  const account = accounts.find((a) => a.value === d.from_account);
  const foreign = account && account.currency !== "SAR";
  const amount = Number(d.amount_sar) || 0;
  const held = client.saldo_dana;

  const why = !account ? t("Choose the account the refund is paid from.")
    : !amount ? t("Enter how much of the deposit to refund.")
      : amount > held ? t("More than the {n} SAR deposit.", { n: fmt(held) })
        : foreign && !(Number(d.amount_paid) > 0) ? t("Enter the amount paid out in {ccy}.", { ccy: account.currency })
          : !d.reason.trim() ? t("Give the reason for the refund.")
            : "";

  const submit = (e) => {
    e.preventDefault();
    if (why) return;
    form.post(`/finance/clients/${client.pk}/refund/`, { forceFormData: true });
  };

  const error = Object.values(errors).filter(Boolean).map((x) => t(x)).join(" ");
  return (
    <FormA title={t("Refund to Client")} onSubmit={submit} error={error || null}>
      <div className={FA.fields}>
        <Field label={t("Client")} required>
          <ReadOnly><span style={{ color: "var(--foreground)", fontWeight: 600 }}>{client.name}</span></ReadOnly>
        </Field>
        <Field label={t("Paid from")} required>
          <Picker searchable={false} value={d.from_account} placeholder={t("Choose account")} heading={t("Paid from")}
            options={accounts.map((a) => ({ value: a.value, label: a.label, meta: [a.branch_name, a.currency].filter(Boolean).join(", ") }))}
            onPick={(o) => form.setData((x) => ({ ...x, from_account: o.value, amount_paid: "" }))}
            extra={account ? <span className={FA.meta}>{account.currency}</span> : null} />
        </Field>
        <Field label={t("From client deposit")} required>
          <AmountIn ccy="SAR" value={d.amount_sar} onChange={set("amount_sar")}
            hint={<button type="button" className={btnClass("o", true)} onClick={() => form.setData("amount_sar", String(Math.max(held, 0)))}>{t("All")}</button>} />
        </Field>
        {foreign ? (
          <Field label={t("Amount paid out")} required>
            <AmountIn ccy={account.currency} value={d.amount_paid} onChange={set("amount_paid")} />
          </Field>
        ) : (
          <Field label={t("Amount paid out")}>
            <ReadOnly>{t("Same as the deposit amount, paid in SAR")}</ReadOnly>
          </Field>
        )}
        <Field label={t("Refund date")} required>
          <DatePicker value={d.refund_date} onChange={set("refund_date")} label={t("Choose refund date")} />
        </Field>
        <Field label={t("Reason")} required>
          <TextIn value={d.reason} onChange={set("reason")} placeholder={t("For example, the client cancelled the trip")} />
        </Field>
      </div>

      <div className={FA.sectionHead}><Caption>{t("Deposit of {name}", { name: client.name })}</Caption></div>
      <div className="rf-eff">
        <div><span>{t("Deposit held now")}</span><span className={FA.num}>{fmt(held)} SAR</span></div>
        <div><span>{t("This refund")}</span><span className={FA.num}>−{fmt(amount)} SAR</span></div>
        <div className="res"><span>{t("Deposit left after approval")}</span><span className={cn(FA.num, held - amount < 0 && "neg")}><b>{fmt(held - amount)}</b> SAR</span></div>
      </div>

      <NoteField label={t("Transfer proof")} optional>
        <FileDrop file={d.proof} onFile={set("proof")} title={t("Upload the bank slip")}
          onTooBig={() => showToast(t("File too large. Maximum upload size is 3 MB."), "error")} />
      </NoteField>
      <NoteField label={t("Note")} value={d.note} onChange={set("note")} placeholder={t("Another user approves it before it is posted.")} />

      <Foot why={why} cancelHref={back} submitLabel={t("Submit for approval")} processing={form.processing} />
      <style>{EFF_CSS}</style>
    </FormA>
  );
}

export const EFF_CSS = `
.rf-eff { border: 1px solid var(--border); border-radius: 14px; padding: 6px 14px; font-size: 13px; }
.rf-eff > div { display: flex; justify-content: space-between; align-items: center; gap: 12px; min-height: 30px; color: var(--muted-foreground); }
.rf-eff .res { border-top: 1px solid var(--border); margin-top: 4px; padding-top: 6px; color: var(--foreground); font-weight: 500; }
.rf-eff .res b { font-weight: 700; font-size: 16px; }
.rf-eff .neg b { color: var(--danger-text); }
`;

export default withStandaloneModal(RefundBody, (p) => `/finance/clients/${p.client.pk}/statement/`);
