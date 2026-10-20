import { useState } from "react";
import { router } from "@inertiajs/react";
import {
  ListPage, Kpis, Kpi, Toolbar, FilterMenu, FilterSection, Check, Primary, TableCard, Pill, Pager, Empty,
  fmtN, dShort, useListNav,
} from "../../components/shadcn/list-a.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";

// Claims for reimbursement (2026-10-19): the branch fronts its operating
// costs and claims them from head office, which pays back the exact rupiah.
export const CLAIM_STATUS = {
  draft: ["outline", "Draft"], submitted: ["amber", "Submitted"], paid: ["green", "Reimbursed"],
  rejected: ["gray", "Rejected"], cancelled: ["gray", "Cancelled"],
};
const TABS = ["", "draft", "submitted", "paid", "rejected", "cancelled"];

export default function Claims({ claims = [], kpis = {}, counts = {}, filters: f = {}, pagination = null }) {
  const { t } = useI18n();
  const perms = usePerms();
  const [go, loading] = useListNav("/finance/claims/", f);
  const [draft, setDraft] = useState(f.status || "");

  return (
    <ListPage title={t("Expense claims")} loading={loading}>
      <Kpis>
        <Kpi label={t("Not claimed yet")} value={fmtN(kpis.unclaimed)} unit="IDR" tone={kpis.unclaimed ? "warn" : undefined}
          foot={t("Paid expenses in no claim")} />
        <Kpi label={t("Claimed, waiting")} value={fmtN(kpis.claimed)} unit="IDR"
          foot={t("In a draft or submitted claim")} on={f.status === "submitted"}
          onClick={() => go({ status: f.status === "submitted" ? "" : "submitted" })} />
        <Kpi label={t("Reimbursed")} value={fmtN(kpis.paid)} unit="IDR" foot={t("Paid back by head office")} />
      </Kpis>

      <Toolbar spaced>
        <FilterMenu count={f.status ? 1 : 0} onOpen={() => setDraft(f.status)}
          onReset={() => setDraft("")} onApply={() => go({ status: draft })}>
          <FilterSection label={t("Status")}>
            {TABS.map((s) => (
              <Check key={s || "all"} radio on={draft === s} onClick={() => setDraft(s)}
                label={s ? t(CLAIM_STATUS[s][1]) : t("All")} count={s ? counts[s] : undefined} />
            ))}
          </FilterSection>
        </FilterMenu>
        <a className="la-tool" href="/finance/expenses/">{t("Expenses")}</a>
        {perms.can("expenses", "create") && <Primary label={t("New claim")} onClick={() => router.visit("/finance/claims/new/")} />}
      </Toolbar>

      <TableCard cols={[110, null, 90, 140, 120, 110]}
        empty={!claims.length && <Empty title={t("No claims")} sub={t("Claim the expenses the branch has paid, for the months you choose.")} />}>
        <thead><tr>
          <th>{t("Claim")}</th><th>{t("Expenses dated")}</th><th className="n">{t("Expenses")}</th>
          <th className="n">{t("Amount (IDR)")}</th><th>{t("Status")}</th><th>{t("Reimbursed on")}</th>
        </tr></thead>
        <tbody>
          {claims.map((c) => {
            const [tone, label] = CLAIM_STATUS[c.status] || CLAIM_STATUS.draft;
            return (
              <tr key={c.id} className={["rejected", "cancelled"].includes(c.status) ? "dim" : ""}
                onClick={() => router.visit(`/finance/claims/${c.id}/`)}>
                <td><span className="mono">{c.claim_number}</span></td>
                <td>{dShort(c.date_from)} – {dShort(c.date_to)}<span className="sub">{c.branch_name}</span></td>
                <td className="n">{c.item_count ?? ""}</td>
                <td className="n">{fmtN(c.total_amount)}</td>
                <td><Pill tone={tone}>{t(label)}</Pill></td>
                <td>{c.paid_date ? dShort(c.paid_date) : <span className="mut">—</span>}</td>
              </tr>
            );
          })}
        </tbody>
      </TableCard>

      <Pager p={pagination} perPage={f.per} onPage={(page) => go({ page })} onPerPage={(per) => go({ per })} />
    </ListPage>
  );
}
