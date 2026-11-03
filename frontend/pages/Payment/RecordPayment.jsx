import { useState } from "react";
import { router } from "@inertiajs/react";
import { FaDialog, Field, Picker, DatePicker, AmountIn, ReadOnly, TextIn, FileDrop, NoteField, Foot, Segmented, PhoneCaption, todayIso, FA } from "../../components/shadcn/form-a.jsx";
import { usePhone } from "../../components/shadcn/list-a.jsx";
import { showToast } from "../../components/shadcn/toast.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

// Record Payment, the "Payment Form" artboard on the Record View HMS canvas:
// the client, what the money pays (an invoice, or a deposit), the branch and
// account it landed in (the account sets the currency), the amount with its
// SAR value, the date and method, and the proof.

// Cash or transfer only (canvas "HMS Mobile v2"); older payments may still
// read "Card", the list shows whatever was recorded.
// Stored as the legacy data has it, so the list filter has one value per method.
const METHODS = ["Bank Transfer", "Cash"];

// SAR value as the backend's convert_to_sar computes it (hw/utils.py): IDR is
// divided by the rate, other foreign currencies multiplied.
const toSar = (amount, ccy, rate) => {
  if (ccy === "SAR") return amount;
  if (!(rate > 0)) return null;
  return ccy === "IDR" ? amount / rate : amount * rate;
};

