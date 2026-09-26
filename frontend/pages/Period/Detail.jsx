import { router } from "@inertiajs/react";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import { DvLink } from "../../components/shadcn/item-row.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { RvBack, RvHero, RvFigure, RvPairs, RvCard, RvSection, RvRail } from "../../components/shadcn/record-view.jsx";
import { Icon } from "../../components/icons.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmtDate } from "../../utils/format.js";
import { usePerms } from "../../utils/perms.js";

const STATUS_TONE = {
  pending: "yellow",
  confirmed: "blue",
  allocated: "green",
  rejected: "red",
  reversed: "gray",
};

const ENTRY_TYPE_TONE = {
  charge: "blue",
  payment: "green",
  allocate: "yellow",
  transfer: "purple",
  refund: "orange",
  penalty: "red",
  reversal: "gray",
};


export default function Detail({ period = {}, entries = [], payments = [], account_balances = [], total_debit = 0, total_credit = 0 }) {
  const { t } = useI18n();
  const canManage = usePerms().can("periods", "edit");
  const [confirm, confirmDialog] = useConfirm();

  const closePeriod = () => {
    confirm({
      title: t("Close Period"),
      message: t("Close this period? No more journal entries will be allowed."),
      onConfirm: () => router.post(`/finance/periods/${period.id}/close/`),
    });
  };

  const lockPeriod = () => {
    confirm({
      title: t("Lock Period"),
      message: t("Lock this period? This is IRREVERSIBLE."),
      danger: true,
      onConfirm: () => router.post(`/finance/periods/${period.id}/lock/`),
    });
  };

  const pill = {
    open: { label: t("Open"), tone: "green" },
    soft_close: { label: t("Soft Close"), tone: "yellow" },
    closed: { label: t("Closed"), tone: "orange" },
    locked: { label: t("Locked"), tone: "gray" },
  }[period.status] || { label: period.status_display, tone: "gray" };

  const diff = (total_debit || 0) - (total_credit || 0);
  const balanced = diff === 0;
  const pendingCount = payments.filter((p) => p.status === "pending").length;

  const entryColumns = [
    { header: t("Entry #"), render: (e) => <span className="font-mono text-xs">{e.entry_number}</span> },
    { header: t("Type"), render: (e) => <StatusPill small tone={ENTRY_TYPE_TONE[e.entry_type] || "gray"} label={e.entry_type_display} /> },
    { header: t("Description"), render: (e) => e.description },
    { header: t("Date"), render: (e) => e.entry_date },
    { header: t("Debit"), align: "right", render: (e) => <span className="font-mono">{e.total_debit?.toLocaleString("en-US")}</span> },
    { header: t("Credit"), align: "right", render: (e) => <span className="font-mono">{e.total_credit?.toLocaleString("en-US")}</span> },
    { header: t("Balanced"), align: "center", render: (e) => (e.is_balanced ? <span style={{ color: "var(--green)" }}>✓</span> : <span style={{ color: "var(--red)" }}>✗</span>) },
  ];

  const paymentColumns = [
    { header: t("Payment #"), render: (p) => <DvLink href={`/finance/payments/${p.id}/`}>{p.payment_number}</DvLink> },
    { header: t("Client"), render: (p) => p.client_name },
    { header: t("Amount"), align: "right", render: (p) => <span className="font-mono">{p.amount_sar?.toLocaleString("en-US")} SAR</span> },
    { header: t("Status"), render: (p) => <StatusPill small tone={STATUS_TONE[p.status] || "gray"} label={p.status_display} /> },
    { header: t("Date"), render: (p) => p.payment_date },
  ];

  return (
    <div className="page shadcn-root hms-rv-page">
      <RvBack href="/finance/periods/" label={t("Back")} />

      <RvHero
        kicker={period.name}
        badge={pill}
        title={t("Financial Period")}
        facts={[
          { k: t("From"), v: fmtDate(period.date_from) || t("Not set") },
          { k: t("To"), v: fmtDate(period.date_to) || t("Not set") },
        ]}
        side={
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <RvFigure
              label={t("Difference")}
              value={fmtDiff(diff)}
              unit="SAR"
              color={balanced ? "var(--green)" : "var(--red)"}
            />
            <RvPairs
              pairs={[
                { k: t("Total debit"), v: (total_debit || 0).toLocaleString("en-US") },
                { k: t("Total credit"), v: (total_credit || 0).toLocaleString("en-US") },
              ]}
            />
          </div>
        }
        note={
          balanced
            ? {
                icon: <Icon name="check" size={12} strokeWidth={2.4} />,
                iconBg: "var(--green)",
                title: t("Balanced"),
                text: pendingCount ? t("{n} payments still awaiting review", { n: pendingCount }) : t("Debits and credits match in this period."),
              }
            : {
                icon: <Icon name="alert-circle" size={13} strokeWidth={2} />,
                iconBg: "var(--red)",
                title: t("Unbalanced"),
                text: `${t("Difference of {n} SAR", { n: fmtSigned(diff) })}${pendingCount ? ` — ${t("{n} payments still awaiting review", { n: pendingCount })}` : ""}`,
              }
        }
        actions={
          <>
            {canManage && period.is_postable && (
              <button key="close" className="hms-rv-btn primary" onClick={closePeriod}>{t("Close Period")}</button>
            )}
            {canManage && period.status === "closed" && (
              <button key="lock" className="hms-rv-btn danger" onClick={lockPeriod}>{t("Lock Period")}</button>
            )}
          </>
        }
      />

      <div className="hms-rv-grid">
        <div className="hms-rv-col">
          <RvCard>
            {account_balances.length > 0 && (
              <RvSection title={t("Account Balances")} meta={`${account_balances.length}`} first>
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                  {account_balances.map((ab) => (
                    <div key={ab.account} style={{ padding: "12px 16px", flex: "1 1 160px", minWidth: 160, border: "1px solid var(--border)", borderRadius: 12, background: "var(--secondary)" }}>
                      <div style={{ fontSize: 12, color: "var(--muted-foreground)" }}>{ab.label}</div>
                      <div className="font-mono font-bold" style={{ fontSize: 20, marginTop: 4, color: ab.balance > 0 ? "var(--green)" : "var(--red)" }}>
                        {ab.balance?.toLocaleString("en-US")} <span style={{ fontSize: 12, fontWeight: 400 }}>SAR</span>
                      </div>
                    </div>
                  ))}
                </div>
              </RvSection>
            )}

            <RvSection title={t("Journal Entries")} meta={`${entries.length}`}>
              <DetailTable columns={entryColumns} rows={entries} rowKey={(e) => e.id} empty={t("No journal entries in this period.")} />
            </RvSection>

            <RvSection title={t("Payments")} meta={`${payments.length}`}>
              <DetailTable columns={paymentColumns} rows={payments} rowKey={(p) => p.id} empty={t("No payments in this period.")} />
            </RvSection>
          </RvCard>
        </div>

        <RvRail
          rows={[
            { k: t("Journal Entries"), v: entries.length },
            { k: t("Payments"), v: payments.length },
            period.closed_by ? { k: t("Closed by"), v: period.closed_by } : null,
            period.closed_at ? { k: t("Closed at"), v: period.closed_at } : null,
            period.locked_by ? { k: t("Locked by"), v: period.locked_by } : null,
            period.locked_at ? { k: t("Locked at"), v: period.locked_at } : null,
          ].filter(Boolean)}
        />
      </div>

      {confirmDialog}
    </div>
  );
}

function fmtDiff(n) {
  return (Math.abs(n) || 0).toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function fmtSigned(n) {
  const v = (Math.abs(n) || 0).toLocaleString("en-US", { maximumFractionDigits: 2 });
  return n < 0 ? `-${v}` : v;
}