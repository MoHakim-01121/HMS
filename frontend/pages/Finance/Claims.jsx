import { useState } from "react";
import { router } from "@inertiajs/react";
import { ListPage, Kpis, Kpi, Toolbar, FilterMenu, FilterSection, Check, Primary, TableCard, PRow, RowMenu, Pill, Pager, Empty, fmtN, dShort, useListNav, Tr, Th, Td, ToolButton } from "../../components/shadcn/list-a.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";

// Claims for reimbursement (2026-10-19): the branch fronts its operating
// costs and claims them from head office, which pays back the exact rupiah.
export const CLAIM_STATUS = {
  draft: ["outline", "Draft"], submitted: ["amber", "Submitted"], partial: ["amber", "Partly paid"], paid: ["green", "Reimbursed"],
  rejected: ["gray", "Rejected"], cancelled: ["gray", "Cancelled"],
};
const TABS = ["", "draft", "submitted", "partial", "paid", "rejected", "cancelled"];

export default function Claims({ claims = [], kpis = {}, counts = {}, filters: f = {}, pagination = null }) {
  const { t } = useI18n();
  const perms = usePerms();
  const [go, loading] = useListNav("/finance/claims/", f);
  const [draft, setDraft] = useState(f.status || "");

  // The row's actions: the desktop row menu, and the same menu on a phone row.
  const menuFor = (c) => [
    { label: t("View details"), onClick: () => router.visit(`/finance/claims/${c.id}/`) },
    { label: t("Download PDF"), href: `/finance/claims/${c.id}/pdf/` },
    c.status === "draft" && perms.can("expenses", "create") && { label: t("Submit to head office"), onClick: () => router.post(`/finance/claims/${c.id}/submit/`) },
    (c.status === "submitted" || c.status === "partial") && perms.can("bank", "edit") && { label: t("Record reimbursement"), onClick: () => router.visit(`/finance/claims/${c.id}/`) },
  ];

  return (
    <ListPage title={t("Expense claims")} loading={loading}>
      <Kpis>
        <Kpi label={t("Not claimed yet")} value={fmtN(kpis.unclaimed)} unit="IDR" tone={kpis.unclaimed ? "warn" : undefined}
          foot={t("Paid expenses in no claim")} />
        <Kpi label={t("Claimed, waiting")} value={fmtN(kpis.claimed)} unit="IDR"
          foot={t("In a draft or submitted claim")} on={f.status === "submitted"}
          onClick={() => go({ status: f.status === "submitted" ? "" : "submitted" })} />
        <Kpi label={t("Reimbursed")} value={fmtN(kpis.paid)} unit="IDR" foot={kpis.credit ? t("{v} IDR head office credit, cuts the next claim", { v: fmtN(kpis.credit) }) : kpis.borne ? t("{v} IDR borne by the branch", { v: fmtN(kpis.borne) }) : t("Paid back by head office")} />
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
        <ToolButton as="a" href="/finance/expenses/">{t("Expenses")}</ToolButton>
        {perms.can("expenses", "create") && <Primary label={t("New claim")} onClick={() => router.visit("/finance/claims/new/")} />}
      </Toolbar>

      <TableCard cols={[104, null, 76, 116, 116, 104, 124, 122, 68]}
        phone={claims.map((c) => {
          const [tone, label] = CLAIM_STATUS[c.status] || CLAIM_STATUS.draft;
          return (
            <PRow key={c.id} menu={<RowMenu label={t("Actions for {n}", { n: c.claim_number })} items={menuFor(c)} />} href={`/finance/claims/${c.id}/`} mono no={c.claim_number} dim={["rejected", "cancelled"].includes(c.status)}
              tag={<Pill tone={tone} sm>{t(label)}</Pill>}
              title={`${dShort(c.date_from)} – ${dShort(c.date_to)}`} amount={fmtN(c.total_amount)} unit="IDR"
              meta={[c.branch_name, c.item_count != null ? t(c.item_count === 1 ? "{n} item" : "{n} items", { n: c.item_count }) : null].filter(Boolean).join(" · ")}
              note={c.paid_date ? t("paid {d}", { d: dShort(c.paid_date) }) : null} />
          );
        })}
        empty={!claims.length && <Empty title={t("No claims")} sub={t("Claim the expenses the branch has paid, for the months you choose.")} />}>
        <thead><Tr>
          <Th>{t("Claim")}</Th><Th>{t("Expenses dated")}</Th><Th className="text-right">{t("Expenses")}</Th>
          <Th className="text-right">{t("Amount (IDR)")}</Th><Th className="text-right">{t("Received")}</Th><Th className="text-right">{t("Remaining")}</Th><Th>{t("Status")}</Th><Th>{t("Reimbursed on")}</Th><Th className="text-center">{t("Action")}</Th>
        </Tr></thead>
        <tbody>
          {claims.map((c) => {
            const [tone, label] = CLAIM_STATUS[c.status] || CLAIM_STATUS.draft;
            return (
              <Tr key={c.id} row={["rejected", "cancelled"].includes(c.status) ? "dim" : undefined}
                onClick={() => router.visit(`/finance/claims/${c.id}/`)}>
                <Td><span className="font-mono text-[13px] font-semibold">{c.claim_number}</span></Td>
                <Td>{dShort(c.date_from)} – {dShort(c.date_to)}<span className="mt-0.5 block overflow-hidden text-ellipsis text-[12px] font-normal text-muted-foreground">{c.branch_name}</span></Td>
                <Td className="text-right">{c.item_count ?? ""}</Td>
                <Td className="text-right">{fmtN(c.total_amount)}</Td>
                <Td className="text-right">{c.received_amount ? fmtN(c.received_amount) : <span className="text-muted-foreground">—</span>}</Td>
                <Td className="text-right">{c.remaining && !["draft", "rejected", "cancelled"].includes(c.status) ? fmtN(c.remaining) : <span className="text-muted-foreground">—</span>}</Td>
                <Td><Pill tone={tone}>{t(label)}</Pill></Td>
                <Td>{c.paid_date ? dShort(c.paid_date) : <span className="text-muted-foreground">—</span>}</Td>
                <Td className="text-center"><RowMenu label={t("Actions for {n}", { n: c.claim_number })} items={menuFor(c)} /></Td>
              </Tr>
            );
          })}
        </tbody>
      </TableCard>

      <Pager p={pagination} perPage={f.per} onPage={(page) => go({ page })} onPerPage={(per) => go({ per })} />
    </ListPage>
  );
}
