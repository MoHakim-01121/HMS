import { useState } from "react";
import { router } from "@inertiajs/react";
import {
  ListPage, Kpis, Kpi, Toolbar, MonthNav, SearchTool, FilterMenu, FilterSection, Check, ExportMenu, Primary,
  TableCard, RowMenu, Pill, Pager, Empty, LIcon, MONTHS, fmtN, dShort, useListNav, rowNav,
} from "../../components/shadcn/list-a.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";
import NewExpense from "./NewExpense.jsx";


// Recorded by Finance in rupiah, approved, then paid (2026-10-11).
const STATUS = {
  submitted: ["outline", "Awaiting approval"], approved: ["amber", "Approved, not paid"],
  paid: ["green", "Paid"], rejected: ["gray", "Rejected"], voided: ["gray", "Voided"],
};
const monthName = (ym, t) => (ym ? t(MONTHS[+ym.slice(5, 7) - 1]) : "");

// Expenses, as on the Record View HMS canvas: spent in the month, awaiting
// approval and approved not paid (both filter the table), the toolbar and the
// table. New expense opens the approved form (NewExpense.jsx).
export default function List({
  expenses = [], branch_choices = [], category_choices = [], filters: f, years = [], counts = {}, people_counts = [],
  kpis = null, pagination = null, vendor_choices = [], staff_choices = [], me = null,
}) {
  const { t } = useI18n();
  const perms = usePerms();
  const canCreate = perms.can("expenses", "create");
  const canExport = perms.can("expenses", "export");
  // Categories are shared by every branch: head office manages them.
  const canManageCategories = perms.can("expenses", "edit") && perms.headOffice;

  const canApprove = perms.can("expenses", "approve");
  const [go, loading] = useListNav("/finance/expenses/", f);
  const [draft, setDraft] = useState(f);
  const tog = (key, v) => setDraft((d) => ({ ...d, [key]: d[key].includes(v) ? d[key].filter((x) => x !== v) : [...d[key], v] }));
  const only = (k) => f.status.length === 1 && f.status[0] === k;
  const [newOpen, setNewOpen] = useState(false);
  const prevName = kpis ? monthName(kpis.prev_month, t) : "";
  const filterCount = (f.status.length ? 1 : 0) + (f.by.length ? 1 : 0);

  return (
    <ListPage title={t("Expenses")} loading={loading}>
      {kpis && (
        <Kpis>
          <Kpi label={t("Spent in {m}", { m: monthName(f.month, t) })} value={fmtN(kpis.spent)} unit="IDR"
            delta={kpis.delta && { text: kpis.delta, good: kpis.delta.startsWith("-"), title: t("{d} vs {m}", { d: kpis.delta, m: prevName }) }}
            foot={kpis.top_category ? t("{c} is the largest share, {p}%", { c: kpis.top_category, p: kpis.top_share }) : t("Nothing paid yet this month")} />
          <Kpi label={t("Awaiting approval")} value={fmtN(kpis.waiting_count)} unit={t("expenses")}
            foot={kpis.waiting_count ? t("{v} IDR, oldest waiting {d} days", { v: fmtN(kpis.waiting_idr), d: kpis.waiting_oldest }) : t("Nothing to approve")}
            on={only("submitted")} onClick={() => go({ status: only("submitted") ? [] : ["submitted"] })} />
          <Kpi label={t("Approved, not paid")} value={fmtN(kpis.approved_idr)} unit="IDR" tone={kpis.approved_idr ? "warn" : undefined}
            foot={kpis.approved_count ? t("{n} expenses to pay, oldest approved {d} days ago", { n: kpis.approved_count, d: kpis.approved_oldest }) : t("Everything approved is paid")}
            on={only("approved")} onClick={() => go({ status: only("approved") ? [] : ["approved"] })} />
        </Kpis>
      )}

      <Toolbar spaced={!!kpis} left={<MonthNav month={f.month} year={f.year} years={years} onChange={(p) => go(p)} />}>
        <SearchTool value={f.q} onSearch={(q) => go({ q })} placeholder={t("Search expense, description, staff")} />
        <FilterMenu count={filterCount} onOpen={() => setDraft(f)}
          onReset={() => setDraft({ ...draft, status: [], by: [] })}
          onApply={() => go({ status: draft.status, by: draft.by })}>
          <FilterSection label={t("Status")}>
            <Check on={draft.status.includes("submitted")} onClick={() => tog("status", "submitted")} label={t("Awaiting approval")} count={counts.submitted} />
            <Check on={draft.status.includes("approved")} onClick={() => tog("status", "approved")} label={t("Approved, not paid")} count={counts.approved} />
            <Check on={draft.status.includes("paid")} onClick={() => tog("status", "paid")} label={t("Paid")} count={counts.paid} />
            <Check on={draft.status.includes("off")} onClick={() => tog("status", "off")} label={t("Rejected or voided")} count={counts.off} />
          </FilterSection>
          {people_counts.length > 1 && (
            <FilterSection label={t("Recorded by")}>
              {people_counts.map((p) => <Check key={p.name} on={draft.by.includes(p.name)} onClick={() => tog("by", p.name)} label={p.name} count={p.count} />)}
            </FilterSection>
          )}
        </FilterMenu>
        {canExport && <ExportMenu items={[{ label: "CSV", href: "/finance/expenses/export/csv/" }]} />}
        <a className="la-tool" href="/finance/claims/">{t("Claims")}</a>
        {canManageCategories && <a className="la-tool" href="/finance/expenses/categories/">{t("Categories")}</a>}
        {canCreate && <Primary label={t("New expense")} onClick={() => setNewOpen(true)} />}
      </Toolbar>

      <TableCard cols={[104, 76, null, 160, 130, 96, 160, 56]}
        empty={!expenses.length && <Empty title={t("No expenses")} sub={t("Nothing matches this period and these filters.")} />}>
        <thead><tr>
          <th>{t("Expense")}</th>
          <th><button type="button" className="srt" style={{ border: 0, background: "none", padding: 0, font: "inherit", cursor: "pointer" }}
            onClick={() => go({ sort: f.sort === "date" ? "-date" : "date" })}>{t("Date")}{f.sort === "date" ? LIcon.sortUp : LIcon.sortDown}</button></th>
          <th>{t("Description")}</th><th>{t("Recorded by")}</th><th className="n">{t("Amount (IDR)")}</th><th>{t("Receipt")}</th><th>{t("Status")}</th><th className="c">{t("Action")}</th>
        </tr></thead>
        <tbody>
          {expenses.map((e) => {
            const [tone, label] = STATUS[e.status] || STATUS.submitted;
            const cats = [...new Set(e.lines.map((l) => l.category_name))];
            const catText = cats.length > 2 ? t("{a}, {b} and {n} more", { a: cats[0], b: cats[1], n: cats.length - 2 }) : cats.join(", ");
            return (
              <tr key={e.id} className={["rejected", "voided"].includes(e.status) ? "dim" : ""} {...rowNav(`/finance/expenses/${e.id}/`)}>
                <td><span className="mono">{e.expense_number}</span></td>
                <td>{dShort(e.expense_date)}</td>
                <td className="ell"><span className="strong">{e.description || catText || t("Expense")}</span>
                  <span className="sub">{t(e.lines.length === 1 ? "{n} line, {c}" : "{n} lines, {c}", { n: e.lines.length, c: catText })}</span></td>
                <td className="ell">{e.recorded_by}{e.vendor && <span className="sub">{e.vendor}</span>}</td>
                <td className="n">{fmtN(e.total_amount)}</td>
                <td>{(() => {
                  const n = e.lines.reduce((s, l) => s + (l.receipts?.length || 0), 0) + (e.proof_url ? 1 : 0);
                  const missing = e.lines.filter((l) => !l.receipts?.length && l.no_receipt_reason).length;
                  return n ? t(n === 1 ? "1 file" : "{n} files", { n }) + (missing ? ` · ${t("{n} without", { n: missing })}` : "")
                    : <span className="mut">{missing ? t("No receipt") : t("None")}</span>;
                })()}</td>
                <td><Pill tone={tone}>{t(label)}</Pill></td>
                <td className="c">
                  <RowMenu label={t("Actions for {n}", { n: e.expense_number })} items={[
                    canApprove && e.status === "submitted" && { label: t("Approve"), onClick: () => router.post(`/finance/expenses/${e.id}/approve/`, {}, { preserveScroll: true }) },
                    e.proof_url && { label: t("View receipt"), href: e.proof_url, external: true },
                    e.status === "approved" && perms.can("expenses", "edit") && { label: t("Pay"), onClick: () => router.visit(`/finance/expenses/${e.id}/`) },
                    canApprove && e.status === "submitted" && { label: t("Reject"), danger: true, onClick: () => router.visit(`/finance/expenses/${e.id}/`) },
                  ]} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </TableCard>

      <Pager p={pagination} perPage={f.per} onPage={(page) => go({ page })} onPerPage={(per) => go({ per })} />

      {newOpen && (
        <NewExpense onClose={() => setNewOpen(false)} branch_choices={branch_choices} category_choices={category_choices}
          staff_choices={staff_choices} vendor_choices={vendor_choices} me={me} />
      )}
    </ListPage>
  );
}
