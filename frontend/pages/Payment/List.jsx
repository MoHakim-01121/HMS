import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import Table from "../../components/shadcn/table.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import {
  Dialog, DialogCloseButton, DialogContent, DialogFooter, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { showToast } from "../../components/shadcn/toast.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Keep in sync with nginx `client_max_body_size` on the VPS. A larger file is
// rejected upstream with a 413 before it ever reaches Django, so catch it here.
const MAX_PROOF_BYTES = 3 * 1024 * 1024;

// Only the allocation table needs bespoke styles — every field above it uses
// the shared FormField/.fg-* system, and the file input picks up the standard
// [data-slot="input"][type="file"] treatment from tailwind.css.
const CSS = `
.pay-dialog .pay-tbl-wrap {
  border: 1px solid var(--border);
  border-radius: var(--radius-control, 16px);
  background: var(--card);
  overflow: hidden;
}
.pay-dialog .pay-tbl { width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 0; }

.pay-dialog .pay-tbl thead th {
  padding: 0 10px; height: 38px;
  font-size: 12px; font-weight: 500; line-height: 38px;
  color: var(--muted-foreground); text-align: left; white-space: nowrap;
  background: var(--muted); border-bottom: 1px solid var(--border);
}
.pay-dialog .pay-tbl thead th.r { text-align: right; }
.pay-dialog .pay-tbl thead th + th { border-left: 1px solid var(--border); }

.pay-dialog .pay-tbl tbody td {
  padding: 0; height: 40px;
  border-bottom: 1px solid var(--border);
  background: transparent; vertical-align: middle;
}
.pay-dialog .pay-tbl tbody td + td { border-left: 1px solid var(--border); }
.pay-dialog .pay-tbl tbody tr:last-child td { border-bottom: 1px solid var(--border); }
.pay-dialog .pay-tbl tbody tr:hover td { background: color-mix(in oklch, var(--muted) 45%, transparent); }

.pay-dialog .pay-tbl .c-num {
  padding: 0 10px; text-align: right;
  font-family: var(--font-mono); font-size: 13px; font-weight: 600;
  color: var(--foreground); font-variant-numeric: tabular-nums;
}

.pay-dialog .pay-tbl .c-in {
  width: 100%; height: 100%; min-height: 40px;
  padding: 0 10px; margin: 0;
  background: transparent; border: none; border-radius: 0; box-shadow: none;
  font-family: inherit; font-size: 13px; font-weight: 400; color: var(--foreground);
  -webkit-appearance: none; appearance: none;
}
.pay-dialog .pay-tbl .c-in:focus {
  outline: none; border-color: transparent;
  box-shadow: inset 0 0 0 2px var(--ring);
  background: var(--card);
}
.pay-dialog .pay-tbl .c-in.c-num { text-align: right; font-variant-numeric: tabular-nums; }
.pay-dialog .pay-tbl .c-in[type="number"]::-webkit-outer-spin-button,
.pay-dialog .pay-tbl .c-in[type="number"]::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.pay-dialog .pay-tbl .c-in[type="number"] { -moz-appearance: textfield; }

.pay-dialog .pay-tbl .c-strong { font-weight: 600; }
.pay-dialog .pay-tbl .c-muted { color: var(--muted-foreground); }

.pay-dialog .pay-warn { font-size: 12px; color: var(--yellow); margin-top: 4px; }

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
  confirmed: "blue",
  allocated: "green",
  rejected: "red",
  reversed: "gray",
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

export default function List({ payments = [], status_choices = [], invoice_choices = [], stats = {} }) {
  const { t } = useI18n();
  const [statusFilter, setStatusFilter] = useState("all");
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
  const [allocations, setAllocations] = useState([]);

  // When invoice changes, populate reservations
  const selectedInvoice = invoice_choices.find((inv) => String(inv.id) === String(recordForm.invoice_id));
  const reservations = selectedInvoice?.reservations || [];

  const updateAllocation = (resId, value) => {
    setAllocations((prev) => {
      const num = parseFloat(value) || 0;
      const existing = prev.find((a) => a.reservation_id === resId);
      if (num <= 0) {
        return prev.filter((a) => a.reservation_id !== resId);
      }
      if (existing) {
        return prev.map((a) => a.reservation_id === resId ? { ...a, amount: num } : a);
      }
      return [...prev, { reservation_id: resId, amount: num }];
    });
  };

  const allocationTotal = allocations.reduce((s, a) => s + (a.amount || 0), 0);

  // Reset allocations when invoice changes
  const onInvoiceChange = (v) => {
    setRecordForm({ ...recordForm, invoice_id: v, amount: "" });
    setAllocations([]);
  };

  // Back to SAR means the rate is definitionally 1 — don't leave a stale
  // foreign rate behind for the next non-SAR payment to inherit.
  const onCurrencyChange = (v) => {
    setRecordForm({ ...recordForm, currency: v, exchange_rate: v === "SAR" ? "1" : recordForm.exchange_rate });
  };

  const filtered = statusFilter === "all"
    ? payments
    : payments.filter((p) => p.status === statusFilter);

  // Live SAR equivalent, mirroring the backend's convert_to_sar rounding.
  const payAmount = parseFloat(recordForm.amount) || 0;
  const payRate = parseFloat(recordForm.exchange_rate) || 0;
  const sarEquiv = recordForm.currency !== "SAR" && payAmount > 0 && payRate > 0
    ? Math.round(payAmount * payRate).toLocaleString()
    : null;

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
    const hasAllocations = allocations.length > 0;
    const payload = {
      ...recordForm,
      ...(hasAllocations ? { allocations: JSON.stringify(allocations) } : {}),
    };
    if (recordForm.proof) {
      const fd = new FormData();
      Object.entries(payload).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "") fd.append(k, v);
      });
      router.post("/finance/payments/record/", fd, {
        onSuccess: () => { setRecordDialog(false); setAllocations([]); },
      });
    } else {
      const { proof, ...rest } = payload;
      router.post("/finance/payments/record/", rest, {
        onSuccess: () => { setRecordDialog(false); setAllocations([]); },
      });
    }
  };

  const columns = [
    {
      header: t("Payment #"),
      className: "col-m-primary",
      render: (p) => (
        <a href={`/finance/payments/${p.id}/`} className="text-blue-600 hover:underline font-medium">
          {p.payment_number}
        </a>
      ),
    },
    {
      header: t("Status"),
      className: "col-m-badge",
      render: (p) => <StatusPill tone={STATUS_TONE[p.status] || "gray"} label={p.status_display} />,
    },
    {
      header: t("Client"),
      className: "col-m-secondary",
      render: (p) => p.client_name || "—",
    },
    {
      header: t("Invoice"),
      className: "col-m-hide",
      render: (p) => p.invoice_number || "—",
    },
    {
      header: t("Amount"),
      className: "mono col-nowrap col-m-amount",
      render: (p) => (
        <>
          <span className="m-hide">{p.amount_sar?.toLocaleString()} SAR</span>
          <span className="m-only" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--text-3)", fontWeight: 700 }}>{t("Amount")}</span>
          <span className="m-only">{p.amount_sar?.toLocaleString()} SAR</span>
        </>
      ),
    },
    {
      header: t("Method"),
      className: "col-m-meta",
      render: (p) => p.method || "—",
    },
    {
      header: t("Date"),
      className: "col-m-meta",
      render: (p) => p.payment_date || "—",
    },
    {
      header: "",
      className: "col-m-actions",
      render: (p) => (
        <RowActions
          actions={[
            { label: t("Detail"), href: `/finance/payments/${p.id}/` },
            ...(p.status === "pending" ? [
              { label: t("Confirm"), onClick: () => setConfirmDialog(p) },
              { label: t("Reject"), onClick: () => setRejectDialog({ ...p, reason: "" }), destructive: true },
            ] : []),
          ]}
        />
      ),
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />

      <div className="page-header">
        <div>
          <div className="page-title">{t("Payments")}</div>
          <div className="page-sub">{t("Track all payment records and their status.")}</div>
        </div>
        <div className="page-actions">
          <a href="/finance/payments/export/csv/" target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">{t("Export CSV")}</a>
          <button className="btn btn-primary btn-sm" onClick={() => setRecordDialog(true)}>+ {t("Record Payment")}</button>
        </div>
      </div>

      {/* KPI Row */}
      <div className="hms-kpi-row">
        <KpiCard label={t("Total Payments")} value={stats.total || 0} icon="wallet" />
        <KpiCard label={t("Pending")} value={stats.pending || 0} icon="clock" tone={stats.pending > 0 ? "yellow" : undefined} />
        <KpiCard label={t("Confirmed")} value={stats.confirmed || 0} icon="check" tone="blue" />
        <KpiCard label={t("Allocated")} value={stats.allocated || 0} icon="check" tone="green" />
      </div>

      {/* Filter Bar */}
      <div className="filter-bar">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
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
      <div className="card">
        {filtered.length > 0 ? (
          <Table columns={columns} rows={filtered} rowKey={(p) => p.id} />
        ) : (
          <EmptyState title="No payments found" sub="No payment records match your filters." />
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

                {reservations.length > 0 && (
                  <FormSection label={t("Allocate to Reservations")}>
                    <div className="pay-tbl-wrap">
                      <table className="pay-tbl">
                        <colgroup>
                          <col style={{ width: 100 }} />
                          <col />
                          <col style={{ width: 110 }} />
                          <col style={{ width: 130 }} />
                        </colgroup>
                        <thead>
                          <tr>
                            <th>#RSV</th>
                            <th>{t("Hotel")}</th>
                            <th className="r">{t("Remaining")}</th>
                            <th className="r">{t("Pay")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {reservations.map((res) => {
                            const alloc = allocations.find((a) => a.reservation_id === res.id);
                            const allocAmount = alloc?.amount || "";
                            return (
                              <tr key={res.id}>
                                <td><span className="c-in c-strong">{res.number}</span></td>
                                <td><span className="c-in c-muted">{res.hotel}</span></td>
                                <td><span className="c-in c-num">{res.remaining?.toLocaleString()}</span></td>
                                <td>
                                  <input type="number" min="0" max={res.remaining} step="1"
                                    value={allocAmount}
                                    onChange={(e) => updateAllocation(res.id, e.target.value)}
                                    placeholder="0"
                                    className="c-in c-num" />
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                    {allocations.length > 0 && allocationTotal !== parseFloat(recordForm.amount || 0) && (
                      <div className="pay-warn">
                        {t("Allocation ({alloc}) != Amount ({amt})", {
                          alloc: allocationTotal.toLocaleString(),
                          amt: (parseFloat(recordForm.amount) || 0).toLocaleString(),
                        })}
                      </div>
                    )}
                  </FormSection>
                )}

                <FormSection label={t("Proof")}>
                  <FormField name="proof" hint={t("Image or PDF")}>
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
              <Button onClick={submitRecord} disabled={!recordForm.invoice_id || !recordForm.amount}>
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
            <textarea
              className="input w-full"
              rows={3}
              placeholder={t("Reason for rejection...")}
              value={rejectDialog.reason}
              onChange={(e) => setRejectDialog({ ...rejectDialog, reason: e.target.value })}
            />
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
