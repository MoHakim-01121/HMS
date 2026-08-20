import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import Table from "../../components/shadcn/table.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";

const STATUS_TONE = {
  open: "badge-green",
  soft_close: "badge-yellow",
  closed: "badge-orange",
  locked: "badge-gray",
};

const ENTRY_TYPE_TONE = {
  charge: "badge-blue",
  payment: "badge-green",
  allocate: "badge-yellow",
  transfer: "badge-purple",
  refund: "badge-orange",
  penalty: "badge-red",
  reversal: "badge-gray",
};

export default function Detail({ period = {}, entries = [], payments = [], account_balances = [], total_debit = 0, total_credit = 0 }) {
  const { t } = useI18n();

  const closePeriod = () => {
    if (confirm(t("Close this period? No more journal entries will be allowed."))) {
      router.post(`/finance/periods/${period.id}/close/`);
    }
  };

  const lockPeriod = () => {
    if (confirm(t("Lock this period? This is IRREVERSIBLE."))) {
      router.post(`/finance/periods/${period.id}/lock/`);
    }
  };

  const entryColumns = [
    {
      header: t("Entry #"),
      render: (e) => <span className="font-medium font-mono text-xs">{e.entry_number}</span>,
    },
    {
      header: t("Type"),
      render: (e) => (
        <span className={`badge ${ENTRY_TYPE_TONE[e.entry_type] || "badge-gray"}`}>
          {e.entry_type_display}
        </span>
      ),
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
    {
      header: t("Balanced"),
      className: "text-center",
      render: (e) => e.is_balanced ? <span className="text-green-600">✓</span> : <span className="text-red-600">✗</span>,
    },
  ];

  const paymentColumns = [
    {
      header: t("Payment #"),
      render: (p) => (
        <a href={`/finance/payments/${p.id}/`} className="text-blue-600 hover:underline">
          {p.payment_number}
        </a>
      ),
    },
    {
      header: t("Client"),
      render: (p) => p.client_name || "—",
    },
    {
      header: t("Amount"),
      className: "text-right font-mono",
      render: (p) => `${p.amount_sar?.toLocaleString()} SAR`,
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
      header: t("Date"),
      render: (p) => p.payment_date || "—",
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack href="/finance/periods/" />
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">{period.name}</h1>
          <p className="text-muted-foreground text-sm">
            {period.date_from} — {period.date_to}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`badge ${STATUS_TONE[period.status] || "badge-gray"}`}>
            {period.status_display}
          </span>
          {period.is_postable && (
            <Button variant="outline" size="sm" onClick={closePeriod}>{t("Close Period")}</Button>
          )}
          {period.status === "closed" && (
            <Button variant="destructive" size="sm" onClick={lockPeriod}>{t("Lock Period")}</Button>
          )}
        </div>
      </div>

      {/* Account Balances */}
      {account_balances.length > 0 && (
        <div className="card p-6 mb-6">
          <h2 className="font-semibold mb-4">{t("Account Balances")}</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {account_balances.map((ab) => (
              <div key={ab.account} className="text-center p-3 border rounded-lg">
                <p className="text-xs text-muted-foreground">{ab.label}</p>
                <p className={`text-lg font-bold font-mono ${ab.balance > 0 ? "text-green-600" : "text-red-600"}`}>
                  {ab.balance?.toLocaleString()}
                </p>
              </div>
            ))}
          </div>
          <div className="flex justify-between mt-4 pt-4 border-t text-sm">
            <span className="text-muted-foreground">{t("Total Debit")}: {total_debit?.toLocaleString()} SAR</span>
            <span className="text-muted-foreground">{t("Total Credit")}: {total_credit?.toLocaleString()} SAR</span>
          </div>
        </div>
      )}

      {/* Journal Entries */}
      <div className="card p-6 mb-6">
        <h2 className="font-semibold mb-4">{t("Journal Entries")}</h2>
        <Table columns={entryColumns} rows={entries} rowKey="id" />
      </div>

      {/* Payments */}
      <div className="card p-6">
        <h2 className="font-semibold mb-4">{t("Payments")}</h2>
        <Table columns={paymentColumns} rows={payments} rowKey="id" />
      </div>
    </div>
  );
}
