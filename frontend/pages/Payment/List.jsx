import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import Table from "../../components/shadcn/table.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";

const STATUS_TONE = {
  pending: "yellow",
  confirmed: "blue",
  allocated: "green",
  rejected: "red",
  reversed: "gray",
};

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
    bank_name: "",
    reference: "",
    note: "",
  });

  const filtered = statusFilter === "all"
    ? payments
    : payments.filter((p) => p.status === statusFilter);

  const confirmPayment = (payment) => {
    router.post(`/finance/payments/${payment.id}/confirm/`);
    setConfirmDialog(null);
  };

  const rejectPayment = () => {
    router.post(`/finance/payments/${rejectDialog.id}/reject/`, { reason: rejectDialog.reason });
    setRejectDialog(null);
  };

  const submitRecord = () => {
    if (recordForm.proof) {
      const fd = new FormData();
      Object.entries(recordForm).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "") fd.append(k, v);
      });
      router.post("/finance/payments/record/", fd, {
        onSuccess: () => setRecordDialog(false),
      });
    } else {
      const { proof, ...rest } = recordForm;
      router.post("/finance/payments/record/", rest, {
        onSuccess: () => setRecordDialog(false),
      });
    }
  };

  const columns = [
    {
      header: t("Payment #"),
      render: (p) => (
        <a href={`/finance/payments/${p.id}/`} className="text-blue-600 hover:underline font-medium">
          {p.payment_number}
        </a>
      ),
    },
    {
      header: t("Client"),
      className: "whitespace-nowrap",
      render: (p) => p.client_name || "—",
    },
    {
      header: t("Invoice"),
      className: "whitespace-nowrap",
      render: (p) => p.invoice_number || "—",
    },
    {
      header: t("Amount"),
      className: "text-right",
      render: (p) => (
        <span className="font-mono font-medium">{p.amount_sar?.toLocaleString()} SAR</span>
      ),
    },
    {
      header: t("Method"),
      render: (p) => p.method || "—",
    },
    {
      header: t("Date"),
      render: (p) => p.payment_date || "—",
    },
    {
      header: t("Status"),
      render: (p) => <StatusPill tone={STATUS_TONE[p.status] || "gray"} label={p.status_display} />,
    },
    {
      header: "",
      className: "w-10",
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
          <a href="/finance/periods/" className="btn btn-secondary btn-sm">{t("Periods")}</a>
          <a href="/finance/payments/export/csv/" target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">{t("Export CSV")}</a>
          <button className="btn btn-primary btn-sm" onClick={() => setRecordDialog(true)}>{t("Record Payment")}</button>
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
          <div className="empty">
            <div className="empty-title">{t("No payments found")}</div>
            <div className="empty-sub">{t("No payment records match your filters.")}</div>
          </div>
        )}
      </div>

      {/* Record Payment Dialog */}
      {recordDialog && (
        <Dialog open onOpenChange={(v) => { if (!v) setRecordDialog(false); }}>
          <DialogContent className="hms-dialog max-w-lg">
            <DialogHeader>
              <DialogTitle>{t("Record Payment")}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <label className="form-label">{t("Invoice")} *</label>
                <Select
                  value={recordForm.invoice_id}
                  onValueChange={(v) => setRecordForm({ ...recordForm, invoice_id: v })}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue placeholder={t("Select invoice...")} />
                  </SelectTrigger>
                  <SelectContent>
                    {invoice_choices.map((inv) => (
                      <SelectItem key={inv.id} value={String(inv.id)}>
                        {inv.label} ({inv.remaining?.toLocaleString()} SAR remaining)
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="form-label">{t("Date")} *</label>
                  <Input
                    type="date"
                    value={recordForm.payment_date}
                    onChange={(e) => setRecordForm({ ...recordForm, payment_date: e.target.value })}
                    className="mt-1"
                  />
                </div>
                <div>
                  <label className="form-label">{t("Amount")} *</label>
                  <Input
                    type="number"
                    value={recordForm.amount}
                    onChange={(e) => setRecordForm({ ...recordForm, amount: e.target.value })}
                    placeholder="0"
                    className="mt-1"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="form-label">{t("Currency")}</label>
                  <Input
                    value={recordForm.currency}
                    onChange={(e) => setRecordForm({ ...recordForm, currency: e.target.value })}
                    className="mt-1"
                  />
                </div>
                <div>
                  <label className="form-label">{t("Exchange Rate")}</label>
                  <Input
                    type="number"
                    step="0.0001"
                    value={recordForm.exchange_rate}
                    onChange={(e) => setRecordForm({ ...recordForm, exchange_rate: e.target.value })}
                    className="mt-1"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="form-label">{t("Method")}</label>
                  <Select
                    value={recordForm.method}
                    onValueChange={(v) => setRecordForm({ ...recordForm, method: v })}
                  >
                    <SelectTrigger className="mt-1">
                      <SelectValue placeholder={t("Select...")} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Cash">Cash</SelectItem>
                      <SelectItem value="Transfer">Transfer</SelectItem>
                      <SelectItem value="Direct">Direct</SelectItem>
                      <SelectItem value="Card">Card</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <label className="form-label">{t("Reference")}</label>
                  <Input
                    value={recordForm.reference}
                    onChange={(e) => setRecordForm({ ...recordForm, reference: e.target.value })}
                    placeholder={t("TRX number, check #, etc.")}
                    className="mt-1"
                  />
                </div>
              </div>
              <div>
                <label className="form-label">{t("Note")}</label>
                <Input
                  value={recordForm.note}
                  onChange={(e) => setRecordForm({ ...recordForm, note: e.target.value })}
                  className="mt-1"
                />
              </div>
              <div>
                <label className="form-label">{t("Proof (optional)")}</label>
                <input
                  type="file"
                  accept="image/*,.pdf"
                  onChange={(e) => setRecordForm({ ...recordForm, proof: e.target.files[0] })}
                  className="mt-1 block w-full text-sm text-muted-foreground file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-primary file:text-primary-foreground hover:file:bg-primary/90"
                />
              </div>
            </div>
            <DialogFooter>
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
