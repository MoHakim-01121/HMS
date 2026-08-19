import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import { useI18n } from "../../utils/i18n.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

function outcomeBadge(key) {
  if (key === "ORDER") return ["badge badge-green", "Order received"];
  if (key === "PROSPECT") return ["badge badge-blue", "Prospect / follow-up needed"];
  if (key === "NO_INTEREST") return ["badge badge-yellow", "No interest"];
  if (key === "NOT_MET") return ["badge badge-red", "Client not met"];
  return ["badge", key || ""];
}

export default function Recap({ monthly }) {
  const { t } = useI18n();
  return (
    <div className="page shadcn-root">
      <PageBack href="/visits/" />
      <div className="page-header">
        <div>
          <div className="page-title">{t("Visits Recap")}</div>
          <div className="page-sub">{t("Visit results summary per month")}</div>
        </div>
      </div>

      {monthly.length ? monthly.map((m, i) => (
        <div className="month-card" key={i}>
          <div className="month-header">
            <div className="month-label">{m.label}</div>
            <div className="month-meta">
              <div className="month-badges">
                {m.planned > 0 && <span className="badge badge-yellow">{m.planned} {t("Planned")}</span>}
                {m.completed > 0 && <span className="badge badge-green">{m.completed} {t("Completed")}</span>}
                {m.cancelled > 0 && <span className="badge badge-red">{m.cancelled} {t("Cancelled")}</span>}
                <span className="badge">{t("{rate}% done", { rate: m.completion_rate })}</span>
              </div>
              <div className="month-total">{m.total} {t("visits")}</div>
            </div>
          </div>

          <div className="month-grid">
            <div>
              <div className="month-foot-label" style={{ marginBottom: 6 }}>{t("Outcome")}</div>
              {m.outcomes.some((o) => o.count > 0) ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {m.outcomes.filter((o) => o.count > 0).map((o) => {
                    const [c, l] = outcomeBadge(o.key);
                    return <span key={o.key} className={c} style={{ alignSelf: "flex-start" }}>{t(l)} · {o.count}</span>;
                  })}
                </div>
              ) : (
                <span style={{ fontSize: 12, color: "var(--muted-foreground)" }}>{t("No completed visits")}</span>
              )}
              {m.total_value_sar > 0 && (
                <div className="month-foot-label" style={{ marginTop: 10 }}>
                  {t("Est. value")}: <span className="month-foot-val">{fmt(m.total_value_sar)} SAR</span>
                </div>
              )}
            </div>
            <div>
              <div className="month-foot-label" style={{ marginBottom: 6 }}>{t("Staff")}</div>
              <table className="recap-table">
                <thead>
                  <tr><th>{t("Staff")}</th><th className="r">{t("Done")}</th><th className="r">{t("Dist (m)")}</th><th className="r">{t("Value")}</th></tr>
                </thead>
                <tbody>
                  {m.staffs.map((s) => (
                    <tr key={s.name}>
                      <td style={{ fontWeight: 600 }}>{s.name}</td>
                      <td className="r">{s.completed}</td>
                      <td className="r mono">{fmt(s.distance_meters)}</td>
                      <td className="r mono">{s.value_sar ? fmt(s.value_sar) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {m.total_distance_meters > 0 && (
                <div className="month-foot-label" style={{ marginTop: 8 }}>
                  {t("Total distance")}: <span className="month-foot-val">{fmt(m.total_distance_meters)} m</span>
                </div>
              )}
            </div>
          </div>

          <div className="month-foot">
            <div style={{ display: "flex", gap: 16 }}>
              <span className="month-foot-label">{t("Total")}: <span className="month-foot-val">{m.total}</span></span>
              {m.total_value_sar > 0 && <span className="month-foot-label">{t("Est. value")}: <span className="month-foot-val">{fmt(m.total_value_sar)} SAR</span></span>}
            </div>
            <a href="/visits/" style={{ fontSize: 12 }}>{t("Open list")} →</a>
          </div>
        </div>
      )) : (
        <div className="card">
          <div className="empty"><div className="empty-title">{t("No visit data yet")}</div></div>
        </div>
      )}
    </div>
  );
}
