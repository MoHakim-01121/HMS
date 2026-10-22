import { useState } from "react";
import { router } from "@inertiajs/react";
import { Popover, PopoverContent, PopoverTrigger } from "../../components/shadcn/ui/popover.jsx";
import {
  ListPage, Toolbar, MonthNav, SearchTool, FilterMenu, FilterSection, Check, ExportMenu,
  TableCard, RowMenu, Pill, Pager, Empty, LIcon, MONTHS, fmtN, dShort, useListNav, rowNav,
} from "../../components/shadcn/list-a.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

// A credit note is issued against an invoice: pick the invoice first.
function NewCreditNote({ invoices }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const list = invoices.filter((i) => !q || `${i.number} ${i.client}`.toLowerCase().includes(q.toLowerCase())).slice(0, 40);
  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); setQ(""); }}>
      <PopoverTrigger asChild><button type="button" className="la-primary">{LIcon.plus}{t("New credit note")}</button></PopoverTrigger>
      <PopoverContent align="end" sideOffset={8} className="la-menu" style={{ width: 320, padding: 6 }}>
        <label className="la-tool la-search" style={{ width: "100%", marginBottom: 4 }}>{LIcon.search}
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Which invoice? Search number or client")} />
        </label>
        <div role="menu" style={{ maxHeight: 280, overflowY: "auto" }}>
          {list.map((i) => (
            <button type="button" key={i.id} role="menuitem" className="la-mi" onClick={() => router.visit(`/finance/invoices/${i.id}/credit-notes/new/`)}>
              <span><span style={{ fontFamily: "var(--font-mono)", fontWeight: 600, fontSize: 13 }}>{i.number}</span><span className="h">{i.client}</span></span>
            </button>
          ))}
          {!list.length && <div className="la-mi" style={{ cursor: "default", color: "var(--muted-foreground)" }}>{t("No invoice matches.")}</div>}
        </div>
      </PopoverContent>
    </Popover>
  );
}

// Credit Notes, as on the Record View HMS canvas: no KPIs; the month's credit
// notes with the month total under the table.
export default function CreditNotes({ credit_notes = [], filters: f, years = [], counts = {}, summary, invoice_choices = [], pagination }) {
  const { t } = useI18n();
  const perms = usePerms();
  const [go, loading] = useListNav("/finance/credit-notes/", f);
  const [draft, setDraft] = useState(f);
  const tog = (v) => setDraft((d) => ({ ...d, applied: d.applied.includes(v) ? d.applied.filter((x) => x !== v) : [...d.applied, v] }));
  const filterCount = (f.applied.length ? 1 : 0) + (f.voided ? 1 : 0);
  const period = f.month ? t(MONTHS[+f.month.slice(5, 7) - 1]) : f.year && f.year !== "all" ? f.year : t("All dates");

  return (
    <ListPage title={t("Credit Notes")} loading={loading}>
      <Toolbar left={<MonthNav month={f.month} year={f.year} years={years} onChange={(p) => go(p)} />}>
        <SearchTool value={f.q} onSearch={(q) => go({ q })} placeholder={t("Search credit note, client, invoice")} />
        <FilterMenu count={filterCount} onOpen={() => setDraft(f)}
          onReset={() => setDraft({ ...draft, applied: [], voided: "" })}
          onApply={() => go({ applied: draft.applied, voided: draft.voided })}>
          <FilterSection label={t("Credit applied to")}>
            <Check on={draft.applied.includes("ar")} onClick={() => tog("ar")} label={t("Accounts receivable")} count={counts.ar} />
            <Check on={draft.applied.includes("deposit")} onClick={() => tog("deposit")} label={t("Customer deposit")} count={counts.deposit} />
          </FilterSection>
          <FilterSection>
            <Check on={!!draft.voided} onClick={() => setDraft({ ...draft, voided: draft.voided ? "" : "1" })} label={t("Show voided")} count={counts.voided} />
          </FilterSection>
        </FilterMenu>
        {perms.can("invoice", "export") && <ExportMenu items={[{ label: "CSV", href: "/finance/credit-notes/export/csv/" }]} />}
        {perms.can("invoice", "create") && <NewCreditNote invoices={invoice_choices} />}
      </Toolbar>

      <TableCard cols={[100, 80, null, 100, null, 130, 96, 56]}
        empty={!credit_notes.length && <Empty title={t("No credit notes")} sub={t("None were issued in this period.")} />}>
        <thead><tr>
          <th>{t("Credit note")}</th><th><span className="srt">{t("Date")}{LIcon.sortDown}</span></th><th>{t("Client")}</th><th>{t("Invoice")}</th>
          <th>{t("Reason")}</th><th className="n">{t("Amount (SAR)")}</th><th>{t("Status")}</th><th className="c">{t("Action")}</th>
        </tr></thead>
        <tbody>
          {credit_notes.map((cn) => {
            const dead = cn.status === "voided";
            return (
              <tr key={cn.id} className={dead ? "dim" : ""} {...rowNav(cn.invoice_url)}>
                <td><span className="mono">{cn.number}</span></td>
                <td>{dShort(cn.date)}</td>
                <td className="ell strong">{cn.client}</td>
                <td><span className="mono">{cn.invoice_number}</span></td>
                <td className="ell" title={cn.reason}>{cn.reason}</td>
                <td className="n">{fmtN(cn.amount_sar)}{cn.to_deposit_sar > 0 && <span className="sub">{t("{v} to deposit", { v: fmtN(cn.to_deposit_sar) })}</span>}</td>
                <td><Pill tone={dead ? "gray" : "green"}>{dead ? t("Voided") : t("Active")}</Pill></td>
                <td className="c">
                  <RowMenu label={t("Actions for {n}", { n: cn.number })} items={[
                    { label: t("Download PDF"), href: `/finance/credit-notes/${cn.id}/pdf/`, external: true },
                    !dead && perms.can("payments", "approve") && { label: t("Void credit note"), danger: true, onClick: () => router.visit(`/finance/credit-notes/${cn.id}/void/`) },
                  ]} />
                </td>
              </tr>
            );
          })}
        </tbody>
        {summary && credit_notes.length > 0 && (
          <tfoot><tr>
            <td colSpan={5}>{t("{p}, {n} credit notes", { p: period, n: summary.count })}</td>
            <td className="n">{fmtN(summary.amount)}{summary.to_deposit > 0 && <span className="sub">{t("{v} to deposit", { v: fmtN(summary.to_deposit) })}</span>}</td>
            <td colSpan={2} className="lbl">{t("Voided not counted")}</td>
          </tr></tfoot>
        )}
      </TableCard>

      <Pager p={pagination} perPage={f.per} onPage={(page) => go({ page })} onPerPage={(per) => go({ per })} />
    </ListPage>
  );
}
