import { useState } from "react";
import { Link, router } from "@inertiajs/react";
import { Popover, PopoverContent, PopoverTrigger } from "../../components/shadcn/ui/popover.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import {
  ListPage, Legend, Kpis, Kpi, Toolbar, SearchTool, FilterMenu, FilterSection, Check, ExportMenu, Primary,
  TableCard, RowMenu, Pill, Pager, Empty, LIcon, fmtN, dShort, useListNav,
} from "../../components/shadcn/list-a.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

const STATUS = { new: ["dark", "New"], active: ["green", "Active"], dormant: ["amber", "Dormant"], inactive: ["gray", "Inactive"] };
const ago = (iso, t) => {
  if (!iso) return "";
  const d = Math.round((new Date() - new Date(iso + "T00:00:00")) / 86400000);
  if (d < 0) return t("in {n} days", { n: -d });
  if (d === 0) return t("today");
  if (d === 1) return t("yesterday");
  if (d < 60) return t("{n} days ago", { n: d });
  return t("{n} months ago", { n: Math.round(d / 30) });
};
const delta = (a, b) => (b == null ? null : `${a - b >= 0 ? "+" : ""}${a - b}`);

// Client list, as on the Record View HMS canvas: KPIs for the umrah season
// against the season before at the same point (New and Dormant filter the
// table), the season picker and the table.
export default function List({ clients, filters: f, seasons, cities, counts, kpis, pagination }) {
  const { t } = useI18n();
  const perms = usePerms();
  const openForm = useFormModal();
  const [confirm, confirmDialog] = useConfirm();
  const [go, loading] = useListNav("/clients/", f);
  const [draft, setDraft] = useState(f);
  const [seasonOpen, setSeasonOpen] = useState(false);
  const tog = (v) => setDraft((d) => ({ ...d, status: d.status.includes(v) ? d.status.filter((x) => x !== v) : [...d.status, v] }));
  const only = (k) => f.status.length === 1 && f.status[0] === k;
  const filterCount = (f.status.length ? 1 : 0) + (f.city ? 1 : 0);
  const k = kpis;
  const vsPrev = (d) => k && k.prev_season ? t("{d} vs the same point of {s}", { d, s: k.prev_season }) : "";

  const del = (c) => confirm({ title: t("Delete client"), message: t("Delete client {name}?", { name: c.name }), onConfirm: () => router.post(`/clients/${c.id}/delete/`) });
  const waLink = (wa) => `https://wa.me/${String(wa).replace(/\D/g, "").replace(/^0/, "62")}`;

  return (
    <ListPage title={t("Clients")} loading={loading}
      legend={k && k.prev_season && <Legend current={k.season} previous={t("{s} at the same point", { s: k.prev_season })} note={k.range} />}>
      {k ? (
        <Kpis>
          <Kpi label={t("New clients")} value={fmtN(k.new)}
            delta={delta(k.new, k.new_then) && { text: delta(k.new, k.new_then), good: k.new >= k.new_then, title: vsPrev(delta(k.new, k.new_then)) }}
            foot={k.new_then != null ? t("{s}: {n} by now", { s: k.prev_season, n: k.new_then }) : t("First season on record")}
            on={only("new")} onClick={() => go({ status: only("new") ? [] : ["new"] })} />
          <Kpi label={t("Active clients")} value={fmtN(k.active)} unit={t("of {n}", { n: k.clients })}
            delta={delta(k.active, k.active_then) && { text: delta(k.active, k.active_then), good: k.active >= k.active_then, title: vsPrev(delta(k.active, k.active_then)) }}
            foot={k.active_then != null ? t("{s}: {n} by now", { s: k.prev_season, n: k.active_then }) : t("Booked at least once this season")} />
          <Kpi label={t("Retention")} value={k.retention ?? "—"} unit={k.retention != null ? "%" : ""}
            delta={k.retention != null && k.retention_then != null && { text: `${k.retention - k.retention_then >= 0 ? "+" : ""}${k.retention - k.retention_then} pts`, good: k.retention >= k.retention_then, title: vsPrev(`${k.retention - k.retention_then} points`) }}
            foot={k.prev_active ? t("{b} of {n} from {s} came back", { b: k.back, n: k.prev_active, s: k.prev_season }) + (k.retention_then != null ? t(", last season {p}%", { p: k.retention_then }) : "") : t("No earlier season to compare")} />
          <Kpi label={t("Dormant")} value={fmtN(k.dormant)} tone={k.dormant ? "warn" : undefined}
            delta={delta(k.dormant, k.dormant_then) && { text: delta(k.dormant, k.dormant_then), good: k.dormant <= k.dormant_then, title: vsPrev(delta(k.dormant, k.dormant_then)) }}
            foot={k.prev_season ? t("Booked in {s}, not yet in {c}, {n} room nights last season", { s: k.prev_season, c: k.season, n: fmtN(k.dormant_nights) }) : t("Booked last season, not yet this one")}
            on={only("dormant")} onClick={() => go({ status: only("dormant") ? [] : ["dormant"] })} />
        </Kpis>
      ) : (
        perms.can("periods", "view") && <p className="la-note" style={{ margin: 0 }}>{t("Season figures appear once umrah seasons are set up.")} <Link href="/finance/periods/" style={{ fontWeight: 600 }}>{t("Set up seasons")}</Link></p>
      )}

      <Toolbar spaced={!!k}
        left={seasons.length > 0 && (
          <Popover open={seasonOpen} onOpenChange={setSeasonOpen}>
            <PopoverTrigger asChild><button type="button" className="la-yr" style={{ marginLeft: 0 }}>{t("Season {s}", { s: f.season })}{LIcon.chev}</button></PopoverTrigger>
            <PopoverContent align="start" sideOffset={6} className="la-menu" style={{ width: 180 }}>
              <div role="menu">{seasons.map((s) => (
                <button type="button" key={s.name} role="menuitem" className={"la-mi" + (s.name === f.season ? " on" : "")}
                  onClick={() => { setSeasonOpen(false); go({ season: s.name }); }}>
                  <span>{s.name}{s.current && <span className="h">{t("current")}</span>}</span>
                </button>
              ))}</div>
            </PopoverContent>
          </Popover>
        )}>
        <SearchTool value={f.q} onSearch={(q) => go({ q })} placeholder={t("Search client, brand, PIC, city")} />
        <FilterMenu count={filterCount} onOpen={() => setDraft(f)}
          onReset={() => setDraft({ ...draft, status: [], city: "" })}
          onApply={() => go({ status: draft.status, city: draft.city })}>
          <FilterSection label={k ? t("Status this season") : t("Status")}>
            {(k ? ["new", "active", "dormant", "inactive"] : ["active", "inactive"]).map((s) => (
              <Check key={s} on={draft.status.includes(s)} onClick={() => tog(s)} label={t(STATUS[s][1])} count={counts[s]} />
            ))}
          </FilterSection>
          <FilterSection label={t("City")}>
            <select className="la-tool" style={{ width: "100%" }} value={draft.city} onChange={(e) => setDraft({ ...draft, city: e.target.value })} aria-label={t("City")}>
              <option value="">{t("All cities")}</option>
              {cities.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </FilterSection>
        </FilterMenu>
        {perms.can("clients", "export") && <ExportMenu items={[{ label: "CSV", hint: t("Contact list: PIC, WhatsApp and city per client"), href: "/clients/export/csv/" }]} />}
        {perms.can("clients", "create") && <Primary label={t("New client")} onClick={() => openForm("/clients/new/")} onPrefetch={() => openForm.prefetch("/clients/new/")} />}
      </Toolbar>

      <TableCard cols={[null, 140, 180, 130, 60, 104, 100, 56]}
        empty={!clients.length && <Empty title={t("No clients")} sub={t("Nothing matches this search and these filters.")} />}>
        <thead><tr>
          <th>{t("Client")}</th><th>{t("City")}</th><th>{t("PIC / WhatsApp")}</th>
          <th><button type="button" className="srt" style={{ border: 0, background: "none", padding: 0, font: "inherit", cursor: "pointer" }}
            onClick={() => go({ sort: f.sort === "name" ? "-last" : "name" })}>{f.sort === "name" ? t("Client name") : t("Last booking")}{LIcon.sortDown}</button></th>
          <th className="n">CL</th><th className="n">{t("Room nights")}</th><th>{t("Status")}</th><th className="c">{t("Action")}</th>
        </tr></thead>
        <tbody>
          {clients.map((c) => {
            const [tone, label] = STATUS[c.status] || STATUS.inactive;
            return (
              <tr key={c.id} className={c.status === "inactive" ? "dim" : ""} onClick={() => router.visit(`/clients/${c.id}/`)}>
                <td className="ell"><span className="strong">{c.brand || c.name}</span>{c.brand && <span className="sub">{c.name}</span>}</td>
                <td className="ell">{c.city || <span className="mut">—</span>}</td>
                <td className="ell">{c.pic || <span className="mut">—</span>}{c.wa && <span className="sub">{c.wa}</span>}</td>
                <td>{c.last_booking ? <>{dShort(c.last_booking)}<span className="sub">{ago(c.last_booking, t)}</span></> : <span className="mut">{t("Never")}</span>}</td>
                <td className={"n" + (c.cl_count ? "" : " zero")}>{c.cl_count}</td>
                <td className={"n" + (c.room_nights ? "" : " zero")}>{fmtN(c.room_nights)}</td>
                <td><Pill tone={tone}>{t(label)}</Pill></td>
                <td className="c">
                  <RowMenu label={t("Actions for {n}", { n: c.name })} items={[
                    c.wa && { label: t("Chat on WhatsApp"), href: waLink(c.wa), external: true },
                    perms.can("clients", "edit") && { label: t("Edit"), onClick: () => openForm(`/clients/${c.id}/edit/`) },
                    perms.can("clients", "delete") && { label: t("Delete"), danger: true, onClick: () => del(c) },
                  ]} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </TableCard>

      <Pager p={pagination} perPage={f.per} onPage={(page) => go({ page })} onPerPage={(per) => go({ per })} />
      {confirmDialog}
    </ListPage>
  );
}
