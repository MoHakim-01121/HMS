import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import Table from "../../components/shadcn/table.jsx";
import Pagination from "../../components/shadcn/pagination.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import { listVisit } from "../../utils/listVisit.js";
import {
  Dialog, DialogCloseButton, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { showToast } from "../../components/shadcn/toast.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";

// Keep in sync with nginx `client_max_body_size` on the VPS. A larger file is
// rejected upstream with a 413 before it ever reaches Django, so catch it here.
const MAX_PROOF_BYTES = 3 * 1024 * 1024;

// Only the unapplied status hint + unapplied bar need bespoke styles —
// every field uses the shared FormField/.fg-* system, and the file input
// picks up the standard [data-slot="input"][type="file"] treatment.
const CSS = `
.pay-dialog .pay-warn { font-size: 12px; color: var(--yellow); margin-top: 4px; }

.pay-unapplied-bar {
  display:flex; align-items:center; gap:10px; flex-wrap:wrap;
  padding:10px 14px; margin-bottom:16px;
  border:1px solid color-mix(in oklch, var(--yellow) 40%, transparent);
  border-radius:14px; background: color-mix(in oklch, var(--yellow) 8%, var(--card));
}
.pay-unapplied-dot { width:8px; height:8px; border-radius:50%; background:var(--yellow); flex-shrink:0; }
.pay-unapplied-text { font-size:13px; font-weight:600; color:var(--foreground); }
.pay-unapplied-hint { font-size:12px; color:var(--muted-foreground); }

/* Pinned action strip — same treatment as the shared modal's sticky
   .hms-form-actions (tailwind.css), as a plain footer since this dialog
   doesn't render the actions inside the scrolling body. */
.pay-dialog .pay-footer {
  padding: 14px 20px;
  border-top: 1px solid var(--border);
  background: var(--background);
  flex-shrink: 0;
}
`;

const STATUS_TONE = {
  pending: "yellow",
  received: "blue",
  confirmed: "blue",
  allocated: "green",
  partially_applied: "yellow",
  applied: "green",
  rejected: "red",
  reversed: "gray",
  voided: "gray",
};

// Same list the Penalty form offers.
const CURRENCIES = ["SAR", "IDR", "USD"];

// Where the money physically lands — drives ledger routing (see
// hw/ledger.py cash_destination). "Direct" is no longer a method here:
// the destination is what matters, not how the client paid.
const RECEIVED_IN = [
  { value: "sby", label: "Surabaya" },
  { value: "jkt", label: "Jakarta" },
  { value: "pusat", label: "HQ (Direct)" },
];

export default function List({ payments = [], status_choices = [], invoice_choices = [], stats = {}, pagination = null, status_filter = "all" }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canCreate = perms.can("payments", "create");
  const canEdit = perms.can("payments", "edit");
  const canExport = perms.can("payments", "export");
  const [statusFilter, setStatusFilter] = useState(status_filter);
  const [confirmDialog, setConfirmDialog] = useState(null);
  const [rejectDialog, setRejectDialog] = useState(null);
  const [recordDialog, setRecordDialog] = useState(false);
  const [recordForm, setRecordForm] = useState({
    invoice_id: "",
    payment_date: new Date().toISOString().split("T")[0],
    amount: "",
    currency: "SAR",
    exchange_rate: "1",
    method: "",
    received_in: "sby",
    bank_name: "",
    reference: "",
    note: "",
  });

  // When invoice changes, populate reservations
  const selectedInvoice = invoice_choices.find((inv) => String(inv.id) === String(recordForm.invoice_id));

  // Filtering is now server-side (keeps pagination consistent). Picking a
  // status resets back to page 1 so the result set matches the filter.
  const onStatusChange = (v) => {
    setStatusFilter(v);
    listVisit("/finance/payments/", v === "all" ? {} : { status: v, page: 1 });
  };

  // Parse a numeric input that may carry thousands separators -- either
  // "48,000,000" (en-US) or "48.000.000" (id-ID). Amounts, rates and
  // allocations here are practical integers, so both separators are
  // stripped before parsing (a lone "." stays a float for sub-1 rates).
  const parseNum = (v) => {
    if (v == null || v === "") return 0;
    const cleaned = String(v).replace(/[^\d.,-]/g, "");
    const n = parseFloat(cleaned.replace(/,/g, "").replace(/\.(?=\d{3}\b)/g, ""));
    return isNaN(n) ? 0 : n;
  };

  // Reset amount when invoice changes
  const onInvoiceChange = (v) => {
    setRecordForm({ ...recordForm, invoice_id: v, amount: "" });
  };

  // Back to SAR means the rate is definitionally 1 — don't leave a stale
  // foreign rate behind for the next non-SAR payment to inherit.
  const onCurrencyChange = (v) => {
    setRecordForm({ ...recordForm, currency: v, exchange_rate: v === "SAR" ? "1" : recordForm.exchange_rate });
  };

  const filtered = payments;

  // Live SAR equivalent, mirroring the backend's convert_to_sar
  // (hw/utils.py): IDR divides by the rate, every other non-SAR currency
  // multiplies. Keeping this in lockstep with the backend is what prevents
  // the preview from disagreeing with the stored amount_sar.
  const payAmount = parseNum(recordForm.amount);
  const payRate = parseNum(recordForm.exchange_rate);
  let sarEquiv = null;
  if (recordForm.currency !== "SAR" && payAmount > 0 && payRate > 0) {
    const sar =
      recordForm.currency === "IDR"
        ? payAmount / payRate
        : payAmount * payRate;
    sarEquiv = Math.round(sar).toLocaleString();
  }


  const confirmPayment = (payment) => {
    router.post(`/finance/payments/${payment.id}/confirm/`);
    setConfirmDialog(null);
  };

  const rejectPayment = () => {
    router.post(`/finance/payments/${rejectDialog.id}/reject/`, { reason: rejectDialog.reason });
    setRejectDialog(null);
  };

  const submitRecord = () => {
    if (recordForm.proof && recordForm.proof.size > MAX_PROOF_BYTES) {
      showToast(t("File too large. Maximum upload size is 3 MB."), "error");
      return;
    }
    if (!recordForm.proof) {
      showToast(t("Proof is required. Attach an image or PDF."), "error");
      return;
    }
    // Strip thousands separators so the backend's _to_float (which removes
    // ",") receives a clean integer and never mis-reads "4,800" as "4.8".
    const cleanNum = (v) => (v == null || v === "" ? v : String(v).replace(/,/g, ""));
    const payload = {
      ...recordForm,
      amount: cleanNum(recordForm.amount),
      exchange_rate: cleanNum(recordForm.exchange_rate),
    };
    const fd = new FormData();
    Object.entries(payload).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") fd.append(k, v);
    });
    fd.append("proof", recordForm.proof);
    router.post("/finance/payments/record/", fd, {
      onSuccess: () => setRecordDialog(false),
    });
  };

  // Single truncating class for the two free-text columns so long client /
  // method values ellipsize instead of stretching the auto-width table into
  // a horizontal scroll (the table itself stays w-full inside the card).
  const ellipsis = { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" };

  const columns = [
    {
      header: t("Payment #"),
      className: "col-m-primary",
      render: (p) => <span className="col-bold col-nowrap">{p.payment_number}</span>,
    },
    {
      header: t("Status"),
      className: "col-m-badge",
      render: (p) => <StatusPill tone={STATUS_TONE[p.status] || "gray"} label={p.status_display} />,
    },
    {
      header: t("Client"),
      className: "col-m-secondary",
      style: { ...ellipsis, maxWidth: 220, minWidth: 120 },
      render: (p) => p.client_name || "—",
    },
    {
      header: t("Invoice"),
      className: "col-m-meta",
      style: ellipsis,
      render: (p) => p.invoice_number || "—",
    },
    {
      header: t("Amount"),
      className: "col-m-amount",
      style: { textAlign: "right" },
      render: (p) => (
        <>
          <span className="col-nowrap">
            {p.amount_sar?.toLocaleString()} SAR
          </span>
          {p.unallocated_sar > 0 && (
            <span className="pay-warn" style={{ display: "block", marginTop: 2, fontSize: 11, fontWeight: 600, whiteSpace: "nowrap" }}>
              {p.unallocated_sar?.toLocaleString()} SAR unalloc
            </span>
          )}
        </>
      ),
    },
    {
      header: t("Method"),
      className: "col-m-meta",
      style: ellipsis,
      render: (p) => p.method || "—",
    },
    {
      header: t("Date"),
      className: "col-m-meta col-nowrap",
      render: (p) => p.payment_date || "—",
    },
    {
      header: "",
      className: "col-m-actions",
      render: (p) => (
        <RowActions
          actions={[
            ...(canEdit && p.status === "pending" ? [
              { icon: "close", label: t("Reject"), variant: "red", onClick: () => setRejectDialog({ ...p, reason: "" }) },
            ] : []),
            ...(canEdit && ["received", "partially_applied"].includes(p.status) ? [
              { icon: "arrow-right", label: t("Apply"), variant: "green", href: `/finance/payments/${p.id}/` },
            ] : []),
          ]}
        />
      ),
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />

      <PageHeader
        title={t("Payments")}
        sub={t("Track all payment records and their status.")}
        actions={
          <>
            {canExport && (
              <Button asChild variant="outline" size="lg">
                <a href="/finance/payments/export/csv/" target="_blank" rel="noreferrer">{t("Export CSV")}</a>
              </Button>
            )}
            {canCreate && (
              <Button size="lg" onClick={() => setRecordDialog(true)}>{t("Record Payment")}</Button>
            )}
          </>
        }
      />

      {/* KPI Row */}
      <div className="hms-kpi-row">
        <KpiCard label={t("Total Payments")} value={stats.total || 0} icon="wallet" />
        <KpiCard label={t("Allocated")} value={stats.allocated || 0} icon="check" tone="green" />
        <KpiCard label={t("Partially Applied")} value={stats.partially_applied || 0} icon="clock" tone="yellow" />
        <KpiCard label={t("Unapplied")} value={stats.unapplied_total ?? "—"} icon="alert" tone={(stats.unapplied_total ?? 0) > 0 ? "yellow" : undefined} />
      </div>

      {/* Unapplied summary bar */}
      {(stats?.unapplied_total || 0) > 0 && (
        <div className="pay-unapplied-bar" role="note">
          <span className="pay-unapplied-dot" aria-hidden="true" />
          <span className="pay-unapplied-text">
            {t("{n} SAR unapplied across {c} payment(s)", {
              n: (stats.unapplied_total ?? 0).toLocaleString(),
              c: stats.unapplied_count ?? 0,
            })}
          </span>
          <span className="pay-unapplied-hint">{t("Assign these to reservations to clear them.")}</span>
        </div>
      )}

      {/* Filter Bar */}
      <div className="filter-bar">
        <Select value={statusFilter} onValueChange={onStatusChange}>
          <SelectTrigger className="w-44" style={{ height: 40 }}>
            <SelectValue placeholder={t("All Status")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("All Status")}</SelectItem>
            {status_choices.map(([value, label]) => (
              <SelectItem key={value} value={value}>{label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <div className="hms-list-card">
        {filtered.length > 0 ? (
          <>
            <Table
              columns={columns}
              rows={filtered}
              rowKey={(p) => p.id}
              onRowClick={(p) => router.visit(`/finance/payments/${p.id}/`)}
            />
            <Pagination
              pagination={pagination}
              unit={t("payments")}
              onPage={(p) => listVisit("/finance/payments/", {
                ...(statusFilter !== "all" ? { status: statusFilter } : {}),
                page: p,
              })}
            />
          </>
        ) : (
          <EmptyState iconName="wallet" title="No payments found" sub="No payment records match your filters." />
        )}
      </div>

      {/* Record Payment Dialog */}
      {recordDialog && (
        <Dialog open onOpenChange={(v) => { if (!v) setRecordDialog(false); }}>
          <DialogContent className="sm:max-w-3xl form-modal-content pay-dialog" showCloseButton={false}>
            <style>{CSS}</style>
            <div className="hms-modal-head">
              <div style={{ minWidth: 0 }}>
                <DialogTitle className="hms-modal-title">{t("Record Payment")}</DialogTitle>
              </div>
              <DialogCloseButton />
            </div>

            <div className="hms-modal-body">
              <form
                onSubmit={(e) => { e.preventDefault(); submitRecord(); }}
                style={{ display: "flex", flexDirection: "column", gap: 24 }}
              >
                <FormSection label={t("Payment Details")}>
                  <FormField label={t("Invoice")} name="invoice_id" required>
                    <Select value={recordForm.invoice_id} onValueChange={onInvoiceChange}>
                      <SelectTrigger className="w-full"><SelectValue placeholder={t("Select invoice...")} /></SelectTrigger>
                      <SelectContent>
                        {invoice_choices.map((inv) => (
                          <SelectItem key={inv.id} value={String(inv.id)}>
                            {inv.label} ({inv.remaining?.toLocaleString()} SAR remaining)
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FormField>

                  {/* fg-3 collapses to a 2-col grid inside .hms-modal-body
                      (tailwind.css). Ordered so both states pack cleanly:
                      SAR → Date|Amount / Currency|Received / Method|Reference;
                      non-SAR → Currency pairs with its Rate. */}
                  <div className="fg-3">
                    <FormField label={t("Date")} name="payment_date" type="date" required
                      value={recordForm.payment_date}
                      onChange={(v) => setRecordForm({ ...recordForm, payment_date: v })} />
                    <FormField label={t("Amount")} name="amount" type="number" required
                      value={recordForm.amount} placeholder="0"
                      onChange={(v) => setRecordForm({ ...recordForm, amount: v })} />
                    <FormField label={t("Currency")} name="currency">
                      <Select value={recordForm.currency} onValueChange={onCurrencyChange}>
                        <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </FormField>
                    {recordForm.currency !== "SAR" && (
                      <FormField label={t("Exchange Rate")} name="exchange_rate" type="number" step="0.0001" required
                        value={recordForm.exchange_rate}
                        onChange={(v) => setRecordForm({ ...recordForm, exchange_rate: v })}
                        hint={sarEquiv ? `≈ ${sarEquiv} SAR` : undefined} />
                    )}
                    <FormField label={t("Received In")} name="received_in">
                      <Select value={recordForm.received_in} onValueChange={(v) => setRecordForm({ ...recordForm, received_in: v })}>
                        <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {RECEIVED_IN.map((r) => <SelectItem key={r.value} value={r.value}>{t(r.label)}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </FormField>
                    <FormField label={t("Method")} name="method">
                      <Select value={recordForm.method} onValueChange={(v) => setRecordForm({ ...recordForm, method: v })}>
                        <SelectTrigger className="w-full"><SelectValue placeholder={t("Select...")} /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="Cash">{t("Cash")}</SelectItem>
                          <SelectItem value="Transfer">{t("Transfer")}</SelectItem>
                          <SelectItem value="Card">{t("Card")}</SelectItem>
                        </SelectContent>
                      </Select>
                    </FormField>
                    <FormField label={t("Reference")} name="reference"
                      value={recordForm.reference} placeholder={t("TRX #, check #, etc.")}
                      onChange={(v) => setRecordForm({ ...recordForm, reference: v })} />
                  </div>

                  <FormField label={t("Note")} name="note">
                    <Textarea rows={2} value={recordForm.note}
                      onChange={(e) => setRecordForm({ ...recordForm, note: e.target.value })} />
                  </FormField>
                </FormSection>

                <FormSection label={t("Proof (required)")}>
                  <FormField name="proof" hint={t("Image or PDF — required for every payment")} required>
                    <Input type="file" accept="image/*,.pdf"
                      onChange={(e) => {
                        const f = e.target.files[0];
                        if (f && f.size > MAX_PROOF_BYTES) {
                          showToast(t("File too large. Maximum upload size is 3 MB."), "error");
                          e.target.value = "";
                          setRecordForm({ ...recordForm, proof: undefined });
                          return;
                        }
                        setRecordForm({ ...recordForm, proof: f });
                      }} />
                  </FormField>
                </FormSection>
              </form>
            </div>

            <DialogFooter className="pay-footer">
              <Button variant="outline" onClick={() => setRecordDialog(false)}>{t("Cancel")}</Button>
              <Button onClick={submitRecord} disabled={!recordForm.invoice_id || !recordForm.amount || !recordForm.proof}>
                {t("Record Payment")}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {/* Confirm Dialog */}
      {confirmDialog && (
        <Dialog open onOpenChange={(v) => { if (!v) setConfirmDialog(null); }}>
          <DialogContent className="hms-dialog">
            <DialogHeader>
              <DialogTitle>{t("Confirm Payment")}</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-muted-foreground">
              {t("Confirm payment {number} for {amount} SAR?", {
                number: confirmDialog.payment_number,
                amount: confirmDialog.amount_sar?.toLocaleString(),
              })}
            </p>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirmDialog(null)}>{t("Cancel")}</Button>
              <Button onClick={() => confirmPayment(confirmDialog)}>{t("Confirm")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {/* Reject Dialog */}
      {rejectDialog && (
        <Dialog open onOpenChange={(v) => { if (!v) setRejectDialog(null); }}>
          <DialogContent className="hms-dialog">
            <DialogHeader>
              <DialogTitle>{t("Reject Payment")}</DialogTitle>
            </DialogHeader>
            <FormField label={t("Reason")} name="reject_reason">
              <Textarea
                rows={3}
                placeholder={t("Reason for rejection...")}
                value={rejectDialog.reason}
                onChange={(e) => setRejectDialog({ ...rejectDialog, reason: e.target.value })}
              />
            </FormField>
            <DialogFooter>
              <Button variant="outline" onClick={() => setRejectDialog(null)}>{t("Cancel")}</Button>
              <Button variant="destructive" onClick={rejectPayment}>{t("Reject")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
