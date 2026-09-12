import { useState } from "react";
import { router } from "@inertiajs/react";
import { DvLink } from "../../components/shadcn/item-row.jsx";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import KebabMenu from "../../components/shadcn/kebab-menu.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import { RvBack, RvHero, RvCard, RvSection, RvRail } from "../../components/shadcn/record-view.jsx";
import { Icon } from "../../components/icons.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import ApplyPaymentSheet from "../../components/shadcn/apply-payment-sheet.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";

export default function Detail({ payment = {}, reservations = [], logs = [], journal_entries = [], receipts = [] }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canEdit = perms.can("payments", "edit");
  const canVoidReceipt = perms.can("invoice", "delete");
  const [confirm, confirmDialog] = useConfirm();
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [applyOpen, setApplyOpen] = useState(false);

  const handleConfirm = () => {
    confirm({
      title: t("Confirm Payment"),
      message: t("Confirm payment {number} for {amount} SAR?", {
        number: payment.payment_number,
        amount: payment.amount_sar?.toLocaleString(),
      }),
      danger: false,
      onConfirm: () => router.post(`/finance/payments/${payment.id}/confirm/`),
    });
  };

  const handleReverse = () => {
    confirm({
      title: t("Reverse Payment"),
      message: t("Are you sure you want to reverse this payment? This will create a reversing journal entry."),
      danger: true,
      onConfirm: () => router.post(`/finance/payments/${payment.id}/reverse/`),
    });
  };

  const handleVoid = () => {
    confirm({
      title: t("Void Payment"),
      message: t("Void payment {number}? This posts a reversal journal entry and marks it voided.", {
        number: payment.payment_number,
      }),
      danger: true,
      onConfirm: () => router.post(`/finance/payments/${payment.id}/void/`),
    });
  };

  const submitReject = () => {
    router.post(`/finance/payments/${payment.id}/reject/`, { reason: rejectReason });
    setRejectOpen(false);
  };

  const handleVoidReceipt = (r) => {
    confirm({
      title: t("Void Receipt"),
      message: t("Void receipt {number}? It will be marked voided.", { number: r.receipt_number }),
      danger: true,
      onConfirm: () => router.post(`/receipts/${r.id}/void/`),
    });
  };

  const allocatable = ["received", "partially_applied"].includes(payment.status);

  const pill = {
    pending: { label: t("Pending"), tone: "yellow" },
    received: { label: t("Received"), tone: "blue" },
    confirmed: { label: t("Confirmed"), tone: "blue" },
    allocated: { label: t("Allocated"), tone: "green" },
    partially_applied: { label: t("Partially Applied"), tone: "yellow" },
    applied: { label: t("Applied"), tone: "green" },
    rejected: { label: t("Rejected"), tone: "red" },
    reversed: { label: t("Reversed"), tone: "gray" },
    voided: { label: t("Voided"), tone: "gray" },
  }[payment.status] || { label: payment.status_display, tone: "gray" };

  const noteByStatus = {
    pending: {
      icon: <Icon name="alert-circle" size={13} strokeWidth={2} />,
      iconBg: "var(--yellow)",
      title: t("Awaiting decision"),
      text: t("Confirm or reject this payment."),
    },
    received: {
      icon: <Icon name="alert-circle" size={13} strokeWidth={2} />,
      iconBg: "var(--blue)",
      title: t("Received"),
      text: t("This payment is ready to be applied to a reservation."),
    },
    partially_applied: {
      icon: <Icon name="alert-circle" size={13} strokeWidth={2} />,
      iconBg: "var(--yellow)",
      title: t("Partially applied"),
      text: t("Part of this payment is not yet allocated."),
    },
    confirmed: {
      icon: <Icon name="check" size={12} strokeWidth={2.4} />,
      iconBg: "var(--green)",
      title: t("Confirmed"),
      text: t("This payment is ready to be allocated."),
    },
    allocated: {
      icon: <Icon name="check" size={12} strokeWidth={2.4} />,
      iconBg: "var(--green)",
      title: t("Fully allocated"),
      text: t("This payment is assigned to reservations."),
    },
    applied: {
      icon: <Icon name="check" size={12} strokeWidth={2.4} />,
      iconBg: "var(--green)",
      title: t("Applied"),
      text: t("This payment is fully assigned."),
    },
    rejected: {
      icon: <Icon name="alert-circle" size={13} strokeWidth={2} />,
      iconBg: "var(--red)",
      title: t("Rejected"),
      text: payment.rejected_reason,
    },
    reversed: {
      icon: <Icon name="alert" size={13} strokeWidth={2} />,
      iconBg: "var(--muted-foreground)",
      title: t("Reversed"),
      text: t("This payment was reversed."),
    },
    voided: {
      icon: <Icon name="alert" size={13} strokeWidth={2} />,
      iconBg: "var(--muted-foreground)",
      title: t("Voided"),
      text: t("This payment was voided."),
    },
  };
  const note = noteByStatus[payment.status] || {
    icon: <Icon name="alert" size={13} strokeWidth={2} />,
    iconBg: "var(--muted-foreground)",
    title: pill.label,
  };

  const primaryActions = [];
  if (canEdit && payment.status === "pending") {
    primaryActions.push(
      <button key="confirm" className="hms-rv-btn primary" onClick={handleConfirm}>{t("Confirm")}</button>,
    );
  }
  if (canEdit && allocatable) {
    primaryActions.push(
      <button key="apply" className="hms-rv-btn" onClick={() => setApplyOpen(true)}>{t("Apply to reservations")}</button>,
    );
  }
  if (canEdit && ["confirmed", "allocated", "applied"].includes(payment.status)) {
    primaryActions.push(
      <button key="reallocate" className="hms-rv-btn" onClick={() => setApplyOpen(true)}>{t("Reallocate")}</button>,
    );
  }

  const menuItems = [];
  if (canEdit && payment.status === "pending") {
    menuItems.push({
      label: t("Reject"),
      danger: true,
      onClick: () => { setRejectReason(""); setRejectOpen(true); },
    });
  }
  if (canEdit && ["confirmed", "allocated", "applied"].includes(payment.status)) {
    menuItems.push({ label: t("Reverse"), danger: true, onClick: handleReverse });
  }
  if (canEdit && ["received", "partially_applied", "applied"].includes(payment.status)) {
    menuItems.push({ label: t("Void"), danger: true, onClick: handleVoid });
  }

  const journalColumns = [
    { header: t("Entry #"), render: (e) => <span className="font-mono text-xs">{e.entry_number}</span> },
    { header: t("Type"), render: (e) => e.entry_type_display },
    { header: t("Description"), render: (e) => e.description },
    { header: t("Date"), render: (e) => e.entry_date },
    { header: t("Debit"), align: "right", render: (e) => e.total_debit?.toLocaleString() },
    { header: t("Credit"), align: "right", render: (e) => e.total_credit?.toLocaleString() },
  ];

  const logColumns = [
    { header: t("Action"), render: (l) => <span className="font-medium">{l.action_display}</span> },
    { header: t("By"), render: (l) => l.performed_by },
    { header: t("Note"), render: (l) => l.note },
    { header: t("Time"), render: (l) => l.performed_at },
  ];

  const sections = [];
  if (payment.note) {
    sections.push({ title: t("Note"), body: <div className="hms-rv-railtext">{payment.note}</div> });
  }
  if (payment.allocations?.length > 0) {
    sections.push({
      title: t("Allocation Details"),
      meta: `${payment.allocations.length}`,
      body: (
        <DetailTable
          columns={[
            { header: t("Reservation"), render: (a) => a.reservation_number || a.reservation_id },
            { header: t("Amount (SAR)"), align: "right", render: (a) => a.amount_sar?.toLocaleString() },
          ]}
          rows={payment.allocations}
          rowKey={(a) => a.id}
        />
      ),
    });
  }
  if (payment.unallocated_sar > 0) {
    sections.push({
      title: t("Unallocated"),
      body: (
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span className="hms-dv-pill tone-yellow">{t("{n} SAR unallocated", { n: payment.unallocated_sar?.toLocaleString() })}</span>
          <span className="text-sm" style={{ color: "var(--muted-foreground)" }}>
            {t("This payment was received but not yet assigned to a reservation.")}
          </span>
        </div>
      ),
    });
  }
  if (payment.proof_url) {
    sections.push({
      title: t("Payment Proof"),
      body: payment.proof_url.endsWith(".pdf") ? (
        <a href={payment.proof_url} target="_blank" rel="noreferrer" className="hms-dv-link text-sm">
          {t("View PDF")}
        </a>
      ) : (
        <a href={payment.proof_url} target="_blank" rel="noreferrer">
          <img src={payment.proof_url} alt="Payment proof" className="max-h-64 rounded" style={{ border: "1px solid var(--border)" }} />
        </a>
      ),
    });
  }
  if (payment.rejected_reason) {
    sections.push({
      title: t("Rejection Reason"),
      body: <p className="text-sm" style={{ color: "var(--red)" }}>{payment.rejected_reason}</p>,
    });
  }
  if (receipts.length > 0) {
    sections.push({
      title: t("Receipts"),
      meta: `${receipts.length}`,
      body: (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {receipts.map((r) => (
            <div key={r.id} style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <span className="font-mono text-xs">{r.receipt_number}</span>
              <StatusPill small label={r.status_display} tone={r.status === "active" ? "green" : "gray"} />
              <a className="hms-dv-link text-sm" href={`/receipts/${r.id}/pdf/`} target="_blank" rel="noreferrer">
                {t("View Receipt PDF")}
              </a>
              {r.status === "active" && canVoidReceipt && (
                <button className="hms-dv-act" onClick={() => handleVoidReceipt(r)} style={{ color: "var(--red)" }}>
                  {t("Void")}
                </button>
              )}
              {r.status === "voided" && r.voided_reason && (
                <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                  {r.voided_reason}
                </span>
              )}
            </div>
          ))}
        </div>
      ),
    });
  }
  sections.push({
    title: t("Audit Trail"),
    body: (
      <DetailTable
        columns={[
          { header: t("Field"), render: (r) => r.label },
          { header: t("Value"), render: (r) => r.value },
        ]}
        rows={[
          { label: t("Created by"), value: payment.created_by },
          { label: t("Created at"), value: payment.created_at },
          { label: t("Confirmed by"), value: payment.confirmed_by },
          { label: t("Confirmed at"), value: payment.confirmed_at },
          { label: t("Period"), value: payment.period?.name },
        ].filter((r) => r.value)}
        rowKey={(r) => r.label}
      />
    ),
  });
  if (journal_entries.length > 0) {
    sections.push({
      title: t("Journal Entries"),
      meta: `${journal_entries.length}`,
      body: <DetailTable columns={journalColumns} rows={journal_entries} rowKey={(e) => e.id} />,
    });
  }
  if (logs.length > 0) {
    sections.push({
      title: t("Activity Log"),
      meta: `${logs.length}`,
      body: <DetailTable columns={logColumns} rows={logs} rowKey={(l) => l.performed_at} />,
    });
  }

  const paymentDate = payment.payment_date
    ? new Date(payment.payment_date).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })
    : null;

  return (
    <div className="page shadcn-root hms-rv-page">
      <RvBack href="/finance/payments/" label={t("Back")} />

      <RvHero
        kicker={payment.payment_number}
        badge={pill}
        title={
          payment.client_name
            ? t("{client} paid {amount} SAR", { client: payment.client_name, amount: payment.amount_sar?.toLocaleString() })
            : t("Payment {number}", { number: payment.payment_number })
        }
        facts={[
          ...(payment.method ? [{ k: t("Method"), v: payment.method }] : []),
          ...(paymentDate ? [{ k: t("Date"), v: paymentDate }] : []),
          { k: t("Invoice"), v: payment.invoice_number || t("Not invoiced") },
        ]}
        note={note}
        actions={
          <>
            {primaryActions}
            <KebabMenu items={menuItems} />
          </>
        }
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
            payment.client_name
              ? {
                  k: t("Client"),
                  v: payment.client_id ? <DvLink href={`/clients/${payment.client_id}/`}>{payment.client_name}</DvLink> : payment.client_name,
                }
              : null,
            payment.amount
              ? { k: t("Original"), v: `${payment.amount?.toLocaleString()} ${payment.currency}` }
              : null,
            payment.exchange_rate ? { k: t("Exchange Rate"), v: payment.exchange_rate } : null,
            {
              k: t("Invoice"),
              v: payment.invoice_number && payment.invoice_id
                ? <DvLink href={`/invoice/${payment.invoice_id}/`}>{payment.invoice_number}</DvLink>
                : t("Not invoiced"),
            },
            payment.method ? { k: t("Method"), v: payment.method } : null,
            payment.receiving_account_label
              ? { k: t("Received Into"), v: payment.receiving_account_label }
              : payment.received_in_display ? { k: t("Received In"), v: payment.received_in_display } : null,
            paymentDate ? { k: t("Date"), v: paymentDate } : null,
            payment.reference ? { k: t("Reference"), v: payment.reference } : null,
            payment.bank_name ? { k: t("Bank"), v: payment.bank_name } : null,
            payment.account_number ? { k: t("Account #"), v: payment.account_number } : null,
          ].filter(Boolean)}
        />
      </div>

      {confirmDialog}

      {rejectOpen && (
        <Dialog open onOpenChange={(v) => { if (!v) setRejectOpen(false); }}>
          <DialogContent className="hms-dialog">
            <DialogHeader>
              <DialogTitle>{t("Reject Payment")}</DialogTitle>
            </DialogHeader>
            <Textarea
              rows={3}
              placeholder={t("Reason for rejection...")}
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
            />
            <DialogFooter>
              <Button variant="outline" onClick={() => setRejectOpen(false)}>{t("Cancel")}</Button>
              <Button variant="destructive" onClick={submitReject}>{t("Reject")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      <ApplyPaymentSheet
        open={applyOpen}
        onOpenChange={setApplyOpen}
        payment={{ id: payment.id, payment_number: payment.payment_number, amount_sar: payment.amount_sar, invoice_id: payment.invoice_id }}
        reservations={reservations}
        initialAllocations={payment.allocations || []}
        onApplied={() => undefined}
      />
    </div>
  );
}