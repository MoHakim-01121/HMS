import { useContext } from "react";
import { useForm } from "@inertiajs/react";
import { FormModalContext, StandaloneFormModal } from "../../components/shadcn/form-modal.jsx";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { Checkbox } from "../../components/shadcn/ui/checkbox.jsx";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/shadcn/ui/select.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Add / edit a bank account (BankAccount). The ledger mapping defaults to the
// branch's cash ledger when left on "Automatic"; once money has touched the
// account (`locked`) its branch, currency and ledger mapping can no longer change.
// Reached directly (a failed submit re-renders it as its own page) it wraps
// itself in StandaloneFormModal, so the form keeps its one dialog presentation.
export default function BankAccountForm({
  account, edit, locked, errors: serverErrors = {},
  branch_choices = [], currency_choices = [], ledger_choices = [],
}) {
  const { t } = useI18n();
  const a = account || {};
  const form = useForm({
    branch: a.branch || "",
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
  const errors = { ...serverErrors, ...form.errors };
  const set = (k) => (v) => form.setData(k, v);
  const inModal = useContext(FormModalContext)?.inModal;

  const submit = (e) => {
    e.preventDefault();
    form.transform((d) => ({
      ...d,
      ledger_account: d.ledger_account === "auto" ? "" : d.ledger_account,
      show_on_invoice: d.show_on_invoice ? "on" : "",
      is_active: d.is_active ? "on" : "",
    }));
    // forceFormData: Django reads request.POST, which a JSON body leaves empty.
    form.post(edit ? `/finance/bank-accounts/${a.id}/edit/` : "/finance/bank-accounts/new/", { forceFormData: true });
  };

  const page = (
    <div className="form-page shadcn-root">
      <PageBack href="/finance/bank-accounts/" label={t("Back")} />
      <FormHeader
        kicker={t("Bank account")}
        title={edit ? t("Edit Bank Account") : t("New Bank Account")}
        sub={t("Accounts marked for invoices appear as “Pay to” on that branch's invoices.")}
      />

      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label={t("Account")}>
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField label={t("Branch")} name="branch" required error={errors.branch}
                hint={locked ? t("Locked: this account already has transactions.") : undefined}>
                <Select value={form.data.branch} onValueChange={set("branch")} disabled={locked}>
                  <SelectTrigger id="branch" className="w-full"><SelectValue placeholder={t("Pick a branch")} /></SelectTrigger>
                  <SelectContent>
                    {branch_choices.map((b) => <SelectItem key={b.value} value={b.value}>{b.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </FormField>
              <FormField label={t("Currency")} name="currency" required error={errors.currency}
                hint={locked ? t("Locked: this account already has transactions.") : undefined}>
                <Select value={form.data.currency} onValueChange={set("currency")} disabled={locked}>
                  <SelectTrigger id="currency" className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {currency_choices.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </FormField>
              <FormField label={t("Bank name")} name="bank_name" required value={form.data.bank_name}
                onChange={set("bank_name")} error={errors.bank_name} placeholder="Bank Mandiri" autoFocus />
              <FormField label={t("Account number")} name="account_identifier" required value={form.data.account_identifier}
                onChange={set("account_identifier")} error={errors.account_identifier} placeholder="1400550011119" inputMode="numeric" />
              <FormField span={2} label={t("Account holder")} name="account_name" value={form.data.account_name}
                onChange={set("account_name")} placeholder="PT Konoz United Indonesia" />
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, marginBottom: 8 }}>
              <Checkbox checked={form.data.show_on_invoice} onCheckedChange={(v) => form.setData("show_on_invoice", !!v)} />
              <span>{t("Show on invoice")} <span style={{ color: "var(--muted-foreground)" }}>— {t("listed under “Pay to” on this branch's invoices")}</span></span>
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
              <Checkbox checked={form.data.is_active} onCheckedChange={(v) => form.setData("is_active", !!v)} />
              <span>{t("Active")} <span style={{ color: "var(--muted-foreground)" }}>— {t("inactive accounts are hidden from invoices and payment pickers")}</span></span>
            </label>
          </FormSection>

          <FormSection label={t("Opening Balance")} sub={t("optional")}>
            <div className="fg-2">
              <FormField
                label={t("Balance ({currency})", { currency: form.data.currency || "" })} name="opening_balance" type="number"
                value={form.data.opening_balance} onChange={set("opening_balance")} error={errors.opening_balance}
                hint={t("What the bank actually held before the first transaction recorded here.")}
              />
              <FormField
                label={t("As of")} name="opening_date" type="date"
                value={form.data.opening_date} onChange={set("opening_date")} error={errors.opening_date}
              />
            </div>
          </FormSection>

          <FormSection label={t("Accounting")} sub={t("advanced")}>
            <FormField label={t("Ledger account")} name="ledger_account" error={errors.ledger_account}
              hint={locked ? t("Locked: this account already has transactions.") : t("Automatic uses the branch's cash ledger.")}>
              <Select value={form.data.ledger_account || "auto"} onValueChange={set("ledger_account")} disabled={locked}>
                <SelectTrigger id="ledger_account" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {!edit ? <SelectItem value="auto">{t("Automatic")}</SelectItem> : null}
                  {ledger_choices.map((l) => <SelectItem key={l.value} value={l.value}>{l.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </FormField>
            <div style={{ marginTop: 12 }}>
              <FormField label={t("Note")} name="note">
                <Textarea name="note" rows={2} value={form.data.note} onChange={(e) => form.setData("note", e.target.value)} />
              </FormField>
            </div>
          </FormSection>

          <FormActions
            cancelHref="/finance/bank-accounts/"
            submitLabel={edit ? t("Save Changes") : t("Add Account")}
            processing={form.processing} />
        </FormPanel>
      </form>
    </div>
  );

  return inModal ? page : <StandaloneFormModal closeHref="/finance/bank-accounts/">{page}</StandaloneFormModal>;
}
