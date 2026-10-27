import { useForm } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField, { FieldGrid } from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/shadcn/ui/select.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";
import { Alert } from "../../components/shadcn/ui/alert.jsx";
import Page from "../../components/shadcn/page.jsx";

const FIELD_LABELS = {
  date: "Date", description: "Description", reference: "Reference", debit: "Debit (out)",
  credit: "Credit (in)", amount: "Amount", drcr: "DB/CR flag", balance: "Balance",
};
const NONE = "__none";

// Import a bank's CSV export: choose the account and file, check the preview
// (fix the column mapping if the guess is wrong), then save it as a statement.
// The file is read in the browser and sent as text, so a mapping change
// re-previews without uploading again.
function ImportFormBody({ account_choices = [], fields = [], form: initial = {}, preview = null, error }) {
  const { t } = useI18n();
  const form = useForm({
    account: initial.account || "",
    csv_text: initial.csv_text || "",
    filename: initial.filename || "",
    mapping: initial.mapping || "",
    period_start: initial.period_start || "",
    period_end: initial.period_end || "",
    opening_balance: initial.opening_balance || "",
    closing_balance: initial.closing_balance || "",
    note: initial.note || "",
    step: "preview",
  });
  const currency = account_choices.find((a) => a.value === form.data.account)?.currency;
  const mapping = form.data.mapping ? JSON.parse(form.data.mapping) : {};

  const send = (step, over = {}) => {
    form.transform((d) => ({ ...d, ...over, step }));
    form.post("/finance/reconciliation/import/", { preserveScroll: true });
  };

  const readFile = (file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      form.setData((d) => ({ ...d, csv_text: String(reader.result || ""), filename: file.name, mapping: "" }));
    };
    reader.readAsText(file);
  };

  const setColumn = (field, value) => {
    const next = { ...mapping };
    if (value === NONE) delete next[field];
    else next[field] = Number(value);
    send("preview", { mapping: JSON.stringify(next) });
  };

  const inOut = preview ? preview.lines.reduce((acc, l) => {
    acc[l.direction] += l.amount;
    return acc;
  }, { in: 0, out: 0 }) : null;
  const gap = preview && form.data.opening_balance !== "" && form.data.closing_balance !== ""
    ? Number(form.data.opening_balance) + inOut.in - inOut.out - Number(form.data.closing_balance)
    : null;

  return (
    <Page size="form">
      <PageBack href="/finance/reconciliation/" label={t("Back")} />
      <FormHeader
        kicker={t("Reconciliation")}
        title={t("Import Bank CSV")}
        sub={t("Upload the statement export from internet banking (Mandiri, BCA and similar). Amounts stay in the account's currency.")}
      />
      {error && <Alert variant="destructive" className="mb-3">{t(error)}</Alert>}
      <form method="post" onSubmit={(e) => { e.preventDefault(); send(preview ? "save" : "preview"); }}>
        <FormPanel>
          <FormSection label={t("File")}>
            <FieldGrid>
              <FormField label={t("Account")} name="account" required>
                <Select value={form.data.account} onValueChange={(v) => v && form.setData("account", v)}>
                  <SelectTrigger id="account" className="w-full"><SelectValue placeholder={t("Choose account")} /></SelectTrigger>
                  <SelectContent>
                    {account_choices.map((a) => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </FormField>
              <FormField label={t("CSV file")} name="csv" required hint={form.data.filename || t("Exported from internet banking")}>
                <Input id="csv" type="file" accept=".csv,.txt,text/csv" onChange={(e) => readFile(e.target.files[0])} />
              </FormField>
            </FieldGrid>
            {form.data.csv_text && (
              <Button type="button" variant="outline" onClick={() => send("preview")} disabled={form.processing}>
                {preview ? t("Preview again") : t("Preview")}
              </Button>
            )}
          </FormSection>

          {preview && (
            <>
              <FormSection label={t("Columns")}>
                <p className="m-0 mb-2.5 text-[13px] text-muted-foreground">{t("Guessed from the header row. Change a column if a value lands in the wrong place.")}</p>
                <div className="grid grid-cols-[repeat(auto-fill,minmax(170px,1fr))] gap-2.5">
                  {fields.map((f) => (
                    <FormField key={f} label={t(FIELD_LABELS[f] || f)} name={`map-${f}`}>
                      <Select value={mapping[f] != null ? String(mapping[f]) : NONE} onValueChange={(v) => v && setColumn(f, v)}>
                        <SelectTrigger id={`map-${f}`} className="w-full"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value={NONE}>{t("— not in file —")}</SelectItem>
                          {preview.headers.map((h, i) => <SelectItem key={i} value={String(i)}>{h || t("Column {n}", { n: i + 1 })}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </FormField>
                  ))}
                </div>
              </FormSection>

              <FormSection label={t("Preview")}>
                <p className="m-0 mb-2.5 text-[13px] text-muted-foreground">
                  {t("{n} lines read · in {in} · out {out}", { n: preview.lines.length, in: fmt(inOut.in), out: fmt(inOut.out) })}
                  {currency ? ` ${currency}` : ""}
                  {preview.skipped.length ? ` · ${t("{n} rows skipped (no date or amount, e.g. pending or balance rows)", { n: preview.skipped.length })}` : ""}
                </p>
                <div className="max-h-80 overflow-auto rounded-[10px] border border-border">
                  <table className="w-full border-collapse text-[13px] [:where(&)_th]:sticky [:where(&)_th]:top-0 [:where(&)_th]:bg-secondary [:where(&)_th]:px-2.5 [:where(&)_th]:py-[7px] [:where(&)_th]:text-left [:where(&)_th]:font-medium [:where(&)_th]:text-muted-foreground [:where(&)_td]:border-t [:where(&)_td]:border-border [:where(&)_td]:px-2.5 [:where(&)_td]:py-[7px] [:where(&)_td]:align-top">
                    <thead>
                      <tr><th>{t("Date")}</th><th>{t("Description")}</th><th className="text-right tabular-nums whitespace-nowrap">{t("In")}</th><th className="text-right tabular-nums whitespace-nowrap">{t("Out")}</th></tr>
                    </thead>
                    <tbody>
                      {preview.lines.slice(0, 50).map((l, i) => (
                        <tr key={i}>
                          <td className="whitespace-nowrap">{l.line_date}</td>
                          <td>{l.description}{l.reference ? <span className="text-muted-foreground"> · {l.reference}</span> : null}</td>
                          <td className="text-right tabular-nums whitespace-nowrap">{l.direction === "in" ? fmt(l.amount) : ""}</td>
                          <td className="text-right tabular-nums whitespace-nowrap">{l.direction === "out" ? fmt(l.amount) : ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {preview.lines.length > 50 ? <p className="m-0 mb-2.5 text-[13px] text-muted-foreground">{t("…and {n} more", { n: preview.lines.length - 50 })}</p> : null}
                </div>
              </FormSection>

              <FormSection label={t("Statement")}>
                <FieldGrid>
                  <FormField label={t("Period Start")} name="period_start" type="date" required value={form.data.period_start} onChange={(v) => form.setData("period_start", v)} />
                  <FormField label={t("Period End")} name="period_end" type="date" required value={form.data.period_end} onChange={(v) => form.setData("period_end", v)} />
                  <FormField label={currency ? `${t("Opening Balance")} (${currency})` : t("Opening Balance")} name="opening_balance" amount signed required
                    value={form.data.opening_balance} onChange={(v) => form.setData("opening_balance", v)} />
                  <FormField label={currency ? `${t("Closing Balance")} (${currency})` : t("Closing Balance")} name="closing_balance" amount signed required
                    value={form.data.closing_balance} onChange={(v) => form.setData("closing_balance", v)} />
                </FieldGrid>
                {gap ? (
                  <p className="mt-2 mb-3 text-[13px] text-yellow" role="status">
                    {t("Opening balance plus the lines doesn't reach the closing balance ({gap} {cur} apart). A line is missing or a balance was mistyped.", { gap: fmt(gap), cur: currency || "" })}
                  </p>
                ) : null}
                <FormField label={t("Note")} name="note" value={form.data.note} onChange={(v) => form.setData("note", v)} />
              </FormSection>
            </>
          )}

          <FormActions
            cancelHref="/finance/reconciliation/"
            submitLabel={preview ? (form.processing ? t("Saving…") : t("Save Statement")) : null}
            processing={form.processing || !form.data.account || !form.data.period_start || !form.data.period_end}
          />
        </FormPanel>
      </form>
    </Page>
  );
}

export default withStandaloneModal(ImportFormBody, "/finance/reconciliation/");
