import { useForm } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import { FormA, Field, Picker, DatePicker, AmountIn, ReadOnly, TextIn, NoteField, Foot, todayIso, FA, Caption, btnClass } from "../../components/shadcn/form-a.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";
import { EFF_CSS } from "./ClientRefund.jsx";

// Move Deposit to Another Client, the "Deposit Transfer Form" artboard on the
// Record View HMS canvas: part of one client's deposit goes to another, shown
// as both deposits after approval. Another user approves it before it is posted.
function DepositTransferBody({ client, clients = [], initial, errors: serverErrors }) {
  const { t } = useI18n();
  const i = initial || {};
  const form = useForm({
    to_client: i.to_client || "", amount_sar: i.amount_sar || "",
    transfer_date: i.transfer_date || todayIso(), reason: i.reason || "", note: i.note || "",
  });
  const d = form.data;
  const set = (k) => (v) => form.setData(k, v);
  const errors = { ...serverErrors, ...form.errors };
  const back = `/finance/clients/${client.pk}/statement/`;

  const to = clients.find((c) => String(c.id) === String(d.to_client));
  const amount = Number(d.amount_sar) || 0;
  const held = client.saldo_dana;

  const why = !to ? t("Choose the client that receives the deposit.")
    : !amount ? t("Enter the amount to move.")
      : amount > held ? t("More than the {n} SAR deposit.", { n: fmt(held) })
        : !d.reason.trim() ? t("Give the reason for the move.")
          : "";

  const submit = (e) => {
    e.preventDefault();
    if (why) return;
    form.post(`/finance/clients/${client.pk}/deposit-transfer/`);
  };

  const error = Object.values(errors).filter(Boolean).map((x) => t(x)).join(" ");
  return (
    <FormA title={t("Move Deposit to Another Client")} onSubmit={submit} error={error || null}>
      <div className={FA.fields}>
        <Field label={t("From client")} required>
          <ReadOnly><span style={{ color: "var(--foreground)", fontWeight: 600 }}>{client.name}</span></ReadOnly>
        </Field>
        <Field label={t("To client")} required>
          <Picker value={String(d.to_client || "")} placeholder={t("Select a client")} heading={t("Clients")}
            options={clients.map((c) => ({ value: String(c.id), label: c.name, meta: [c.city, c.deposit ? t("deposit {n} SAR", { n: fmt(c.deposit) }) : null].filter(Boolean).join(", ") }))}
            onPick={(o) => form.setData("to_client", o.value)} />
        </Field>
        <Field label={t("Amount")} required>
          <AmountIn ccy="SAR" value={d.amount_sar} onChange={set("amount_sar")}
            hint={<button type="button" className={btnClass("o", true)} onClick={() => form.setData("amount_sar", String(Math.max(held, 0)))}>{t("All")}</button>} />
        </Field>
        <Field label={t("Transfer date")} required>
          <DatePicker value={d.transfer_date} onChange={set("transfer_date")} label={t("Choose transfer date")} />
        </Field>
        <Field label={t("Reason")} required className={FA.wide}>
          <TextIn value={d.reason} onChange={set("reason")} placeholder={t("For example, the agency moved this booking to its partner")} />
        </Field>
      </div>

      <div className={FA.sectionHead}><Caption>{t("Deposits after approval")}</Caption></div>
      <div className="rf-eff">
        <div><span>{client.name}</span><span className={FA.num}>{fmt(held)} {t("to")} <b style={{ color: held - amount < 0 ? "var(--danger-text)" : "var(--foreground)" }}>{fmt(held - amount)}</b> SAR</span></div>
        <div><span>{to ? to.name : t("Receiving client")}</span><span className={FA.num}>{to ? <>{fmt(to.deposit || 0)} {t("to")} <b style={{ color: "var(--foreground)" }}>{fmt((to.deposit || 0) + amount)}</b> SAR</> : "—"}</span></div>
      </div>

      <NoteField label={t("Note")} value={d.note} onChange={set("note")} placeholder={t("Another user approves it before it is posted.")} />

      <Foot why={why} cancelHref={back} submitLabel={t("Submit for approval")} processing={form.processing} />
      <style>{EFF_CSS}</style>
    </FormA>
  );
}

export default withStandaloneModal(DepositTransferBody, (p) => `/finance/clients/${p.client.pk}/statement/`);
