import { Link, usePage } from "@inertiajs/react";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtDateShort } from "../../utils/format.js";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import { Icon } from "../../components/icons.jsx";

// Finance Hub — control-room screen. One page answers the daily finance
// questions: where is the cash, who owes us, what needs review, what still
// needs remitting. Blocks are gated server-side per module; the frontend
// simply skips what the props omit. Figures stay monochrome ink
// (--foreground), colour is reserved for status pills and warnings.
const CSS = `
.fh { padding:4px 24px 40px; max-width:1280px; }
.fh-head { display:flex; align-items:flex-end; justify-content:space-between; gap:20px; margin-bottom:16px; flex-wrap:wrap; }
.fh-title { font-size:26px; font-weight:600; letter-spacing:-.024em; line-height:1.1; color:var(--foreground); margin:0; }
.fh-date { font-size:12.5px; color:var(--muted-foreground); margin-top:4px; font-variant-numeric:tabular-nums; }
.fh-actions { display:flex; gap:9px; flex-shrink:0; }
.fh-btn { height:38px; display:inline-flex; align-items:center; justify-content:center; gap:8px; padding:0 17px; border-radius:9999px; font-family:inherit; font-size:12.5px; font-weight:600; cursor:pointer; white-space:nowrap; text-decoration:none; transition:background .12s, border-color .12s; }
.fh-btn-outline { border:1px solid var(--input); background:var(--card); color:var(--foreground); }
.fh-btn-outline:hover { border-color:var(--foreground); }
.fh-btn-primary { border:1px solid var(--primary); background:var(--primary); color:var(--primary-foreground); padding:0 18px; }
.fh-btn-primary:hover { background:var(--primary-hover); border-color:var(--primary-hover); }

/* Cash strip — 4 tiles in the same .hms-kpi-row rhythm as home. */
.fh-cash { padding:16px 18px; background:var(--card); }
.fh-cash-label { font-size:12px; font-weight:500; color:var(--muted-foreground); }
.fh-cash-val { margin-top:7px; font-size:19px; font-weight:600; letter-spacing:-.02em; color:var(--foreground); font-variant-numeric:tabular-nums; }
.fh-cash-cur { margin-left:5px; font-size:10.5px; font-weight:600; color:var(--muted-foreground); letter-spacing:0; }
@media (max-width:600px) {
  .fh-cash { padding:13px 15px; }
  .fh-cash-val { font-size:17px; }
}

/* Panel grids — same 12-col rhythm as the home dashboard. */
.fh-grid-a { display:grid; grid-template-columns:1fr; gap:20px; margin-top:20px; }
@media (min-width:900px) { .fh-grid-a { grid-template-columns:minmax(0,7fr) minmax(0,5fr); align-items:stretch; } }
.fh-grid-b { display:grid; grid-template-columns:1fr; gap:20px; margin-top:20px; }
@media (min-width:900px) { .fh-grid-b { grid-template-columns:repeat(3,minmax(0,1fr)); align-items:stretch; } }
.fh-card { display:flex; flex-direction:column; min-width:0; }
.fh-card .hms-dv-body { padding:24px 24px 16px; flex:1; }
@media (max-width:600px) {
  .fh-card .hms-dv-body { padding:20px 16px 12px; }
  .fh-actions { display:none; }
  .fh-title { font-size:20px; }
  .fh-head { margin-bottom:12px; }
}

/* Debtor / action rows — dense clickable list with right-aligned figure. */
.fh-list { display:flex; flex-direction:column; margin-top:4px; }
.fh-row { display:flex; align-items:center; gap:12px; padding:11px 0; border-bottom:1px solid var(--border); }
.fh-row:last-child { border-bottom:none; }
.fh-row-main { min-width:0; flex:1; }
.fh-row-name { font-size:13px; font-weight:500; color:var(--foreground); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.fh-row-name a { color:inherit; text-decoration:none; border-bottom:1px solid var(--border); }
.fh-row-name a:hover { border-bottom-color:var(--foreground); }
.fh-row-sub { font-size:11.5px; color:var(--muted-foreground); margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.fh-row-amt { flex:none; font-size:13.5px; font-weight:600; color:var(--foreground); font-variant-numeric:tabular-nums; white-space:nowrap; }
.fh-empty { font-size:13px; color:var(--muted-foreground); padding:14px 0 6px; }
`;

const PAY_TONE = {
  pending: "yellow", received: "blue", confirmed: "blue", allocated: "green",
  partially_applied: "yellow", applied: "green", rejected: "red",
  reversed: "gray", voided: "gray",
};
const EXP_TONE = {
  draft: "gray", posted: "blue", partially_paid: "yellow", paid: "green", voided: "gray",
};

