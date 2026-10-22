import { useState } from "react";
import {
  ListPage, Toolbar, SearchTool, FilterMenu, FilterSection, Check, DateRange,
  TableCard, Pill, Pager, Empty, fmtN, dLong, useListNav, rowNav,
} from "../../components/shadcn/list-a.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Journal entries: the ledger, newest first. Search and the Filter panel
// (type, date range) drive the server's filters; corrections are reversals.
export default function Journal({
  entries = [], type_choices = [], page_num = 1, num_pages = 1,
  total = 0, filters = {},
}) {
  const { t } = useI18n();
  const f = { type: "", date_from: "", date_to: "", q: "", ...filters };
  const [go, loading] = useListNav("/finance/journal/", f);
  const [draft, setDraft] = useState(f);
  const filterCount = (f.type ? 1 : 0) + (f.date_from || f.date_to ? 1 : 0);
  const range = f.date_from || f.date_to
    ? `${f.date_from ? dLong(f.date_from) : "…"} – ${f.date_to ? dLong(f.date_to) : "…"}`
    : t("All dates");

  return (
    <ListPage title={t("Journal Entries")} loading={loading}>
      <Toolbar left={<span className="la-note">{range}, {t("{n} entries", { n: fmtN(total) })}</span>}>
        <SearchTool value={f.q} onSearch={(q) => go({ q })} placeholder={t("Search number or description")} />
        <FilterMenu count={filterCount} onOpen={() => setDraft(f)}
          onReset={() => setDraft({ ...draft, type: "", date_from: "", date_to: "" })}
          onApply={() => go({ type: draft.type, date_from: draft.date_from, date_to: draft.date_to })}>
          <FilterSection label={t("Type")}>
            <Check radio on={!draft.type} onClick={() => setDraft({ ...draft, type: "" })} label={t("All types")} />
            {type_choices.map(([value, label]) => (
              <Check radio key={value} on={draft.type === value} onClick={() => setDraft({ ...draft, type: value })} label={label} />
            ))}
          </FilterSection>
          <FilterSection label={t("Date")}>
            <DateRange from={draft.date_from} to={draft.date_to}
              onFrom={(v) => setDraft({ ...draft, date_from: v })} onTo={(v) => setDraft({ ...draft, date_to: v })} />
          </FilterSection>
        </FilterMenu>
      </Toolbar>

      <TableCard cols={[120, 170, null, 120, 130, 130]}
        empty={!entries.length && <Empty title={t("No journal entries")} sub={t("No entries match your filters.")} />}>
        <thead><tr>
          <th>{t("Entry #")}</th><th>{t("Type")}</th><th>{t("Description")}</th><th>{t("Date")}</th>
          <th className="n">{t("Debit")}</th><th className="n">{t("Credit")}</th>
        </tr></thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.id} {...rowNav(`/finance/journal/${e.id}/`)}>
              <td><span className="mono">{e.entry_number}</span></td>
              <td>{e.is_reversal ? <Pill tone="red" sm>{t("Reversal")}</Pill> : e.entry_type_display}</td>
              <td className="ell" title={e.description}>{e.description}</td>
              <td>{dLong(e.entry_date)}</td>
              <td className={"n" + (e.debit ? "" : " zero")}>{fmtN(e.debit)}</td>
              <td className={"n" + (e.credit ? "" : " zero")}>{fmtN(e.credit)}</td>
            </tr>
          ))}
        </tbody>
      </TableCard>

      {num_pages > 1 && (
        <Pager p={{ number: page_num, num_pages }} summary={t("Page {p} of {n}", { p: page_num, n: num_pages })}
          onPage={(page) => go({ page })} />
      )}
    </ListPage>
  );
}
