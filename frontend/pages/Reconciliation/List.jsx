import { useState } from "react";
import { router } from "@inertiajs/react";
import { ListPage, Toolbar, SearchTool, FilterMenu, FilterSection, Check, Primary, TableCard, RowMenu, Pill, Amt, Pager, Empty, LIcon, useListNav, rowNav, Tr, Th, Td, Note, ToolButton } from "../../components/shadcn/list-a.jsx";
import FormField, { amountText, amountValue } from "../../components/shadcn/form-field.jsx";
import { Icon } from "../../components/icons.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogTitle,
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

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
// "2026-10-01".."2026-10-29" -> "01 to 29 Oct 2026"
const periodLabel = (a, b, t) => {
  const [ay, am, ad] = a.split("-"), [by, bm, bd] = b.split("-");
  if (ay === by && am === bm) return t("{a} to {b} {m} {y}", { a: ad, b: bd, m: MON[+bm - 1], y: by });
  return t("{a} to {b}", { a: `${ad} ${MON[+am - 1]}${ay !== by ? " " + ay : ""}`, b: `${bd} ${MON[+bm - 1]} ${by}` });
};

// Bank Reconciliation, as on the Record View HMS canvas: no KPIs; one row per
// bank statement with its closing balance, lines matched and the difference
// against the books. Statements come in by import, or typed in.
export default function List({ statements = [], account_choices = [], filters: f, counts = {}, account_counts = [], pagination }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canEdit = perms.can("bank", "edit");
  const openForm = useFormModal();
  const [go, loading] = useListNav("/finance/reconciliation/", f);
  const [draft, setDraft] = useState(f);
  const tog = (key, v) => setDraft((d) => ({ ...d, [key]: d[key].includes(v) ? d[key].filter((x) => x !== v) : [...d[key], v] }));

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

  return (
    <ListPage title={t("Bank Reconciliation")} loading={loading}>
      <Toolbar left={<Note>{t("Bank statements")}</Note>}>
        <SearchTool value={f.q} onSearch={(q) => go({ q })} placeholder={t("Search account or period")} />
        <FilterMenu count={(f.status.length ? 1 : 0) + (f.acct.length ? 1 : 0)} onOpen={() => setDraft(f)}
          onReset={() => setDraft({ ...draft, status: [], acct: [] })}
          onApply={() => go({ status: draft.status, acct: draft.acct })}>
          <FilterSection label={t("Status")}>
            <Check on={draft.status.includes("wip")} onClick={() => tog("status", "wip")} label={t("In progress")} count={counts.wip} />
            <Check on={draft.status.includes("done")} onClick={() => tog("status", "done")} label={t("Reconciled")} count={counts.done} />
          </FilterSection>
          {account_counts.length > 1 && (
            <FilterSection label={t("Account")}>
              {account_counts.map((a) => <Check key={a.name} on={draft.acct.includes(a.name)} onClick={() => tog("acct", a.name)} label={a.name} count={a.count} />)}
            </FilterSection>
          )}
        </FilterMenu>
        {canEdit && <ToolButton onClick={() => setNewOpen(true)}>{t("Type in")}</ToolButton>}
        {canEdit && <Primary label={t("Import statement")} onClick={() => openForm("/finance/reconciliation/import/")} onPrefetch={() => openForm.prefetch("/finance/reconciliation/import/")} />}
      </Toolbar>

      <TableCard cols={[null, 190, 200, 120, 180, 120, 56]}
        empty={!statements.length && <Empty title={t("No statements")} sub={t("Import the bank's CSV export, or type a statement in, to start reconciling.")} />}>
        <thead><Tr>
          <Th>{t("Account")}</Th><Th><span className="inline-flex items-center gap-1 font-semibold text-foreground">{t("Statement period")}{LIcon.sortDown}</span></Th>
          <Th className="text-right">{t("Statement closing balance")}</Th><Th className="text-right">{t("Lines matched")}</Th>
          <Th className="text-right">{t("Difference")}</Th><Th>{t("Status")}</Th><Th className="text-center">{t("Action")}</Th>
        </Tr></thead>
        <tbody>
          {statements.map((s) => (
            <Tr key={s.id} {...rowNav(`/finance/reconciliation/${s.id}/`)}>
              <Td className="truncate font-medium">{s.account_label}</Td>
              <Td>{periodLabel(s.period_start, s.period_end, t)}</Td>
              <Td className="text-right"><Amt code={s.currency} value={s.closing_balance} /></Td>
              <Td className="text-right">{t("{a} of {b}", { a: s.lines_matched, b: s.lines_total })}</Td>
              <Td className="text-right">{s.difference ? <span className="font-medium text-danger-text"><Amt code={s.currency} value={s.difference} /></span> : <span className="text-success-text">0</span>}</Td>
              <Td><Pill tone={s.state === "done" ? "green" : "amber-o"}>{s.state === "done" ? t("Reconciled") : t("In progress")}</Pill></Td>
              <Td className="text-center">
                <RowMenu label={t("Actions for {n}", { n: s.account_label })} items={[
                  { label: s.state === "done" ? t("Open") : t("Continue matching"), onClick: () => router.visit(`/finance/reconciliation/${s.id}/`) },
                ]} />
              </Td>
            </Tr>
          ))}
        </tbody>
      </TableCard>

      <Pager p={pagination} perPage={f.per} onPage={(page) => go({ page })} onPerPage={(per) => go({ per })} />

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
                  <FormField label={inCur("Opening Balance")} name="opening_balance" amount signed
                    value={form.opening_balance} onChange={(v) => setForm({ ...form, opening_balance: v })} />
                  <FormField label={inCur("Closing Balance")} name="closing_balance" amount signed required
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
                        <Input inputMode="numeric" aria-label={t("Amount")} placeholder={currency || "0"} value={amountText(l.amount)} onChange={(e) => updateLine(i, "amount", amountValue(e.target.value))} />
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
    </ListPage>
  );
}
