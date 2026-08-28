import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import DetailCard from "../../components/shadcn/detail-card.jsx";
import DetailGrid from "../../components/shadcn/detail-grid.jsx";
import DetailAmount from "../../components/shadcn/detail-amount.jsx";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import Section from "../../components/shadcn/section.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { useI18n } from "../../utils/i18n.jsx";

export default function Detail({ payment = {}, logs = [], journal_entries = [] }) {
  const { t } = useI18n();
  const [confirm, confirmDialog] = useConfirm();

  const handleConfirm = () => {
    confirm({
      title: t("Confirm Payment"),
      message: t("Confirm payment {number} for {amount} SAR?", {
        number: payment.payment_number,
        amount: payment.amount_sar?.toLocaleString(),
      }),
      danger: false,
      onConfirm: () => router.post(`/finance/payments/${payment.id}/confirm/`),
    });
  };

  const handleReverse = () => {
    confirm({
      title: t("Reverse Payment"),
      message: t("Are you sure you want to reverse this payment? This will create a reversing journal entry."),
      danger: true,
      onConfirm: () => router.post(`/finance/payments/${payment.id}/reverse/`),
    });
  };

  const handleReject = () => {
    const reason = window.prompt(t("Reason for rejection:"));
    if (reason !== null) {
      router.post(`/finance/payments/${payment.id}/reject/`, { reason });
    }
  };

  const pill = {
    pending: { label: t("Pending"), tone: "yellow" },
    confirmed: { label: t("Confirmed"), tone: "blue" },
    allocated: { label: t("Allocated"), tone: "green" },
    rejected: { label: t("Rejected"), tone: "red" },
    reversed: { label: t("Reversed"), tone: "gray" },
  }[payment.status] || { label: payment.status_display, tone: "gray" };

  const metaActions = [];
  if (payment.status === "pending") {
    metaActions.push(
      <button key="confirm" className="hms-dv-act" onClick={handleConfirm}>{t("Confirm")}</button>,
      <button key="reject" className="hms-dv-act" onClick={handleReject} style={{ color: "var(--red)" }}>{t("Reject")}</button>,
    );
  }
  if (payment.status === "confirmed" || payment.status === "allocated") {
    metaActions.push(
      <button key="reverse" className="hms-dv-act" onClick={handleReverse} style={{ color: "var(--red)" }}>{t("Reverse")}</button>,
    );
  }

  const journalColumns = [
    { header: t("Entry #"), render: (e) => <span className="font-mono text-xs">{e.entry_number}</span> },
    { header: t("Type"), render: (e) => e.entry_type_display },
    { header: t("Description"), render: (e) => e.description },
    { header: t("Date"), render: (e) => e.entry_date },
    { header: t("Debit"), align: "right", render: (e) => e.total_debit?.toLocaleString() },
    { header: t("Credit"), align: "right", render: (e) => e.total_credit?.toLocaleString() },
  ];

  const logColumns = [
    { header: t("Action"), render: (l) => <span className="font-medium">{l.action_display}</span> },
    { header: t("By"), render: (l) => l.performed_by || "—" },
    { header: t("Note"), render: (l) => l.note || "—" },
    { header: t("Time"), render: (l) => l.performed_at || "—" },
  ];

  return (
    <div className="page dv-page hms-dv-page shadcn-root">
      <PageBack href="/finance/payments/" label={t("Back")} />

      <DetailCard
        crumbs={[{ label: t("Payments"), href: "/finance/payments/" }]}
        kicker={payment.payment_number}
        title={payment.client_name || "—"}
        sub={payment.invoice_number ? t("Invoice: {number}", { number: payment.invoice_number }) : null}
        pill={pill}
        actions={metaActions}
      >
        <DetailGrid
          rows={[
            { label: t("Amount"), icon: "wallet", value: `${payment.amount_sar?.toLocaleString()} SAR`, color: "var(--green)" },
            { label: t("Original"), icon: "wallet", value: `${payment.amount?.toLocaleString()} ${payment.currency}` },
            { label: t("Exchange Rate"), value: payment.exchange_rate },
            { label: t("Method"), icon: "invoice", value: payment.method || "—" },
            { label: t("Received In"), icon: "wallet", value: payment.received_in_display || "—" },
            { label: t("Date"), value: payment.payment_date || "—" },
            { label: t("Reference"), value: payment.reference || "—" },
            payment.bank_name ? { label: t("Bank"), value: payment.bank_name } : null,
            payment.account_number ? { label: t("Account #"), value: payment.account_number } : null,
          ].filter(Boolean)}
          right={
            <DetailAmount
              label={t("Payment Amount")}
              value={payment.amount_sar}
              currency="SAR"
              tone={payment.status === "rejected" ? "red" : payment.status === "allocated" ? "green" : "yellow"}
            />
          }
        />

        {payment.note && (
          <Section label={t("Note")} icon="invoice">
            <p className="text-sm" style={{ padding: "0 20px 16px", whiteSpace: "pre-wrap" }}>{payment.note}</p>
          </Section>
        )}

        {payment.allocations?.length > 0 && (
          <Section label={t("Allocation Details")} icon="invoice">
            <DetailTable
              columns={[
                { header: t("Reservation"), render: (a) => a.reservation_number || a.reservation_id || "—" },
                { header: t("Amount (SAR)"), align: "right", render: (a) => a.amount_sar?.toLocaleString() },
              ]}
              rows={payment.allocations}
              rowKey={(a) => a.id}
            />
          </Section>
        )}

        {payment.proof_url && (
          <Section label={t("Payment Proof")} icon="invoice">
            <div style={{ padding: "0 20px 16px" }}>
              {payment.proof_url?.endsWith(".pdf") ? (
                <a href={payment.proof_url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline text-sm">
                  {t("View PDF")}
                </a>
              ) : (
                <a href={payment.proof_url} target="_blank" rel="noreferrer">
                  <img src={payment.proof_url} alt="Payment proof" className="max-h-64 rounded" style={{ border: "1px solid var(--border)" }} />
                </a>
              )}
            </div>
          </Section>
        )}

        {payment.rejected_reason && (
          <Section label={t("Rejection Reason")} icon="invoice">
            <p className="text-sm" style={{ padding: "0 20px 16px", color: "var(--red)" }}>{payment.rejected_reason}</p>
          </Section>
        )}

        {/* Audit Trail */}
        <Section label={t("Audit Trail")} icon="invoice">
          <DetailTable
            columns={[
              { header: t("Field"), render: (r) => r.label },
              { header: t("Value"), render: (r) => r.value },
            ]}
            rows={[
              { label: t("Created by"), value: payment.created_by || "—" },
              { label: t("Created at"), value: payment.created_at || "—" },
              { label: t("Confirmed by"), value: payment.confirmed_by || "—" },
              { label: t("Confirmed at"), value: payment.confirmed_at || "—" },
              { label: t("Period"), value: payment.period?.name || "—" },
            ]}
            rowKey={(r) => r.label}
          />
        </Section>

        {/* Journal Entries */}
        {journal_entries.length > 0 && (
          <Section label={t("Journal Entries")} icon="invoice" count={journal_entries.length}>
            <DetailTable columns={journalColumns} rows={journal_entries} rowKey={(e) => e.id} />
          </Section>
        )}

        {/* Activity Log */}
        {logs.length > 0 && (
          <Section label={t("Activity Log")} icon="invoice" count={logs.length}>
            <DetailTable columns={logColumns} rows={logs} rowKey={(l) => l.performed_at} />
          </Section>
        )}
      </DetailCard>

      {confirmDialog}
    </div>
  );
}
