import { useState } from "react";
import { ListPage, Toolbar, SearchTool, FilterMenu, FilterSection, Check, TableCard, Pill, Empty, fmtN, dLong, useListNav, rowNav, Tr, Th, Td, Note } from "../../components/shadcn/list-a.jsx";
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
      <Toolbar left={<Note>{t("Cancellation penalties across confirmation letters")}</Note>}>
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
        <thead><Tr>
          <Th>{t("Penalty #")}</Th><Th>{t("Status")}</Th><Th>{t("Client")}</Th><Th>{t("CL")}</Th>
          <Th>{t("Cancelled on")}</Th><Th className="text-right">{t("Amount (SAR)")}</Th>
        </Tr></thead>
        <tbody>
          {penalties.map((p) => (
            <Tr key={p.id} {...rowNav(`/penalty/${p.id}/`)}>
              <Td><span className="font-mono text-[13px] font-semibold">{p.penalty_number}</span></Td>
              <Td><Pill tone={p.is_paid ? "green" : "amber"}>{p.is_paid ? t("Paid") : t("Unpaid")}</Pill></Td>
              <Td className="truncate font-medium">{p.client_name || "—"}</Td>
              <Td>{p.cl_id ? <span className="font-mono text-[13px] font-semibold">{p.confirmation_number}</span> : <span className="text-muted-foreground">—</span>}</Td>
              <Td>{dLong(p.cancellation_date)}</Td>
              <Td className="text-right">{fmtN(p.amount_sar)}</Td>
            </Tr>
          ))}
        </tbody>
        {penalties.length > 0 && (
          <tfoot><Tr>
            <Td colSpan={5}>{total > penalties.length ? t("Newest {n} of {m} penalties", { n: penalties.length, m: total }) : t("{n} penalties", { n: total })}</Td>
            <Td className="text-right">{fmtN(sum)}</Td>
          </Tr></tfoot>
        )}
      </TableCard>
    </ListPage>
  );
}
