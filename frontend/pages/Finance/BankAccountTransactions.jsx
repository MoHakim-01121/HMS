import { useState } from "react";
import { router } from "@inertiajs/react";
import { DPage, DTop, DHead, DCard, DPill } from "../../components/shadcn/detail-a.jsx";
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
        actions={(
          <form className="bt-range" onSubmit={(e) => { e.preventDefault(); apply(from, to); }}>
            <input type="date" aria-label={t("From")} value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} />
            <span>–</span>
            <input type="date" aria-label={t("To")} value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} />
            <button type="submit" className="da-btn soft">{t("Apply")}</button>
            {filtered ? <button type="button" className="da-btn" onClick={() => { setFrom(""); setTo(""); apply("", ""); }}>{t("Reset")}</button> : null}
          </form>
        )}
      >
        {rows.length ? (
          <div className="da-scroll">
            <table className="da-t">
              <thead>
                <tr>
                  <th className="d">{t("Date")}</th><th>{t("Source")}</th><th>{t("Status")}</th>
                  <th className="n w">{t("Money in")}</th><th className="n w">{t("Money out")}</th><th className="n w">{t("Balance")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td className="d">{fmtDate(r.transaction_date)}</td>
                    <td>
                      <span className="strong">{r.source_type} #{r.source_id}</span>
                      {r.reference ? <span className="sub">{r.reference}</span> : null}
                    </td>
                    <td><DPill sm tone={r.matched ? "green" : "gray"}>{r.matched ? t("Reconciled") : t("Unmatched")}</DPill></td>
                    <td className="n good">{r.direction === "in" ? fmt(r.amount_sar) : ""}</td>
                    <td className="n">{r.direction !== "in" ? fmt(r.amount_sar) : ""}</td>
                    <td className="n bold" style={r.running_balance_sar < 0 ? { color: "var(--danger-text)" } : undefined}>{fmt(r.running_balance_sar)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={3}>{t("Total")}</td>
                  <td className="n good">{fmt(moneyIn)}</td>
                  <td className="n">{fmt(moneyOut)}</td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>
        ) : <div className="da-empty">{t("No bank transactions recorded for this account yet.")}</div>}
      </DCard>

      <style>{`
.bt-range { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-weight: 400; color: var(--muted-foreground); }
.bt-range input { width: 150px !important; flex: none; height: 32px; padding: 0 10px; border: 1px solid var(--input); border-radius: 10px; background: var(--card); font: 500 13px var(--font-sans); color: var(--foreground); }
.da-card-h:has(.bt-range) { align-items: center; flex-wrap: wrap; padding-bottom: 12px; }
`}</style>
    </DPage>
  );
}
