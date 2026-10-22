import { useState } from "react";
import { Link, router } from "@inertiajs/react";
import {
  ListPage, Kpis, Kpi, Toolbar, SearchTool, FilterMenu, FilterSection, Check,
  TableCard, RowMenu, Pager, Empty, LIcon, fmtN, useListNav, rowNav,
} from "../../components/shadcn/list-a.jsx";
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

      <Toolbar spaced left={<span className="la-note">{t("Balances as of {d}, in SAR", { d: longDate(as_of) })}</span>}>
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
        <Link className="la-tool" href="/finance/ar-aging/">{t("AR Aging")}</Link>
      </Toolbar>

      <TableCard cols={[null, 130, 130, 160, 160, 56]}
        empty={!clients.length && <Empty title={t("No clients")} sub={t("Nothing matches this search and filter.")} />}>
        <thead><tr>
          <th>{t("Client")}</th><th className="n">{t("Debit")}</th><th className="n">{t("Credit")}</th>
          <th className="n"><span className="srt">{t("Balance")}{LIcon.sortDown}</span></th><th className="n">{t("Customer deposit")}</th><th className="c">{t("Action")}</th>
        </tr></thead>
        <tbody>
          {clients.map((c) => (
            <tr key={c.client_id} {...rowNav(statement(c))}>
              <td className="ell strong">{c.name}</td>
              <td className="n">{fmtN(c.ar_debit)}</td>
              <td className="n">{fmtN(c.ar_credit)}</td>
              <td className="n">
                {c.piutang ? <span>{fmtN(Math.abs(c.piutang))} {c.piutang > 0 ? "Dr" : "Cr"}</span> : <span className="zero">0</span>}
                {c.overdue > 0 && <span className="sub warnt">{t("{v} overdue", { v: fmtN(c.overdue) })}</span>}
              </td>
              <td className="n">
                {c.saldo_dana ? <span>{fmtN(c.saldo_dana)} Cr</span> : <span className="zero">0</span>}
                {c.offset > 0 && <span className="sub"><span className="la-pill gray sm" style={{ color: "var(--foreground)" }}>{t("Offset {v}", { v: fmtN(c.offset) })}</span></span>}
              </td>
              <td className="c">
                <RowMenu label={t("Actions for {n}", { n: c.name })} items={[
                  { label: t("Open statement"), onClick: () => router.visit(statement(c)) },
                  { label: t("Statement PDF"), href: `/finance/clients/${c.client_id}/statement/pdf/`, external: true },
                  { label: t("Reservation statement PDF"), href: `/finance/clients/${c.client_id}/statement/pdf/?mode=byres`, external: true },
                  c.offset > 0 && { label: t("Apply deposit against AR"), onClick: () => router.visit(statement(c)) },
                ]} />
              </td>
            </tr>
          ))}
        </tbody>
        {clients.length > 0 && (
          <tfoot><tr>
            <td>{t("All {n} clients", { n: p?.count ?? clients.length })}</td>
            <td className="n">{fmtN(totals.ar_debit)}</td>
            <td className="n">{fmtN(totals.ar_credit)}</td>
            <td className="n">{fmtN(Math.abs(totals.piutang))} {totals.piutang >= 0 ? "Dr" : "Cr"}</td>
            <td className="n">{fmtN(totals.saldo_dana)} Cr</td>
            <td />
          </tr></tfoot>
        )}
      </TableCard>

      <Pager p={p} perPage={f.per} onPage={(page) => go({ page })} onPerPage={(per) => go({ per })}
        summary={p && p.count ? t("Showing {a} to {b} of {n} clients", { a: p.start_index, b: p.end_index, n: p.count }) : null} />
    </ListPage>
  );
}
