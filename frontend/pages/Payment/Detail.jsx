import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
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

  const confirm = () => {
    router.post(`/finance/payments/${payment.id}/confirm/`);
  };

  const reverse = () => {
    if (confirm(t("Are you sure you want to reverse this payment?"))) {
      router.post(`/finance/payments/${payment.id}/reverse/`);
    }
  };

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
          {payment.status === "pending" && (
            <Button onClick={confirm}>{t("Confirm")}</Button>
          )}
          {(payment.status === "confirmed" || payment.status === "allocated") && (
            <Button variant="destructive" onClick={reverse}>{t("Reverse")}</Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Payment Info */}
        <div className="card p-6">
          <h2 className="font-semibold mb-4">{t("Payment Details")}</h2>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t("Amount")}</span>
              <span className="font-mono font-medium">{payment.amount_sar?.toLocaleString()} SAR</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t("Method")}</span>
              <span>{payment.method || "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t("Date")}</span>
              <span>{payment.payment_date || "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t("Reference")}</span>
              <span>{payment.reference || "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t("Status")}</span>
              <span className={`badge ${STATUS_TONE[payment.status] || "badge-gray"}`}>
                {payment.status_display}
              </span>
            </div>
          </div>
        </div>

        {/* Audit Info */}
        <div className="card p-6">
          <h2 className="font-semibold mb-4">{t("Audit Trail")}</h2>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t("Created by")}</span>
              <span>{payment.created_by || "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t("Created at")}</span>
              <span>{payment.created_at || "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t("Confirmed by")}</span>
              <span>{payment.confirmed_by || "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t("Confirmed at")}</span>
              <span>{payment.confirmed_at || "—"}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Journal Entries */}
      {journal_entries.length > 0 && (
        <div className="card p-6 mt-6">
          <h2 className="font-semibold mb-4">{t("Journal Entries")}</h2>
          <div className="space-y-3">
            {journal_entries.map((je) => (
              <div key={je.id} className="flex items-center justify-between text-sm border-b pb-2">
                <div>
                  <span className="font-medium">{je.entry_number}</span>
                  <span className="ml-2 text-muted-foreground">{je.description}</span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-muted-foreground">{je.entry_date}</span>
                  <span className="font-mono">{je.total_debit?.toLocaleString()} / {je.total_credit?.toLocaleString()}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Activity Log */}
      {logs.length > 0 && (
        <div className="card p-6 mt-6">
          <h2 className="font-semibold mb-4">{t("Activity Log")}</h2>
          <div className="space-y-3">
            {logs.map((log, i) => (
              <div key={i} className="flex items-start gap-3 text-sm border-b pb-2">
                <div className="w-2 h-2 rounded-full bg-blue-500 mt-1.5" />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{log.action_display}</span>
                    <span className="text-muted-foreground">by {log.performed_by}</span>
                  </div>
                  {log.note && <p className="text-muted-foreground mt-1">{log.note}</p>}
                </div>
                <span className="text-muted-foreground text-xs">{log.performed_at}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
