import { useForm } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import { FormA, Field, Picker, DatePicker, AmountIn, ReadOnly, TextIn, FileDrop, NoteField, Foot, todayIso, FA } from "../../components/shadcn/form-a.jsx";
import { cn } from "@/lib/utils";
import { showToast } from "../../components/shadcn/toast.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

// New Transfer, the "Transfer Form" artboard on the Record View HMS canvas.
// Money moves between two accounts of one branch: office accounts, the cash
// a staff member holds, or to a staff member who holds none yet (their
// advance is opened on save). Same currency: one amount. Different
// currencies: both real amounts from the bank, the rate is derived and
// flagged when it strays from the last exchange of the pair.
function ExchangeFormBody({ account_choices = [], staff_choices = [], last_rates = {}, warning_pct = 3, form: initial = {}, error }) {
  const { t } = useI18n();
  const form = useForm({
    exchange_date: initial.exchange_date || todayIso(),
    from_account: initial.from_account || "",
    amount_out: initial.amount_out || "",
    to_account: initial.to_account || "",
    amount_in: initial.amount_in || "",
    reference: initial.reference || "",
    note: initial.note || "",
    proof: null,
  });
  const d = form.data;
  const set = (k) => (v) => form.setData(k, v);

  const from = account_choices.find((a) => a.value === d.from_account);
  const giving = staff_choices.find((s) => s.value === d.to_account);
  const toAcc = account_choices.find((a) => a.value === d.to_account);
  const to = giving ? { ...giving, currency: from?.currency, kind: "staff", fresh: true } : toAcc;
  const out = Number(d.amount_out) || 0;
  const inn = Number(d.amount_in) || 0;
  const cross = !!(from && to && from.currency !== to.currency);
  const sar = cross ? (from.currency === "SAR" ? out : inn) : 0;
  const other = cross ? (from.currency === "SAR" ? inn : out) : 0;
  const rate = cross && sar && other ? other / sar : null;
  const pairRate = cross && out && inn ? inn / out : null;
  const prev = pairRate ? last_rates[`${from.currency}>${to.currency}`] : null;
  const deviation = pairRate && prev ? (Math.abs(pairRate - prev) / prev) * 100 : null;
  const toStaff = to?.kind === "staff";
  const fromStaff = from?.kind === "staff";

  const meta = (a) => (a.kind === "staff"
    ? t("Holds {n} {ccy}", { n: fmt(a.balance), ccy: a.currency })
    : t("{no}, balance {n} {ccy}", { no: a.kind === "cash" ? t("Cash") : a.number || t("Bank"), n: fmt(a.balance), ccy: a.currency }));
  const label = (a) => (a.kind === "staff" ? t("Cash held by {name}", { name: a.label.replace(/ \([A-Z]{3}\)$/, "") }) : a.label);
  const office = t("Office accounts");
  const held = t("Held by staff");
  const give = t("Give to staff");
  const accountOpt = (a) => ({ value: a.value, label: label(a), meta: meta(a), group: a.kind === "staff" ? held : office });

  const fromOptions = account_choices
    .filter((a) => a.value !== d.to_account)
    .sort((a, b) => (a.kind === "staff") - (b.kind === "staff"))
    .map(accountOpt);
  // The target stays in the source's branch; a staff member gets an advance in
  // the source's currency, so those who already hold one are listed under
  // "Held by staff" instead.
  const toOptions = from ? [
    ...account_choices.filter((a) => a.branch === from.branch && a.value !== from.value)
      .sort((a, b) => (a.kind === "staff") - (b.kind === "staff")).map(accountOpt),
    ...staff_choices
      .filter((s) => s.branch === from.branch
        && !account_choices.some((a) => a.kind === "staff" && a.holder === s.user && a.currency === from.currency))
      .map((s) => ({ value: s.value, label: s.label, meta: t("No cash yet, account created on save"), group: give })),
  ] : [];

  const why = !from ? t("Choose the account the money leaves.")
    : !to ? t("Choose where the money goes.")
      : !out ? t("Enter the amount sent.")
        : out > from.balance && !fromStaff ? t("More than the {n} {ccy} in {name}.", { n: fmt(from.balance), ccy: from.currency, name: from.label })
          : out > Math.max(from.balance, 0) && fromStaff ? t("{name} holds only {n} {ccy}.", { name: label(from), n: fmt(Math.max(from.balance, 0)), ccy: from.currency })
            : cross && !inn ? t("Enter the amount received.")
              : "";

  const submit = (e) => {
    e.preventDefault();
    if (why) return;
    form.transform((x) => ({ ...x, amount_in: cross ? x.amount_in : x.amount_out }));
    form.post("/finance/exchanges/new/", { forceFormData: true });
  };

  const pickFrom = (o) => {
    const a = account_choices.find((x) => x.value === o.value);
    const keepTo = to && a && (giving ? giving.branch === a.branch : toAcc?.branch === a.branch);
    form.setData((x) => ({ ...x, from_account: o.value, to_account: keepTo ? x.to_account : "", amount_in: "" }));
  };

  return (
    <FormA title={t("New Transfer")} onSubmit={submit} error={error ? t(error) : null}>
      <div className={FA.fields}>
        <Field label={t("From account")} required>
          <Picker value={d.from_account} options={fromOptions} placeholder={t("Choose account")} onPick={pickFrom}
            extra={from ? <span className={FA.meta}>{fmt(from.balance)} {from.currency}</span> : null} />
        </Field>
        <Field label={t("To account")} required>
          <Picker value={d.to_account} options={toOptions} placeholder={from ? t("Choose account") : t("Choose the source first")}
            onPick={(o) => form.setData((x) => ({ ...x, to_account: o.value, amount_in: "" }))}
            emptyText={t("No other account in this branch.")}
            extra={to ? (to.fresh
              ? <><span className={FA.newTag}>{t("New")}</span><span className={FA.meta}>{to.currency}</span></>
              : <span className={FA.meta}>{fmt(to.balance)} {to.currency}</span>) : null} />
        </Field>
        <Field label={t("Amount sent")} required>
          <AmountIn ccy={from?.currency || "IDR"} value={d.amount_out} onChange={set("amount_out")} />
        </Field>
        {cross ? (
          <Field label={t("Amount received")} required>
            <AmountIn ccy={to.currency} value={d.amount_in} onChange={set("amount_in")}
              hint={rate ? `1 SAR = ${fmt(rate)} ${from.currency === "SAR" ? to.currency : from.currency}` : null} />
          </Field>
        ) : (
          <Field label={t("Amount received")}>
            <ReadOnly>{t("Same as sent, both in {ccy}", { ccy: from?.currency || "IDR" })}</ReadOnly>
          </Field>
        )}
        <Field label={t("Transfer date")} required>
          <DatePicker value={d.exchange_date} onChange={set("exchange_date")} label={t("Choose transfer date")} />
        </Field>
        <Field label={t("Reference")} optional>
          <TextIn value={d.reference} onChange={set("reference")}
            placeholder={toStaff || fromStaff ? t("For example, handover note no.") : t("Bank reference")} />
        </Field>
      </div>
      {deviation != null && deviation > warning_pct ? (
        <div className={cn(FA.alert, "text-warning-text")} role="status">
          {t("This rate is {pct}% away from the last {from}→{to} exchange ({prev}). Check both amounts.", {
            pct: deviation.toFixed(1), from: from.currency, to: to.currency,
            prev: prev.toLocaleString("en-US", { maximumFractionDigits: 4 }),
          })}
        </div>
      ) : null}

      <NoteField label={t("Transfer proof")} optional>
        <FileDrop file={d.proof} onFile={set("proof")} title={t("Upload the bank slip or a signed handover note")}
          onTooBig={() => showToast(t("File too large. Maximum upload size is 3 MB."), "error")} />
      </NoteField>
      <NoteField label={t("Note")} value={d.note} onChange={set("note")}
        placeholder={toStaff ? t("What the money is for, for example Sales team visit to Malang")
          : fromStaff ? t("For example, leftover from Malang visit") : t("Anything worth knowing later")} />

      <Foot why={why} cancelHref="/finance/exchanges/" submitLabel={t("Save transfer")} processing={form.processing} />
    </FormA>
  );
}

export default withStandaloneModal(ExchangeFormBody, "/finance/exchanges/");
