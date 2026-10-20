import { useState } from "react";
import { router } from "@inertiajs/react";
import { DPage, DTop, DHead, DBanner, DBtn, DChip, DTabs, DLog, dayMonth } from "../../components/shadcn/detail-a.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import ApplyPaymentSheet from "../../components/shadcn/apply-payment-sheet.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";
import { fmt, fmtDec, fmtDate, fmtStay } from "../../utils/format.js";

// Payment detail, the "Payment Detail" artboard on the Record View HMS canvas:
// a strip above the card says what is left to do (confirm, allocate), the
// head card holds the proof and receipt chips and every fact, and the tabs
// below hold the allocation, the journal and the activity.

const TONE = { green: "green", yellow: "amber", amber: "amber", red: "red", blue: "info", gray: "gray" };

// ISO timestamp -> "09 Oct 14:42"
const stamp = (iso) => {
  if (!iso) return "";
  const m = /T(\d{2}):(\d{2})/.exec(iso);
  return `${dayMonth(iso)}${m ? ` ${m[1]}:${m[2]}` : ""}`;
};

export default function Detail({ payment = {}, reservations = [], unbilled_reservations = [], logs = [], journal_entries = [], receipts = [] }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canEdit = perms.can("payments", "edit");
  // The recorder does not confirm their own payment (admins excepted); the
  // server enforces the same in payment_confirm.
  const canApprove = perms.can("payments", "approve");
  const canConfirm = canApprove && (perms.isAdmin || payment.created_by !== perms.user?.username);
  const canVoidReceipt = perms.can("payments", "delete");
  const [confirm, confirmDialog] = useConfirm();
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  // Linked from an invoice's overpayment banner (?apply=1): open the sheet.
  const [applyOpen, setApplyOpen] = useState(
    () => typeof window !== "undefined" && new URLSearchParams(window.location.search).get("apply") === "1",
  );
  const [tab, setTab] = useState("allocation");

  const proof = payment.proof?.[0] || null;
  const status = payment.status;
  const pending = status === "pending";
  const allocatable = ["received", "partially_applied"].includes(status);
  const reallocatable = ["confirmed", "allocated", "applied"].includes(status);
  const unallocated = payment.unallocated_sar > 0;
  // rejected/reversed/voided carry no live money: nothing to chase, no red.
  const dead = ["rejected", "reversed", "voided"].includes(status);

  const pill = {
    rejected: { label: t("Rejected"), tone: "red" },
    reversed: { label: t("Reversed"), tone: "gray" },
    voided: { label: t("Voided"), tone: "gray" },
  }[status] || {
    label: t(payment.status_group_label || payment.status_display),
    tone: TONE[payment.status_group_tone] || "gray",
  };

  const handleConfirm = () => confirm({
    title: t("Confirm Payment"),
    message: t("Confirm payment {number} for {amount} SAR?", { number: payment.payment_number, amount: fmt(payment.amount_sar) }),
    confirmLabel: "Confirm",
    icon: "check",
    danger: false,
    onConfirm: () => router.post(`/finance/payments/${payment.id}/confirm/`),
  });

  const submitReject = () => {
    router.post(`/finance/payments/${payment.id}/reject/`, { reason: rejectReason });
    setRejectOpen(false);
  };

  const handleVoidReceipt = (r) => confirm({
    title: t("Void Receipt"),
    message: t("Void receipt {number}? It will be marked voided.", { number: r.receipt_number }),
    confirmLabel: "Void",
    icon: "close",
    danger: true,
    onConfirm: () => router.post(`/receipts/${r.id}/void/`),
  });

  // Void and Reverse take a received payment back out; both need
  // payments.delete like every other void.
  const canRetire = perms.can("payments", "delete") && !dead && !pending;
  const retire = (action) => {
    const isVoid = action === "void";
    confirm({
      title: isVoid ? t("Void Payment") : t("Reverse Payment"),
      message: isVoid
        ? t("Void payment {number}? Its journal is reversed on the payment date ({date}), as if it was never received. Use this for a payment recorded by mistake.", {
          number: payment.payment_number, date: fmtDate(payment.payment_date),
        })
        : t("Reverse payment {number}? Its journal is reversed today; the original receipt stays in its own month. Use this when the money went back after it was received.", {
          number: payment.payment_number,
        }),
      confirmLabel: isVoid ? "Void" : "Reverse",
      icon: isVoid ? "close" : "swap",
      danger: true,
      onConfirm: () => router.post(`/finance/payments/${payment.id}/${action}/`),
    });
  };

  // Excess stays on the payment until someone moves it to the client's
  // deposit: an explicit step, because deposit money can then leave the
  // client's invoices (refund, transfer to another client).
  const canAllocate = canEdit && (allocatable || reallocatable);
  const canDeposit = canEdit && allocatable && unallocated;
  const handleDeposit = () => confirm({
    title: t("Move {n} SAR to deposit?", { n: fmt(payment.unallocated_sar) }),
    message: t("The unallocated part of this payment becomes {client}'s deposit. It can then pay other invoices, be transferred, or be refunded.", { client: payment.client_name || "" }),
    confirmLabel: t("Move to deposit"),
    onConfirm: () => router.post(`/finance/payments/${payment.id}/to-deposit/`),
  });

  const allocations = payment.allocations || [];
  const activeReceipts = receipts.filter((r) => r.status === "active");

  const menu = [
    canAllocate && !unallocated && {
      label: allocations.length ? t("Reallocate") : t("Apply to reservations"),
      icon: "edit",
      onClick: () => setApplyOpen(true),
    },
    ...(canVoidReceipt ? activeReceipts.map((r, i) => ({
      label: activeReceipts.length > 1 ? t("Void receipt {number}…", { number: r.receipt_number }) : t("Void receipt…"),
      icon: "receipt",
      danger: true,
      separator: i === 0,
      onClick: () => handleVoidReceipt(r),
    })) : []),
    canRetire && { label: t("Reverse payment…"), icon: "reverse", danger: true, separator: !(canVoidReceipt && activeReceipts.length), onClick: () => retire("reverse") },
    canRetire && { label: t("Void payment…"), icon: "close", danger: true, onClick: () => retire("void") },
  ];

  const foreign = payment.currency && payment.currency !== "SAR";
  const receivedInto = payment.receiving_account_label || payment.received_in_display;
  const facts = [
    { k: t("Amount"), v: `${fmt(payment.amount_sar)} SAR`, strong: true },
    !pending && !dead && { k: t("Allocated"), v: `${fmt(payment.allocated_sar)} SAR` },
    !pending && !dead && { k: t("Unallocated"), v: `${fmt(payment.unallocated_sar)} SAR`, tone: unallocated ? "danger" : undefined },
    { k: t("Received"), v: fmtDate(payment.payment_date) || t("Not set") },
    payment.client_name && { k: t("Client"), v: payment.client_id && perms.can("clients", "view") ? <a href={`/clients/${payment.client_id}/`}>{payment.client_name}</a> : payment.client_name },
    { k: t("Invoice"), v: payment.invoice_number ? (payment.invoice_id && perms.can("invoice", "view") ? <a href={`/invoice/${payment.invoice_id}/`}>{payment.invoice_number}</a> : payment.invoice_number) : <span className="dim">{t("Not linked")}</span> },
    payment.method && { k: t("Method"), v: payment.method },
    payment.received_in_display && { k: t("Branch"), v: payment.received_in_display },
    foreign && { k: t("Original"), v: `${fmtDec(payment.amount)} ${payment.currency}` },
    foreign && payment.exchange_rate && { k: t("Exchange rate"), v: `1 SAR = ${fmtDec(payment.exchange_rate)} ${payment.currency}` },
    payment.reference && { k: t("Reference"), v: payment.reference },
    receivedInto && { k: t("Received into"), v: receivedInto },
  ];

  const chips = [
    proof && <DChip key="proof" href={proof.url} icon="clip" label={t("Open payment proof, {name}", { name: proof.name })}>{proof.name || t("Proof")}</DChip>,
    ...receipts.map((r) => (
      <DChip key={r.id} href={`/receipts/${r.id}/pdf/`} icon="receipt" label={t("Open receipt {number} PDF", { number: r.receipt_number })}>
        {t("Receipt")} <span className="da-mono" style={{ fontSize: 12 }}>{r.receipt_number}</span>
        {r.status !== "active" ? <span style={{ color: "var(--muted-foreground)" }}>· {r.status_display}</span> : null}
      </DChip>
    )),
  ];

  const noteBox = status === "rejected" && payment.rejected_reason
    ? { label: t("Rejection reason"), text: payment.rejected_reason }
    : payment.note ? { label: t("Note"), text: payment.note } : null;

  let banner = null;
  if (pending && (canConfirm || canApprove)) {
    banner = (
      <DBanner actions={(
        <>
          {canApprove ? <DBtn onClick={() => { setRejectReason(""); setRejectOpen(true); }}>{t("Reject")}</DBtn> : null}
          {canConfirm ? <DBtn primary onClick={handleConfirm}>{t("Confirm")}</DBtn> : null}
        </>
      )}>
        <b>{fmt(payment.amount_sar)} SAR</b> {t("is waiting to be confirmed by Finance.")}
      </DBanner>
    );
  } else if (allocatable && unallocated) {
    banner = (
      <DBanner actions={canEdit ? (
        <>
          {canDeposit ? <DBtn onClick={handleDeposit}>{t("Move to deposit")}</DBtn> : null}
          <DBtn primary onClick={() => setApplyOpen(true)}>{t("Allocate")}</DBtn>
        </>
      ) : null}>
        <b>{fmt(payment.unallocated_sar)} SAR</b> {t("of this payment is not allocated to a reservation yet.")}
      </DBanner>
    );
  }

  const unallocatedRow = unallocated && !dead && allocations.length > 0;

  return (
    <DPage>
      <DTop href="/finance/payments/" stamp={payment.created_at ? t("Created {date}", { date: fmtDate(payment.created_at.slice(0, 10)) }) : undefined} />

      {banner}
      {payment.deposited_sar > 0 ? (
        <DBanner tone="info">{t("{n} SAR of this payment was moved to the client's deposit.", { n: fmt(payment.deposited_sar) })}</DBanner>
      ) : null}

      <DHead title={payment.payment_number} badge={pill} menu={menu} chips={chips} cols={4} facts={facts} note={noteBox} />

      <section className="da-card">
        <DTabs
          label={t("Payment records")}
          value={tab}
          onChange={setTab}
          tabs={[
            { key: "allocation", label: t("Allocation"), count: allocations.length },
            { key: "journal", label: t("Journal"), count: journal_entries.length },
            { key: "activity", label: t("Activity"), count: logs.length },
          ]}
        />

        {tab === "allocation" ? (
          <div role="tabpanel" className="da-scroll">
            {allocations.length ? (
              <table className="da-t">
                <thead><tr><th>{t("Reservation")}</th><th>{t("Hotel")}</th><th>{t("Stay")}</th><th className="n">{t("Amount (SAR)")}</th></tr></thead>
                <tbody>
                  {allocations.map((a) => (
                    <tr key={a.id}>
                      <td>
                        <span className="mono">{a.reservation_number || `#${a.reservation_id}`}</span>
                        {a.invoice_number && a.invoice_number !== payment.invoice_number ? <span className="sub">{a.invoice_number}</span> : null}
                      </td>
                      <td className="strong">{a.hotel || ""}</td>
                      <td className="mut nw">{fmtStay(a.check_in, a.check_out)}</td>
                      <td className="n">{fmt(a.amount_sar)}</td>
                    </tr>
                  ))}
                  {unallocatedRow ? (
                    <tr>
                      <td className="mut">{t("Unallocated")}</td>
                      <td className="mut">{t("Held on the client balance")}</td>
                      <td />
                      <td className="n" style={{ color: "var(--danger-text)" }}>{fmt(payment.unallocated_sar)}</td>
                    </tr>
                  ) : null}
                </tbody>
                <tfoot><tr><td colSpan={3}>{t("Total received")}</td><td className="n">{fmt(payment.amount_sar)} SAR</td></tr></tfoot>
              </table>
            ) : <div className="da-empty">{t("Not yet allocated to a reservation.")}</div>}
          </div>
        ) : null}

        {tab === "journal" ? (
          <div role="tabpanel" className="da-scroll">
            {journal_entries.length ? (
              <table className="da-t">
                <thead><tr><th>{t("Entry #")}</th><th>{t("Type")}</th><th>{t("Description")}</th><th>{t("Date")}</th><th className="n">{t("Debit")}</th><th className="n">{t("Credit")}</th></tr></thead>
                <tbody>
                  {journal_entries.map((e) => (
                    <tr key={e.id}>
                      <td className="mono">{e.entry_number}</td>
                      <td className="strong">{e.entry_type_display}</td>
                      <td className="mut">{e.description}</td>
                      <td className="nw">{e.entry_date}</td>
                      <td className="n">{fmt(e.total_debit)}</td>
                      <td className="n">{fmt(e.total_credit)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <div className="da-empty">{t("No journal entry yet — it is posted when the payment is confirmed.")}</div>}
          </div>
        ) : null}

        {tab === "activity" ? (
          <div role="tabpanel">
            <DLog
              wide
              empty={t("No activity recorded yet.")}
              rows={logs.map((l, i) => ({
                key: i,
                when: stamp(l.performed_at),
                body: <>{l.action_display}{l.note ? <span className="by">: {l.note}</span> : null}</>,
                by: l.performed_by,
              }))}
            />
          </div>
        ) : null}
      </section>

      {confirmDialog}

      {rejectOpen && (
        <Dialog open onOpenChange={(v) => { if (!v) setRejectOpen(false); }}>
          <DialogContent className="hms-dialog">
            <DialogHeader>
              <DialogTitle>{t("Reject payment {number}?", { number: payment.payment_number })}</DialogTitle>
            </DialogHeader>
            <p style={{ fontSize: 13, color: "var(--muted-foreground)", margin: "6px 0 0", lineHeight: 1.6 }}>
              {t("The {n} SAR will stop counting against this client's balance. This cannot be undone.", { n: fmt(payment.amount_sar) })}
            </p>
            <label htmlFor="reject-reason" style={{ display: "block", fontSize: 12, color: "var(--muted-foreground)", margin: "16px 0 6px" }}>{t("Reason")}</label>
            <Textarea id="reject-reason" rows={3} value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
            <DialogFooter>
              <Button variant="outline" onClick={() => setRejectOpen(false)}>{t("Cancel")}</Button>
              <Button variant="destructive" onClick={submitReject}>{t("Reject payment")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      <ApplyPaymentSheet
        open={applyOpen}
        onOpenChange={setApplyOpen}
        payment={{ id: payment.id, payment_number: payment.payment_number, amount_sar: payment.amount_sar, invoice_id: payment.invoice_id }}
        reservations={reservations}
        unbilled={unbilled_reservations}
        initialAllocations={allocations}
        onApplied={() => undefined}
      />
    </DPage>
  );
}
