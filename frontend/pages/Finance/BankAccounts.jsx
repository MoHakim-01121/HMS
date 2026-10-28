import { useState } from "react";
import { router } from "@inertiajs/react";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { ListPage, Toolbar, SearchTool, FilterMenu, FilterSection, Check, ExportMenu, Primary, TableCard, PRow, PTotal, RowMenu, Pill, Amt, Empty, fmtN, useListNav, rowNav, Tr, Th, Td, Note } from "../../components/shadcn/list-a.jsx";
import { cn } from "@/lib/utils";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

const CUR_NAME = { IDR: "Rupiah", USD: "US dollar", SAR: "Riyal" };
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const longDate = (iso) => { if (!iso) return ""; const [y, m, d] = iso.split("-"); return `${d} ${MON[+m - 1]} ${y}`; };

// Bank and Cash, as on the Record View HMS canvas: no KPIs; the accounts in a
// band per currency, the book balance in the account's currency next to its
// SAR value, and the total at the book rate.
export default function BankAccounts({ accounts = [], filters: f, counts = {}, as_of, can_set_up: canSetUp = false }) {
  const { t } = useI18n();
  const perms = usePerms();
  const openForm = useFormModal();
  const [go, loading] = useListNav("/finance/bank-accounts/", f);
  const [draft, setDraft] = useState(f);
  const tog = (key, v) => setDraft((d) => ({ ...d, [key]: d[key].includes(v) ? d[key].filter((x) => x !== v) : [...d[key], v] }));
  const filterCount = (f.kind.length ? 1 : 0) + (f.cur.length ? 1 : 0) + (f.branch.length ? 1 : 0);

  const office = accounts.filter((a) => a.kind !== "staff");
  const staff = accounts.filter((a) => a.kind === "staff");
  const bands = [];
  for (const a of office) {
    let b = bands[bands.length - 1];
    if (!b || b.cur !== a.currency) { b = { cur: a.currency, rows: [] }; bands.push(b); }
    b.rows.push(a);
  }
  const sarTotal = accounts.filter((a) => a.is_active && !a.ledger_shared).reduce((s, a) => s + (a.book_balance || 0), 0);
  const txHref = (a) => `/finance/bank-accounts/${a.kind}/${a.id}/`;

  // The row's actions: the desktop row menu, and the same menu on a phone
  // row. A staff advance is topped up or taken back, not set up or reconciled.
  const menuFor = (a) => a.kind === "staff" ? [
    { label: t("Transactions"), onClick: () => router.visit(txHref(a)) },
    perms.can("bank", "create") && { label: t("Give or take back money"), onClick: () => openForm("/finance/exchanges/new/") },
  ] : [
    { label: t("Transactions"), onClick: () => router.visit(txHref(a)) },
    a.kind === "bank" && perms.can("bank", "view") && { label: t("Reconcile"), onClick: () => router.visit("/finance/reconciliation/") },
    canSetUp && { label: t("Edit"), onClick: () => openForm(`/finance/bank-accounts/${a.id}/edit/`) },
  ];

  return (
    <ListPage title={t("Bank and Cash")} loading={loading}>
      <Toolbar left={<Note>{t("Balances as of {d}", { d: longDate(as_of) })}</Note>}>
        <SearchTool value={f.q} onSearch={(q) => go({ q })} placeholder={t("Search account")} />
        <FilterMenu count={filterCount} onOpen={() => setDraft(f)}
          onReset={() => setDraft({ ...draft, kind: [], cur: [], branch: [] })}
          onApply={() => go({ kind: draft.kind, cur: draft.cur, branch: draft.branch })}>
          <FilterSection label={t("Type")}>
            <Check on={draft.kind.includes("bank")} onClick={() => tog("kind", "bank")} label={t("Bank")} count={counts.kind?.bank || 0} />
            <Check on={draft.kind.includes("cash")} onClick={() => tog("kind", "cash")} label={t("Cash")} count={counts.kind?.cash || 0} />
            <Check on={draft.kind.includes("staff")} onClick={() => tog("kind", "staff")} label={t("Held by staff")} count={counts.kind?.staff || 0} />
          </FilterSection>
          <FilterSection label={t("Currency")}>
            {["IDR", "USD", "SAR"].map((c) => <Check key={c} on={draft.cur.includes(c)} onClick={() => tog("cur", c)} label={c} count={counts.cur?.[c] || 0} />)}
          </FilterSection>
          {Object.keys(counts.branch || {}).length > 1 && (
            <FilterSection label={t("Branch")}>
              {Object.entries(counts.branch).map(([b, n]) => <Check key={b} on={draft.branch.includes(b)} onClick={() => tog("branch", b)} label={b} count={n} />)}
            </FilterSection>
          )}
        </FilterMenu>
        {perms.can("bank", "export") && <ExportMenu items={[{ label: "CSV", href: "/finance/bank-accounts/export/csv/" }]} />}
        {canSetUp && <Primary label={t("New account")} onClick={() => openForm("/finance/bank-accounts/new/")} onPrefetch={() => openForm.prefetch("/finance/bank-accounts/new/")} />}
      </Toolbar>

      <TableCard cols={[null, 90, 110, 200, 130, 150, 56]}
        phone={accounts.length > 0 && <>
          {[...office, ...staff].map((a) => (
            <PRow key={a.kind + a.id} menu={<RowMenu label={t("Actions for {n}", { n: a.name })} items={menuFor(a)} />} href={txHref(a)} no={a.name} dim={!a.is_active}
              end={`${fmtN(a.native_balance)} ${a.currency}`} amountTone={a.native_balance < 0 ? "text-danger-text" : undefined}
              meta={[a.kind === "bank" ? t("Bank") : a.kind === "cash" ? t("Cash") : t("Staff"), a.branch_name,
                a.kind === "staff" ? null : a.last_reconciled ? t("reconciled {d}", { d: longDate(a.last_reconciled) }) : t("never reconciled")].filter(Boolean).join(" · ")}
              note={a.currency !== "SAR" && !a.ledger_shared ? `${fmtN(a.book_balance)} SAR` : null} />
          ))}
          <PTotal label={(() => { const n = accounts.filter((a) => a.is_active).length; return t(n === 1 ? "Total, 1 account" : "Total, {n} accounts", { n }); })()}>{fmtN(sarTotal)} SAR</PTotal>
        </>}
        empty={!accounts.length && <Empty title={t("No accounts")} sub={t("Nothing matches this search and these filters.")} />}>
        <thead><Tr>
          <Th>{t("Account")}</Th><Th>{t("Type")}</Th><Th>{t("Branch")}</Th>
          <Th className="text-right">{t("Book balance")}</Th><Th className="text-right">{t("SAR value")}</Th><Th>{t("Last reconciled")}</Th><Th className="text-center">{t("Action")}</Th>
        </Tr></thead>
        <tbody>
          {bands.map((b) => {
            const live = b.rows.filter((a) => a.is_active);
            const sum = live.reduce((s, a) => s + (a.native_balance || 0), 0);
            const sar = live.filter((a) => !a.ledger_shared).reduce((s, a) => s + (a.book_balance || 0), 0);
            return [
              <Tr key={"band-" + b.cur} row="band">
                <Td colSpan={3}>{t(b.rows.length === 1 ? "{c}, 1 account" : "{c}, {n} accounts", { c: t(CUR_NAME[b.cur] || b.cur), n: b.rows.length })}</Td>
                <Td className="text-right"><Amt code={b.cur} value={sum} /></Td>
                <Td className="text-right text-muted-foreground">{fmtN(sar)}</Td>
                <Td colSpan={2} />
              </Tr>,
              ...b.rows.map((a) => (
                <Tr key={a.kind + a.id} row={a.is_active ? undefined : "dim"} {...rowNav(txHref(a))}>
                  <Td className="truncate"><span className="font-medium">{a.name}</span>{a.account_identifier && <span className="mt-0.5 block overflow-hidden text-ellipsis text-[12px] font-normal text-muted-foreground" style={{ fontFamily: "var(--font-mono)" }}>{a.account_identifier}</span>}</Td>
                  <Td>{a.kind === "bank" ? t("Bank") : t("Cash")}</Td>
                  <Td>{a.branch_name}</Td>
                  <Td className={"text-right" + (a.native_balance < 0 ? " font-medium text-danger-text" : "")}><Amt code={a.currency} value={a.native_balance} /></Td>
                  <Td className="text-right text-muted-foreground">{a.ledger_shared ? <span title={t("Several accounts post to this ledger account")}>{t("shared ledger")}</span> : fmtN(a.book_balance)}</Td>
                  <Td>{a.last_reconciled ? longDate(a.last_reconciled) : <span className="text-muted-foreground">{t("Never")}</span>}{!a.is_active && <span className="mt-0.5 block overflow-hidden text-ellipsis text-[12px] font-normal text-muted-foreground"><Pill tone="gray" sm>{t("Inactive")}</Pill></span>}</Td>
                  <Td className="text-center">
                    <RowMenu label={t("Actions for {n}", { n: a.name })} items={menuFor(a)} />
                  </Td>
                </Tr>
              )),
            ];
          })}
          {staff.length > 0 && [
            <Tr key="band-staff" row="band">
              <Td colSpan={3}>{t(staff.length === 1 ? "Held by staff, 1 person" : "Held by staff, {n} people", { n: staff.length })}</Td>
              <Td className="text-right">{[...new Set(staff.map((a) => a.currency))].map((c) => (
                <Amt key={c} code={c} value={staff.filter((a) => a.currency === c).reduce((s, a) => s + a.native_balance, 0)} />
              ))}</Td>
              <Td className="text-right text-muted-foreground">{fmtN(staff.reduce((s, a) => s + (a.book_balance || 0), 0))}</Td>
              <Td colSpan={2} />
            </Tr>,
            ...staff.map((a) => {
              const days = a.given_on ? Math.max(0, Math.round((Date.now() - new Date(a.given_on)) / 86400000)) : null;
              const stale = days != null && days > 30 && !a.spent_since && a.native_balance > 0;
              return (
                <Tr key={"staff" + a.id} {...rowNav(txHref(a))}>
                  <Td className="truncate"><span className="font-medium">{a.name}</span></Td>
                  <Td>{t("Staff")}</Td>
                  <Td>{a.branch_name}</Td>
                  <Td className={"text-right" + (a.native_balance < 0 ? " font-medium text-danger-text" : "")}>
                    <Amt code={a.currency} value={a.native_balance} />
                    {a.native_balance < 0 ? <span className="mt-0.5 block overflow-hidden text-ellipsis text-[12px] font-normal text-muted-foreground">{t("owed to them")}</span> : null}
                  </Td>
                  <Td className="text-right text-muted-foreground">{fmtN(a.book_balance)}</Td>
                  <Td>
                    {a.given_on ? <span className={cn(stale ? "font-medium text-danger-text" : undefined)}>{t("Given {d}", { d: longDate(a.given_on) })}</span> : <span className="text-muted-foreground">{t("Not given yet")}</span>}
                    {days != null ? <span className="mt-0.5 block overflow-hidden text-ellipsis text-[12px] font-normal text-muted-foreground">{t(days === 1 ? "Held 1 day" : "Held {n} days", { n: days })}{a.spent_since ? "" : `, ${t("no expense yet")}`}</span> : null}
                  </Td>
                  <Td className="text-center">
                    <RowMenu label={t("Actions for {n}", { n: a.name })} items={menuFor(a)} />
                  </Td>
                </Tr>
              );
            }),
          ]}
        </tbody>
        {accounts.length > 0 && (
          <tfoot><Tr>
            <Td colSpan={4}>{(() => { const n = accounts.filter((a) => a.is_active).length; return t(n === 1 ? "Total, 1 account" : "Total, {n} accounts", { n }); })()}</Td>
            <Td className="text-right">{fmtN(sarTotal)}</Td>
            <Td colSpan={2} label>{t("SAR value at the book rate")}</Td>
          </Tr></tfoot>
        )}
      </TableCard>
    </ListPage>
  );
}
