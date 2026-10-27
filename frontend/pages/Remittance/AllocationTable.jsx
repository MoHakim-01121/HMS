import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";
import { cn } from "@/lib/utils";

// Below 700px the table folds into cards: reservation and amount on one line,
// client and check-in under it, the allocation input across the bottom.
const TH = "border-b border-border px-3 py-2.5 text-left text-[12px] font-medium whitespace-nowrap text-muted-foreground";
const TD = "border-b border-border px-3 py-2.5 align-middle text-[13px] max-[700px]:border-0 max-[700px]:p-0";
const NUM = "text-right whitespace-nowrap tabular-nums";
// The empty list here, and the note on a transfer that has nothing to allocate.
export const EMPTY = "m-0 rounded-[14px] border border-dashed border-border p-[18px] text-center text-[13px] text-muted-foreground";
const SUB = "mt-0.5 block text-[11px] font-normal whitespace-nowrap text-muted-foreground";


export const allocKey = (row) => `${row.linked_number}|${row.invoice_id ?? ""}`;

// Isian otomatis — sama dengan remittance_allocation.suggest di backend:
// kandidat sudah diurutkan server (lunas dulu, lalu check-in terdekat), isi
// berurutan sampai `amount` habis, per reservasi dibatasi uang klien siap.
export function suggestAllocations(candidates, amount) {
  let left = Math.max(0, Math.floor(Number(amount) || 0));
  const out = {};
  for (const row of candidates) {
    if (left <= 0) break;
    const take = Math.min(row.available, left);
    if (take > 0) {
      out[allocKey(row)] = String(take);
      left -= take;
    }
  }
  return out;
}

function Group({ label, rows, values, onChange, t }) {
  if (!rows.length) return null;
  return (
    <>
      <tr className="max-[700px]:block"><th colSpan={5} scope="colgroup" className={cn(TH, "bg-[color:color-mix(in_oklch,var(--muted)_40%,var(--card))] px-3 pt-3 pb-1.5 font-semibold tracking-[.07em] uppercase max-[700px]:block")}>{label}</th></tr>
      {rows.map((row) => {
        const key = allocKey(row);
        const value = values[key] ?? "";
        const over = (Number(value) || 0) > row.available;
        return (
          <tr key={key} className={cn("last:[&>td]:border-b-0 max-[700px]:grid max-[700px]:grid-cols-[1fr_auto] max-[700px]:gap-x-3 max-[700px]:gap-y-0.5 max-[700px]:border-b max-[700px]:border-border max-[700px]:px-3 max-[700px]:py-2.5", Number(value) > 0 && "[&>td]:bg-[color:color-mix(in_oklch,var(--muted)_45%,transparent)]")}>
            <td className={cn(TD, "max-[700px]:col-start-1")}>
              <span className="block font-mono text-[12px] font-bold">{row.linked_number}</span>
              <span className={SUB}>{row.hotel || row.invoice_number}</span>
            </td>
            <td className={cn(TD, "text-muted-foreground max-[700px]:col-start-1 max-[700px]:text-[12px]")}>{row.customer_name || "—"}</td>
            <td className={cn(TD, "whitespace-nowrap tabular-nums max-[700px]:col-start-1 max-[700px]:text-[12px]")}>{row.check_in || "—"}</td>
            <td className={cn(TD, NUM, "max-[700px]:col-start-2 max-[700px]:row-start-1")}>
              {fmt(row.available)}
              {!row.paid_in_full && (
                <span className={SUB}>{t("paid {paid} of {total}", { paid: fmt(row.paid_sar), total: fmt(row.total_sar) })}</span>
              )}
            </td>
            <td className={cn(TD, "text-right max-[700px]:col-span-full max-[700px]:mt-2")}>
              <input
                type="number" inputMode="numeric" min="0" step="1" placeholder="0"
                className="ml-auto block w-[110px] rounded-[calc(var(--radius)-4px)] border border-input bg-transparent px-2.5 py-1.5 text-right text-[13px] text-foreground transition-[border-color] duration-[120ms] focus:border-ring focus:outline-none aria-invalid:border-red disabled:cursor-not-allowed disabled:opacity-50 max-[700px]:w-full" value={value}
                aria-label={t("Allocation for {number}", { number: row.linked_number })}
                aria-invalid={over || undefined}
                onChange={(e) => onChange(key, e.target.value)}
              />
              {over && <span className="mt-[3px] block text-[11px] text-red">{t("Max {n}", { n: fmt(row.available) })}</span>}
            </td>
          </tr>
        );
      })}
    </>
  );
}

export default function AllocationTable({ rows, values, onChange, emptyText }) {
  const { t } = useI18n();
  if (!rows.length) return <div className={EMPTY}>{emptyText}</div>;
  return (
    <div className="overflow-hidden rounded-[14px] border border-border">
      <table className="w-full border-collapse max-[700px]:block">
        <thead className="max-[700px]:hidden">
          <tr>
            <th scope="col" className={TH}>{t("Reservation")}</th>
            <th scope="col" className={TH}>{t("Client")}</th>
            <th scope="col" className={TH}>{t("Check-in")}</th>
            <th scope="col" className={cn(TH, "text-right")}>{t("Ready to allocate")}</th>
            <th scope="col" className={cn(TH, "text-right")}>{t("Allocation")}</th>
          </tr>
        </thead>
        <tbody className="max-[700px]:block">
          <Group label={t("Paid in full")} rows={rows.filter((r) => r.paid_in_full)} values={values} onChange={onChange} t={t} />
          <Group label={t("Not fully paid")} rows={rows.filter((r) => !r.paid_in_full)} values={values} onChange={onChange} t={t} />
        </tbody>
      </table>
    </div>
  );
}
