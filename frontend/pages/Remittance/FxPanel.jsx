import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtDec } from "../../utils/format.js";
import { cn } from "@/lib/utils";

const HINT = "mt-1.5 mb-0 text-muted-foreground";
const ROW = "flex justify-between gap-3 py-[3px] tabular-nums [&>span:last-child]:text-right";

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
    <div className="mt-1 mb-3.5 rounded-[12px] border border-border bg-[color:color-mix(in_oklch,var(--muted)_45%,var(--card))] px-3.5 py-3 text-[13px]" aria-live="polite">
      <div className="mb-1.5 font-semibold">{t("FX profit")}</div>
      {rows.map(([k, v]) => (
        <div key={k} className={ROW}><span className="text-muted-foreground">{k}</span><span>{v}</span></div>
      ))}
      <div className={cn(ROW, "mt-1 border-t border-border pt-[7px] text-[13px] font-semibold")}>
        <span>{profit != null && profit < 0 ? t("FX loss") : t("FX profit")}</span>
        <span className={profit != null && profit < 0 ? "text-red" : profit > 0 ? "text-success" : undefined}>
          {profit != null ? `${fmt(Math.abs(profit))} IDR` : "—"}
        </span>
      </div>
      {!f && <p className={HINT}>{legacy
        ? t("Fill in the rupiah sent and the original amount to see the profit.")
        : t("Enter the IDR amount and rate to see the profit.")}</p>}
      {f && legacy && original == null && <p className={HINT}>{t("Fill in the original amount the clients paid for this transfer.")}</p>}
      {f && !legacy && f.uncovered > 0 && (
        <p className="mt-1.5 mb-0 text-yellow">{t("{n} SAR of this transfer has no client rupiah behind it, so no original rate.", { n: fmt(f.uncovered) })}</p>
      )}
    </div>
  );
}

