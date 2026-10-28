import { router } from "@inertiajs/react";
import { cn } from "@/lib/utils";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { DPage, DTop, DHead, DBanner, DBtn, DCard, DPill, DLines, DLine, DLinesTotal, DA, DC } from "../../components/shadcn/detail-a.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtDate } from "../../utils/format.js";
import { usePerms } from "../../utils/perms.js";

// Financial period detail, in the detail-page language of the Record View HMS
// canvas (no artboard of its own): a strip with the step that is due (close,
// lock), the head card with the totals as facts, then the month-end
// checklist, account balances, journal entries and payments.

const PAY_TONE = { pending: "amber", confirmed: "info", allocated: "green", rejected: "red", reversed: "gray" };
const CHECK = { ok: { tone: "green", label: "OK" }, warn: { tone: "amber", label: "Review" }, fail: { tone: "red", label: "Blocking" } };

const dec = (n) => (Math.abs(n) || 0).toLocaleString("en-US", { maximumFractionDigits: 2 });

export default function Detail({ period = {}, entries = [], payments = [], account_balances = [], total_debit = 0, total_credit = 0, checklist = null }) {
  const { t } = useI18n();
  const canManage = usePerms().can("periods", "edit");
  const [confirm, confirmDialog] = useConfirm();

  const openItems = checklist ? checklist.fails + checklist.warns : 0;
  const closePeriod = () => confirm({
    title: t("Close Period"),
    message: openItems
      ? t("{n} checklist item(s) are still open. Close this period anyway? No more journal entries will be allowed.", { n: openItems })
      : t("Close this period? No more journal entries will be allowed."),
    onConfirm: () => router.post(`/finance/periods/${period.id}/close/`),
  });
  const lockPeriod = () => confirm({
    title: t("Lock Period"),
    message: t("Lock this period? This is IRREVERSIBLE."),
    danger: true,
    onConfirm: () => router.post(`/finance/periods/${period.id}/lock/`),
  });

  const pill = {
    open: { label: t("Open"), tone: "green" },
    soft_close: { label: t("Soft Close"), tone: "amber" },
    closed: { label: t("Closed"), tone: "amber" },
    locked: { label: t("Locked"), tone: "gray" },
  }[period.status] || { label: period.status_display, tone: "gray" };

  const diff = (total_debit || 0) - (total_credit || 0);
  const balanced = diff === 0;
  const pendingCount = payments.filter((p) => p.status === "pending").length;
  const canClose = canManage && period.is_postable;
  const canLock = canManage && period.status === "closed";
  const lockBlocked = checklist && !checklist.can_lock;

  const sentence = !balanced
    ? <><b>{t("Unbalanced.")}</b> {t("Difference of {n} SAR", { n: `${diff < 0 ? "-" : ""}${dec(diff)}` })}{pendingCount ? `, ${t("{n} payments still awaiting review", { n: pendingCount })}` : ""}.</>
    : pendingCount ? <><b>{pendingCount}</b> {t("payments still awaiting review.")}</>
      : canLock ? (lockBlocked ? t("Resolve the blocking checklist items first.") : t("Closed. Lock it once the books are final; locking cannot be undone."))
        : canClose ? (openItems ? t("{n} checklist item(s) are still open.", { n: openItems }) : t("Debits and credits match in this period."))
          : null;

  return (
    <DPage>
      <DTop href="/finance/periods/" />

      {sentence ? (
        <DBanner
          tone={!balanced ? "danger" : pendingCount || openItems || lockBlocked ? "warning" : "success"}
          actions={canClose || canLock ? (
            <>
              {canClose ? <DBtn primary onClick={closePeriod}>{t("Close Period")}</DBtn> : null}
              {canLock ? <DBtn primary disabled={lockBlocked} onClick={lockPeriod}>{t("Lock Period")}</DBtn> : null}
            </>
          ) : null}
        >
          {sentence}
        </DBanner>
      ) : null}

      <DHead
        title={period.name}
        badge={pill}
        facts={[
          { k: t("From"), v: fmtDate(period.date_from) || t("Not set") },
          { k: t("To"), v: fmtDate(period.date_to) || t("Not set") },
          { k: t("Total debit"), v: `${dec(total_debit)} SAR` },
          { k: t("Total credit"), v: `${dec(total_credit)} SAR` },
          { k: t("Difference"), v: `${dec(diff)} SAR`, tone: balanced ? "success" : "danger" },
          { k: t("Journal Entries"), v: entries.length },
          { k: t("Payments"), v: payments.length },
          period.closed_by && { k: t("Closed by"), v: period.closed_at ? `${period.closed_by}, ${period.closed_at}` : period.closed_by },
          period.locked_by && { k: t("Locked by"), v: period.locked_at ? `${period.locked_by}, ${period.locked_at}` : period.locked_by },
        ]}
      />

      {checklist ? (
        <DCard
          title={t("Month-end checklist")}
          meta={checklist.fails ? t("{n} blocking", { n: checklist.fails }) : checklist.warns ? t("{n} to review", { n: checklist.warns }) : t("All clear")}
        >
          <div className={DA.scroll}>
            <table data-slot="detail-table" className={DA.table}>
              <tbody>
                {checklist.items.map((i) => (
                  <tr key={i.key}>
                    <td style={{ width: 96 }}><DPill sm tone={CHECK[i.status]?.tone}>{t(CHECK[i.status]?.label || i.status)}</DPill></td>
                    <td>
                      <span className={DC.strong}>{t(i.label)}</span>
                      <span className={DC.sub}>{t(i.detail, i.params)}</span>
                      {i.status !== "ok" && i.rows.length ? i.rows.map((r) => <span key={r} className={DC.sub}>{r}</span>) : null}
                    </td>
                    <td className={DC.n}>{i.link && i.status !== "ok" ? <a href={i.link}>{t("Open")}</a> : null}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </DCard>
      ) : null}

      {account_balances.length ? (
        <DCard title={t("Account Balances")} count={account_balances.length} meta="SAR">
          <div className={DA.scroll}>
            <table data-slot="detail-table" className={DA.table}>
              <tbody>
                {account_balances.map((ab) => (
                  <tr key={ab.account}>
                    <td>{ab.label}</td>
                    <td className={cn(DC.n, DC.bold)} style={{ color: ab.balance > 0 ? "var(--success-text)" : ab.balance < 0 ? "var(--danger-text)" : undefined }}>{fmt(ab.balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </DCard>
      ) : null}

      <DCard title={t("Journal Entries")} count={entries.length}>
        {entries.length ? (
          <>
          <DLines>
            {entries.map((e) => (
              <DLine key={e.id} mono title={e.entry_number} sub={[e.entry_type_display, e.entry_date, e.description].filter(Boolean).join(" · ")}
                value={fmt(e.total_debit)} valueSub={e.is_balanced ? null : t("Not balanced")} valueTone={e.is_balanced ? undefined : "text-danger-text"} />
            ))}
            <DLinesTotal label={t("Total")}>{fmt(total_debit)} / {fmt(total_credit)}</DLinesTotal>
          </DLines>
          <div className={DA.scrollWide}>
            <table data-slot="detail-table" className={DA.table}>
              <thead><tr><th>{t("Entry #")}</th><th>{t("Type")}</th><th>{t("Description")}</th><th>{t("Date")}</th><th className={DC.n}>{t("Debit")}</th><th className={DC.n}>{t("Credit")}</th><th className={DC.n}>{t("Balanced")}</th></tr></thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id}>
                    <td className={DC.mono}>{e.entry_number}</td>
                    <td className={DC.strong}>{e.entry_type_display}</td>
                    <td className={DC.mut}>{e.description}</td>
                    <td className={DC.nw}>{e.entry_date}</td>
                    <td className={DC.n}>{fmt(e.total_debit)}</td>
                    <td className={DC.n}>{fmt(e.total_credit)}</td>
                    <td className={DC.n}>{e.is_balanced ? <span className={DC.good}>{t("Yes")}</span> : <span className={DC.late}>{t("No")}</span>}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot><tr><td colSpan={4}>{t("Total")}</td><td className={DC.n}>{fmt(total_debit)}</td><td className={DC.n}>{fmt(total_credit)}</td><td /></tr></tfoot>
            </table>
          </div>
          </>
        ) : <div className={DA.empty}>{t("No journal entries in this period.")}</div>}
      </DCard>

      <DCard title={t("Payments")} count={payments.length}>
        {payments.length ? (
          <>
          <DLines>
            {payments.map((p) => (
              <DLine key={p.id} href={`/finance/payments/${p.id}/`} mono title={p.payment_number}
                sub={[p.client_name, p.payment_date].filter(Boolean).join(" · ")}
                value={fmt(p.amount_sar)} valueSub={p.status_display} />
            ))}
          </DLines>
          <div className={DA.scrollWide}>
            <table data-slot="detail-table" className={DA.table}>
              <thead><tr><th>{t("Payment")}</th><th>{t("Client")}</th><th>{t("Date")}</th><th>{t("Status")}</th><th className={DC.n}>{t("Amount (SAR)")}</th></tr></thead>
              <tbody>
                {payments.map((p) => (
                  <tr key={p.id}>
                    <td><a href={`/finance/payments/${p.id}/`}>{p.payment_number}</a></td>
                    <td>{p.client_name}</td>
                    <td className={DC.nw}>{p.payment_date}</td>
                    <td><DPill sm tone={PAY_TONE[p.status] || "gray"}>{p.status_display}</DPill></td>
                    <td className={DC.n}>{fmt(p.amount_sar)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </>
        ) : <div className={DA.empty}>{t("No payments in this period.")}</div>}
      </DCard>

      {confirmDialog}
    </DPage>
  );
}
