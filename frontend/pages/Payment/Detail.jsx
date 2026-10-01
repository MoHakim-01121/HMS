import { useRef, useState } from "react";
import { Link, router } from "@inertiajs/react";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import ApplyPaymentSheet from "../../components/shadcn/apply-payment-sheet.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";
import { fmt, fmtDec, fmtDate, fmtSize, fmtStay } from "../../utils/format.js";

const extLabel = (name) => {
  const ext = (name || "").split(".").pop();
  return (ext || "FILE").toUpperCase();
};

const stayRange = (a) => fmtStay(a.check_in, a.check_out);

export default function Detail({ payment = {}, reservations = [], invoice_choices = [], logs = [], journal_entries = [], receipts = [] }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canEdit = perms.can("payments", "edit");
  const canVoidReceipt = perms.can("invoice", "delete");
  const [confirm, confirmDialog] = useConfirm();
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [applyOpen, setApplyOpen] = useState(false);
  const [tab, setTab] = useState("allocation");
  const tabRefs = useRef({});

  const proof = payment.proof?.[0] || null;

  const handleConfirm = () => {
    confirm({
      title: t("Confirm Payment"),
      message: t("Confirm payment {number} for {amount} SAR?", {
        number: payment.payment_number,
        amount: fmt(payment.amount_sar),
      }),
      confirmLabel: "Confirm",
      icon: "check",
      danger: false,
      onConfirm: () => router.post(`/finance/payments/${payment.id}/confirm/`),
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
      confirmLabel: "Void",
      icon: "close",
      danger: true,
      onConfirm: () => router.post(`/receipts/${r.id}/void/`),
    });
  };

  const allocatable = ["received", "partially_applied"].includes(payment.status);
  const reallocatable = ["confirmed", "allocated", "applied"].includes(payment.status);
  const unallocated = payment.unallocated_sar > 0;
  // rejected/reversed/voided carry no live money: the split still states what
  // the record holds, but it is not a balance anyone has to chase, so it drops
  // the red tint.
  const dead = ["rejected", "reversed", "voided"].includes(payment.status);

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

  // One primary action per state, plus Reject in the top bar exactly as the
  // mockup has it (backend accepts reject on PENDING only). Reverse and Void
  // are not offered here -- payment-level actions live in the list's action
  // column.
  let primary = null;
  if (canEdit && payment.status === "pending") {
    primary = { label: t("Confirm"), onClick: handleConfirm };
  } else if (canEdit && (allocatable || reallocatable)) {
    primary = {
      label: unallocated
        ? t("Allocate {n} SAR", { n: fmt(payment.unallocated_sar) })
        : payment.allocations?.length
          ? t("Reallocate")
          : t("Apply to reservations"),
      onClick: () => setApplyOpen(true),
    };
  }
  const canReject = canEdit && payment.status === "pending";
  // Excess stays on the payment until someone moves it to the client's
  // deposit: an explicit step, because deposit money can then leave the
  // client's invoices (refund, transfer to another client).
  const canDeposit = canEdit && allocatable && unallocated;
  const handleDeposit = () => {
    confirm({
      title: t("Move {n} SAR to deposit?", { n: fmt(payment.unallocated_sar) }),
      message: t("The unallocated part of this payment becomes {client}'s deposit. It can then pay other invoices, be transferred, or be refunded.", { client: payment.client_name || "" }),
      confirmLabel: t("Move to deposit"),
      onConfirm: () => router.post(`/finance/payments/${payment.id}/to-deposit/`),
    });
  };

  const allocations = payment.allocations || [];
  // The design closes the allocation table with a muted "Unallocated — held on
  // the client balance" line before the total; it reads as a row, so it is one.
  const allocationRows = unallocated && allocations.length
    ? [...allocations, { id: "__unallocated__", unallocatedRow: true }]
    : allocations;

  const muted = (s) => <span style={{ color: "var(--muted-foreground)" }}>{s}</span>;

  const allocationColumns = [
    {
      header: t("Reservation"),
      render: (a) => (a.unallocatedRow
        ? muted(t("Unallocated"))
        : <span className="hms-pd-mono">{a.reservation_number || a.service_item_name || `#${a.reservation_id || a.service_item_id}`}</span>),
    },
    {
      header: t("Hotel"),
      strong: true,
      render: (a) => (a.unallocatedRow
        ? muted(t("Held on the client balance"))
        : a.hotel || a.service_item_name || muted("—")),
    },
    {
      header: t("Stay"),
      render: (a) => (a.unallocatedRow ? "" : muted(stayRange(a) || "—")),
    },
    {
      header: t("Amount (SAR)"),
      align: "right",
      render: (a) => (a.unallocatedRow
        ? <span style={{ color: "var(--red)" }}>{fmt(payment.unallocated_sar)}</span>
        : fmt(a.amount_sar)),
    },
  ];

  const journalColumns = [
    { header: t("Entry #"), render: (e) => <span className="hms-pd-mono">{e.entry_number}</span> },
    { header: t("Type"), strong: true, render: (e) => e.entry_type_display },
    { header: t("Description"), render: (e) => muted(e.description) },
    { header: t("Date"), render: (e) => e.entry_date },
    { header: t("Debit"), align: "right", render: (e) => fmt(e.total_debit) },
    { header: t("Credit"), align: "right", render: (e) => fmt(e.total_credit) },
  ];

  const logColumns = [
    { header: t("Action"), strong: true, render: (l) => l.action_display },
    { header: t("By"), render: (l) => l.performed_by },
    { header: t("Note"), render: (l) => muted(l.note) },
    { header: t("Time"), render: (l) => muted(l.performed_at) },
  ];

  const tabs = [
    { id: "allocation", label: t("Allocation"), count: allocations.length },
    { id: "journal", label: t("Journal"), count: journal_entries.length },
    { id: "activity", label: t("Activity"), count: logs.length },
  ];

  const onTabKey = (e) => {
    const i = tabs.findIndex((x) => x.id === tab);
    let n = null;
    if (e.key === "ArrowRight") n = (i + 1) % tabs.length;
    else if (e.key === "ArrowLeft") n = (i - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") n = 0;
    else if (e.key === "End") n = tabs.length - 1;
    if (n == null) return;
    e.preventDefault();
    const next = tabs[n].id;
    setTab(next);
    tabRefs.current[next]?.focus();
  };

  const paymentDate = fmtDate(payment.payment_date) || null;
  const receivedLine = [
    paymentDate ? t("received {date}", { date: paymentDate }) : null,
    payment.method ? t("by {method}", { method: payment.method.toLowerCase() }) : null,
  ].filter(Boolean).join(" ");

  const foreign = payment.currency && payment.currency !== "SAR";
  const receivedInto =
    payment.receiving_account_label
    || payment.received_in_display;

  const meta = [
    payment.method ? { k: t("Method"), v: payment.method } : null,
    payment.received_in_display ? { k: t("Branch"), v: payment.received_in_display } : null,
    foreign ? { k: t("Original"), v: `${fmtDec(payment.amount)} ${payment.currency}`, wide: true } : null,
    foreign && payment.exchange_rate
      ? { k: t("Exchange rate"), v: `1 SAR = ${fmtDec(payment.exchange_rate)} ${payment.currency}`, wide: true }
      : null,
    payment.reference ? { k: t("Reference"), v: payment.reference, wide: true } : null,
    receivedInto ? { k: t("Received into"), v: receivedInto, wide: true, wrap: true } : null,
  ].filter(Boolean);

  const noteCard = payment.status === "rejected" && payment.rejected_reason
    ? { title: t("Rejection reason"), text: payment.rejected_reason }
    : payment.note
      ? { title: t("Note"), text: payment.note }
      : null;

  const panelFor = (id, children) => (
    <div className="hms-pd-panel" role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`}>
      {children}
    </div>
  );

  return (
    <div className="page shadcn-root hms-pd">
      <style>{CSS}</style>

      <div className="hms-pd-top">
        {/* Same link as RvBack; inlined because the number and actions share its row. */}
        <Link href="/finance/payments/" className="hms-rv-backlink">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>
          {t("Back")}
        </Link>
        <span className="hms-pd-no">{payment.payment_number}</span>
        <span className="hms-pd-topacts">
          {canReject ? (
            <button type="button" className="hms-rv-btn danger" onClick={() => { setRejectReason(""); setRejectOpen(true); }}>
              {t("Reject")}
            </button>
          ) : null}
        </span>
      </div>

      <div className="hms-pd-layout">
        <main className="hms-pd-main">
          <div className="hms-pd-statusrow">
            <StatusPill label={pill.label} tone={pill.tone} />
            {receivedLine ? <span className="hms-pd-caption">{receivedLine}</span> : null}
          </div>

          <h1 className="hms-pd-amount">
            {fmt(payment.amount_sar)}
            <span className="u">SAR</span>
          </h1>

          <p className="hms-pd-lede">
            {payment.client_name ? (
              <>
                {t("from")}{" "}
                {payment.client_id
                  ? <a href={`/clients/${payment.client_id}/`}>{payment.client_name}</a>
                  : <strong>{payment.client_name}</strong>}
              </>
            ) : null}
            {payment.invoice_number ? (
              <>
                {payment.client_name ? " " : null}
                {t("against invoice")}{" "}
                {payment.invoice_id
                  ? <a href={`/invoice/${payment.invoice_id}/`}>{payment.invoice_number}</a>
                  : <strong>{payment.invoice_number}</strong>}
              </>
            ) : null}
            {foreign ? (
              <>
                {", "}
                {t("paid as {amount} {currency}", { amount: fmtDec(payment.amount), currency: payment.currency })}
                {payment.exchange_rate
                  ? ` ${t("at 1 SAR = {rate} {currency}", { rate: fmtDec(payment.exchange_rate), currency: payment.currency })}`
                  : null}
              </>
            ) : null}
            {payment.client_name || payment.invoice_number || foreign ? "." : t("Not linked to an invoice.")}
          </p>

          <div className="hms-pd-stats">
            <div>
              <div className="k">{t("Allocated")}</div>
              <div className="v">{fmt(payment.allocated_sar)}</div>
            </div>
            <div>
              <div className="k">{t("Unallocated")}</div>
              <div className="v" style={unallocated && !dead ? { color: "var(--red)" } : undefined}>
                {fmt(payment.unallocated_sar)}
              </div>
            </div>
            {primary ? (
              <button type="button" className="hms-pd-primary" onClick={primary.onClick}>{primary.label}</button>
            ) : null}
            {canDeposit ? (
              <button type="button" className="hms-rv-btn" onClick={handleDeposit}>{t("Move to deposit")}</button>
            ) : null}
          </div>
          {payment.deposited_sar > 0 ? (
            <div className="hms-rv-railtext" style={{ marginTop: 8 }}>
              {t("{n} SAR of this payment was moved to the client's deposit.", { n: fmt(payment.deposited_sar) })}
            </div>
          ) : null}

          <div className="hms-pd-tabs" role="tablist" aria-label={t("Payment records")} onKeyDown={onTabKey}>
            {tabs.map((x) => (
              <button
                key={x.id}
                type="button"
                role="tab"
                id={`tab-${x.id}`}
                ref={(el) => { tabRefs.current[x.id] = el; }}
                aria-selected={tab === x.id}
                aria-controls={`panel-${x.id}`}
                tabIndex={tab === x.id ? 0 : -1}
                className={`hms-pd-tab${tab === x.id ? " active" : ""}`}
                onClick={() => setTab(x.id)}
              >
                {x.label}
                <span className="n">{x.count}</span>
              </button>
            ))}
          </div>

          {tab === "allocation" ? panelFor("allocation", (
            <DetailTable
              columns={allocationColumns}
              rows={allocationRows}
              rowKey={(a) => a.id}
              empty={t("Not yet allocated to a reservation.")}
              footer={allocations.length ? [{ label: t("Total received"), value: fmt(payment.amount_sar) }] : null}
            />
          )) : null}

          {tab === "journal" ? panelFor("journal", (
            <DetailTable
              columns={journalColumns}
              rows={journal_entries}
              rowKey={(e) => e.id}
              empty={t("No journal entry yet — it is posted when the payment is confirmed.")}
            />
          )) : null}

          {tab === "activity" ? panelFor("activity", (
            <DetailTable
              columns={logColumns}
              rows={logs}
              rowKey={(l) => l.performed_at}
              empty={t("No activity recorded yet.")}
            />
          )) : null}
        </main>

        <aside className="hms-pd-aside" aria-label={t("Payment summary")}>
          <section className="hms-pd-card">
            <h2>{t("Payment")}</h2>
            <dl className="hms-pd-dl">
              {meta.map((m, i) => (
                <div key={i} style={m.wide ? { gridColumn: "1 / -1" } : undefined}>
                  <dt>{m.k}</dt>
                  <dd style={m.wrap ? { overflowWrap: "anywhere" } : undefined}>{m.v}</dd>
                </div>
              ))}
            </dl>
            {proof ? (
              <a className="hms-pd-file" href={proof.url} target="_blank" rel="noreferrer" title={proof.name || undefined}>
                <span className="ico" aria-hidden="true">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" />
                  </svg>
                </span>
                <span style={{ minWidth: 0 }}>
                  <span className="n">{proof.name || payment.payment_number}</span>
                  <span className="s">{extLabel(proof.name)}, {fmtSize(proof.size)}</span>
                </span>
              </a>
            ) : null}
          </section>

          {receipts.length > 0 ? (
            <section className="hms-pd-card">
              <h2>{t("Receipt")}</h2>
              {receipts.map((r) => (
                <div key={r.id} className="hms-pd-rcpt">
                  <div className="hms-pd-rcpt-h">
                    <span className="hms-pd-mono">{r.receipt_number}</span>
                    <StatusPill small label={r.status_display} tone={r.status === "active" ? "green" : "gray"} />
                  </div>
                  <div className="hms-pd-rcpt-acts">
                    <a className="hms-pd-btn grow" href={`/receipts/${r.id}/pdf/`} target="_blank" rel="noreferrer">
                      {t("View PDF")}
                    </a>
                    {r.status === "active" && canVoidReceipt ? (
                      <button type="button" className="hms-pd-btn danger" onClick={() => handleVoidReceipt(r)}>
                        {t("Void")}
                      </button>
                    ) : null}
                  </div>
                  {r.status === "voided" && r.voided_reason ? (
                    <p className="hms-pd-rcpt-reason">{r.voided_reason}</p>
                  ) : null}
                </div>
              ))}
            </section>
          ) : null}

          {noteCard ? (
            <section className="hms-pd-card">
              <h2>{noteCard.title}</h2>
              <p className="hms-pd-note">{noteCard.text}</p>
            </section>
          ) : null}
        </aside>
      </div>

      {confirmDialog}

      {rejectOpen && (
        <Dialog open onOpenChange={(v) => { if (!v) setRejectOpen(false); }}>
          <DialogContent className="hms-dialog">
            <DialogHeader>
              <DialogTitle>{t("Reject payment {number}?", { number: payment.payment_number })}</DialogTitle>
            </DialogHeader>
            <p className="hms-pd-dlgdesc">
              {t("The {n} SAR will stop counting against this client's balance. This cannot be undone.", {
                n: fmt(payment.amount_sar),
              })}
            </p>
            <label className="hms-pd-dlglabel" htmlFor="reject-reason">{t("Reason")}</label>
            <Textarea
              id="reject-reason"
              rows={3}
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
            />
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
        invoiceChoices={invoice_choices}
        initialAllocations={payment.allocations || []}
        onApplied={() => undefined}
      />
    </div>
  );
}

// Layout transcribed from the Claude Design file "Payment Detail v2": a wide
// record column carrying the amount as the page headline and three tabbed
// record tables, beside a sticky 280px summary column of small cards. Every
// colour is a Homlu token rather than the mockup's literal oklch values, so
// light and dark both hold; geometry, type scale and spacing follow the
// mockup.
const CSS = `
.hms-pd { max-width: 1120px; padding-bottom: 72px; }

.hms-pd-top { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; }
.hms-pd-no { font: 400 12px ui-monospace, "SF Mono", Menlo, monospace; color: var(--muted-foreground); font-variant-numeric: tabular-nums; }
.hms-pd-topacts { margin-left: auto; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.hms-pd-btn { display: inline-flex; align-items: center; justify-content: center; min-height: 30px; padding: 4px 10px; font-family: inherit; font-size: 12.5px; font-weight: 500; color: var(--foreground); background: var(--card); border: 1px solid var(--border); border-radius: 8px; cursor: pointer; white-space: nowrap; text-decoration: none; }
.hms-pd-btn:hover { border-color: var(--foreground); }
.hms-pd-btn:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
.hms-pd-btn.danger { color: var(--red); }
.hms-pd-btn.grow { flex: 1; }

.hms-pd-layout { display: flex; flex-wrap: wrap; gap: 20px; align-items: flex-start; }
.hms-pd-main { flex: 999 1 460px; min-width: 0; background: var(--card); border: 1px solid var(--border); border-radius: 20px; box-shadow: 0 2px 10px rgb(0 0 0 / .04); padding: 24px 20px 12px; }
.hms-pd-aside { flex: 1 1 280px; min-width: 0; position: sticky; top: calc(var(--topbar-h, 0px) + 24px); display: grid; gap: 14px; }
.hms-pd-card { min-width: 0; background: var(--card); border: 1px solid var(--border); border-radius: 20px; box-shadow: 0 2px 10px rgb(0 0 0 / .04); padding: 18px 20px; }
.hms-pd-card h2 { font-size: 14px; font-weight: 600; margin: 0; letter-spacing: -.01em; }

.hms-pd-statusrow { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.hms-pd-caption { font-size: 13px; color: var(--muted-foreground); }
.hms-pd-amount { font-size: clamp(36px, 7vw, 52px); font-weight: 500; letter-spacing: -.035em; line-height: 1.05; margin: 16px 0 0; color: var(--foreground); font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.hms-pd-amount .u { font-size: 19px; font-weight: 400; color: var(--muted-foreground); letter-spacing: 0; margin-left: 10px; }
.hms-pd-lede { font-size: 14px; color: var(--muted-foreground); margin: 10px 0 0; line-height: 1.6; max-width: 60ch; text-wrap: pretty; }
.hms-pd-lede strong { font-weight: 400; color: var(--foreground); }
.hms-pd-lede a { color: var(--foreground); text-decoration: none; border-bottom: 1px solid var(--input); }
.hms-pd-lede a:hover { border-bottom-color: var(--foreground); }

.hms-pd-stats { margin-top: 24px; padding-top: 18px; border-top: 1px solid var(--hairline); display: flex; align-items: flex-end; gap: 32px; flex-wrap: wrap; }
.hms-pd-stats .k { font-size: 12px; color: var(--muted-foreground); }
.hms-pd-stats .v { font-size: 19px; font-weight: 600; margin-top: 2px; color: var(--foreground); font-variant-numeric: tabular-nums; }
.hms-pd-primary { margin-left: auto; display: inline-flex; align-items: center; justify-content: center; min-height: 30px; padding: 4px 12px; font-family: inherit; font-size: 12.5px; font-weight: 600; color: var(--primary-foreground); background: var(--primary); border: 1px solid var(--primary); border-radius: 8px; cursor: pointer; white-space: nowrap; }
.hms-pd-primary:hover { background: color-mix(in oklch, var(--primary) 88%, black); border-color: color-mix(in oklch, var(--primary) 88%, black); }
.hms-pd-primary:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }

.hms-pd-tabs { display: flex; gap: 4px; margin-top: 32px; border-bottom: 1px solid var(--border); overflow-x: auto; overflow-y: hidden; }
.hms-pd-tab { display: inline-flex; align-items: center; gap: 7px; min-height: 40px; padding: 0 12px; margin-bottom: -1px; font-family: inherit; font-size: 13px; font-weight: 500; color: var(--muted-foreground); background: transparent; border: 0; border-bottom: 2px solid transparent; cursor: pointer; white-space: nowrap; }
.hms-pd-tab:hover { color: var(--foreground); }
.hms-pd-tab:focus-visible { outline: 2px solid var(--ring); outline-offset: -2px; }
.hms-pd-tab.active { font-weight: 600; color: var(--foreground); border-bottom-color: var(--foreground); }
.hms-pd-tab .n { font-size: 11.5px; font-weight: 500; color: var(--muted-foreground); background: var(--secondary); border-radius: 9999px; padding: 1px 8px; font-variant-numeric: tabular-nums; }

.hms-pd-panel { padding-top: 18px; padding-bottom: 12px; }
.hms-pd-mono { font: 400 12px ui-monospace, "SF Mono", Menlo, monospace; font-variant-numeric: tabular-nums; }
.hms-pd-panel .hms-dv-table th { font-size: 12px; font-weight: 500; padding: 0 16px 9px 0; }
.hms-pd-panel .hms-dv-table td { padding: 12px 16px 12px 0; vertical-align: middle; }
.hms-pd-panel .hms-dv-table th:last-child, .hms-pd-panel .hms-dv-table td:last-child { padding-right: 0; }
.hms-pd-panel .hms-dv-table .strong { font-weight: 500; }
.hms-pd-panel .hms-dv-table tfoot td { border-top: none; padding: 13px 16px 4px 0; }
.hms-pd-panel .hms-dv-table tfoot td:last-child { padding-right: 0; }
.hms-pd-panel .hms-dv-table tfoot .lbl { font-weight: 400; color: var(--muted-foreground); }
.hms-pd-panel .hms-dv-table tfoot .val { font-weight: 600; }

.hms-pd-dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px 16px; align-items: start; margin: 12px 0 0; padding: 14px 0 16px; border-top: 1px solid var(--hairline); }
.hms-pd-dl > div { min-width: 0; }
.hms-pd-dl dt { font-size: 12px; color: var(--muted-foreground); }
.hms-pd-dl dd { font-size: 14px; font-weight: 500; margin: 2px 0 0; color: var(--foreground); font-variant-numeric: tabular-nums; }

.hms-pd-file { display: flex; align-items: center; gap: 10px; min-width: 0; padding-top: 12px; border-top: 1px solid var(--hairline); text-decoration: none; border-radius: 8px; }
.hms-pd-file:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
.hms-pd-file .ico { width: 32px; height: 32px; border-radius: 8px; background: var(--secondary); color: var(--muted-foreground); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.hms-pd-file .n { display: block; font-size: 13px; font-weight: 500; color: var(--foreground); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hms-pd-file .s { display: block; font-size: 12px; color: var(--muted-foreground); margin-top: 1px; }

.hms-pd-rcpt + .hms-pd-rcpt { margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--hairline); }
.hms-pd-rcpt-h { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.hms-pd-rcpt-acts { display: flex; gap: 8px; margin-top: 12px; }
.hms-pd-rcpt-reason { margin: 8px 0 0; font-size: 12px; line-height: 1.5; color: var(--muted-foreground); }
.hms-pd-note { font-size: 13px; line-height: 1.6; margin: 8px 0 0; color: var(--foreground); text-wrap: pretty; }

.hms-pd-dlgdesc { font-size: 13px; color: var(--muted-foreground); margin: 6px 0 0; line-height: 1.6; }
.hms-pd-dlglabel { display: block; font-size: 12px; color: var(--muted-foreground); margin-top: 16px; margin-bottom: 6px; }

@media (max-width: 600px) {
  .hms-pd-main { padding: 18px 16px 8px; border-radius: 16px; }
  .hms-pd-card { border-radius: 16px; }
  .hms-pd-aside { position: static; }
  .hms-pd-stats { gap: 24px; }
  .hms-pd-primary { margin-left: 0; flex: 1 0 100%; }
  .hms-pd-panel .hms-dv-table td { padding: 3px 0; }
}
`;
