import { useEffect, useMemo, useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import Table from "../../components/shadcn/table.jsx";
import Pagination from "../../components/shadcn/pagination.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle } from "../../components/shadcn/ui/drawer.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import FilterRadioGroup from "../../components/shadcn/filter-radio-group.jsx";
import { Icon } from "../../components/icons.jsx";
import { fmt } from "../../utils/format.js";

const TABS = [
  { val: "schedule", label: "Schedule" },
  { val: "history", label: "History" },
  { val: "recap", label: "Recap" },
];
const VIEWS = [
  { val: "month", label: "Month" },
  { val: "week", label: "Week" },
  { val: "agenda", label: "Agenda" },
];
const DAY_NAMES = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];
const WEEK_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const STATUS_TONE = {
  COMPLETED: "green",
  CANCELLED: "red",
};

const STATUS_OPTS = [
  { val: "", label: "All", cls: "c-all" },
  { val: "PLANNED", label: "Planned", cls: "c-pen" },
  { val: "COMPLETED", label: "Completed", cls: "c-rec" },
  { val: "CANCELLED", label: "Cancelled", cls: "c-can" },
];

function statusLabel(s, t) {
  return s === "COMPLETED" ? t("Completed") : s === "CANCELLED" ? t("Cancelled") : t("Planned");
}

function statusClass(s) {
  const tone = STATUS_TONE[s] || "yellow";
  const map = { green: "badge-green", red: "badge-red", yellow: "badge-yellow" };
  return `badge ${map[tone] || "badge-gray"}`;
}

function chipColor(s) {
  if (s === "COMPLETED") return { bg: "var(--green-muted)", fg: "var(--green)", border: "1px solid color-mix(in oklch, var(--green) 40%, transparent)" };
  if (s === "CANCELLED") return { bg: "var(--red-muted)", fg: "var(--red)", border: "1px solid color-mix(in oklch, var(--red) 40%, transparent)" };
  return { bg: "var(--accent-muted)", fg: "var(--accent-2)", border: "1px solid color-mix(in oklch, var(--accent-2) 40%, transparent)" };
}

function toMin(s) {
  if (!s) return null;
  const [h, m] = s.split(":").map(Number);
  return h * 60 + m;
}

function timeLabel(v) {
  if (v.start_time && v.end_time) return `${v.start_time}–${v.end_time}`;
  return v.start_time || v.end_time || "";
}

function fmtDay(iso, locale) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function pad(n) {
  return String(n).padStart(2, "0");
}

function addDays(iso, delta) {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d + delta);
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
}

// Legend drawn under the board: colour carries status meaning (Cloudbeds blocks
// / Guesty colour-coding pattern), shown once near the calendar rather than
// repeated per chip.
function StatusLegend() {
  const { t } = useI18n();
  const items = [
    { s: "PLANNED", label: "Planned" },
    { s: "COMPLETED", label: "Completed" },
    { s: "CANCELLED", label: "Cancelled" },
  ];
  return (
    <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap", marginTop: 12 }}>
      {items.map(({ s, label }) => (
        <span key={s} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--muted-foreground)" }}>
          <span style={{ width: 9, height: 9, borderRadius: 3, background: chipColor(s).bg, border: chipColor(s).border }} />
          {t(label)}
        </span>
      ))}
    </div>
  );
}

