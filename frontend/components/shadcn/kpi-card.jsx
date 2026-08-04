import { useId } from "react";
import { ResponsiveContainer, AreaChart, Area } from "recharts";
import { Icon } from "../icons.jsx";

// KPI stat card shell (21st.dev "Progress Metric Card", makviesainte) — see
// the .hms-kpi* rules in tailwind.css. `sparkline` is optional and only
// worth passing when a real historical series backs it (2+ points); most
// callers here are point-in-time totals with nothing to plot.
const TONE_CLASS = { red: "tone-red", green: "tone-green", yellow: "tone-yellow", blue: "tone-blue" };

export default function KpiCard({ label, value, unit, icon, tone, warn, trend, trendGood = true, foot, sparkline, sparkKey = "value" }) {
  const gradId = `kpiSpark-${useId().replace(/:/g, "")}`;
  const hasSpark = Array.isArray(sparkline) && sparkline.length >= 2;
  const valCls = "hms-kpi-val" + (warn ? " warn" : tone && TONE_CLASS[tone] ? ` ${TONE_CLASS[tone]}` : "");

  return (
    <div className="hms-kpi">
      {hasSpark && (
        <div className="hms-kpi-spark" aria-hidden="true">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={sparkline} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--foreground)" stopOpacity={0.08} />
                  <stop offset="100%" stopColor="var(--foreground)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area type="monotone" dataKey={sparkKey} stroke="none" fill={`url(#${gradId})`} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="hms-kpi-body">
        <div className="hms-kpi-head">
          <span className="hms-kpi-label">{label}</span>
          {icon && <span className="hms-kpi-icon"><Icon name={icon} /></span>}
        </div>
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
      </div>
      {foot && <div className="hms-kpi-foot">{foot}</div>}
    </div>
  );
}
