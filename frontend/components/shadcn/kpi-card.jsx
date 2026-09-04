// KPI cell for the "papan angka" board (Homlu v2.1, doc 01/02). One row of
// these lives inside a single divided card (.hms-kpi-row) — no per-cell
// border, icon or sparkline. Three stacked parts: label, figure, then a
// delta row: a FILLED library badge (green good / red bad / grey neutral)
// carrying the change, followed by the plain meta text.
const TONE_CLASS = { red: "tone-red", green: "tone-green", yellow: "tone-yellow", blue: "tone-blue" };

export default function KpiCard({ label, value, unit, tone, warn, trend, trendGood = true, foot }) {
  const valCls = "hms-kpi-val" + (warn ? " warn" : tone && TONE_CLASS[tone] ? ` ${TONE_CLASS[tone]}` : "");

  let deltaCls = "neutral";
  let deltaText = null;
  if (trend && trend.dir && trend.dir !== "flat") {
    const good = trendGood ? trend.dir === "up" : trend.dir === "down";
    deltaCls = good ? "good" : "bad";
    const pct = Math.abs(trend.pct ?? 0).toFixed(0);
    deltaText = `${trend.dir === "up" ? "+" : "−"}${pct}%`;
  }

  return (
    <div className="hms-kpi">
      <div className="hms-kpi-body">
        <span className="hms-kpi-label">{label}</span>
        <div className="hms-kpi-val-row">
          <span className={valCls}>
            {value}
            {unit && <span className="hms-kpi-unit">{unit}</span>}
          </span>
        </div>
        {(deltaText || foot) && (
          <div className="hms-kpi-delta-row">
            {deltaText && <span className={"hms-kpi-badge " + deltaCls}>{deltaText}</span>}
            {foot && <span className="hms-kpi-foot">{foot}</span>}
          </div>
        )}
      </div>
    </div>
  );
}
