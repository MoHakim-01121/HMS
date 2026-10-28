import { Icon } from "../../components/icons.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";
import { cn } from "@/lib/utils";
import { TH, TD, NUM, SUB } from "./AllocationTable.jsx";

// Reservations chosen on the Tracking tab for this transfer. Only a plan: HQ's
// receipt form starts from it, the allocation itself is made there.
export default function PlanTable({ rows, onChange, onRemove }) {
  const { t } = useI18n();
  const total = rows.reduce((sum, r) => sum + (Number(r.amount_sar) || 0), 0);
  return (
    <div className="overflow-hidden rounded-[14px] border border-border">
      <table className="w-full border-collapse max-[700px]:block">
        <thead className="max-[700px]:hidden">
          <tr>
            <th scope="col" className={TH}>{t("Reservation")}</th>
            <th scope="col" className={TH}>{t("Client")}</th>
            <th scope="col" className={TH}>{t("Check-in")}</th>
            <th scope="col" className={cn(TH, "text-right")}>{t("Planned")}</th>
            <th scope="col" className={cn(TH, "w-10")}><span className="sr-only">{t("Remove")}</span></th>
          </tr>
        </thead>
        <tbody className="max-[700px]:block">
          {rows.map((row) => {
            const over = (Number(row.amount_sar) || 0) > row.plannable;
            return (
              <tr key={row.invoice_line_id} className="max-[700px]:grid max-[700px]:grid-cols-[1fr_auto] max-[700px]:gap-x-3 max-[700px]:gap-y-0.5 max-[700px]:border-b max-[700px]:border-border max-[700px]:px-3 max-[700px]:py-2.5">
                <td className={cn(TD, "max-[700px]:col-start-1")}>
                  <span className="block font-mono text-[12px] font-bold">{row.linked_number}</span>
                  <span className={SUB}>{row.hotel}</span>
                </td>
                <td className={cn(TD, "text-muted-foreground max-[700px]:col-start-1 max-[700px]:text-[12px]")}>{row.client_name || "—"}</td>
                <td className={cn(TD, "whitespace-nowrap tabular-nums max-[700px]:col-start-1 max-[700px]:text-[12px]")}>{row.check_in || "—"}</td>
                <td className={cn(TD, NUM, "max-[700px]:col-start-2 max-[700px]:row-start-1")}>
                  <input
                    type="number" inputMode="numeric" min="1" step="1"
                    className="ml-auto block w-[110px] rounded-[calc(var(--radius)-4px)] border border-input bg-transparent px-2.5 py-1.5 text-right text-[13px] text-foreground transition-[border-color] duration-[120ms] focus:border-ring focus:outline-none aria-invalid:border-red"
                    value={row.amount_sar}
                    aria-label={t("Planned for {number}", { number: row.linked_number })}
                    aria-invalid={over || undefined}
                    onChange={(e) => onChange(row.invoice_line_id, e.target.value)}
                  />
                  {over && <span className="mt-[3px] block text-[11px] text-red">{t("Max {n}", { n: fmt(row.plannable) })}</span>}
                </td>
                <td className={cn(TD, "text-right max-[700px]:col-start-2 max-[700px]:row-start-2")}>
                  <button type="button" onClick={() => onRemove(row.invoice_line_id)} aria-label={t("Remove {number}", { number: row.linked_number })}
                    className="inline-grid size-7 cursor-pointer place-content-center rounded-full border-0 bg-transparent text-muted-foreground hover:bg-secondary hover:text-foreground focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring">
                    <Icon name="close" size={14} />
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot className="max-[700px]:block">
          <tr className="max-[700px]:flex max-[700px]:justify-between max-[700px]:px-3 max-[700px]:py-2.5">
            <td colSpan={3} className="px-3 py-2.5 text-[13px] text-muted-foreground max-[700px]:p-0">{t("{n} reservations", { n: rows.length })}</td>
            <td className={cn(NUM, "px-3 py-2.5 text-[13px] font-semibold max-[700px]:p-0")}>{fmt(total)} SAR</td>
            <td className="max-[700px]:hidden" />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
