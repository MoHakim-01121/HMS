import { useState } from "react";
import {
  ListPage, Toolbar, SearchTool, FilterMenu, FilterSection, Check,
  TableCard, Pill, Empty, fmtN, dLong, useListNav, rowNav,
} from "../../components/shadcn/list-a.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Cancellation penalties across confirmation letters. Paid or not comes from
// the ledger (the server filters on it); the newest 100 are shown.
export default function List({ penalties = [], total = 0, filters = {} }) {
  const { t } = useI18n();
  const f = { q: "", status: "", ...filters };
  const [go, loading] = useListNav("/finance/penalties/", f);
  const [draft, setDraft] = useState(f.status);
  const sum = penalties.reduce((a, p) => a + (p.amount_sar || 0), 0);

  return (
    <ListPage title={t("Penalties")} loading={loading}>
      <Toolbar left={<span className="la-note">{t("Cancellation penalties across confirmation letters")}</span>}>
        <SearchTool value={f.q} onSearch={(q) => go({ q })} placeholder={t("Search penalty, CL or client")} />
        <FilterMenu count={f.status ? 1 : 0} onOpen={() => setDraft(f.status)} onReset={() => setDraft("")}
          onApply={() => go({ status: draft })}>
          <FilterSection label={t("Status")}>
            <Check radio on={!draft} onClick={() => setDraft("")} label={t("All")} />
            <Check radio on={draft === "paid"} onClick={() => setDraft("paid")} label={t("Paid")} />
            <Check radio on={draft === "unpaid"} onClick={() => setDraft("unpaid")} label={t("Unpaid")} />
          </FilterSection>
        </FilterMenu>
      </Toolbar>

      <TableCard cols={[130, 110, null, 120, 130, 140]}
        empty={!penalties.length && <Empty title={t("No penalties")} sub={f.q || f.status ? t("No penalties match your filters.") : t("Penalties appear when a confirmed CL is cancelled with a charge.")} />}>
        <thead><tr>
          <th>{t("Penalty #")}</th><th>{t("Status")}</th><th>{t("Client")}</th><th>{t("CL")}</th>
          <th>{t("Cancelled on")}</th><th className="n">{t("Amount (SAR)")}</th>
        </tr></thead>
        <tbody>
          {penalties.map((p) => (
            <tr key={p.id} {...rowNav(`/penalty/${p.id}/`)}>
              <td><span className="mono">{p.penalty_number}</span></td>
              <td><Pill tone={p.is_paid ? "green" : "amber"}>{p.is_paid ? t("Paid") : t("Unpaid")}</Pill></td>
              <td className="ell strong">{p.client_name || "—"}</td>
              <td>{p.cl_id ? <span className="mono">{p.confirmation_number}</span> : <span className="mut">—</span>}</td>
              <td>{dLong(p.cancellation_date)}</td>
              <td className="n">{fmtN(p.amount_sar)}</td>
            </tr>
          ))}
        </tbody>
        {penalties.length > 0 && (
          <tfoot><tr>
            <td colSpan={5}>{total > penalties.length ? t("Newest {n} of {m} penalties", { n: penalties.length, m: total }) : t("{n} penalties", { n: total })}</td>
            <td className="n">{fmtN(sum)}</td>
          </tr></tfoot>
        )}
      </TableCard>
    </ListPage>
  );
}
