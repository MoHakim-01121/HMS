import { useState } from "react";
import { Link } from "@inertiajs/react";
import {
  ListPage, Toolbar, Kpis, Kpi, ExportMenu, TableCard, Section, Empty, fmtN, dLong, useListNav, rowNav,
} from "../../components/shadcn/list-a.jsx";
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

      <Toolbar left={<span className="la-note">{t("What every client still owes, by days past the due date")}</span>}>
        <label className="la-tool la-asof">{t("As of")}
          <input type="date" value={aging.as_of} onChange={(e) => e.target.value && go({ as_of: e.target.value })} aria-label={t("As of")} />
        </label>
        {perms.can("statements", "export") && <ExportMenu items={[{ label: "CSV", href: `/finance/ar-aging/export/csv/?as_of=${aging.as_of}` }]} />}
      </Toolbar>

      <TableCard cols={[null, 120, 120, 120, 120, 120, 140]}
        empty={!aging.clients.length && <Empty title={t("Nothing owed")} sub={t("No client has an open balance on {d}.", { d: dLong(aging.as_of) })} />}>
        <thead><tr>
          <th>{t("Client")}</th>
          {BUCKETS.map(([k, label]) => <th key={k} className="n">{t(label)}</th>)}
          <th className="n">{t("Total (SAR)")}</th>
        </tr></thead>
        <tbody>
          {aging.clients.map((c) => (
            <tr key={c.client_id} className={c.client_id === picked ? "on" : ""} onClick={() => setPicked(c.client_id === picked ? null : c.client_id)}>
              <td className="ell strong">{c.name}</td>
              {BUCKETS.map(([k]) => <td key={k} className="n">{amount(c.buckets[k], LATE.includes(k))}</td>)}
              <td className="n"><b>{fmtN(c.total)}</b></td>
            </tr>
          ))}
        </tbody>
        {aging.clients.length > 0 && (
          <tfoot><tr>
            <td>{t("Total")}</td>
            {BUCKETS.map(([k]) => <td key={k} className="n">{fmtN(aging.buckets[k])}</td>)}
            <td className="n">{fmtN(aging.total)}</td>
          </tr></tfoot>
        )}
      </TableCard>

      {client && (
        <>
          <Section title={client.name} sub={t("Open invoices as of {d}", { d: dLong(aging.as_of) })}>
            <span className="la-right">
              <Link className="la-tool" href={`/finance/clients/${client.client_id}/statement/`}>{t("Statement")}</Link>
              <button type="button" className="la-tool" onClick={() => setPicked(null)}>{t("Close")}</button>
            </span>
          </Section>
          <TableCard cols={[null, 140, 140, 160]}
            empty={!client.invoices.length && <Empty title={t("No invoice on record")} />}>
            <thead><tr>
              <th>{t("Invoice")}</th><th>{t("Due date")}</th><th className="n">{t("Days overdue")}</th><th className="n">{t("Remaining (SAR)")}</th>
            </tr></thead>
            <tbody>
              {client.invoices.map((i) => (
                <tr key={i.id} {...rowNav(`/invoice/${i.id}/`)}>
                  <td><span className="mono">{i.invoice_number}</span></td>
                  <td>{i.due_date ? dLong(i.due_date) : "–"}</td>
                  <td className={"n" + (LATE.includes(i.bucket) ? " late" : "")}>{i.days_overdue || <span className="mut">{t("Not yet due")}</span>}</td>
                  <td className="n">{amount(i.amount, LATE.includes(i.bucket))}</td>
                </tr>
              ))}
            </tbody>
          </TableCard>
        </>
      )}
    </ListPage>
  );
}
