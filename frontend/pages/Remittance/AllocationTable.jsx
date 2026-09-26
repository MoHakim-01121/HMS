import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

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
      <tr className="rcp-group"><th colSpan={5} scope="colgroup">{label}</th></tr>
      {rows.map((row) => {
        const key = allocKey(row);
        const value = values[key] ?? "";
        const over = (Number(value) || 0) > row.available;
        return (
          <tr key={key} className={Number(value) > 0 ? "is-on" : undefined}>
            <td className="rcp-res">
              <span className="rcp-res-no">{row.linked_number}</span>
              <span className="rcp-sub">{row.hotel || row.invoice_number}</span>
            </td>
            <td className="rcp-client">{row.customer_name || "—"}</td>
            <td className="rcp-date">{row.check_in || "—"}</td>
            <td className="rcp-num">
              {fmt(row.available)}
              {!row.paid_in_full && (
                <span className="rcp-sub">{t("paid {paid} of {total}", { paid: fmt(row.paid_sar), total: fmt(row.total_sar) })}</span>
              )}
            </td>
            <td className="rcp-in">
              <input
                type="number" inputMode="numeric" min="0" step="1" placeholder="0"
                className="rem-input" value={value}
                aria-label={t("Allocation for {number}", { number: row.linked_number })}
                aria-invalid={over || undefined}
                onChange={(e) => onChange(key, e.target.value)}
              />
              {over && <span className="rcp-err">{t("Max {n}", { n: fmt(row.available) })}</span>}
            </td>
          </tr>
        );
      })}
    </>
  );
}

export default function AllocationTable({ rows, values, onChange, emptyText }) {
  const { t } = useI18n();
  if (!rows.length) return <div className="rcp-empty">{emptyText}</div>;
  return (
    <div className="rcp-table-wrap">
      <table className="rcp-table">
        <thead>
          <tr>
            <th scope="col">{t("Reservation")}</th>
            <th scope="col">{t("Client")}</th>
            <th scope="col">{t("Check-in")}</th>
            <th scope="col" className="r">{t("Ready to allocate")}</th>
            <th scope="col" className="r">{t("Allocation")}</th>
          </tr>
        </thead>
        <tbody>
          <Group label={t("Paid in full")} rows={rows.filter((r) => r.paid_in_full)} values={values} onChange={onChange} t={t} />
          <Group label={t("Not fully paid")} rows={rows.filter((r) => !r.paid_in_full)} values={values} onChange={onChange} t={t} />
        </tbody>
      </table>
    </div>
  );
}
