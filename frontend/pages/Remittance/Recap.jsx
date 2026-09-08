import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

export default function Recap({ monthly }) {
  const { t } = useI18n();
  return (
    <div className="page shadcn-root">
      <PageBack href="/remittance/" />
      <PageHeader
        title={t("Monthly Recap")}
        sub={t("Remittance summary per month")}
      />

      {monthly.length ? monthly.map((m, i) => (
        <div className="month-card" key={i}>
          <div className="month-header">
            <div className="month-label">{m.label}</div>
            <div className="month-meta">
              <div className="month-badges">
                {m.count_pending > 0 && <StatusPill tone="yellow" label={`${m.count_pending} ${t("Pending")}`} />}
                {m.count_received > 0 && <StatusPill tone="green" label={`${m.count_received} ${t("Received")}`} />}
              </div>
              <div className="month-total">{fmt(m.total_sent)} SAR</div>
              <Button variant="ghost" size="xs" asChild>
                <a href={`/remittance/export/pdf/?month=${m.period}`} target="_blank" rel="noreferrer">PDF ↓</a>
              </Button>
            </div>
          </div>
          <table className="recap-table">
            <thead>
              <tr><th>{t("No")}</th><th>{t("Date")}</th><th>{t("Res Count")}</th><th>{t("Status")}</th><th className="r">{t("Total SAR")}</th></tr>
            </thead>
            <tbody>
              {m.remittances.map((rem) => (
                <tr key={rem.id} style={{ cursor: "pointer" }} onClick={() => router.visit(`/remittance/${rem.id}/`)}>
                  <td className="mono" style={{ fontWeight: 600 }}>{rem.remittance_number}</td>
                  <td>{rem.date}</td>
                  <td style={{ color: "var(--text-2)" }}>{rem.lines_count} {t("reservations")}</td>
                  <td>{rem.status === "received" ? <StatusPill tone="green" label={t("Received")} /> : <StatusPill tone="yellow" label={t("Pending")} />}</td>
                  <td className="mono r" style={{ fontWeight: 600 }}>{fmt(rem.total_sar)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="month-foot">
            <div style={{ display: "flex", gap: 16 }}>
              {m.total_received > 0 && <span className="month-foot-label">{t("Received")}: <span className="month-foot-val" style={{ color: "var(--green)" }}>{fmt(m.total_received)}</span></span>}
              {m.total_pending > 0 && <span className="month-foot-label">{t("Pending")}: <span className="month-foot-val" style={{ color: "var(--yellow)" }}>{fmt(m.total_pending)}</span></span>}
            </div>
            <span className="month-foot-label">{t("Total")}: <span className="month-foot-val">{fmt(m.total_sent)} SAR</span></span>
          </div>
        </div>
      )) : (
        <div className="hms-list-card">
          <EmptyState iconName="remittance" title="No remittance data yet" />
        </div>
      )}
    </div>
  );
}