export default function RecordPayment({ onClose, client_choices = [], invoice_choices = [], account_choices = [] }) {
  const { t } = useI18n();
  const phone = usePhone();
  const [clientId, setClientId] = useState("");
  const [invoiceId, setInvoiceId] = useState("");
  const branches = [...new Map(account_choices.map((a) => [a.branch, a.branch_name || a.branch.toUpperCase()])).entries()];
  const [branch, setBranch] = useState(branches.length === 1 ? branches[0][0] : "");
  const [account, setAccount] = useState("");
  const [amount, setAmount] = useState("");
  const [rate, setRate] = useState("");
  const [date, setDate] = useState(todayIso());
  const [method, setMethod] = useState("Bank Transfer");
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const [proof, setProof] = useState(null);
  const [busy, setBusy] = useState(false);

  const acc = account_choices.find((a) => a.value === account);
  const ccy = acc?.currency || "SAR";
  const inv = invoice_choices.find((i) => String(i.id) === invoiceId);
  const theirs = invoice_choices.filter((i) => String(i.client_id) === clientId);
  const sar = toSar(Number(amount) || 0, ccy, Number(rate) || 0);

  const pickClient = (o) => {
    setClientId(o.value);
    if (inv && String(inv.client_id) !== o.value) setInvoiceId("");
  };
  const pickBranch = (o) => {
    setBranch(o.value);
    if (acc && acc.branch !== o.value) setAccount("");
  };
  const pickAccount = (o) => {
    const a = account_choices.find((x) => x.value === o.value);
    setAccount(o.value);
    if (a.currency === "SAR") setRate("");
  };

  const why = !clientId ? t("Choose the client who paid.")
    : !branch ? t("Choose where the money was received.")
      : !acc ? t("Choose the account it landed in.")
        : !(Number(amount) > 0) ? t("Enter the amount received.")
          : ccy !== "SAR" && !(Number(rate) > 0) ? t("Enter the exchange rate.")
            : !proof ? t("Attach the proof of payment.")
              : "";

  // On a phone the foot says what the payment does, as the canvas draws it.
  const left = inv && sar != null ? inv.remaining - sar : null;
  const invNo = inv?.label.split(" - ")[0];
  const effect = !phone || !(sar > 0) ? null
    : `${fmt(sar)} SAR · ${!inv ? t("Held on the client balance") : left <= 0 ? t("{n} will be paid in full.", { n: invNo }) : t("{n} keeps {v} SAR left.", { n: invNo, v: fmt(left) })}`;

  const submit = (e) => {
    e.preventDefault();
    if (why || busy) return;
    const fd = new FormData();
    const put = (k, v) => { if (v !== "" && v != null) fd.append(k, v); };
    put("client_id", clientId);
    put("invoice_id", invoiceId);
    put("payment_date", date);
    put("amount", amount);
    put("currency", ccy);
    put("exchange_rate", ccy === "SAR" ? "1" : rate);
    put("account", account);
    put("method", method);
    put("reference", reference.trim());
    put("note", note.trim());
    fd.append("proof", proof);
    setBusy(true);
    router.post("/finance/payments/record/", fd, { onFinish: () => setBusy(false), onSuccess: onClose });
  };

  return (
    <FaDialog title={t("Record Payment")} onClose={onClose}>
      <form method="post" onSubmit={submit} noValidate>
        <div className={FA.fields}>
          <Field label={t("Client")} required>
            <Picker value={clientId} placeholder={t("Select a client")} heading={t("Client")} onPick={pickClient}
              options={client_choices.map((c) => ({ value: String(c.id), label: c.name, meta: c.city || "" }))} />
          </Field>
          <Field label={t("Payment for")} required>
            <Picker searchable={theirs.length > 6} value={invoiceId || "deposit"} heading={t("Payment for")}
              placeholder={t("Select a client first")}
              onPick={(o) => setInvoiceId(o.value === "deposit" ? "" : o.value)}
              options={clientId ? [
                ...theirs.map((i) => ({ value: String(i.id), label: i.label.split(" - ")[0], meta: t("{n} SAR remaining", { n: fmt(i.remaining) }) })),
                { value: "deposit", label: t("Deposit, no invoice"), meta: t("Held on the client balance") },
              ] : []}
              extra={inv ? <span className={FA.meta}>{t("{n} SAR left", { n: fmt(inv.remaining) })}</span> : null} />
          </Field>
          <PhoneCaption>{t("Amount")}</PhoneCaption>
          <Field label={t("Received at")} required>
            <Picker searchable={false} value={branch} placeholder={t("Choose branch")} heading={t("Received at")}
              options={branches.map(([code, name]) => ({ value: code, label: name }))} onPick={pickBranch} />
          </Field>
          <Field label={t("Received into")} required>
            <Picker searchable={false} value={account} placeholder={branch ? t("Choose account") : t("Choose the branch first")}
              heading={t("Received into")} onPick={pickAccount}
              options={account_choices.filter((a) => a.branch === branch).map((a) => ({
                value: a.value, label: a.label, meta: a.kind === "cash" ? t("Cash, {c}", { c: a.currency }) : [a.number, a.currency].filter(Boolean).join(", "),
              }))}
              extra={acc ? <span className={FA.meta}>{acc.currency}</span> : null} />
          </Field>
          <Field label={t("Amount received")} required>
            <AmountIn ccy={ccy} value={amount} onChange={setAmount}
              hint={ccy !== "SAR" && sar ? `${fmt(sar)} SAR` : null} />
          </Field>
          {ccy !== "SAR" ? (
            <Field label={t("Exchange rate")} required>
              <TextIn value={rate} onChange={(v) => setRate(v.replace(/[^\d.]/g, ""))} inputMode="decimal"
                icon={<span className={FA.meta}>1 SAR =</span>} suffix={<span className={FA.meta}>{ccy}</span>} />
            </Field>
          ) : (
            <Field label={t("Exchange rate")}>
              <ReadOnly>{t("Not needed, received in SAR")}</ReadOnly>
            </Field>
          )}
          <PhoneCaption>{t("Received")}</PhoneCaption>
          <Field label={t("Payment date")} required>
            <DatePicker value={date} onChange={setDate} label={t("Choose payment date")} />
          </Field>
          <Field label={t("Method")} required>
            {phone ? (
              <Segmented wide label={t("Method")} value={method} onChange={setMethod}
                options={METHODS.map((m) => [m, t(m === "Bank Transfer" ? "Bank transfer" : m)])} />
            ) : (
              <Picker searchable={false} value={method} heading={t("Method")} onPick={(o) => setMethod(o.value)}
                options={METHODS.map((m) => ({ value: m, label: t(m === "Bank Transfer" ? "Bank transfer" : m) }))} />
            )}
          </Field>
          <Field label={t("Reference")} optional className={FA.wide}>
            <TextIn value={reference} onChange={setReference} placeholder={t("Bank transfer or receipt number")} />
          </Field>
        </div>

        <div className="mt-6 hidden phone:block"><PhoneCaption>{t("Proof and note")}</PhoneCaption></div>
        <NoteField label={t("Proof of payment")} required>
          <FileDrop file={proof} onFile={setProof} title={t("Upload the transfer slip or receipt")}
            onTooBig={() => showToast(t("File too large. Maximum upload size is 3 MB."), "error")} />
        </NoteField>
        <NoteField label={t("Note")} value={note} onChange={setNote} placeholder={t("Anything the finance team should know")} />

        <Foot why={why} note={effect} onCancel={onClose} submitLabel={t("Record payment")} processing={busy} />
      </form>
    </FaDialog>
  );
}
