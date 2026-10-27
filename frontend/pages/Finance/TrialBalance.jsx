import { Fragment, useState } from "react";
import { ListPage, Toolbar, Kpis, Kpi, FilterMenu, FilterSection, Check, DateRange, TableCard, Pill, Empty, fmtN, dLong, useListNav, Tr, Th, Td, Note } from "../../components/shadcn/list-a.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Neraca Saldo: saldo awal, mutasi debit/kredit dan saldo akhir tiap akun,
// satu pita per tipe akun. Saldo ditulis ke arah normal akunnya (kredit untuk
// kewajiban, ekuitas, pendapatan), merah bila berbalik. Laba tahun-tahun buku
// sebelumnya ada di Laba Ditahan; rentang yang melewati 31 Desember ikut
// membawa tutup tahun virtual di kolom mutasi. Angka dalam SAR utuh.
export default function TrialBalance({
  rows = [], total_debit = 0, total_credit = 0, balanced = true, year_ends = [], years = [], seasons = [], filters = {},
}) {
  const { t } = useI18n();
  const f = { date_from: "", date_to: "", ...filters };
  const [go, loading] = useListNav("/finance/trial-balance/", f);
  const [draft, setDraft] = useState(f);
  const diff = total_debit - total_credit;
  const ranged = !!(f.date_from || f.date_to);
  const fy = (y) => ({ date_from: `${y}-01-01`, date_to: `${y}-12-31` });
  const year = years.find((y) => fy(y).date_from === f.date_from && fy(y).date_to === f.date_to);
  const season = seasons.find((s) => s.date_from === f.date_from && s.date_to === f.date_to);
  const range = season ? t("Season {s}", { s: season.name }) : year ? t("Financial year {y}", { y: year })
    : ranged ? `${f.date_from ? dLong(f.date_from) : "…"} – ${f.date_to ? dLong(f.date_to) : "…"}` : t("All dates");

  const accountsLabel = (n) => t(n === 1 ? "{n} account" : "{n} accounts", { n });
  // A balance read the way the account normally runs; reversed shows red.
  const bal = (r, v) => (r.normal_balance === "credit" ? -v || 0 : v);
  const balCell = (r, v) => (
    <Td className={"text-right" + (!v ? " text-muted-foreground" : bal(r, v) < 0 ? " font-medium text-danger-text" : "")}>{fmtN(bal(r, v))}</Td>
  );
  // Accounts in type order, one band per type.
  const types = [];
  for (const g of rows) {
    let tp = types.find((x) => x.type === g.type);
    if (!tp) types.push(tp = { type: g.type, label: g.type_display, rows: [] });
    tp.rows.push(g);
  }

  return (
    <ListPage title={t("Trial Balance")} loading={loading}
      legend={<Pill tone={balanced ? "green" : "red"}>{balanced ? t("Balanced") : t("Unbalanced")}</Pill>}>
      <Kpis>
        <Kpi label={t("Total debit")} value={fmtN(total_debit)} unit="SAR" foot={ranged ? t("in this period") : t("all time")} />
        <Kpi label={t("Total credit")} value={fmtN(total_credit)} unit="SAR" foot={accountsLabel(rows.length)} />
        <Kpi label={t("Difference")} value={fmtN(diff)} unit="SAR" tone={balanced ? undefined : "warn"}
          foot={balanced ? t("debits equal credits") : t("debits and credits do not match")} />
      </Kpis>

      <Toolbar left={<Note>{range}{year_ends.length > 0 && <> · {t("Includes the year-end close on {d}", { d: year_ends.map(dLong).join(", ") })}</>}</Note>}>
        <FilterMenu count={ranged ? 1 : 0} onOpen={() => setDraft(f)}
          onReset={() => setDraft({ date_from: "", date_to: "" })}
          onApply={() => go({ date_from: draft.date_from, date_to: draft.date_to })}>
          <FilterSection label={t("Financial year")}>
            {years.map((y) => (
              <Check radio key={y} label={String(y)}
                on={draft.date_from === fy(y).date_from && draft.date_to === fy(y).date_to}
                onClick={() => setDraft(fy(y))} />
            ))}
          </FilterSection>
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

      <TableCard cols={[null, 150, 130, 130, 150]}
        empty={!rows.length && <Empty title={t("No journal data")} sub={t("No entries match your filters.")} />}>
        <thead><Tr>
          <Th>{t("Account")}</Th><Th className="text-right">{t("Opening")}</Th><Th className="text-right">{t("Debit")}</Th>
          <Th className="text-right">{t("Credit")}</Th><Th className="text-right">{t("Closing")}</Th>
        </Tr></thead>
        <tbody>
          {types.map((tp) => (
            <Fragment key={tp.type}>
              <Tr row="band"><Td colSpan={5}>{t(tp.label)} · {accountsLabel(tp.rows.length)}</Td></Tr>
              {tp.rows.map((g) => (
                <Tr key={g.account} row="static">
                  <Td className="truncate font-medium">{g.account_name}</Td>
                  {balCell(g, g.opening)}
                  <Td className={"text-right" + (g.debit ? "" : " text-muted-foreground")}>{fmtN(g.debit)}</Td>
                  <Td className={"text-right" + (g.credit ? "" : " text-muted-foreground")}>{fmtN(g.credit)}</Td>
                  {balCell(g, g.closing)}
                </Tr>
              ))}
            </Fragment>
          ))}
        </tbody>
        {rows.length > 0 && (
          <tfoot><Tr>
            <Td>{t("Total")}</Td>
            <Td />
            <Td className="text-right">{fmtN(total_debit)}</Td>
            <Td className="text-right">{fmtN(total_credit)}</Td>
            <Td className={"text-right" + (balanced ? "" : " font-medium text-danger-text")}>{balanced ? "" : fmtN(diff)}</Td>
          </Tr></tfoot>
        )}
      </TableCard>
    </ListPage>
  );
}
