import { useState } from "react";
import { cn } from "@/lib/utils";
import { router } from "@inertiajs/react";
import { DPage, DTop, DHead, DCard, DPill, DLines, DLine, DA, DC, dBtnClass } from "../../components/shadcn/detail-a.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtDate } from "../../utils/format.js";

// One bank or cash account's cash book, in the detail-page language of the
// Record View HMS canvas (no artboard of its own). The running balance is the
// cumulative sum of these records, not the journal-derived book balance.
export default function BankAccountTransactions({ account, rows = [], filters = {} }) {
  const { t } = useI18n();
  const [from, setFrom] = useState(filters.date_from || "");
  const [to, setTo] = useState(filters.date_to || "");
  const apply = (f, tt) => router.get(`/finance/bank-accounts/${account.kind}/${account.id}/`,
    { date_from: f || undefined, date_to: tt || undefined }, { preserveScroll: true, preserveState: true });

  const moneyIn = rows.filter((r) => r.direction === "in").reduce((s, r) => s + r.amount_sar, 0);
  const moneyOut = rows.filter((r) => r.direction !== "in").reduce((s, r) => s + r.amount_sar, 0);
  const unmatched = rows.filter((r) => !r.matched).length;
  const balance = rows.length ? rows[0].running_balance_sar : 0;
  const filtered = !!(filters.date_from || filters.date_to);

  return (
    <DPage>
      <DTop href="/finance/bank-accounts/" />

      <DHead
        title={account.name}
        badge={{ label: account.kind === "cash" ? t("Cash") : account.kind === "staff" ? t("Held by staff") : t("Bank"), tone: "gray" }}
        facts={[
          { k: t("Currency"), v: account.currency },
          { k: filtered ? t("Balance at end of range") : t("Balance"), v: `${fmt(balance)} SAR`, strong: true, tone: balance < 0 ? "danger" : undefined },
          { k: t("Money in"), v: `${fmt(moneyIn)} SAR`, tone: moneyIn ? "success" : undefined },
          { k: t("Money out"), v: `${fmt(moneyOut)} SAR` },
          { k: t("Transactions"), v: rows.length },
          { k: t("Not reconciled"), v: unmatched, tone: unmatched ? "warning" : undefined },
        ]}
        note={{ label: t("About this balance"), text: account.kind === "staff"
          ? t("Money this staff member holds: given by transfer, spent on approved expenses. Below zero means the office owes them.")
          : t("Transaction history for this account — running balance is a cumulative sum of these records, not the journal-derived book balance.") }}
      />

      <DCard
        title={t("Transactions")}
        count={rows.length || null}
        headClassName="flex-wrap items-center pb-3"
        actions={(
          <form className="flex flex-wrap items-center gap-1.5 font-normal text-muted-foreground" onSubmit={(e) => { e.preventDefault(); apply(from, to); }}>
            <input className="h-8 w-[150px] flex-none rounded-[10px] border border-input bg-card px-2.5 font-sans text-[13px] leading-[normal] font-medium text-foreground" type="date" aria-label={t("From")} value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} />
            <span>–</span>
            <input className="h-8 w-[150px] flex-none rounded-[10px] border border-input bg-card px-2.5 font-sans text-[13px] leading-[normal] font-medium text-foreground" type="date" aria-label={t("To")} value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} />
            <button type="submit" className={dBtnClass({ soft: true })}>{t("Apply")}</button>
            {filtered ? <button type="button" className={dBtnClass()} onClick={() => { setFrom(""); setTo(""); apply("", ""); }}>{t("Reset")}</button> : null}
          </form>
        )}
      >
        {rows.length ? (
          <DLines>
            {rows.map((r) => (
              <DLine key={r.id} title={`${r.source_type} #${r.source_id}`}
                sub={[fmtDate(r.transaction_date), r.reference, r.matched ? t("Reconciled") : t("Unmatched")].filter(Boolean).join(" · ")}
                value={`${r.direction === "in" ? "+" : "−"}${fmt(r.amount_sar)}`} valueTone={r.direction === "in" ? "text-success-text" : undefined}
                valueSub={t("Balance {v}", { v: fmt(r.running_balance_sar) })} />
            ))}
          </DLines>
        ) : null}
        {rows.length ? (
          <div className={DA.scrollWide}>
            <table data-slot="detail-table" className={DA.table}>
              <thead>
                <tr>
                  <th className={DC.date}>{t("Date")}</th><th>{t("Source")}</th><th>{t("Status")}</th>
                  <th className={cn(DC.n, DC.nWide)}>{t("Money in")}</th><th className={cn(DC.n, DC.nWide)}>{t("Money out")}</th><th className={cn(DC.n, DC.nWide)}>{t("Balance")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td className={DC.date}>{fmtDate(r.transaction_date)}</td>
                    <td>
                      <span className={DC.strong}>{r.source_type} #{r.source_id}</span>
                      {r.reference ? <span className={DC.sub}>{r.reference}</span> : null}
                    </td>
                    <td><DPill sm tone={r.matched ? "green" : "gray"}>{r.matched ? t("Reconciled") : t("Unmatched")}</DPill></td>
                    <td className={cn(DC.n, DC.good)}>{r.direction === "in" ? fmt(r.amount_sar) : ""}</td>
                    <td className={DC.n}>{r.direction !== "in" ? fmt(r.amount_sar) : ""}</td>
                    <td className={cn(DC.n, DC.bold, r.running_balance_sar < 0 && "text-danger-text")}>{fmt(r.running_balance_sar)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={3}>{t("Total")}</td>
                  <td className={cn(DC.n, DC.good)}>{fmt(moneyIn)}</td>
                  <td className={DC.n}>{fmt(moneyOut)}</td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>
        ) : <div className={DA.empty}>{t("No bank transactions recorded for this account yet.")}</div>}
      </DCard>

    </DPage>
  );
}
