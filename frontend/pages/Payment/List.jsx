import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import Table from "../../components/shadcn/table.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { useI18n } from "../../utils/i18n.jsx";

const STATUS_TONE = {
  pending: "badge-yellow",
  confirmed: "badge-blue",
  allocated: "badge-green",
  rejected: "badge-red",
  reversed: "badge-gray",
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

  const rejectPayment = (payment) => {
    router.post(`/finance/payments/${payment.id}/reject/`, { reason: rejectDialog.reason });
    setRejectDialog(null);
  };

  const submitRecord = () => {
    router.post("/finance/payments/record/", recordForm, {
      onSuccess: () => setRecordDialog(false),
    });
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
      className: "text-right font-mono",
      render: (p) => `${p.amount_sar?.toLocaleString()} SAR`,
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
      render: (p) => (
        <span className={`badge ${STATUS_TONE[p.status] || "badge-gray"}`}>
          {p.status_display}
        </span>
      ),
    },
    {
      header: "",
      className: "w-10",
      render: (p) => (
        <RowActions
          items={[
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
      <PageBack href="/" />
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">{t("Payments")}</h1>
          <p className="text-muted-foreground text-sm">{t("Track all payment records and their status.")}</p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder={t("All Status")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("All Status")}</SelectItem>
              {status_choices.map(([value, label]) => (
                <SelectItem key={value} value={value}>{label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <a href="/finance/payments/export/csv/" target="_blank" rel="noreferrer">
            <Button variant="outline" size="sm">{t("Export CSV")}</Button>
          </a>
          <Button size="sm" onClick={() => setRecordDialog(true)}>{t("Record Payment")}</Button>
          <a href="/finance/periods/">
            <Button variant="outline" size="sm">{t("Periods")}</Button>
          </a>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard label={t("Total Payments")} value={stats.total || 0} />
        <StatCard label={t("Pending")} value={stats.pending || 0} tone="yellow" />
        <StatCard label={t("Confirmed")} value={stats.confirmed || 0} tone="blue" />
        <StatCard label={t("Allocated")} value={stats.allocated || 0} tone="green" />
      </div>

      <Table columns={columns} rows={filtered} rowKey="id" />

      {/* Record Payment Dialog */}
      {recordDialog && (
        <Dialog open onOpenChange={(v) => { if (!v) setRecordDialog(false); }}>
          <DialogContent className="hms-dialog max-w-lg">
            <DialogHeader>
              <DialogTitle>{t("Record Payment")}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium">{t("Invoice")} *</label>
                <Select
                  value={recordForm.invoice_id}
                  onValueChange={(v) => setRecordForm({ ...recordForm, invoice_id: v })}
                >
                  <SelectTrigger className="w-full mt-1">
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
                  <label className="text-sm font-medium">{t("Date")} *</label>
                  <Input
                    type="date"
                    value={recordForm.payment_date}
                    onChange={(e) => setRecordForm({ ...recordForm, payment_date: e.target.value })}
                    className="mt-1"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium">{t("Amount")} *</label>
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
                  <label className="text-sm font-medium">{t("Currency")}</label>
                  <Input
                    value={recordForm.currency}
                    onChange={(e) => setRecordForm({ ...recordForm, currency: e.target.value })}
                    className="mt-1"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium">{t("Exchange Rate")}</label>
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
                  <label className="text-sm font-medium">{t("Method")}</label>
                  <Select
                    value={recordForm.method}
                    onValueChange={(v) => setRecordForm({ ...recordForm, method: v })}
                  >
                    <SelectTrigger className="w-full mt-1">
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
                  <label className="text-sm font-medium">{t("Reference")}</label>
                  <Input
                    value={recordForm.reference}
                    onChange={(e) => setRecordForm({ ...recordForm, reference: e.target.value })}
                    placeholder={t("TRX number, check #, etc.")}
                    className="mt-1"
                  />
                </div>
              </div>
              <div>
                <label className="text-sm font-medium">{t("Note")}</label>
                <Input
                  value={recordForm.note}
                  onChange={(e) => setRecordForm({ ...recordForm, note: e.target.value })}
                  className="mt-1"
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
            <p>{t("Confirm payment {number} for {amount} SAR?", { number: confirmDialog.payment_number, amount: confirmDialog.amount_sar?.toLocaleString() })}</p>
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
              placeholder={t("Reason for rejection...")}
              value={rejectDialog.reason}
              onChange={(e) => setRejectDialog({ ...rejectDialog, reason: e.target.value })}
            />
            <DialogFooter>
              <Button variant="outline" onClick={() => setRejectDialog(null)}>{t("Cancel")}</Button>
              <Button variant="destructive" onClick={() => rejectPayment(rejectDialog)}>{t("Reject")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

function StatCard({ label, value, tone }) {
  return (
    <div className="card p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-2xl font-bold mt-1">{typeof value === "number" ? value.toLocaleString() : value}</p>
    </div>
  );
}
