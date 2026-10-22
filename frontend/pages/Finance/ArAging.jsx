import { useState } from "react";
import { Link } from "@inertiajs/react";
import { ListPage, Toolbar, Kpis, Kpi, ExportMenu, TableCard, Section, Empty, fmtN, dLong, useListNav, rowNav, Tr, Th, Td, Note, ToolButton, toolInput, ToolbarRight } from "../../components/shadcn/list-a.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

const BUCKETS = [
  ["current", "Not yet due"],
  ["1_30", "1–30 days"],
  ["31_60", "31–60 days"],
  ["61_90", "61–90 days"],
  ["90_plus", "> 90 days"],
];
const LATE = ["31_60", "61_90", "90_plus"];

// AR Aging: what every client still owes, grouped by how far past the due
// date it is, as of a chosen day. Click a client for its open invoices.
export default function ArAging({ aging }) {
  const { t } = useI18n();
  const perms = usePerms();
  const [go, loading] = useListNav("/finance/ar-aging/", { as_of: aging.as_of });
  const [picked, setPicked] = useState(null);
  const client = picked && aging.clients.find((c) => c.client_id === picked);

  const amount = (v, late) => (v ? <span className={late ? "late" : undefined}>{fmtN(v)}</span> : <span className="mut">–</span>);
  const late = LATE.reduce((s, k) => s + aging.buckets[k], 0);
  const overdue = aging.total - aging.buckets.current;

  return (
    <ListPage title={t("AR Aging")} loading={loading}>
      <Kpis>
        <Kpi label={t("Total receivable")} value={fmtN(aging.total)} unit="SAR" foot={t("{n} clients owe", { n: aging.clients.length })} />
        <Kpi label={t("Overdue")} value={fmtN(overdue)} unit="SAR" tone={overdue > 0 ? "warn" : undefined} foot={t("past the due date")} />
        <Kpi label={t("Over 30 days late")} value={fmtN(late)} unit="SAR" tone={late > 0 ? "warn" : undefined} foot={t("needs follow-up")} />
      </Kpis>

      <Toolbar left={<Note>{t("What every client still owes, by days past the due date")}</Note>}>
        <ToolButton as="label" className="cursor-text gap-2 text-muted-foreground">{t("As of")}
          <input className={toolInput} type="date" value={aging.as_of} onChange={(e) => e.target.value && go({ as_of: e.target.value })} aria-label={t("As of")} />
        </ToolButton>
        {perms.can("statements", "export") && <ExportMenu items={[{ label: "CSV", href: `/finance/ar-aging/export/csv/?as_of=${aging.as_of}` }]} />}
      </Toolbar>

      <TableCard cols={[null, 120, 120, 120, 120, 120, 140]}
        empty={!aging.clients.length && <Empty title={t("Nothing owed")} sub={t("No client has an open balance on {d}.", { d: dLong(aging.as_of) })} />}>
        <thead><Tr>
          <Th>{t("Client")}</Th>
          {BUCKETS.map(([k, label]) => <Th key={k} className="text-right">{t(label)}</Th>)}
          <Th className="text-right">{t("Total (SAR)")}</Th>
        </Tr></thead>
        <tbody>
          {aging.clients.map((c) => (
            <Tr key={c.client_id} row={c.client_id === picked ? "on" : undefined} onClick={() => setPicked(c.client_id === picked ? null : c.client_id)}>
              <Td className="truncate font-medium">{c.name}</Td>
              {BUCKETS.map(([k]) => <Td key={k} className="text-right">{amount(c.buckets[k], LATE.includes(k))}</Td>)}
              <Td className="text-right"><b>{fmtN(c.total)}</b></Td>
            </Tr>
          ))}
        </tbody>
        {aging.clients.length > 0 && (
          <tfoot><Tr>
            <Td>{t("Total")}</Td>
            {BUCKETS.map(([k]) => <Td key={k} className="text-right">{fmtN(aging.buckets[k])}</Td>)}
            <Td className="text-right">{fmtN(aging.total)}</Td>
          </Tr></tfoot>
        )}
      </TableCard>

      {client && (
        <>
          <Section title={client.name} sub={t("Open invoices as of {d}", { d: dLong(aging.as_of) })}>
            <ToolbarRight>
              <ToolButton as={Link} href={`/finance/clients/${client.client_id}/statement/`}>{t("Statement")}</ToolButton>
              <ToolButton onClick={() => setPicked(null)}>{t("Close")}</ToolButton>
            </ToolbarRight>
          </Section>
          <TableCard cols={[null, 140, 140, 160]}
            empty={!client.invoices.length && <Empty title={t("No invoice on record")} />}>
            <thead><Tr>
              <Th>{t("Invoice")}</Th><Th>{t("Due date")}</Th><Th className="text-right">{t("Days overdue")}</Th><Th className="text-right">{t("Remaining (SAR)")}</Th>
            </Tr></thead>
            <tbody>
              {client.invoices.map((i) => (
                <Tr key={i.id} {...rowNav(`/invoice/${i.id}/`)}>
                  <Td><span className="font-mono text-[13px] font-semibold">{i.invoice_number}</span></Td>
                  <Td>{i.due_date ? dLong(i.due_date) : "–"}</Td>
                  <Td className={"text-right" + (LATE.includes(i.bucket) ? " font-medium text-danger-text" : "")}>{i.days_overdue || <span className="text-muted-foreground">{t("Not yet due")}</span>}</Td>
                  <Td className="text-right">{amount(i.amount, LATE.includes(i.bucket))}</Td>
                </Tr>
              ))}
            </tbody>
          </TableCard>
        </>
      )}
    </ListPage>
  );
}
