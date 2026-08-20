import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import Table from "../../components/shadcn/table.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { useI18n } from "../../utils/i18n.jsx";

const STATUS_TONE = {
  pending: "badge-yellow",
  confirmed: "badge-blue",
  allocated: "badge-green",
  rejected: "badge-red",
  reversed: "badge-gray",
};

export default function Detail({ payment = {}, logs = [], journal_entries = [] }) {
  const { t } = useI18n();
  const confirm = useConfirm();

  const handleConfirm = () => {
    confirm({
      title: t("Confirm Payment"),
      description: t("Confirm payment {number} for {amount} SAR?", {
        number: payment.payment_number,
        amount: payment.amount_sar?.toLocaleString(),
      }),
      onConfirm: () => router.post(`/finance/payments/${payment.id}/confirm/`),
    });
  };

  const handleReverse = () => {
    confirm({
      title: t("Reverse Payment"),
      description: t("Are you sure you want to reverse this payment? This will create a reversing journal entry."),
      variant: "destructive",
      onConfirm: () => router.post(`/finance/payments/${payment.id}/reverse/`),
    });
  };

  const jeColumns = [
    {
      header: t("Entry #"),
      render: (e) => <span className="font-medium font-mono text-xs">{e.entry_number}</span>,
    },
    {
      header: t("Type"),
      render: (e) => e.entry_type_display,
    },
    {
      header: t("Description"),
      render: (e) => e.description,
    },
    {
      header: t("Date"),
      render: (e) => e.entry_date,
    },
    {
      header: t("Debit"),
      className: "text-right font-mono",
      render: (e) => e.total_debit?.toLocaleString(),
    },
    {
      header: t("Credit"),
      className: "text-right font-mono",
      render: (e) => e.total_credit?.toLocaleString(),
    },
  ];

  const logColumns = [
    {
      header: t("Action"),
      render: (l) => <span className="font-medium">{l.action_display}</span>,
    },
    {
      header: t("By"),
      render: (l) => l.performed_by || "—",
    },
    {
      header: t("Note"),
      render: (l) => l.note || "—",
    },
    {
      header: t("Time"),
      render: (l) => l.performed_at || "—",
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack href="/finance/payments/" />
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">{payment.payment_number}</h1>
          <p className="text-muted-foreground text-sm">
            {t("Payment to {client}", { client: payment.client_name || "—" })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`badge ${STATUS_TONE[payment.status] || "badge-gray"}`}>
            {payment.status_display}
          </span>
          {payment.status === "pending" && (
            <Button onClick={handleConfirm}>{t("Confirm")}</Button>
          )}
          {(payment.status === "confirmed" || payment.status === "allocated") && (
            <Button variant="destructive" onClick={handleReverse}>{t("Reverse")}</Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card p-6">
          <h2 className="font-semibold mb-4">{t("Payment Details")}</h2>
          <div className="space-y-3 text-sm">
            <Row label={t("Amount")} value={`${payment.amount_sar?.toLocaleString()} SAR`} mono />
            <Row label={t("Original")} value={`${payment.amount?.toLocaleString()} ${payment.currency}`} />
            <Row label={t("Rate")} value={payment.exchange_rate} />
            <Row label={t("Method")} value={payment.method || "—"} />
            <Row label={t("Date")} value={payment.payment_date || "—"} />
            <Row label={t("Reference")} value={payment.reference || "—"} />
            <Row label={t("Bank")} value={payment.bank_name || "—"} />
            <Row label={t("Account #")} value={payment.account_number || "—"} />
          </div>
        </div>

        <div className="card p-6">
          <h2 className="font-semibold mb-4">{t("Audit Trail")}</h2>
          <div className="space-y-3 text-sm">
            <Row label={t("Created by")} value={payment.created_by || "—"} />
            <Row label={t("Created at")} value={payment.created_at || "—"} />
            <Row label={t("Confirmed by")} value={payment.confirmed_by || "—"} />
            <Row label={t("Confirmed at")} value={payment.confirmed_at || "—"} />
            <Row label={t("Period")} value={payment.period?.name || "—"} />
            {payment.rejected_reason && (
              <Row label={t("Rejection reason")} value={payment.rejected_reason} />
            )}
          </div>
        </div>
      </div>

      {payment.note && (
        <div className="card p-6 mt-6">
          <h2 className="font-semibold mb-2">{t("Note")}</h2>
          <p className="text-sm whitespace-pre-wrap">{payment.note}</p>
        </div>
      )}

      {journal_entries.length > 0 && (
        <div className="card p-6 mt-6">
          <h2 className="font-semibold mb-4">{t("Journal Entries")}</h2>
          <Table columns={jeColumns} rows={journal_entries} rowKey="id" />
        </div>
      )}

      {logs.length > 0 && (
        <div className="card p-6 mt-6">
          <h2 className="font-semibold mb-4">{t("Activity Log")}</h2>
          <Table columns={logColumns} rows={logs} rowKey="performed_at" />
        </div>
      )}
    </div>
  );
}

function Row({ label, value, mono }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className={mono ? "font-mono font-medium" : ""}>{value}</span>
    </div>
  );
}
