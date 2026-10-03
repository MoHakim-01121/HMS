import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtDec } from "../../utils/format.js";

// Laba kurs setoran, dihitung langsung saat form diisi:
// nominal original = SAR × kurs asal (rupiah yang dulu dibayar client),
// laba = nominal original − rupiah yang dikirim.
//
// Setoran baru: kurs asal = rata-rata uang client rupiah yang belum disetor
// (`pool`). Setoran lama: nominal original diisi user (`original`).
export function fxFigures({ pool, sentIdr, sar, original }) {
  if (!sentIdr || !sar) return null;
  if (original != null) {
    return { sar, original, originRate: original / sar, profit: original - sentIdr, uncovered: 0 };
  }
  if (!pool?.rate) return { sar, original: null, originRate: null, profit: null, uncovered: sar };
  const covered = Math.min(sar, pool.sar);
  const originalAmt = pool.rate * covered;
  const sentForCovered = (sentIdr * covered) / sar;
  return {
    sar,
    original: originalAmt,
    originRate: pool.rate,
    profit: covered > 0 ? originalAmt - sentForCovered : null,
    uncovered: sar - covered,
  };
}

export default function FxPanel({ pool, sentIdr, sar, original, legacy = false }) {
  const { t } = useI18n();
  const f = fxFigures({ pool, sentIdr, sar, original: legacy ? original : null });
  const rows = [];
  if (!legacy && pool) {
    rows.push([
      t("Client money in rupiah"),
      pool.rate ? `${fmt(pool.amount)} IDR · ${fmt(pool.sar)} SAR` : t("none yet"),
    ]);
  }
  if (f) {
    rows.push([t("Sent"), `${fmt(sentIdr)} IDR → ${fmt(f.sar)} SAR · ${t("rate")} ${fmtDec(sentIdr / f.sar, 2)}`]);
    rows.push([
      t("Original amount"),
      f.original != null ? `${fmt(f.original)} IDR · ${t("original rate")} ${fmtDec(f.originRate, 2)}` : "—",
    ]);
  }
  const profit = f?.profit;
  return (
    <div className="rem-fx" aria-live="polite">
      <div className="rem-fx-title">{t("FX profit")}</div>
      {rows.map(([k, v]) => (
        <div key={k} className="rem-fx-row"><span>{k}</span><span>{v}</span></div>
      ))}
      <div className="rem-fx-row rem-fx-total">
        <span>{profit != null && profit < 0 ? t("FX loss") : t("FX profit")}</span>
        <span className={profit != null && profit < 0 ? "is-loss" : profit > 0 ? "is-gain" : ""}>
          {profit != null ? `${fmt(Math.abs(profit))} IDR` : "—"}
        </span>
      </div>
      {!f && <p className="rem-fx-hint">{legacy
        ? t("Fill in the rupiah sent and the original amount to see the profit.")
        : t("Enter the IDR amount and rate to see the profit.")}</p>}
      {f && legacy && original == null && <p className="rem-fx-hint">{t("Fill in the original amount the clients paid for this transfer.")}</p>}
      {f && !legacy && f.uncovered > 0 && (
        <p className="rem-fx-warn">{t("{n} SAR of this transfer has no client rupiah behind it, so no original rate.", { n: fmt(f.uncovered) })}</p>
      )}
    </div>
  );
}

export const FX_CSS = `
.rem-fx { margin: 4px 0 14px; padding: 12px 14px; border-radius: 12px; border: 1px solid var(--border);
  background: color-mix(in oklch, var(--muted) 45%, var(--card)); font-size: 12.5px; }
.rem-fx-title { font-weight: 600; margin-bottom: 6px; }
.rem-fx-row { display: flex; justify-content: space-between; gap: 12px; padding: 3px 0; font-variant-numeric: tabular-nums; }
.rem-fx-row > span:first-child { color: var(--muted-foreground); }
.rem-fx-row > span:last-child { text-align: right; }
.rem-fx-total { border-top: 1px solid var(--border); margin-top: 4px; padding-top: 7px; font-weight: 600; font-size: 13px; }
.rem-fx-total > span:first-child { color: var(--foreground); }
.rem-fx-total .is-gain { color: var(--green); }
.rem-fx-total .is-loss { color: var(--red); }
.rem-fx-hint { margin: 6px 0 0; color: var(--muted-foreground); }
.rem-fx-warn { margin: 6px 0 0; color: var(--yellow); }
`;