function remPill(rem) {
  if (rem.status === "received") return { label: "Received", tone: "green" };
  if (rem.settled_sar > 0) return { label: "Partially", tone: "blue" };
  return { label: "Pending", tone: "yellow" };
}
function payPill(status) {
  return { label: status, tone: PAY_TONE[status] || "gray" };
}
function expPill(status) {
  return { label: status, tone: EXP_TONE[status] || "gray" };
}

export default function FinanceDashboard(props) {
  const { t } = useI18n();
  const { props: pageProps } = usePage();
  const canPay = props.can?.payments;
  const today = new Date().toLocaleDateString("en-GB", { weekday: "long", month: "long", day: "numeric", year: "numeric" });

  const cash = props.cash;
  const payments = props.payments;
  const receivables = props.receivables;
  const remittance = props.remittance;
  const expenses = props.expenses;
  const journal = props.journal;

  const perms = pageProps.auth?.user?.perms || {};
  const cashTotal = (cash?.sby ?? 0) + (cash?.jkt ?? 0) + (cash?.pusat ?? 0) + (cash?.transit ?? 0);

  return (
    <div className="page shadcn-root fh">
      <style>{CSS}</style>

      <div className="fh-head">
        <div>
          <h1 className="fh-title">{t("Finance")}</h1>
          <div className="fh-date">{today}</div>
        </div>
        <div className="fh-actions">
          {perms.payments?.includes("create") && (
            <Link className="fh-btn fh-btn-outline" href="/finance/payments/record/">
              <Icon name="plus" size={15} strokeWidth={1.9} />{t("Record Payment")}
            </Link>
          )}
          {perms.expenses?.includes("create") && (
            <Link className="fh-btn fh-btn-outline" href="/finance/expenses/record/">
              <Icon name="plus" size={15} strokeWidth={1.9} />{t("Record Expense")}
            </Link>
          )}
          {perms.remittance?.includes("create") && (
            <Link className="fh-btn fh-btn-primary" href="/remittance/new/">
              <Icon name="plus" size={15} strokeWidth={1.9} />{t("New Remittance")}
            </Link>
          )}
        </div>
      </div>

      <div className="hms-kpi-row">
        {canPay && (
          <KpiCard
            label={t("Cash & Bank")}
            value={fmt(cashTotal)}
            unit="SAR"
            foot={t("Surabaya · Jakarta · HQ · Transit")}
          />
        )}
        {receivables && (
          <KpiCard
            label={t("Total Receivable")}
            value={fmt(receivables.total)}
            unit="SAR"
            warn={receivables.total > 0}
            foot={receivables.count > 0 ? t("{n} clients owe", { n: receivables.count }) : t("nothing outstanding")}
          />
        )}
        {payments && (
          <KpiCard
            label={t("Payments Awaiting Review")}
            value={fmt(payments.pending_review)}
            warn={payments.pending_review > 0}
            foot={t("{amount} SAR pending", { amount: fmt(payments.pending_review_total) })}
          />
        )}
        {remittance && (
          <KpiCard
            label={t("Remit to HQ")}
            value={fmt(remittance.kewajiban_kirim)}
            unit="SAR"
            warn={remittance.pending_count > 0}
            foot={t("{n} remittance pending", { n: remittance.pending_count })}
          />
        )}
      </div>

      {cash && (
        <div className="hms-kpi-row fh-cash-row">
          {[
            { label: t("Cash Surabaya"), value: cash.sby },
            { label: t("Cash Jakarta"), value: cash.jkt },
            { label: t("Cash HQ"), value: cash.pusat },
            { label: t("In Transit"), value: cash.transit },
          ].map((c) => (
            <div className="fh-cash" key={c.label}>
              <div>
                <div className="fh-cash-label">{c.label}</div>
                <div className="fh-cash-val">{fmt(c.value)}<span className="fh-cash-cur">SAR</span></div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="fh-grid-a">
        {payments && (
          <div className="hms-dv-card fh-card">
            <div className="hms-dv-body">
              <div className="hms-dv-sech">
                <span className="hms-dv-sec-title">{t("Payments Awaiting Review")} <span className="hms-dv-count">{payments.recent.length}</span></span>
                <span className="hms-dv-sec-actions"><Link className="hms-dv-act" href="/finance/payments/">{t("View all")}</Link></span>
              </div>
              {payments.recent.length === 0 ? (
                <div className="fh-empty">{t("No payments awaiting review.")}</div>
              ) : (
                <div className="hms-dv-table-wrap">
                  <table className="hms-dv-table">
                    <thead>
                      <tr>
                        <th>{t("Payment")}</th>
                        <th>{t("Client")}</th>
                        <th className="num">{t("Amount")}</th>
                        <th>{t("Status")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {payments.recent.map((p) => {
                        const pill = payPill(p.status);
                        return (
                          <tr key={p.id}>
                            <td><Link className="strong" href={`/finance/payments/${p.id}/`}>{p.number}</Link></td>
                            <td className="strong" data-label={t("Client")}>{p.client}<span className="sub">{fmtDateShort(p.date)}</span></td>
                            <td className="num" data-label={t("Amount")}>{fmt(p.amount_sar)} <span className="sub">SAR</span></td>
                            <td data-label={t("Status")}><StatusPill small label={pill.label} tone={pill.tone} /></td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {receivables && (
          <div className="hms-dv-card fh-card">
            <div className="hms-dv-body">
              <div className="hms-dv-sech">
                <span className="hms-dv-sec-title">{t("Client Receivables")} <span className="hms-dv-count">{receivables.count}</span></span>
                <span className="hms-dv-sec-actions"><Link className="hms-dv-act" href="/finance/statements/">{t("Statements")}</Link></span>
              </div>
              {receivables.top.length === 0 ? (
                <div className="fh-empty">{t("No outstanding receivables.")}</div>
              ) : (
                <div className="fh-list">
                  {receivables.top.map((r) => (
                    <div className="fh-row" key={r.client_id}>
                      <div className="fh-row-main">
                        <div className="fh-row-name">
                          <Link href={`/finance/clients/${r.client_id}/statement/`}>{r.name}</Link>
                        </div>
                        <div className="fh-row-sub">{t("billed")} {fmt(r.tagihan)} SAR</div>
                      </div>
                      <div className="fh-row-amt">{fmt(r.piutang)} SAR</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="fh-grid-b">
        {remittance && (
          <div className="hms-dv-card fh-card">
            <div className="hms-dv-body">
              <div className="hms-dv-sech">
                <span className="hms-dv-sec-title">{t("Remittances")} <span className="hms-dv-count">{remittance.pending_count} {t("pending")}</span></span>
                <span className="hms-dv-sec-actions"><Link className="hms-dv-act" href="/remittance/?tab=tracking">{t("Tracking")}</Link></span>
              </div>
              {remittance.recent.length === 0 ? (
                <div className="fh-empty">{t("No remittances yet.")}</div>
              ) : (
                <div className="fh-list">
                  {remittance.recent.map((r) => {
                    const pill = remPill(r);
                    return (
                      <div className="fh-row" key={r.id}>
                        <div className="fh-row-main">
                          <div className="fh-row-name"><Link href={`/remittance/${r.id}/`}>{r.number}</Link></div>
                          <div className="fh-row-sub">{fmtDateShort(r.date)} · <StatusPill small label={pill.label} tone={pill.tone} /></div>
                        </div>
                        <div className="fh-row-amt">{fmt(r.amount_sar)} <span style={{ color: "var(--muted-foreground)", fontSize: 11, fontWeight: 500 }}>SAR</span></div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        {expenses && (
          <div className="hms-dv-card fh-card">
            <div className="hms-dv-body">
              <div className="hms-dv-sech">
                <span className="hms-dv-sec-title">{t("Expenses")} <span className="hms-dv-count">{t("this month")}</span></span>
                <span className="hms-dv-sec-actions"><Link className="hms-dv-act" href="/finance/expenses/">{t("View all")}</Link></span>
              </div>
              <div className="fh-list" style={{ marginBottom: 10 }}>
                <div className="fh-row">
                  <div className="fh-row-main">
                    <div className="fh-row-name">{t("This month")}</div>
                    <div className="fh-row-sub">{t("{amount} SAR outstanding", { amount: fmt(expenses.month_outstanding) })}</div>
                  </div>
                  <div className="fh-row-amt">{fmt(expenses.month_total)} <span style={{ color: "var(--muted-foreground)", fontSize: 11, fontWeight: 500 }}>SAR</span></div>
                </div>
              </div>
              <div className="fh-list">
                {expenses.recent.map((e) => {
                  const pill = expPill(e.status);
                  return (
                    <div className="fh-row" key={e.id}>
                      <div className="fh-row-main">
                        <div className="fh-row-name"><Link href={`/finance/expenses/${e.id}/`}>{e.number}</Link></div>
                        <div className="fh-row-sub">{e.vendor} · <StatusPill small label={pill.label} tone={pill.tone} /></div>
                      </div>
                      <div className="fh-row-amt">{fmt(e.amount_sar)}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {journal && (
          <div className="hms-dv-card fh-card">
            <div className="hms-dv-body">
              <div className="hms-dv-sech">
                <span className="hms-dv-sec-title">{t("Journal")}</span>
                <span className="hms-dv-sec-actions"><Link className="hms-dv-act" href="/finance/journal/">{t("View all")}</Link></span>
              </div>
              {journal.recent.length === 0 ? (
                <div className="fh-empty">{t("No journal entries yet.")}</div>
              ) : (
                <div className="fh-list">
                  {journal.recent.map((e) => (
                    <div className="fh-row" key={e.id}>
                      <div className="fh-row-main">
                        <div className="fh-row-name"><Link href={`/finance/journal/${e.id}/`}>{e.number}</Link></div>
                        <div className="fh-row-sub">{fmtDateShort(e.date)} · {e.entry_type_display}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}