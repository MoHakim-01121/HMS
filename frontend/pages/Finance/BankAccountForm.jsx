import { useState } from "react";
import { useForm } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import { FormA, Field, Picker, DatePicker, AmountIn, TextIn, NoteField, Foot, FA } from "../../components/shadcn/form-a.jsx";
import { cn } from "@/lib/utils";
import { useI18n } from "../../utils/i18n.jsx";

const CUR_NAME = { IDR: "Rupiah", USD: "US dollar", SAR: "Riyal" };

// New / edit account, the "Bank Account Form" artboard on the Record View HMS
// canvas: a bank account or a cash box. The ledger mapping (under
// Accounting) defaults to the branch's cash ledger; once money has touched
// the account (`locked`) its branch, currency and ledger mapping stay put.
function BankAccountFormBody({
  account, edit, locked, errors: serverErrors = {},
  branch_choices = [], currency_choices = [], ledger_choices = [],
}) {
  const { t } = useI18n();
  const a = account || {};
  const form = useForm({
    kind: a.kind || "bank",
    name: a.name || "",
    branch: a.branch || (branch_choices.length === 1 ? branch_choices[0].value : ""),
    bank_name: a.bank_name || "",
    account_identifier: a.account_identifier || "",
    account_name: a.account_name || "",
    currency: a.currency || "IDR",
    ledger_account: a.ledger_account || "",
    show_on_invoice: !!a.show_on_invoice,
    is_active: edit ? !!a.is_active : a.is_active !== false,
    note: a.note || "",
    opening_balance: a.opening_balance ?? "",
    opening_date: a.opening_date || "",
  });
  const d = form.data;
  const set = (k) => (v) => form.setData(k, v);
  const errors = { ...serverErrors, ...form.errors };
  const [adv, setAdv] = useState(!!errors.ledger_account || (edit && !!a.ledger_account));
  const bank = d.kind === "bank";
  const hqOnlySar = d.branch === "pusat";

  const why = !d.branch ? t("Pick a branch.")
    : bank && !d.bank_name.trim() ? t("Enter the bank name.")
      : bank && !d.account_identifier.trim() ? t("Enter the account number.")
        : !bank && !d.name.trim() ? t("Name the cash box.")
          : bank && !d.account_name.trim() ? t("Enter the account holder.")
            : hqOnlySar && d.currency !== "SAR" ? t("HQ only holds SAR.")
              : Number(d.opening_balance) && !d.opening_date ? t("Pick the date of the opening balance.")
                : "";

  const submit = (e) => {
    e.preventDefault();
    if (why) return;
    form.transform((x) => ({
      ...x,
      ledger_account: x.ledger_account === "auto" ? "" : x.ledger_account,
      show_on_invoice: bank && x.show_on_invoice ? "on" : "",
      is_active: x.is_active ? "on" : "",
    }));
    // forceFormData: Django reads request.POST, which a JSON body leaves empty.
    form.post(edit ? `/finance/bank-accounts/${a.id}/edit/` : "/finance/bank-accounts/new/", { forceFormData: true });
  };

  const err = (k) => (errors[k] ? t(errors[k]) : null);
  const lockedHint = locked ? t("Locked: this account already has transactions.") : null;

  return (
    <FormA title={edit ? t("Edit Account") : t("New Account")} onSubmit={submit}>
      {!edit ? (
        <div className="ba-seg" role="radiogroup" aria-label={t("Account type")}>
          {[["bank", t("Bank account")], ["cash", t("Cash")]].map(([k, label]) => (
            <button key={k} type="button" role="radio" aria-checked={d.kind === k} className={d.kind === k ? "on" : ""}
              onClick={() => form.setData("kind", k)}>{label}</button>
          ))}
        </div>
      ) : null}
      <div className={cn(FA.fields, !edit && "mt-[18px]")}>
        {bank ? (
          <>
            <Field label={t("Bank name")} required error={err("bank_name")}>
              <TextIn value={d.bank_name} onChange={set("bank_name")} placeholder={t("For example, BSI")} autoFocus={!edit} invalid={!!errors.bank_name} />
            </Field>
            <Field label={t("Account number")} required error={err("account_identifier")}>
              <TextIn value={d.account_identifier} onChange={set("account_identifier")} placeholder={t("As printed on the statement")} inputMode="numeric" invalid={!!errors.account_identifier} />
            </Field>
          </>
        ) : null}
        <Field label={t("Account name")} required={!bank} optional={bank} error={err("name")}>
          <TextIn value={d.name} onChange={set("name")} placeholder={bank ? t("For example, BSI Surabaya") : t("For example, Kas Surabaya")} autoFocus={!edit && !bank} invalid={!!errors.name} />
        </Field>
        <Field label={t("Currency")} required error={err("currency")} hint={lockedHint}>
          <Picker searchable={false} value={d.currency} heading={t("Currency")}
            options={currency_choices.map((c) => ({ value: c, label: t(CUR_NAME[c] || c), meta: c }))}
            onPick={(o) => !locked && form.setData("currency", o.value)}
            extra={<span className={FA.meta}>{d.currency}</span>} />
        </Field>
        <Field label={t("Branch")} required error={err("branch")} hint={lockedHint}>
          <Picker searchable={false} value={d.branch} placeholder={t("Pick a branch")} heading={t("Branch")}
            options={branch_choices.map((b) => ({ value: b.value, label: b.label }))}
            onPick={(o) => !locked && form.setData("branch", o.value)} />
        </Field>
        {bank ? (
          <Field label={t("Account holder")} required>
            <TextIn value={d.account_name} onChange={set("account_name")} placeholder={t("Name on the account")} />
          </Field>
        ) : null}
        <Field label={t("Opening balance")} optional error={err("opening_balance")}>
          <AmountIn ccy={d.currency} value={d.opening_balance} onChange={set("opening_balance")} />
        </Field>
        <Field label={t("As of")} error={err("opening_date")}>
          <DatePicker value={d.opening_date} onChange={set("opening_date")} label={t("Choose the date of the opening balance")} />
        </Field>
      </div>

      {bank ? (
        <div className="ba-sw">
          <span><b>{t("Show on invoices")}</b><span>{t("Listed under Pay to on this branch's invoices")}</span></span>
          <button type="button" role="switch" aria-checked={d.show_on_invoice} aria-label={t("Show on invoices")}
            className={"ba-tg" + (d.show_on_invoice ? " on" : "")} onClick={() => form.setData("show_on_invoice", !d.show_on_invoice)} />
        </div>
      ) : null}
      {edit ? (
        <div className="ba-sw">
          <span><b>{t("Active")}</b><span>{t("Inactive accounts are hidden from invoices and payment pickers")}</span></span>
          <button type="button" role="switch" aria-checked={d.is_active} aria-label={t("Active")}
            className={"ba-tg" + (d.is_active ? " on" : "")} onClick={() => form.setData("is_active", !d.is_active)} />
        </div>
      ) : null}

      <div className="ba-adv">
        <button type="button" aria-expanded={adv} onClick={() => setAdv((v) => !v)}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M9 6l6 6-6 6" /></svg>
          {t("Accounting")}
        </button>
        {adv ? (
          <div className={cn(FA.fields, "mt-3")}>
            <Field label={t("Ledger account")} error={err("ledger_account")} hint={lockedHint} className={FA.wide}>
              <Picker value={d.ledger_account || "auto"} heading={t("Ledger account")}
                options={[...(!edit ? [{ value: "auto", label: t("Automatic"), meta: t("The branch's cash ledger for this currency") }] : []),
                  ...ledger_choices.map((l) => ({ value: l.value, label: l.label }))]}
                onPick={(o) => !locked && form.setData("ledger_account", o.value)} />
            </Field>
          </div>
        ) : null}
      </div>

      <NoteField label={t("Note")} value={d.note} onChange={set("note")} placeholder={t("Anything worth knowing about this account")} />

      <Foot why={why} cancelHref="/finance/bank-accounts/" submitLabel={edit ? t("Save changes") : t("Add account")} processing={form.processing} />
      <style>{`
.ba-seg { display: inline-flex; gap: 4px; padding: 4px; border-radius: 12px; background: var(--secondary); }
.ba-seg > button { height: 34px; padding: 0 16px; border: 0; border-radius: 9px; background: none; font: 500 13px var(--font-sans); color: var(--muted-foreground); cursor: pointer; }
.ba-seg > button.on { background: var(--card); color: var(--foreground); box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.ba-sw { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 18px; padding: 12px 16px; border: 1px solid var(--border); border-radius: 14px; }
.ba-sw + .ba-sw { margin-top: 10px; }
.ba-sw b { display: block; font-size: 14px; font-weight: 500; }
.ba-sw span span { display: block; font-size: 12px; color: var(--muted-foreground); }
.ba-tg { position: relative; flex: none; width: 38px; height: 22px; border: 0; border-radius: 999px; background: var(--input); cursor: pointer; padding: 0; transition: background 150ms ease; }
.ba-tg::after { content: ""; position: absolute; top: 3px; left: 3px; width: 16px; height: 16px; border-radius: 50%; background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.2); transition: transform 150ms ease; }
.ba-tg.on { background: var(--foreground); }
.ba-tg.on::after { transform: translateX(16px); }
.ba-adv { margin-top: 18px; }
.ba-adv > button { display: inline-flex; align-items: center; gap: 6px; padding: 0; border: 0; background: none; font: 600 13px var(--font-sans); color: var(--muted-foreground); cursor: pointer; }
.ba-adv > button svg { transition: transform 150ms ease; }
.ba-adv > button[aria-expanded="true"] svg { transform: rotate(90deg); }
.ba-seg > button:focus-visible, .ba-tg:focus-visible, .ba-adv > button:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
`}</style>
    </FormA>
  );
}

export default withStandaloneModal(BankAccountFormBody, "/finance/bank-accounts/");
