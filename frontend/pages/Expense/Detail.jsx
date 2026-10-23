import { useState } from "react";
import { cn } from "@/lib/utils";
import { router } from "@inertiajs/react";
import { DPage, DTop, DHead, DBanner, DBtn, DChip, DCard, DA, DC } from "../../components/shadcn/detail-a.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtDate } from "../../utils/format.js";
import { usePerms } from "../../utils/perms.js";

const idr = (n) => `${fmt(n)} IDR`;
const today = () => new Date().toISOString().split("T")[0];

// Expense detail, the "Expense Detail" artboard on the Record View HMS canvas.
// An expense is recorded by Finance in rupiah, approved by Finance, a Manager
// or an Admin, then paid by Finance from one of the branch's rupiah accounts;
// the strip above the card carries the step that is due.
export default function Detail({ expense = {}, account_choices = [], journal_entries = [] }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canApprove = perms.can("expenses", "approve");
  const canPay = perms.can("expenses", "edit");
  const canVoid = perms.can("expenses", "delete");
  const [dialog, setDialog] = useState(null); // "pay" | "reject" | "void"
  const [payForm, setPayForm] = useState({ account: account_choices.length === 1 ? account_choices[0].value : "", payment_date: today(), reference: "" });
  const [reason, setReason] = useState("");
  const close = () => { setDialog(null); setReason(""); };
  const post = (action, data = {}) => router.post(`/finance/expenses/${expense.id}/${action}/`, data, { onSuccess: close });

  const status = expense.status;
  const pill = {
    submitted: { label: t("Awaiting approval"), tone: "amber" },
    approved: { label: t("Approved"), tone: "info" },
    paid: { label: t("Paid"), tone: "green" },
    rejected: { label: t("Rejected"), tone: "gray" },
    voided: { label: t("Voided"), tone: "gray" },
  }[status] || { label: expense.status_display, tone: "gray" };

  let banner = null;
  if (status === "submitted") {
    banner = (
      <DBanner actions={canApprove ? <DBtn primary onClick={() => post("approve")}>{t("Approve")}</DBtn> : null}>
        <b>{idr(expense.total_amount)}</b>{" "}
        {expense.paid_with
          ? t("was paid with {account}. It is booked as soon as it is approved.", { account: expense.paid_with })
          : t("is waiting for approval by Finance, a manager or an admin.")}
      </DBanner>
    );
  } else if (status === "approved") {
    banner = (
      <DBanner actions={canPay ? <DBtn primary onClick={() => setDialog("pay")}>{t("Pay")}</DBtn> : null}>
        <b>{idr(expense.total_amount)}</b> {t("is approved and waiting to be paid from a branch rupiah account.")}
      </DBanner>
    );
  } else if (status === "rejected" || status === "voided") {
    banner = (
      <DBanner tone="gray">
        <b>{status === "rejected" ? t("Rejected.") : t("Voided.")}</b>{" "}
        {expense.decision_note || (status === "rejected" ? t("No money moved.") : t("The payment was reversed."))}
      </DBanner>
    );
  }

  const menu = [
    (status === "submitted" || status === "approved") && canApprove && { label: t("Reject"), icon: "close", danger: true, onClick: () => setDialog("reject") },
    status === "paid" && canVoid && { label: t("Void"), icon: "close", danger: true, onClick: () => setDialog("void") },
  ];

  const paid = status === "paid" || status === "voided";
  const expenseDate = fmtDate(expense.expense_date) || null;
  const lines = expense.lines || [];

  return (
    <DPage>
      <DTop href="/finance/expenses/" />

      {banner}

      <DHead
        title={expense.expense_number}
        badge={pill}
        menu={menu}
        chips={expense.proof_url ? [<DChip key="proof" href={expense.proof_url} icon="clip" label={t("Open receipt")}>{decodeURIComponent(expense.proof_url.split("/").pop())}</DChip>] : null}
        cols={3}
        facts={[
          { k: t("Vendor"), v: expense.vendor || t("Not set") },
          { k: t("Total"), v: idr(expense.total_amount), strong: true },
          { k: t("Cost date"), v: expenseDate || t("Not set") },
          { k: t("Branch"), v: expense.branch_name },
          expense.spent_by && { k: t("Spent by"), v: expense.spent_by },
          { k: t("Paid with"), v: expense.paid_with || t("The office, after approval") },
          { k: t("Recorded by"), v: expense.created_by },
          expense.decided_by && { k: status === "rejected" ? t("Rejected by") : t("Approved by"), v: expense.decided_by },
          paid && { k: t("Booked"), v: `${fmt(expense.total_amount_sar)} SAR` },
          expense.payment && { k: t("Paid from"), v: expense.payment.account_name },
          expense.payment && { k: t("Paid on"), v: fmtDate(expense.payment.payment_date) },
          expense.payment?.reference && { k: t("Reference"), v: expense.payment.reference },
        ]}
        note={expense.note ? { text: expense.note } : null}
      />

      <DCard title={t("Lines")} count={lines.length}>
        <div className={DA.scroll}>
          <table data-slot="detail-table" className={DA.table}>
            <thead>
              <tr>
                <th>{t("Category")}</th><th>{t("Description")}</th><th>{t("Receipt")}</th>
                <th className={DC.n}>{t("Amount (IDR)")}</th>
                {paid ? <th className={DC.n}>{t("Booked (SAR)")}</th> : null}
              </tr>
            </thead>
            <tbody>
              {lines.map((l) => (
                <tr key={l.id}>
                  <td className={DC.strong}>{l.category_name}</td>
                  <td>{l.description || ""}</td>
                  <td>
                    {l.receipts?.length ? l.receipts.map((r) => (
                      <a key={r.url} href={r.url} target="_blank" rel="noreferrer" style={{ display: "block" }}>{r.name}</a>
                    )) : l.no_receipt_reason ? (
                      <span style={{ color: "var(--warning-text)" }}>{t("No receipt")}<span className={DC.sub}>{l.no_receipt_reason}</span></span>
                    ) : <span className={DC.mut}>{expense.proof_url ? t("See the expense receipt") : ""}</span>}
                  </td>
                  <td className={DC.n}>{fmt(l.amount)}</td>
                  {paid ? <td className={cn(DC.n, DC.mut)}>{fmt(l.amount_sar)}</td> : null}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={3} style={{ paddingBottom: 16 }}>{t("Total")}</td>
                <td className={DC.n} style={{ paddingBottom: 16 }}>{idr(expense.total_amount)}</td>
                {paid ? <td className={DC.n} style={{ paddingBottom: 16 }}>{fmt(expense.total_amount_sar)} SAR</td> : null}
              </tr>
            </tfoot>
          </table>
        </div>
      </DCard>

      {journal_entries.length ? (
        <DCard title={t("Journal Entries")} count={journal_entries.length}>
          <div className={DA.scroll}>
            <table data-slot="detail-table" className={DA.table}>
              <thead><tr><th>{t("Entry #")}</th><th>{t("Type")}</th><th>{t("Description")}</th><th>{t("Date")}</th><th className={DC.n}>{t("Debit")}</th><th className={DC.n}>{t("Credit")}</th></tr></thead>
              <tbody>
                {journal_entries.map((e) => (
                  <tr key={e.id}>
                    <td className={DC.mono}>{e.entry_number}</td>
                    <td className={DC.strong}>{e.entry_type_display}</td>
                    <td className={DC.mut}>{e.description}</td>
                    <td className={DC.nw}>{e.entry_date}</td>
                    <td className={DC.n}>{fmt(e.total_debit)}</td>
                    <td className={DC.n}>{fmt(e.total_credit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </DCard>
      ) : null}

      {dialog === "pay" && (
        <Dialog open onOpenChange={(v) => { if (!v) close(); }}>
          <DialogContent>
            <DialogHeader><DialogTitle>{t("Pay {number}", { number: expense.expense_number })}</DialogTitle></DialogHeader>
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>{idr(expense.total_amount)}</div>
              <FormField label={t("Paid from")} name="account" required
                hint={t("The SAR value is taken from the account's own rate; no rate to type.")}>
                <Select value={payForm.account} onValueChange={(v) => setPayForm({ ...payForm, account: v })}>
                  <SelectTrigger className="w-full"><SelectValue placeholder={t("Select account...")} /></SelectTrigger>
                  <SelectContent>
                    {account_choices.map((a) => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </FormField>
              <FormField label={t("Transfer date")} name="payment_date" type="date" required
                value={payForm.payment_date} onChange={(v) => setPayForm({ ...payForm, payment_date: v })} />
              <FormField label={t("Reference")} name="reference"
                value={payForm.reference} onChange={(v) => setPayForm({ ...payForm, reference: v })} />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={close}>{t("Cancel")}</Button>
              <Button onClick={() => post("pay", payForm)} disabled={!payForm.account}>{t("Record Payment")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {(dialog === "reject" || dialog === "void") && (
        <Dialog open onOpenChange={(v) => { if (!v) close(); }}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{dialog === "reject" ? t("Reject {number}", { number: expense.expense_number }) : t("Void {number}", { number: expense.expense_number })}</DialogTitle>
            </DialogHeader>
            <p style={{ fontSize: 13, color: "var(--muted-foreground)", margin: 0 }}>
              {dialog === "reject"
                ? t("No money moves. The expense stays on record as rejected.")
                : t("The payment and its journal are reversed; the rupiah returns to the account.")}
            </p>
            <FormField label={t("Reason")} name="reason">
              <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
            </FormField>
            <DialogFooter>
              <Button variant="outline" onClick={close}>{t("Cancel")}</Button>
              <Button variant="destructive" onClick={() => post(dialog, { reason })}>{dialog === "reject" ? t("Reject") : t("Void")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </DPage>
  );
}
