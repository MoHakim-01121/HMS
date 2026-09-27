import { useState } from "react";
import { router } from "@inertiajs/react";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import KebabMenu from "../../components/shadcn/kebab-menu.jsx";
import { RvBack, RvHero, RvCard, RvSection, RvRail } from "../../components/shadcn/record-view.jsx";
import { Icon } from "../../components/icons.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmtDate } from "../../utils/format.js";
import { usePerms } from "../../utils/perms.js";

export default function Detail({ expense = {}, account_choices = [], journal_entries = [] }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canEdit = perms.can("expenses", "edit");
  const canDelete = perms.can("expenses", "delete");
  const [confirm, confirmDialog] = useConfirm();
  const [payOpen, setPayOpen] = useState(false);
  const [payForm, setPayForm] = useState({
    amount: "", payment_date: new Date().toISOString().split("T")[0],
    account: "", reference: "",
  });

  const handleVoid = () => {
    confirm({
      title: t("Void Expense"),
      message: t("Void expense {number}? This reverses every posted entry and cannot be undone.", {
        number: expense.expense_number,
      }),
      danger: true,
      onConfirm: () => router.post(`/finance/expenses/${expense.id}/void/`),
    });
  };

  const submitPay = () => {
    router.post(`/finance/expenses/${expense.id}/pay/`, payForm, {
      onSuccess: () => { setPayOpen(false); setPayForm({ amount: "", payment_date: new Date().toISOString().split("T")[0], account: "", reference: "" }); },
    });
  };

  const pill = {
    draft: { label: t("Draft"), tone: "gray" },
    posted: { label: t("Posted"), tone: "blue" },
    partially_paid: { label: t("Partially Paid"), tone: "yellow" },
    paid: { label: t("Paid"), tone: "green" },
    voided: { label: t("Voided"), tone: "gray" },
  }[expense.status] || { label: expense.status_display, tone: "gray" };

  const noteByStatus = {
    posted: {
      icon: <Icon name="alert-circle" size={13} strokeWidth={2} />,
      iconBg: "var(--yellow)",
      title: t("Awaiting payment"),
      text: t("This expense has not been paid yet."),
    },
    partially_paid: {
      icon: <Icon name="alert-circle" size={13} strokeWidth={2} />,
      iconBg: "var(--yellow)",
      title: t("Partially paid"),
      text: t("{n} SAR still outstanding.", { n: expense.outstanding_sar?.toLocaleString("en-US") }),
    },
    paid: {
      icon: <Icon name="check" size={12} strokeWidth={2.4} />,
      iconBg: "var(--green)",
      title: t("Paid in full"),
      text: t("This expense has been fully settled."),
    },
    voided: {
      icon: <Icon name="alert" size={13} strokeWidth={2} />,
      iconBg: "var(--muted-foreground)",
      title: t("Voided"),
      text: t("This expense was voided."),
    },
  };
  const note = noteByStatus[expense.status] || { icon: <Icon name="alert" size={13} strokeWidth={2} />, iconBg: "var(--muted-foreground)", title: pill.label };

  const primaryActions = [];
  if (canEdit && expense.outstanding_sar > 0 && expense.status !== "voided") {
    primaryActions.push(
      <button key="pay" className="hms-rv-btn primary" onClick={() => setPayOpen(true)}>{t("Add Payment")}</button>,
    );
  }

  const menuItems = [];
  if (canDelete && expense.status !== "voided") {
    menuItems.push({ label: t("Void"), danger: true, onClick: handleVoid });
  }

  const sections = [
    {
      title: t("Lines"),
      meta: `${expense.lines?.length || 0}`,
      body: (
        <DetailTable
          columns={[
            { header: t("Category"), render: (l) => l.category_name },
            { header: t("Description"), render: (l) => l.description || "—" },
            { header: t("Amount (SAR)"), align: "right", render: (l) => l.amount_sar?.toLocaleString("en-US") },
          ]}
          rows={expense.lines || []}
          rowKey={(l) => l.id}
        />
      ),
    },
  ];
  if (expense.note) {
    sections.push({ title: t("Note"), body: <div className="hms-rv-railtext">{expense.note}</div> });
  }
  if (expense.payments?.length > 0) {
    sections.push({
      title: t("Payments"),
      meta: `${expense.payments.length}`,
      body: (
        <DetailTable
          columns={[
            { header: t("Date"), render: (p) => p.payment_date },
            { header: t("Account"), render: (p) => p.account_name || "—" },
            { header: t("Amount (SAR)"), align: "right", render: (p) => p.amount_sar?.toLocaleString("en-US") },
            { header: t("Reference"), render: (p) => p.reference || "—" },
            { header: t("Status"), render: (p) => p.status_display },
          ]}
          rows={expense.payments}
          rowKey={(p) => p.id}
        />
      ),
    });
  }
  if (journal_entries.length > 0) {
    sections.push({
      title: t("Journal Entries"),
      meta: `${journal_entries.length}`,
      body: (
        <DetailTable
          columns={[
            { header: t("Entry #"), render: (e) => <span className="font-mono text-xs">{e.entry_number}</span> },
            { header: t("Type"), render: (e) => e.entry_type_display },
            { header: t("Description"), render: (e) => e.description },
            { header: t("Date"), render: (e) => e.entry_date },
            { header: t("Debit"), align: "right", render: (e) => e.total_debit?.toLocaleString("en-US") },
            { header: t("Credit"), align: "right", render: (e) => e.total_credit?.toLocaleString("en-US") },
          ]}
          rows={journal_entries}
          rowKey={(e) => e.id}
        />
      ),
    });
  }

  const expenseDate = fmtDate(expense.expense_date) || null;

  return (
    <div className="page shadcn-root hms-rv-page">
      <RvBack href="/finance/expenses/" label={t("Back")} />

      <RvHero
        kicker={expense.expense_number}
        badge={pill}
        title={expense.vendor || expense.description || expense.expense_number}
        facts={[
          { k: t("Branch"), v: expense.branch_name },
          ...(expenseDate ? [{ k: t("Date"), v: expenseDate }] : []),
          { k: t("Total"), v: `${expense.total_amount_sar?.toLocaleString("en-US")} SAR` },
        ]}
        note={note}
        actions={<>{primaryActions}<KebabMenu items={menuItems} /></>}
      />

      <div className="hms-rv-grid">
        <div className="hms-rv-col">
          <RvCard>
            {sections.map((s, i) => (
              <RvSection key={s.title} title={s.title} meta={s.meta} first={i === 0}>
                {s.body}
              </RvSection>
            ))}
          </RvCard>
        </div>

        <RvRail
          rows={[
            { k: t("Branch"), v: expense.branch_name },
            expense.vendor ? { k: t("Vendor"), v: expense.vendor } : null,
            expenseDate ? { k: t("Date"), v: expenseDate } : null,
            { k: t("Currency"), v: expense.currency },
            { k: t("Total"), v: `${expense.total_amount_sar?.toLocaleString("en-US")} SAR` },
            { k: t("Paid"), v: `${expense.paid_sar?.toLocaleString("en-US")} SAR` },
            expense.outstanding_sar > 0 ? { k: t("Outstanding"), v: `${expense.outstanding_sar?.toLocaleString("en-US")} SAR` } : null,
            { k: t("Created by"), v: expense.created_by },
          ].filter(Boolean)}
        />
      </div>

      {confirmDialog}

      {payOpen && (
        <Dialog open onOpenChange={(v) => { if (!v) setPayOpen(false); }}>
          <DialogContent className="hms-dialog">
            <DialogHeader>
              <DialogTitle>{t("Add Payment")}</DialogTitle>
            </DialogHeader>
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <FormField label={t("Amount")} name="amount" type="number" required
                value={payForm.amount} placeholder={String(expense.outstanding_sar || "")}
                onChange={(v) => setPayForm({ ...payForm, amount: v })}
                hint={t("Outstanding: {n} SAR", { n: expense.outstanding_sar?.toLocaleString("en-US") })} />
              <FormField label={t("Date")} name="payment_date" type="date" required
                value={payForm.payment_date} onChange={(v) => setPayForm({ ...payForm, payment_date: v })} />
              <FormField label={t("Paid from")} name="account" required>
                <Select value={payForm.account} onValueChange={(v) => setPayForm({ ...payForm, account: v })}>
                  <SelectTrigger className="w-full"><SelectValue placeholder={t("Select account...")} /></SelectTrigger>
                  <SelectContent>
                    {account_choices.filter((a) => a.currency === expense.currency).map((a) => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </FormField>
              <FormField label={t("Reference")} name="reference"
                value={payForm.reference} onChange={(v) => setPayForm({ ...payForm, reference: v })} />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setPayOpen(false)}>{t("Cancel")}</Button>
              <Button onClick={submitPay} disabled={!payForm.amount || !payForm.account}>{t("Record Payment")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
