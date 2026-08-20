import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import Table from "../../components/shadcn/table.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
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

export default function List({ payments = [], status_choices = [] }) {
  const { t } = useI18n();
  const [statusFilter, setStatusFilter] = useState("all");
  const [confirmDialog, setConfirmDialog] = useState(null);
  const [rejectDialog, setRejectDialog] = useState(null);

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
          <a href="/finance/periods/">
            <Button variant="outline" size="sm">{t("Periods")}</Button>
          </a>
        </div>
      </div>

      <Table columns={columns} rows={filtered} rowKey="id" />

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
