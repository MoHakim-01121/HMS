import { useForm } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/shadcn/ui/select.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

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
    <div className="form-page shadcn-root">
      <PageBack href="/finance/reconciliation/" label={t("Back")} />
      <FormHeader
        kicker={t("Reconciliation")}
        title={t("Import Bank CSV")}
        sub={t("Upload the statement export from internet banking (Mandiri, BCA and similar). Amounts stay in the account's currency.")}
      />
      {error && <div className="alert alert-error" style={{ marginBottom: 12 }}>{t(error)}</div>}
      <form method="post" onSubmit={(e) => { e.preventDefault(); send(preview ? "save" : "preview"); }}>
        <FormPanel>
          <FormSection label={t("File")}>
            <div className="fg-2">
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
            </div>
            {form.data.csv_text && (
              <Button type="button" variant="outline" onClick={() => send("preview")} disabled={form.processing}>
                {preview ? t("Preview again") : t("Preview")}
              </Button>
            )}
          </FormSection>

          {preview && (
            <>
              <FormSection label={t("Columns")}>
                <p className="imp-hint">{t("Guessed from the header row. Change a column if a value lands in the wrong place.")}</p>
                <div className="imp-map">
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
                <p className="imp-hint">
                  {t("{n} lines read · in {in} · out {out}", { n: preview.lines.length, in: fmt(inOut.in), out: fmt(inOut.out) })}
                  {currency ? ` ${currency}` : ""}
                  {preview.skipped.length ? ` · ${t("{n} rows skipped (no date or amount, e.g. pending or balance rows)", { n: preview.skipped.length })}` : ""}
                </p>
                <div className="imp-table">
                  <table>
                    <thead>
                      <tr><th>{t("Date")}</th><th>{t("Description")}</th><th className="r">{t("In")}</th><th className="r">{t("Out")}</th></tr>
                    </thead>
                    <tbody>
                      {preview.lines.slice(0, 50).map((l, i) => (
                        <tr key={i}>
                          <td className="nw">{l.line_date}</td>
                          <td>{l.description}{l.reference ? <span className="dim"> · {l.reference}</span> : null}</td>
                          <td className="r">{l.direction === "in" ? fmt(l.amount) : ""}</td>
                          <td className="r">{l.direction === "out" ? fmt(l.amount) : ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {preview.lines.length > 50 ? <p className="imp-hint">{t("…and {n} more", { n: preview.lines.length - 50 })}</p> : null}
                </div>
              </FormSection>

              <FormSection label={t("Statement")}>
                <div className="fg-2">
                  <FormField label={t("Period Start")} name="period_start" type="date" required value={form.data.period_start} onChange={(v) => form.setData("period_start", v)} />
                  <FormField label={t("Period End")} name="period_end" type="date" required value={form.data.period_end} onChange={(v) => form.setData("period_end", v)} />
                  <FormField label={currency ? `${t("Opening Balance")} (${currency})` : t("Opening Balance")} name="opening_balance" type="number" required
                    value={form.data.opening_balance} onChange={(v) => form.setData("opening_balance", v)} />
                  <FormField label={currency ? `${t("Closing Balance")} (${currency})` : t("Closing Balance")} name="closing_balance" type="number" required
                    value={form.data.closing_balance} onChange={(v) => form.setData("closing_balance", v)} />
                </div>
                {gap ? (
                  <p className="imp-warn" role="status">
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
      <style>{CSS}</style>
    </div>
  );
}

const CSS = `
.imp-hint { margin: 0 0 10px; font-size: 12.5px; color: var(--muted-foreground); }
.imp-warn { margin: 8px 0 12px; font-size: 12.5px; color: var(--yellow); }
.imp-map { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 10px; }
.imp-table { max-height: 320px; overflow: auto; border: 1px solid var(--border); border-radius: 10px; }
.imp-table table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.imp-table th { position: sticky; top: 0; background: var(--secondary); text-align: left; font-weight: 500; color: var(--muted-foreground); padding: 7px 10px; }
.imp-table td { padding: 7px 10px; border-top: 1px solid var(--border); vertical-align: top; }
.imp-table .r { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.imp-table .nw { white-space: nowrap; }
.imp-table .dim { color: var(--muted-foreground); }
`;

export default withStandaloneModal(ImportFormBody, "/finance/reconciliation/");