export default function List({
  tab, view, selected_date, year, month,
  status_filter, client_filter, staff_filter,
  is_staff, staff_list, clients, month_visits, week_visits, week_start,
  visits, pagination, total_count, recap,
}) {
  const { t } = useI18n();
  const perms = usePerms();
  const openForm = useFormModal();
  const [selDate, setSelDate] = useState(selected_date);
  const [drawerDay, setDrawerDay] = useState(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [selStatus, setSelStatus] = useState(status_filter || "");
  const [selClient, setSelClient] = useState(client_filter ? String(client_filter) : "");
  const [selStaff, setSelStaff] = useState(staff_filter ? String(staff_filter) : "");
  const [busy, setBusy] = useState(false);

  // Server round-trips land on new prop arrays, so clearing on their identity
  // change means one skeleton per navigation, never stuck.
  useEffect(() => { setBusy(false); }, [month_visits, week_visits]);

  const go = (params = {}, extra = {}) => {
    const p = new URLSearchParams();
    const nextTab = params.tab ?? tab;
    p.set("tab", nextTab);
    p.set("view", params.view ?? view);
    p.set("status", params.status != null ? params.status : (status_filter || ""));
    p.set("client", params.client != null ? params.client : (client_filter ? String(client_filter) : ""));
    p.set("staff", params.staff != null ? params.staff : (staff_filter ? String(staff_filter) : ""));
    if (nextTab === "schedule") p.set("date", params.date ?? selDate);
    if (params.page) p.set("page", String(params.page));
    setBusy(true);
    router.get(`/visits/?${p.toString()}`, {}, { preserveState: true, preserveScroll: true, replace: true, ...extra });
  };

  const applyPanel = () => {
    setPanelOpen(false);
    go({ status: selStatus, client: selClient, staff: selStaff });
  };
  const resetPanel = () => {
    setSelStatus("");
    setSelClient("");
    setSelStaff("");
    setPanelOpen(false);
    go({ status: "", client: "", staff: "" });
  };

  const shiftMonth = (delta) => {
    setDrawerDay(null);
    go({ date: addDays(`${year}-${pad(month)}-01`, 40 * delta).slice(0, 7) + "-01" });
  };
  const shiftWeek = (delta) => {
    setDrawerDay(null);
    go({ date: addDays(selDate, 7 * delta) });
  };
  const pickToday = () => {
    setDrawerDay(null);
    go({ date: new Date().toISOString().slice(0, 10) });
  };

  const openDay = (iso) => {
    setSelDate(iso);
    setDrawerDay(iso);
    go({ date: iso });
  };

  // Union the props that may cover the selected day (month_visits for month/agenda,
  // week_visits for the week grid which can span a month boundary), keyed by ISO date.
  const byIso = useMemo(() => {
    const map = {};
    for (const v of [...(month_visits || []), ...(view === "week" ? week_visits || [] : [])]) {
      const key = v.date;
      if (!map[key] || !map[key].some((x) => x.id === v.id)) (map[key] = map[key] || []).push(v);
    }
    for (const k of Object.keys(map)) map[k].sort((a, b) => (toMin(a.start_time) ?? 1440) - (toMin(b.start_time) ?? 1440));
    return map;
  }, [month_visits, week_visits, view]);

  const drawerVisits = drawerDay ? (byIso[drawerDay] || []) : [];
  const monthVisitsAll = useMemo(() => (month_visits || []).sort((a, b) => a.date.localeCompare(b.date)), [month_visits]);

  // Month summary chips (occupancy-at-a-glance from Cloudbeds header counts).
  const monthStats = useMemo(() => {
    const s = { PLANNED: 0, COMPLETED: 0, CANCELLED: 0 };
    for (const v of month_visits || []) if (s[v.status] != null) s[v.status]++;
    return s;
  }, [month_visits]);

  const firstDow = new Date(year, month - 1, 1).getDay();
  const daysInMonth = new Date(year, month, 0).getDate();
  const cells = [];
  for (let i = 0; i < firstDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  while (cells.length % 7) cells.push(null);

  const todayStr = new Date().toISOString().slice(0, 10);
  const monthLabel = new Date(year, month - 1, 1).toLocaleDateString("en-US", { month: "long", year: "numeric" });

  // Week grid: rows = staff, columns = Mon..Sun. Falls back to a single
  // "All staff" row when there is no staff to split by (is_staff, or filters).
  const weekAnchor = week_start || selDate;
  const weekDays = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(weekAnchor, i)), [weekAnchor]);
  const weekRows = useMemo(() => {
    if (is_staff) return [{ id: "me", name: t("Me"), all: true }];
    if (staff_list && staff_list.length) return staff_list.map((s) => ({ id: s.id, name: s.name }));
    return [{ id: "all", name: t("All staff"), all: true }];
  }, [is_staff, staff_list, t]);
  const weekLabel = `${fmtDay(weekDays[0], "en-US").toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" })} – ${fmtDay(weekDays[6], "en-US").toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" })}`;

  const boardSub = busy
    ? t("Loading…")
    : view === "week"
      ? t("Who meets whom, per day")
      : view === "agenda"
        ? t("This month, in order")
        : t("{count} visits in {month}", { count: month_visits?.length || 0, month: monthLabel });

  return (
    <div className="page shadcn-root">
      <PageBack />
      <PageHeader
        title={t("Visits")}
        sub={boardSub}
        actions={
          <>
            {perms.can("visits", "create") && (
              <Button type="button" size="lg" onClick={() => openForm("/visits/new/")} onPointerEnter={() => openForm.prefetch("/visits/new/")} onFocus={() => openForm.prefetch("/visits/new/")}>
                {t("+ New Visit")}
              </Button>
            )}
          </>
        }
      />

      <div className="filter-bar">
        <div className="fbar-actions">
          {TABS.map((tb) => (
            <button
              key={tb.val}
              type="button"
              className={"fbar-btn" + (tab === tb.val ? " active" : "")}
              onClick={() => { setDrawerDay(null); go({ tab: tb.val }); }}
            >
              {t(tb.label)}
            </button>
          ))}
        </div>

        {tab === "schedule" && (
          <div className="fbar-actions" style={{ gap: 8 }}>
            <div className="fbar-btn-group" role="group" aria-label={t("View")}>
              {VIEWS.map((v) => (
                <button
                  key={v.val}
                  type="button"
                  className={"fbar-btn" + (view === v.val ? " active" : "")}
                  onClick={() => { setDrawerDay(null); go({ view: v.val }); }}
                >
                  {t(v.label)}
                </button>
              ))}
            </div>

            <button type="button" className="btn btn-secondary" style={{ height: 30, padding: "0 12px", fontSize: 12 }} onClick={pickToday}>
              {t("Today")}
            </button>

            <div className="filter-panel-wrap" onClick={(e) => e.stopPropagation()}>
              <button type="button" className="fbar-btn" onClick={() => setPanelOpen((v) => !v)}>
                <Icon name="filter" size={13} /> {t("Filter")}
                {(status_filter || client_filter || staff_filter) && <span className="fbar-count">1</span>}
              </button>
              {panelOpen && (
                <div className="filter-panel open">
                  <div className="fp-head"><span className="fp-title">{t("Filter")}</span></div>
                  <div className="fp-section">
                    <div className="fp-section-head">
                      <span className="fp-section-label">{t("Status")}</span>
                      <button type="button" className="fp-reset" onClick={() => setSelStatus("")}>{t("Reset")}</button>
                    </div>
                    <FilterRadioGroup label={t("Status")} options={STATUS_OPTS} value={selStatus} onChange={setSelStatus} dot />
                  </div>
                  <div className="fp-section">
                    <div className="fp-section-head">
                      <span className="fp-section-label">{t("Client")}</span>
                      <button type="button" className="fp-reset" onClick={() => setSelClient("")}>{t("Reset")}</button>
                    </div>
                    <select
                      value={selClient}
                      onChange={(e) => setSelClient(e.target.value)}
                      className="btn btn-secondary"
                      style={{ width: "100%", height: 30, padding: "0 10px", fontSize: 12 }}
                    >
                      <option value="">{t("All clients")}</option>
                      {(clients || []).map((c) => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  </div>
                  {!is_staff && (
                    <div className="fp-section">
                      <div className="fp-section-head">
                        <span className="fp-section-label">{t("Staff")}</span>
                        <button type="button" className="fp-reset" onClick={() => setSelStaff("")}>{t("Reset")}</button>
                      </div>
                      <select
                        value={selStaff}
                        onChange={(e) => setSelStaff(e.target.value)}
                        className="btn btn-secondary"
                        style={{ width: "100%", height: 30, padding: "0 10px", fontSize: 12 }}
                      >
                        <option value="">{t("All staff")}</option>
                        {(staff_list || []).map((s) => (
                          <option key={s.id} value={s.id}>{s.name}</option>
                        ))}
                      </select>
                    </div>
                  )}
                  <div className="fp-footer">
                    <Button type="button" variant="ghost" size="sm" onClick={resetPanel}>{t("Reset all")}</Button>
                    <Button type="button" size="sm" onClick={applyPanel}>{t("Apply")}</Button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {tab === "history" ? (
        <div className="hms-list-card">
          {visits && visits.length ? (
            <>
              <Table
                columns={[
                  { header: t("Client"), className: "col-m-primary", render: (v) => v.client_name || "—" },
                  {
                    header: t("Status"), className: "col-m-badge",
                    render: (v) => <StatusPill tone={STATUS_TONE[v.status] || "yellow"} label={statusLabel(v.status, t)} />,
                  },
                  { header: t("Date"), className: "col-muted col-nowrap col-m-hide", render: (v) => v.scheduled_date + (v.time ? ` · ${v.time}` : "") },
                  { header: t("Purpose"), className: "col-ellipsis col-m-secondary", render: (v) => v.purpose },
                  { header: t("Staff"), className: "col-muted col-m-meta", render: (v) => v.staff_name || "—" },
                  {
                    header: "", className: "col-m-actions",
                    render: (v) => (
                      <RowActions actions={[
                        v.status === "PLANNED" && perms.can("visits", "edit") &&
                          { icon: "edit", label: t("Edit"), onClick: () => openForm(`/visits/${v.id}/edit/`) },
                      ]} />
                    ),
                  },
                ]}
                rows={visits}
                rowKey={(v) => v.id}
                onRowClick={(v) => router.visit(`/visits/${v.id}/`)}
              />
              <Pagination pagination={pagination} unit={t("visits")} onPage={(p) => go({ page: p, tab: "history" })} />
            </>
          ) : (
            <EmptyState iconName="visits" title="No visits yet" sub="Use the Filter panel or the + New Visit button in the top right" />
          )}
        </div>
      ) : (
        <div className="hms-list-card" style={{ padding: 0 }}>
          {busy ? (
            <div style={{ padding: "56px 20px", display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
              <span className="hms-skel-bar" style={{ width: 220, height: 14 }} />
              <span className="hms-skel-bar" style={{ width: 320, height: 14 }} />
              <span className="hms-skel-bar" style={{ width: 180, height: 14 }} />
            </div>
          ) : view === "month" ? (
            <>
              <div className="visits-board-head">
                <button type="button" className="btn btn-ghost" style={{ fontSize: 14 }} onClick={() => shiftMonth(-1)} aria-label={t("Previous month")}>←</button>
                <div style={{ fontWeight: 600, fontSize: 15 }}>{monthLabel}</div>
                <button type="button" className="btn btn-ghost" style={{ fontSize: 14 }} onClick={() => shiftMonth(1)} aria-label={t("Next month")}>→</button>
                <div className="visits-board-stats">
                  {monthStats.PLANNED > 0 && <StatusPill tone="yellow" small label={`${monthStats.PLANNED} ${t("Planned")}`} />}
                  {monthStats.COMPLETED > 0 && <StatusPill tone="green" small label={`${monthStats.COMPLETED} ${t("Completed")}`} />}
                  {monthStats.CANCELLED > 0 && <StatusPill tone="red" small label={`${monthStats.CANCELLED} ${t("Cancelled")}`} />}
                </div>
              </div>

              <div className="visits-month-grid">
                {DAY_NAMES.map((d) => (
                  <div key={d} className="visits-month-dow">{d}</div>
                ))}
                {cells.map((d, i) => {
                  if (d == null) return <div key={i} />;
                  const iso = `${year}-${pad(month)}-${pad(d)}`;
                  const list = byIso[iso] || [];
                  const isToday = iso === todayStr;
                  const isSel = iso === selDate;
                  return (
                    <button
                      key={i}
                      type="button"
                      onClick={() => openDay(iso)}
                      className={"visits-cell" + (isToday ? " today" : "") + (isSel ? " selected" : "")}
                      aria-label={`${fmtDay(iso).toLocaleDateString("en-US", { month: "long", day: "numeric" })}, ${list.length} ${t("visits")}`}
                    >
                      <span className="visits-cell-day">{d}</span>
                      {list.length > 0 && <span className="visits-cell-count">{list.length}</span>}
                      {list.slice(0, 2).map((v) => (
                        <span key={v.id} className="visits-cell-chip" style={chipColor(v.status)}>
                          {v.start_time ? `${v.start_time} ` : ""}{v.client_name}
                        </span>
                      ))}
                      {list.length > 2 && <span className="visits-cell-more">+{list.length - 2} {t("more")}</span>}
                    </button>
                  );
                })}
              </div>
              <StatusLegend />
              {!Object.keys(byIso).length && (
                <EmptyState iconName="visits" title="No visits this month" sub="Click a day to add a visit, or use + New Visit" />
              )}
            </>
          ) : view === "week" ? (
            <>
              <div className="visits-board-head">
                <button type="button" className="btn btn-ghost" style={{ fontSize: 14 }} onClick={() => shiftWeek(-1)} aria-label={t("Previous week")}>←</button>
                <div style={{ fontWeight: 600, fontSize: 15 }}>{weekLabel}</div>
                <button type="button" className="btn btn-ghost" style={{ fontSize: 14 }} onClick={() => shiftWeek(1)} aria-label={t("Next week")}>→</button>
                <div className="visits-board-stats">
                  <button type="button" className="btn btn-secondary" style={{ height: 26, padding: "0 10px", fontSize: 11 }} onClick={pickToday}>{t("Today")}</button>
                </div>
              </div>

              <div className="visits-week-scroll">
                <div className="visits-week-grid" style={{ gridTemplateColumns: `110px repeat(7, minmax(96px, 1fr))` }}>
                  <div className="visits-week-corner">{t("Staff")}</div>
                  {weekDays.map((iso) => {
                    const dt = fmtDay(iso);
                    const isToday = iso === todayStr;
                    const isSel = iso === selDate;
                    return (
                      <div key={iso} className={"visits-week-head" + (isToday ? " today" : "")}>
                        <button
                          type="button"
                          className="visits-week-daybtn"
                          onClick={() => openDay(iso)}
                          style={isSel ? { borderColor: "var(--primary)" } : {}}
                        >
                          <span className="visits-week-dow">{WEEK_DAYS[dt.getDay() === 0 ? 6 : dt.getDay() - 1]}</span>
                          <span className="visits-week-num">{dt.getDate()}</span>
                        </button>
                      </div>
                    );
                  })}

                  {weekRows.map((row) => (
                    <FragmentRow key={row.id} row={row} weekDays={weekDays} byIso={byIso} openDay={openDay} t={t} />
                  ))}
                </div>
              </div>
              <StatusLegend />
              {!week_visits?.length && (
                <EmptyState iconName="visits" title="No visits that week" sub="Use the Today button to jump back, or + New Visit" />
              )}
            </>
          ) : (
            <>
              <div className="visits-board-head">
                <button type="button" className="btn btn-ghost" style={{ fontSize: 14 }} onClick={() => shiftMonth(-1)} aria-label={t("Previous month")}>←</button>
                <div style={{ fontWeight: 600, fontSize: 15 }}>{monthLabel}</div>
                <button type="button" className="btn btn-ghost" style={{ fontSize: 14 }} onClick={() => shiftMonth(1)} aria-label={t("Next month")}>→</button>
                <div className="visits-board-stats">
                  {monthStats.PLANNED > 0 && <StatusPill tone="yellow" small label={`${monthStats.PLANNED} ${t("Planned")}`} />}
                  {monthStats.COMPLETED > 0 && <StatusPill tone="green" small label={`${monthStats.COMPLETED} ${t("Completed")}`} />}
                  {monthStats.CANCELLED > 0 && <StatusPill tone="red" small label={`${monthStats.CANCELLED} ${t("Cancelled")}`} />}
                </div>
              </div>

              {monthVisitsAll.length ? (
                <div style={{ display: "flex", flexDirection: "column" }}>
                  {monthVisitsAll.map((v, i) => {
                    const firstOfDay = i === 0 || monthVisitsAll[i - 1].date !== v.date;
                    const idx = byIso[v.date].findIndex((x) => x.id === v.id);
                    return (
                      <div key={v.id}>
                        {firstOfDay && (
                          <div className="visits-agenda-day">
                            {fmtDay(v.date).toLocaleDateString("en-US", { weekday: "long", day: "numeric", month: "long" })}
                            <span className="visits-agenda-count">{byIso[v.date].length}</span>
                          </div>
                        )}
                        <button
                          type="button"
                          className={"visits-agenda-row" + (idx === 0 ? " first" : "")}
                          onClick={() => openDay(v.date)}
                        >
                          <span className="visits-agenda-time">{timeLabel(v) || "—"}</span>
                          <span className="visits-agenda-client">{v.client_name}</span>
                          <span style={{ color: "var(--muted-foreground)", fontSize: 12, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{v.purpose}</span>
                          {!is_staff && <span className="visits-agenda-staff">{v.staff_name}</span>}
                          <StatusPill tone={STATUS_TONE[v.status] || "yellow"} small label={statusLabel(v.status, t)} />
                        </button>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <EmptyState iconName="visits" title="No visits this month" sub="Use the + New Visit button to schedule one" />
              )}
            </>
          )}
        </div>
      )}

      <Drawer open={drawerDay != null} onOpenChange={(o) => { if (!o) setDrawerDay(null); }} direction="right">
        <DrawerContent className="visits-drawer">
          <DrawerHeader>
            <DrawerTitle>
              {drawerDay ? fmtDay(drawerDay).toLocaleDateString("en-US", { weekday: "long", day: "numeric", month: "long", year: "numeric" }) : ""}
            </DrawerTitle>
            <div style={{ fontSize: 13, color: "var(--muted-foreground)" }}>
              {drawerVisits.length} {t("visits")}
            </div>
          </DrawerHeader>
          <div style={{ padding: "0 16px", display: "flex", gap: 8, flexWrap: "wrap" }}>
            {perms.can("visits", "create") && (
              <Button
                type="button"
                size="sm"
                onClick={() => openForm(`/visits/new/?date=${drawerDay}`)}
                onPointerEnter={() => openForm.prefetch(`/visits/new/?date=${drawerDay}`)}
                onFocus={() => openForm.prefetch(`/visits/new/?date=${drawerDay}`)}
              >
                + {t("Add visit on this day")}
              </Button>
            )}
            {drawerDay && drawerDay !== todayStr && (
              <Button type="button" variant="outline" size="sm" onClick={() => openDay(todayStr)}>{t("Jump to today")}</Button>
            )}
          </div>
          <div style={{ padding: "12px 16px 24px", display: "flex", flexDirection: "column", gap: 8 }}>
            {drawerVisits.length ? drawerVisits.map((v) => (
              <div key={v.id} className="visits-drawer-row">
                <div style={{ minWidth: 0, flex: 1, cursor: "pointer" }} onClick={() => router.visit(`/visits/${v.id}/`)}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>{v.client_name}</span>
                    {!is_staff && <span style={{ fontSize: 11, color: "var(--muted-foreground)" }}>{v.staff_name}</span>}
                  </div>
                  <div style={{ marginTop: 3, fontSize: 12, color: "var(--muted-foreground)" }}>
                    {timeLabel(v) || t("No time set")}
                    {v.purpose ? ` · ${v.purpose}` : ""}
                  </div>
                </div>
                <StatusPill tone={STATUS_TONE[v.status] || "yellow"} small label={statusLabel(v.status, t)} />
                {v.status === "PLANNED" && perms.can("visits", "edit") && (
                  <button type="button" className="app-icon-btn" title={t("Edit")} aria-label={t("Edit")} onClick={() => openForm(`/visits/${v.id}/edit/`)}>
                    <Icon name="edit" size={14} />
                  </button>
                )}
              </div>
            )) : (
              <EmptyState iconName="visits" title="No visits on this day" sub="Use + Add visit on this day to schedule one" />
            )}
          </div>
        </DrawerContent>
      </Drawer>
    </div>
  );
}

const OUTCOME_TONE = {
  ORDER: "green",
  PROSPECT: "blue",
  NO_INTEREST: "yellow",
  NOT_MET: "red",
};

const OUTCOME_LABEL = {
  ORDER: "Order received",
  PROSPECT: "Prospect / follow-up needed",
  NO_INTEREST: "No interest",
  NOT_MET: "Client not met",
};

function outcomeBadge(key, t) {
  return <StatusPill tone={OUTCOME_TONE[key] || "gray"} label={t(OUTCOME_LABEL[key] || key || "")} />;
}

function RecapPanel({ monthly, onOpenList }) {
  const { t } = useI18n();
  return (
    <div className="hms-list-card">
      {monthly && monthly.length ? monthly.map((m, i) => (
        <div className="month-card" key={i}>
          <div className="month-header">
            <div className="month-label">{m.label}</div>
            <div className="month-meta">
              <div className="month-badges">
                {m.planned > 0 && <StatusPill tone="yellow" label={`${m.planned} ${t("Planned")}`} />}
                {m.completed > 0 && <StatusPill tone="green" label={`${m.completed} ${t("Completed")}`} />}
                {m.cancelled > 0 && <StatusPill tone="red" label={`${m.cancelled} ${t("Cancelled")}`} />}
                <StatusPill tone="gray" label={t("{rate}% done", { rate: m.completion_rate })} />
              </div>
              <div className="month-total">{m.total} {t("visits")}</div>
            </div>
          </div>

          <div className="month-grid">
            <div>
              <div className="month-foot-label" style={{ marginBottom: 6 }}>{t("Outcome")}</div>
              {m.outcomes.some((o) => o.count > 0) ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {m.outcomes.filter((o) => o.count > 0).map((o) => (
                    <span key={o.key} style={{ alignSelf: "flex-start", display: "inline-flex", alignItems: "center", gap: 4 }}>
                      {outcomeBadge(o.key, t)} <span style={{ fontSize: 11, color: "var(--muted-foreground)" }}>· {o.count}</span>
                    </span>
                  ))}
                </div>
              ) : (
                <span style={{ fontSize: 12, color: "var(--muted-foreground)" }}>{t("No completed visits")}</span>
              )}
              {m.total_value_sar > 0 && (
                <div className="month-foot-label" style={{ marginTop: 10 }}>
                  {t("Est. value")}: <span className="month-foot-val">{fmt(m.total_value_sar)} SAR</span>
                </div>
              )}
            </div>
            <div>
              <div className="month-foot-label" style={{ marginBottom: 6 }}>{t("Staff")}</div>
              <table className="recap-table">
                <thead>
                  <tr><th>{t("Staff")}</th><th className="r">{t("Done")}</th><th className="r">{t("Dist (m)")}</th><th className="r">{t("Value")}</th></tr>
                </thead>
                <tbody>
                  {m.staffs.map((s) => (
                    <tr key={s.name}>
                      <td style={{ fontWeight: 600 }}>{s.name}</td>
                      <td className="r">{s.completed}</td>
                      <td className="r mono">{fmt(s.distance_meters)}</td>
                      <td className="r mono">{s.value_sar ? fmt(s.value_sar) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {m.total_distance_meters > 0 && (
                <div className="month-foot-label" style={{ marginTop: 8 }}>
                  {t("Total distance")}: <span className="month-foot-val">{fmt(m.total_distance_meters)} m</span>
                </div>
              )}
            </div>
          </div>

          <div className="month-foot">
            <div style={{ display: "flex", gap: 16 }}>
              <span className="month-foot-label">{t("Total")}: <span className="month-foot-val">{m.total}</span></span>
              {m.total_value_sar > 0 && <span className="month-foot-label">{t("Est. value")}: <span className="month-foot-val">{fmt(m.total_value_sar)} SAR</span></span>}
            </div>
            <button type="button" className="btn btn-ghost" style={{ fontSize: 12, padding: 0 }} onClick={onOpenList}>{t("Open list")} →</button>
          </div>
        </div>
      )) : (
        <EmptyState iconName="visits" title="No visit data yet" />
      )}
    </div>
  );
}

function FragmentRow({ row, weekDays, byIso, openDay, t }) {
  return (
    <>
      <div className="visits-week-staff" title={row.name}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 12 }}>{row.name}</span>
      </div>
      {weekDays.map((iso) => {
        const list = (byIso[iso] || []).filter((v) => row.all || v.staff_id === row.id);
        return (
          <button
            key={iso}
            type="button"
            className="visits-week-cell"
            onClick={() => openDay(iso)}
            aria-label={`${iso}, ${list.length} ${t("visits")}`}
          >
            {list.slice(0, 2).map((v) => (
              <span key={v.id} className="visits-week-chip" style={chipColor(v.status)}>
                {v.start_time ? `${v.start_time} ` : ""}{v.client_name}
              </span>
            ))}
            {list.length > 2 && <span className="visits-cell-more">+{list.length - 2}</span>}
          </button>
        );
      })}
    </>
  );
}