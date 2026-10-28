import { useState } from "react";
import { router } from "@inertiajs/react";
import { Popover, PopoverTrigger } from "../../components/shadcn/ui/popover.jsx";
import { ListPage, Toolbar, MonthNav, SearchTool, FilterMenu, FilterSection, Check, ExportMenu, TableCard, PRow, RowMenu, Pill, Pager, Empty, LIcon, MONTHS, fmtN, dShort, useListNav, rowNav, Tr, Th, Td, primaryClass, Menu, MenuItem, MenuHint, ToolButton, toolInput } from "../../components/shadcn/list-a.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { cn } from "@/lib/utils";
import { focusOnOpen } from "../../utils/device.js";

// A credit note is issued against an invoice: pick the invoice first.
function NewCreditNote({ invoices }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const list = invoices.filter((i) => !q || `${i.number} ${i.client}`.toLowerCase().includes(q.toLowerCase())).slice(0, 40);
  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); setQ(""); }}>
      <PopoverTrigger asChild><button type="button" className={primaryClass}>{LIcon.plus}{t("New credit note")}</button></PopoverTrigger>
      <Menu role={null} align="end" sideOffset={8} className="w-[320px] p-1.5">
        <ToolButton as="label" className="mb-1 w-full cursor-text focus-within:border-foreground">{LIcon.search}
          <input className={cn(toolInput, "flex-1")} autoFocus={focusOnOpen()} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Which invoice? Search number or client")} />
        </ToolButton>
        <div role="menu" className="max-h-[280px] overflow-y-auto">
          {list.map((i) => (
            <MenuItem key={i.id} onClick={() => router.visit(`/finance/invoices/${i.id}/credit-notes/new/`)}>
              <span><span className="font-mono text-[13px] font-semibold">{i.number}</span><MenuHint>{i.client}</MenuHint></span>
            </MenuItem>
          ))}
          {!list.length && <MenuItem as="div" role={undefined} className="cursor-default text-muted-foreground">{t("No invoice matches.")}</MenuItem>}
        </div>
      </Menu>
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

  // The row's actions: the desktop row menu, and the same menu on a phone row.
  const menuFor = (c) => {
    const dead = c.status === "voided";
    return [
      { label: t("Download PDF"), href: `/finance/credit-notes/${c.id}/pdf/`, external: true },
      !dead && perms.can("payments", "approve") && { label: t("Void credit note"), danger: true, onClick: () => router.visit(`/finance/credit-notes/${c.id}/void/`) },
    ];
  };
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
        phone={credit_notes.map((c) => (
          <PRow key={c.id} menu={<RowMenu label={t("Actions for {n}", { n: c.number })} items={menuFor(c)} />} href={c.invoice_url} mono no={c.number} dim={c.status === "voided"}
            tag={<Pill tone={c.status === "voided" ? "gray" : "green"} sm>{c.status === "voided" ? t("Voided") : t("Active")}</Pill>}
            title={c.client} amount={fmtN(c.amount_sar)} unit="SAR"
            meta={[dShort(c.date), c.invoice_number, c.reason].filter(Boolean).join(" · ")} />
        ))}
        empty={!credit_notes.length && <Empty title={t("No credit notes")} sub={t("None were issued in this period.")} />}>
        <thead><Tr>
          <Th>{t("Credit note")}</Th><Th><span className="inline-flex items-center gap-1 font-semibold text-foreground">{t("Date")}{LIcon.sortDown}</span></Th><Th>{t("Client")}</Th><Th>{t("Invoice")}</Th>
          <Th>{t("Reason")}</Th><Th className="text-right">{t("Amount (SAR)")}</Th><Th>{t("Status")}</Th><Th className="text-center">{t("Action")}</Th>
        </Tr></thead>
        <tbody>
          {credit_notes.map((cn) => {
            const dead = cn.status === "voided";
            return (
              <Tr key={cn.id} row={dead ? "dim" : undefined} {...rowNav(cn.invoice_url)}>
                <Td><span className="font-mono text-[13px] font-semibold">{cn.number}</span></Td>
                <Td>{dShort(cn.date)}</Td>
                <Td className="truncate font-medium">{cn.client}</Td>
                <Td><span className="font-mono text-[13px] font-semibold">{cn.invoice_number}</span></Td>
                <Td className="truncate" title={cn.reason}>{cn.reason}</Td>
                <Td className="text-right">{fmtN(cn.amount_sar)}{cn.to_deposit_sar > 0 && <span className="mt-0.5 block overflow-hidden text-ellipsis text-[12px] font-normal text-muted-foreground">{t("{v} to deposit", { v: fmtN(cn.to_deposit_sar) })}</span>}</Td>
                <Td><Pill tone={dead ? "gray" : "green"}>{dead ? t("Voided") : t("Active")}</Pill></Td>
                <Td className="text-center">
                  <RowMenu label={t("Actions for {n}", { n: cn.number })} items={menuFor(cn)} />
                </Td>
              </Tr>
            );
          })}
        </tbody>
        {summary && credit_notes.length > 0 && (
          <tfoot><Tr>
            <Td colSpan={5}>{t("{p}, {n} credit notes", { p: period, n: summary.count })}</Td>
            <Td className="text-right">{fmtN(summary.amount)}{summary.to_deposit > 0 && <span className="mt-0.5 block overflow-hidden text-ellipsis text-[12px] font-normal text-muted-foreground">{t("{v} to deposit", { v: fmtN(summary.to_deposit) })}</span>}</Td>
            <Td colSpan={2} label>{t("Voided not counted")}</Td>
          </Tr></tfoot>
        )}
      </TableCard>

      <Pager p={pagination} perPage={f.per} onPage={(page) => go({ page })} onPerPage={(per) => go({ per })} />
    </ListPage>
  );
}
