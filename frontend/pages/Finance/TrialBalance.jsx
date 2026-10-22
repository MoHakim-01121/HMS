import { Fragment, useState } from "react";
import {
  ListPage, Toolbar, Kpis, Kpi, FilterMenu, FilterSection, Check, DateRange,
  TableCard, Pill, Empty, fmtN, dLong, useListNav,
} from "../../components/shadcn/list-a.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Neraca Saldo: total debit & kredit tiap akun pada rentang tanggal, satu
// pita per tipe akun, dan baris total di footer. Angka dalam SAR utuh; KPI di
// atas tabel membawa debit, kredit dan selisih supaya seimbang/tidak terbaca
// sebelum masuk tabel.
export default function TrialBalance({
  groups = [], total_debit = 0, total_credit = 0, balanced = true, seasons = [], filters = {},
}) {
  const { t } = useI18n();
  const f = { date_from: "", date_to: "", ...filters };
  const [go, loading] = useListNav("/finance/trial-balance/", f);
  const [draft, setDraft] = useState(f);
  const diff = total_debit - total_credit;
  const ranged = !!(f.date_from || f.date_to);
  const season = seasons.find((s) => s.date_from === f.date_from && s.date_to === f.date_to);
  const range = season ? t("Season {s}", { s: season.name })
    : ranged ? `${f.date_from ? dLong(f.date_from) : "…"} – ${f.date_to ? dLong(f.date_to) : "…"}` : t("All dates");

  const accountsLabel = (n) => t(n === 1 ? "{n} account" : "{n} accounts", { n });
  // Accounts in type order, one band per type.
  const types = [];
  for (const g of groups) {
    let tp = types.find((x) => x.type === g.type);
    if (!tp) types.push(tp = { type: g.type, label: g.type_display, rows: [] });
    tp.rows.push(g);
  }

  return (
    <ListPage title={t("Trial Balance")} loading={loading}
      legend={<Pill tone={balanced ? "green" : "red"}>{balanced ? t("Balanced") : t("Unbalanced")}</Pill>}>
      <Kpis>
        <Kpi label={t("Total debit")} value={fmtN(total_debit)} unit="SAR" foot={ranged ? t("in this period") : t("all time")} />
        <Kpi label={t("Total credit")} value={fmtN(total_credit)} unit="SAR" foot={accountsLabel(groups.length)} />
        <Kpi label={t("Difference")} value={fmtN(diff)} unit="SAR" tone={balanced ? undefined : "warn"}
          foot={balanced ? t("debits equal credits") : t("debits and credits do not match")} />
      </Kpis>

      <Toolbar left={<span className="la-note">{range}</span>}>
        <FilterMenu count={ranged ? 1 : 0} onOpen={() => setDraft(f)}
          onReset={() => setDraft({ date_from: "", date_to: "" })}
          onApply={() => go({ date_from: draft.date_from, date_to: draft.date_to })}>
          {seasons.length > 0 && (
            <FilterSection label={t("Season")}>
              {seasons.map((s) => (
                <Check radio key={s.id} label={s.name}
                  on={draft.date_from === s.date_from && draft.date_to === s.date_to}
                  onClick={() => setDraft({ date_from: s.date_from, date_to: s.date_to })} />
              ))}
            </FilterSection>
          )}
          <FilterSection label={t("Date")}>
            <DateRange from={draft.date_from} to={draft.date_to}
              onFrom={(v) => setDraft({ ...draft, date_from: v })} onTo={(v) => setDraft({ ...draft, date_to: v })} />
          </FilterSection>
        </FilterMenu>
      </Toolbar>

      <TableCard cols={[null, 160, 160, 160]}
        empty={!groups.length && <Empty title={t("No journal data")} sub={t("No entries match your filters.")} />}>
        <thead><tr>
          <th>{t("Account")}</th><th className="n">{t("Debit")}</th><th className="n">{t("Credit")}</th><th className="n">{t("Net")}</th>
        </tr></thead>
        <tbody>
          {types.map((tp) => (
            <Fragment key={tp.type}>
              <tr className="band"><td colSpan={4}>{t(tp.label)} · {accountsLabel(tp.rows.length)}</td></tr>
              {tp.rows.map((g) => (
                <tr key={g.account} className="static">
                  <td className="ell strong">{g.account_display}</td>
                  <td className={"n" + (g.debit ? "" : " zero")}>{fmtN(g.debit)}</td>
                  <td className={"n" + (g.credit ? "" : " zero")}>{fmtN(g.credit)}</td>
                  <td className={"n" + (g.net < 0 ? " late" : "")}>{fmtN(g.net)}</td>
                </tr>
              ))}
            </Fragment>
          ))}
        </tbody>
        {groups.length > 0 && (
          <tfoot><tr>
            <td>{t("Total")}</td>
            <td className="n">{fmtN(total_debit)}</td>
            <td className="n">{fmtN(total_credit)}</td>
            <td className={"n" + (balanced ? "" : " late")}>{fmtN(diff)}</td>
          </tr></tfoot>
        )}
      </TableCard>
    </ListPage>
  );
}
