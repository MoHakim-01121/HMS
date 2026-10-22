import { useState } from "react";
import { router } from "@inertiajs/react";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { ListPage, Toolbar, MonthNav, SearchTool, FilterMenu, FilterSection, Check, ExportMenu, Primary, TableCard, RowMenu, Pill, Pager, Empty, LIcon, MONTHS, fmtN, dShort, useListNav, Tr, Th, Td } from "../../components/shadcn/list-a.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

// Rate the way people read it: the bigger currency per one of the smaller
// (4,110 IDR per SAR), not 0.000243.
const rateOf = (ex) => {
  if (ex.from_currency === ex.to_currency) return null;
  const r = ex.amount_out / ex.amount_in;
  return r >= 1 ? { v: r, per: `${ex.from_currency} per ${ex.to_currency}` } : { v: 1 / r, per: `${ex.to_currency} per ${ex.from_currency}` };
};

// Transfer and Exchange, as on the Record View HMS canvas: no KPIs; the
// month's transfers and exchanges, with a summary under the table.
export default function Exchanges({ exchanges = [], filters: f, years = [], counts = {}, account_counts = [], summary, pagination }) {
  const { t } = useI18n();
  const perms = usePerms();
  const openForm = useFormModal();
  const [confirm, confirmDialog] = useConfirm();
  const [go, loading] = useListNav("/finance/exchanges/", f);
  const [draft, setDraft] = useState(f);
  const tog = (key, v) => setDraft((d) => ({ ...d, [key]: d[key].includes(v) ? d[key].filter((x) => x !== v) : [...d[key], v] }));
  const filterCount = (f.type.length ? 1 : 0) + (f.acct.length ? 1 : 0) + (f.voided ? 1 : 0);
  const period = f.month ? t(MONTHS[+f.month.slice(5, 7) - 1]) : f.year && f.year !== "all" ? f.year : t("All dates");

  const voidEx = (ex) => confirm({
    title: t("Void transfer"),
    message: t("Void {number}? Both cash-book rows stop counting; the record stays for audit.", { number: ex.exchange_number }),
    confirmLabel: t("Void"),
    onConfirm: () => router.post(`/finance/exchanges/${ex.id}/void/`),
  });

  return (
    <ListPage title={t("Transfer and Exchange")} loading={loading}>
      <Toolbar left={<MonthNav month={f.month} year={f.year} years={years} onChange={(p) => go(p)} />}>
        <SearchTool value={f.q} onSearch={(q) => go({ q })} placeholder={t("Search number, account, reference")} />
        <FilterMenu count={filterCount} onOpen={() => setDraft(f)}
          onReset={() => setDraft({ ...draft, type: [], acct: [], voided: "" })}
          onApply={() => go({ type: draft.type, acct: draft.acct, voided: draft.voided })}>
          <FilterSection label={t("Type")}>
            <Check on={draft.type.includes("transfer")} onClick={() => tog("type", "transfer")} label={t("Transfer, same currency")} count={counts.transfer} />
            <Check on={draft.type.includes("exchange")} onClick={() => tog("type", "exchange")} label={t("Exchange")} count={counts.exchange} />
          </FilterSection>
          {account_counts.length > 1 && (
            <FilterSection label={t("Account")}>
              {account_counts.map((a) => <Check key={a.name} on={draft.acct.includes(a.name)} onClick={() => tog("acct", a.name)} label={a.name} count={a.count} />)}
            </FilterSection>
          )}
          <FilterSection>
            <Check on={!!draft.voided} onClick={() => setDraft({ ...draft, voided: draft.voided ? "" : "1" })} label={t("Show voided")} count={counts.voided} />
          </FilterSection>
        </FilterMenu>
        {perms.can("bank", "export") && <ExportMenu items={[{ label: "CSV", href: "/finance/exchanges/export/csv/" }]} />}
        {perms.can("bank", "create") && <Primary label={t("New transfer")} onClick={() => openForm("/finance/exchanges/new/")} onPrefetch={() => openForm.prefetch("/finance/exchanges/new/")} />}
      </Toolbar>

      <TableCard cols={[100, 80, 104, null, null, 150, 96, 56]}
        empty={!exchanges.length && <Empty title={t("No transfers")} sub={t("Nothing moved between accounts in this period.")} />}>
        <thead><Tr>
          <Th>{t("Number")}</Th>
          <Th><button type="button" className="inline-flex items-center gap-1 font-semibold text-foreground" style={{ border: 0, background: "none", padding: 0, font: "inherit", cursor: "pointer" }}
            onClick={() => go({ sort: f.sort === "date" ? "-date" : "date" })}>{t("Date")}{f.sort === "date" ? LIcon.sortUp : LIcon.sortDown}</button></Th>
          <Th>{t("Type")}</Th><Th>{t("From")}</Th><Th>{t("To")}</Th><Th className="text-right">{t("Rate")}</Th><Th>{t("Status")}</Th><Th className="text-center">{t("Action")}</Th>
        </Tr></thead>
        <tbody>
          {exchanges.map((ex) => {
            const r = rateOf(ex);
            const dead = ex.status === "voided";
            return (
              <Tr key={ex.id} row={dead ? "dim" : undefined} style={{ cursor: "default" }}>
                <Td><span className="font-mono text-[13px] font-semibold">{ex.exchange_number}</span></Td>
                <Td>{dShort(ex.exchange_date)}</Td>
                <Td>{r ? t("Exchange") : t("Transfer")}</Td>
                <Td className="truncate">{ex.from_label}<span className="mt-0.5 block overflow-hidden text-ellipsis text-[12px] font-normal text-muted-foreground">{fmtN(ex.amount_out)} {ex.from_currency}</span></Td>
                <Td className="truncate">{ex.to_label}<span className="mt-0.5 block overflow-hidden text-ellipsis text-[12px] font-normal text-muted-foreground">{fmtN(ex.amount_in)} {ex.to_currency}</span></Td>
                <Td className="text-right">{r ? <>{fmtN(r.v)}<span className="mt-0.5 block overflow-hidden text-ellipsis text-[12px] font-normal text-muted-foreground">{r.per}</span></> : <span className="text-muted-foreground">{t("Same currency")}</span>}</Td>
                <Td><Pill tone={dead ? "gray" : "green"}>{dead ? t("Voided") : t("Active")}</Pill></Td>
                <Td className="text-center">
                  <RowMenu label={t("Actions for {n}", { n: ex.exchange_number })} items={[
                    ex.proof_url && { label: t("View proof"), href: ex.proof_url, external: true },
                    !dead && perms.can("bank", "delete") && { label: t("Void transfer"), danger: true, onClick: () => voidEx(ex) },
                  ]} />
                </Td>
              </Tr>
            );
          })}
        </tbody>
        {summary && exchanges.length > 0 && (
          <tfoot><Tr><Td colSpan={8} style={{ fontWeight: 400, whiteSpace: "normal" }}>
            <b>{period}:</b>{" "}
            {t("{a} transfers and {b} exchanges.", { a: summary.transfers, b: summary.exchanges })}{" "}
            {summary.sar_in > 0 && t("{idr} IDR exchanged to {sar} SAR at an average rate of {r}.", { idr: fmtN(summary.idr_out), sar: fmtN(summary.sar_in), r: fmtN(summary.avg_rate) })}{" "}
            <span className="text-muted-foreground">{t("Voided entries are not counted.")}</span>
          </Td></Tr></tfoot>
        )}
      </TableCard>

      <Pager p={pagination} perPage={f.per} onPage={(page) => go({ page })} onPerPage={(per) => go({ per })} />
      {confirmDialog}
    </ListPage>
  );
}
