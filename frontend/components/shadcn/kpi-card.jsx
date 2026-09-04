import { Icon } from "../icons.jsx";

// KPI cell for the "papan angka" board (Homlu v2.1, doc 01/02). One row of
// these lives inside a single divided card (.hms-kpi-row) — no per-cell
// border, icon or sparkline. Three stacked parts: label, figure (+ optional
// delta badge), then a meta line. `icon` and `sparkline` are still accepted
// so existing call sites keep working, but v2.1 renders neither.
const TONE_CLASS = { red: "tone-red", green: "tone-green", yellow: "tone-yellow", blue: "tone-blue" };

export default function KpiCard({ label, value, unit, tone, warn, trend, trendGood = true, foot }) {
  const valCls = "hms-kpi-val" + (warn ? " warn" : tone && TONE_CLASS[tone] ? ` ${TONE_CLASS[tone]}` : "");

  return (
    <div className="hms-kpi">
      <div className="hms-kpi-body">
        <span className="hms-kpi-label">{label}</span>
        <div className="hms-kpi-val-row">
          <span className={valCls}>
            {value}
            {unit && <span className="hms-kpi-unit">{unit}</span>}
          </span>
          {trend && trend.dir && trend.dir !== "flat" && (
            <span className={"hms-kpi-trend " + trend.dir + (trendGood ? "" : " bad")}>
              <Icon name={trend.dir === "up" ? "trend-up" : "trend-down"} strokeWidth={2.5} />
              {Math.abs(trend.pct ?? 0).toFixed(0)}%
            </span>
          )}
        </div>
        {foot && <div className="hms-kpi-foot">{foot}</div>}
      </div>
    </div>
  );
}
