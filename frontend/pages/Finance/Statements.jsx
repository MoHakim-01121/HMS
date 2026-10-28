import { useState } from "react";
import { Link, router } from "@inertiajs/react";
import { ListPage, Kpis, Kpi, Toolbar, SearchTool, FilterMenu, FilterSection, Check, TableCard, PRow, PTotal, RowMenu, Pager, Empty, LIcon, fmtN, useListNav, rowNav, Tr, Th, Td, Note, ToolButton, Pill } from "../../components/shadcn/list-a.jsx";
import { useI18n } from "../../utils/i18n.jsx";

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const longDate = (iso) => { const [y, m, d] = iso.split("-"); return `${d} ${MON[+m - 1]} ${y}`; };

// Client Ledger, as on the Record View HMS canvas: receivables, what is
// overdue, customer deposits and what can be offset (the last three filter
// the table); one row per client with its receivable and deposit, in SAR.
export default function Statements({ clients = [], totals = {}, kpis, counts = {}, as_of, filters: f, pagination }) {
  const { t } = useI18n();
  const [go, loading] = useListNav("/finance/statements/", f);
  const [draft, setDraft] = useState(f);
  const pick = (k) => go({ show: f.show === k ? "" : k });
  const statement = (c) => `/finance/clients/${c.client_id}/statement/`;
  const p = pagination;

  // The row's actions: the desktop row menu, and the same menu on a phone row.
  const menuFor = (c) => [
    { label: t("Open statement"), onClick: () => router.visit(statement(c)) },
    { label: t("Statement PDF"), href: `/finance/clients/${c.client_id}/statement/pdf/`, external: true },
    { label: t("Reservation statement PDF"), href: `/finance/clients/${c.client_id}/statement/pdf/?mode=byres`, external: true },
    c.offset > 0 && { label: t("Apply deposit against AR"), onClick: () => router.visit(statement(c)) },
  ];
  return (
    <ListPage title={t("Client Ledger")} loading={loading}>
      {kpis && (
        <Kpis>
          <Kpi label={t("Accounts receivable")} value={fmtN(kpis.ar)} unit="SAR"
            foot={t("{n} clients with an open balance", { n: kpis.ar_clients })} />
          <Kpi label={t("Overdue receivables")} value={fmtN(kpis.overdue)} unit="SAR" tone={kpis.overdue ? "warn" : undefined}
            foot={kpis.overdue_clients ? t("{n} clients, oldest {d} days overdue", { n: kpis.overdue_clients, d: kpis.oldest_days }) : t("Nothing is overdue")}
            on={f.show === "due"} onClick={() => pick("due")} />
          <Kpi label={t("Customer deposits")} value={fmtN(kpis.deposits)} unit="SAR"
            foot={t("Liability to {n} clients", { n: kpis.deposit_clients })}
            on={f.show === "dep"} onClick={() => pick("dep")} />
          <Kpi label={t("Available for offset")} value={fmtN(kpis.offset)} unit="SAR"
            foot={t("{n} clients with both receivable and deposit", { n: kpis.offset_clients })}
            on={f.show === "off"} onClick={() => pick("off")} />
        </Kpis>
      )}

      <Toolbar spaced left={<Note>{t("Balances as of {d}, in SAR", { d: longDate(as_of) })}</Note>}>
        <SearchTool value={f.q} onSearch={(q) => go({ q })} placeholder={t("Search client")} />
        <FilterMenu count={f.show ? 1 : 0} onOpen={() => setDraft(f)}
          onReset={() => setDraft({ ...draft, show: "", sort: "receivable" })}
          onApply={() => go({ show: draft.show, sort: draft.sort })}>
          <FilterSection label={t("Show")}>
            {[["", "All clients", "all"], ["owe", "Open balance", "owe"], ["due", "Overdue", "due"], ["dep", "With customer deposit", "dep"], ["off", "Available for offset", "off"]].map(([k, l, c]) => (
              <Check key={k || "all"} radio on={draft.show === k} onClick={() => setDraft({ ...draft, show: k })} label={t(l)} count={counts[c]} />
            ))}
          </FilterSection>
          <FilterSection label={t("Sort by")}>
            {[["receivable", "Debit balance, largest first"], ["deposit", "Customer deposit, largest first"], ["name", "Client name"]].map(([k, l]) => (
              <Check key={k} radio on={draft.sort === k} onClick={() => setDraft({ ...draft, sort: k })} label={t(l)} />
            ))}
          </FilterSection>
        </FilterMenu>
        <ToolButton as={Link} href="/finance/ar-aging/">{t("AR Aging")}</ToolButton>
      </Toolbar>

      <TableCard cols={[null, 130, 130, 160, 160, 56]}
        phone={clients.length > 0 && <>
          {clients.map((c) => (
            <PRow key={c.client_id} menu={<RowMenu label={t("Actions for {n}", { n: c.name })} items={menuFor(c)} />} href={statement(c)} no={c.name}
              end={c.piutang ? `${fmtN(Math.abs(c.piutang))} ${c.piutang > 0 ? "Dr" : "Cr"}` : "0"}
              meta={t("Debit {d} · Credit {c}", { d: fmtN(c.ar_debit), c: fmtN(c.ar_credit) })}
              note={c.overdue > 0 ? t("{v} overdue", { v: fmtN(c.overdue) }) : c.saldo_dana ? `${t("Deposit")} ${fmtN(c.saldo_dana)}` : null}
              noteTone={c.overdue > 0 ? "text-warning-text" : undefined} />
          ))}
          <PTotal label={t("All {n} clients", { n: p?.count ?? clients.length })}>{fmtN(Math.abs(totals.piutang))} {totals.piutang >= 0 ? "Dr" : "Cr"}</PTotal>
        </>}
        empty={!clients.length && <Empty title={t("No clients")} sub={t("Nothing matches this search and filter.")} />}>
        <thead><Tr>
          <Th>{t("Client")}</Th><Th className="text-right">{t("Debit")}</Th><Th className="text-right">{t("Credit")}</Th>
          <Th className="text-right"><span className="inline-flex items-center gap-1 font-semibold text-foreground">{t("Balance")}{LIcon.sortDown}</span></Th><Th className="text-right">{t("Customer deposit")}</Th><Th className="text-center">{t("Action")}</Th>
        </Tr></thead>
        <tbody>
          {clients.map((c) => (
            <Tr key={c.client_id} {...rowNav(statement(c))}>
              <Td className="truncate font-medium">{c.name}</Td>
              <Td className="text-right">{fmtN(c.ar_debit)}</Td>
              <Td className="text-right">{fmtN(c.ar_credit)}</Td>
              <Td className="text-right">
                {c.piutang ? <span>{fmtN(Math.abs(c.piutang))} {c.piutang > 0 ? "Dr" : "Cr"}</span> : <span className="text-muted-foreground">0</span>}
                {c.overdue > 0 && <span className="mt-0.5 block overflow-hidden text-ellipsis text-[12px] font-normal text-warning-text">{t("{v} overdue", { v: fmtN(c.overdue) })}</span>}
              </Td>
              <Td className="text-right">
                {c.saldo_dana ? <span>{fmtN(c.saldo_dana)} Cr</span> : <span className="text-muted-foreground">0</span>}
                {c.offset > 0 && <span className="mt-0.5 block overflow-hidden text-ellipsis text-[12px] font-normal text-muted-foreground"><Pill tone="gray" sm className="text-foreground">{t("Offset {v}", { v: fmtN(c.offset) })}</Pill></span>}
              </Td>
              <Td className="text-center">
                <RowMenu label={t("Actions for {n}", { n: c.name })} items={menuFor(c)} />
              </Td>
            </Tr>
          ))}
        </tbody>
        {clients.length > 0 && (
          <tfoot><Tr>
            <Td>{t("All {n} clients", { n: p?.count ?? clients.length })}</Td>
            <Td className="text-right">{fmtN(totals.ar_debit)}</Td>
            <Td className="text-right">{fmtN(totals.ar_credit)}</Td>
            <Td className="text-right">{fmtN(Math.abs(totals.piutang))} {totals.piutang >= 0 ? "Dr" : "Cr"}</Td>
            <Td className="text-right">{fmtN(totals.saldo_dana)} Cr</Td>
            <Td />
          </Tr></tfoot>
        )}
      </TableCard>

      <Pager p={p} perPage={f.per} onPage={(page) => go({ page })} onPerPage={(per) => go({ per })}
        summary={p && p.count ? t("Showing {a} to {b} of {n} clients", { a: p.start_index, b: p.end_index, n: p.count }) : null} />
    </ListPage>
  );
}
