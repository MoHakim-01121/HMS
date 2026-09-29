import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import Table from "../../components/shadcn/table.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import { Icon } from "../../components/icons.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";

const CSS = `
.rec-line-row { display:grid; grid-template-columns: 120px 90px 1fr 110px 32px; gap:8px; align-items:start; }
@media (max-width: 640px) { .rec-line-row { grid-template-columns: 1fr; } }
.rec-line-del { display:flex; align-items:center; justify-content:center; height:36px; color:var(--muted-foreground); }
.rec-line-del:hover { color:var(--red); }
`;

const EMPTY_LINE = { line_date: new Date().toISOString().split("T")[0], direction: "in", description: "", amount: "" };

export default function List({ statements = [], account_choices = [] }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canEdit = perms.can("remittance", "edit");
  const openForm = useFormModal();

  const [newOpen, setNewOpen] = useState(false);
  const [form, setForm] = useState({
    account: "", period_start: "", period_end: "",
    opening_balance: "0", closing_balance: "", note: "",
  });
  const [lines, setLines] = useState([{ ...EMPTY_LINE }]);

  const updateLine = (i, key, val) => setLines(lines.map((l, idx) => (idx === i ? { ...l, [key]: val } : l)));
  const addLine = () => setLines([...lines, { ...EMPTY_LINE }]);
  const removeLine = (i) => setLines(lines.length > 1 ? lines.filter((_, idx) => idx !== i) : [{ ...EMPTY_LINE }]);

  const resetForm = () => {
    setForm({ account: "", period_start: "", period_end: "", opening_balance: "0", closing_balance: "", note: "" });
    setLines([{ ...EMPTY_LINE }]);
  };

  const submit = () => {
    const validLines = lines.filter((l) => Number(l.amount) > 0 && l.line_date);
    if (!form.account || !form.period_start || !form.period_end) return;
    router.post("/finance/reconciliation/new/", {
      ...form,
      lines: JSON.stringify(validLines),
    }, { onSuccess: () => { setNewOpen(false); resetForm(); } });
  };

  const currency = account_choices.find((a) => a.value === form.account)?.currency;
  const inCur = (label) => (currency ? `${t(label)} (${currency})` : t(label));

  const columns = [
    { header: t("Account"), render: (s) => s.account_label },
    { header: t("Period"), render: (s) => `${s.period_start} – ${s.period_end}` },
    {
      header: t("Status"),
      render: (s) => <StatusPill tone={s.is_fully_matched ? "green" : "yellow"} label={s.is_fully_matched ? t("Fully Matched") : t("Unmatched Lines")} />,
    },
    { header: t("Lines"), align: "right", render: (s) => `${s.lines_matched}/${s.lines_total}` },
    {
      header: t("Difference"), align: "right",
      render: (s) => (
        <span className="col-nowrap" style={{ color: s.difference !== 0 ? "var(--yellow)" : "var(--green)" }}>
          {s.difference?.toLocaleString("en-US")} {s.currency}
        </span>
      ),
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />

      <PageHeader
        title={t("Reconciliation")}
        sub={t("Match bank statements against recorded bank transactions.")}
        actions={canEdit ? (
          <>
            <Button size="lg" variant="outline" onClick={() => setNewOpen(true)}>+ {t("Type In")}</Button>
            <Button size="lg" onClick={() => openForm("/finance/reconciliation/import/")}>{t("Import CSV")}</Button>
          </>
        ) : null}
      />

      <div className="hms-list-card">
        {statements.length > 0 ? (
          <Table
            columns={columns}
            rows={statements}
            rowKey={(s) => s.id}
            onRowClick={(s) => router.visit(`/finance/reconciliation/${s.id}/`)}
          />
        ) : (
          <EmptyState iconName="wallet" title={t("No statements found")} sub={t("Import the bank's CSV export, or type a statement in, to start reconciling.")} />
        )}
      </div>

      {newOpen && (
        <Dialog open onOpenChange={(v) => { if (!v) setNewOpen(false); }}>
          <DialogContent className="sm:max-w-2xl form-modal-content" showCloseButton={false}>
            <style>{CSS}</style>
            <div className="hms-modal-head">
              <DialogTitle className="hms-modal-title">{t("New Statement")}</DialogTitle>
            </div>
            <div className="hms-modal-body">
              <form onSubmit={(e) => { e.preventDefault(); submit(); }} style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                <div className="fg-3">
                  <FormField label={t("Account")} name="account" required>
                    <Select value={form.account} onValueChange={(v) => setForm({ ...form, account: v })}>
                      <SelectTrigger className="w-full"><SelectValue placeholder={t("Select account...")} /></SelectTrigger>
                      <SelectContent>
                        {account_choices.map((a) => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </FormField>
                  <FormField label={t("Period Start")} name="period_start" type="date" required
                    value={form.period_start} onChange={(v) => setForm({ ...form, period_start: v })} />
                  <FormField label={t("Period End")} name="period_end" type="date" required
                    value={form.period_end} onChange={(v) => setForm({ ...form, period_end: v })} />
                  <FormField label={inCur("Opening Balance")} name="opening_balance" type="number"
                    value={form.opening_balance} onChange={(v) => setForm({ ...form, opening_balance: v })} />
                  <FormField label={inCur("Closing Balance")} name="closing_balance" type="number" required
                    value={form.closing_balance} onChange={(v) => setForm({ ...form, closing_balance: v })} />
                </div>

                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>{t("Lines")}</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {lines.map((l, i) => (
                      <div key={i} className="rec-line-row">
                        <Input type="date" value={l.line_date} onChange={(e) => updateLine(i, "line_date", e.target.value)} />
                        <Select value={l.direction} onValueChange={(v) => updateLine(i, "direction", v)}>
                          <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="in">{t("In")}</SelectItem>
                            <SelectItem value="out">{t("Out")}</SelectItem>
                          </SelectContent>
                        </Select>
                        <Input placeholder={t("Description")} value={l.description} onChange={(e) => updateLine(i, "description", e.target.value)} />
                        <Input type="number" placeholder={currency || "0"} value={l.amount} onChange={(e) => updateLine(i, "amount", e.target.value)} />
                        <button type="button" className="rec-line-del" onClick={() => removeLine(i)} aria-label={t("Remove line")}>
                          <Icon name="trash" size={14} />
                        </button>
                      </div>
                    ))}
                    <button type="button" className="exp-add-row" style={{ fontSize: 13, fontWeight: 600, color: "var(--primary)", alignSelf: "flex-start" }} onClick={addLine}>
                      {t("+ Add line")}
                    </button>
                  </div>
                </div>

                <FormField label={t("Note")} name="note">
                  <Textarea rows={2} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
                </FormField>
              </form>
            </div>
            <DialogFooter className="pay-footer">
              <Button variant="outline" onClick={() => setNewOpen(false)}>{t("Cancel")}</Button>
              <Button onClick={submit} disabled={!form.account || !form.period_start || !form.period_end}>{t("Save")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
