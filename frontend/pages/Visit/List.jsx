import { useMemo, useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import Table from "../../components/shadcn/table.jsx";
import Pagination from "../../components/shadcn/pagination.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

const TABS = [
  { val: "schedule", label: "Schedule" },
  { val: "history", label: "History" },
];
const DAY_NAMES = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];
const HOUR_START = 8;
const HOUR_END = 18;
const RANGE_MIN = HOUR_START * 60;
const RANGE_MAX = HOUR_END * 60;

const STATUS_TONE = {
  COMPLETED: "green",
  CANCELLED: "red",
};

function statusBadge(s, t) {
  const tone = STATUS_TONE[s] || "yellow";
  const label = s === "COMPLETED" ? t("Completed") : s === "CANCELLED" ? t("Cancelled") : t("Planned");
  return <StatusPill tone={tone} label={label} />;
}

function statusClass(s) {
  const tone = STATUS_TONE[s] || "yellow";
  const map = { green: "badge-green", red: "badge-red", yellow: "badge-yellow" };
  return `badge ${map[tone] || "badge-gray"}`;
}

function toMin(s) {
  if (!s) return null;
  const [h, m] = s.split(":").map(Number);
  return h * 60 + m;
}

function blockColor(s) {
  if (s === "COMPLETED") return { bg: "var(--green-muted)", fg: "var(--green)", border: "1px solid color-mix(in oklch, var(--green) 40%, transparent)" };
  if (s === "CANCELLED") return { bg: "var(--red-muted)", fg: "var(--red)", border: "1px solid color-mix(in oklch, var(--red) 40%, transparent)" };
  return { bg: "var(--accent-muted)", fg: "var(--accent-2)", border: "1px solid color-mix(in oklch, var(--accent-2) 40%, transparent)" };
}

function blockStyle(v) {
  const start = toMin(v.start_time);
  if (start == null) return null;
  const end = toMin(v.end_time);
  const top = Math.max(start, RANGE_MIN) - RANGE_MIN;
  const bottom = end != null ? Math.min(end, RANGE_MAX) : RANGE_MIN + 60;
  const h = Math.max(bottom - top, 12);
  return { top: `${(top / (RANGE_MAX - RANGE_MIN)) * 100}%`, height: `${(h / (RANGE_MAX - RANGE_MIN)) * 100}%` };
}

function timeLabel(v) {
  if (v.start_time && v.end_time) return `${v.start_time}–${v.end_time}`;
  return v.start_time || v.end_time || "";
}

export default function List({ tab, selected_date, year, month, staff_filter, is_staff, staff_list, month_visits, visits, pagination, total_count }) {
  const { t } = useI18n();
  const perms = usePerms();
  const openForm = useFormModal();
  const [selDate, setSelDate] = useState(selected_date);
  const selY = Number(selDate.slice(0, 4)), selM = Number(selDate.slice(5, 7)), selD = Number(selDate.slice(8, 10));

  const go = (params, extra = {}) => {
    const p = new URLSearchParams({ tab: params.tab ?? tab });
    if (params.tab === "history") {
      p.delete("date");
    } else {
      if (params.date) p.set("date", params.date);
      else if (tab !== "history") p.set("date", params.date ?? selDate);
      if (params.staff != null) p.set("staff", params.staff);
    }
    if (params.page) p.set("page", params.page);
    router.get(`/visits/?${p.toString()}`, {}, { preserveState: true, preserveScroll: true, replace: true, ...extra });
  };

  const shiftMonth = (delta) => {
    const d = new Date(year, month - 1 + delta, 1);
    const target = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
    go({ date: target });
  };

  const pickDate = (iso) => {
    setSelDate(iso);
    go({ date: iso });
  };

  const byDay = useMemo(() => {
    const map = {};
    for (const v of month_visits || []) {
      (map[v.day] = map[v.day] || []).push(v);
    }
    for (const k of Object.keys(map)) map[k].sort((a, b) => (a.start_time || "99").localeCompare(b.start_time || "99"));
    return map;
  }, [month_visits]);

  const firstDow = new Date(year, month - 1, 1).getDay();
  const daysInMonth = new Date(year, month, 0).getDate();
  const cells = [];
  for (let i = 0; i < firstDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  while (cells.length % 7) cells.push(null);

  const todayStr = new Date().toISOString().slice(0, 10);
  const monthLabel = new Date(year, month - 1, 1).toLocaleDateString("en-US", { month: "long", year: "numeric" });
  const dayVisits = byDay[selD] || [];
  const timed = dayVisits.filter((v) => toMin(v.start_time) != null);
  const untimed = dayVisits.filter((v) => toMin(v.start_time) == null);

  return (
    <div className="page shadcn-root">
      <PageBack />
      <div className="page-header">
        <div>
          <div className="page-title">{t("Visits")}</div>
          <div className="page-sub">{t("{count} visits", { count: total_count })}</div>
        </div>
        <div className="page-actions">
          <a href="/visits/recap/" className="btn btn-secondary" style={{ height: 32, padding: "0 12px", fontSize: 13 }}>{t("Recap")}</a>
          {perms.can("visits", "create") && (
            <button type="button" onClick={() => openForm("/visits/new/")} className="btn btn-primary">{t("+ New Visit")}</button>
          )}
        </div>
      </div>

      <div className="filter-bar">
        <div className="fbar-actions">
          {TABS.map((tb) => (
            <button
              key={tb.val}
              type="button"
              className={"fbar-btn" + (tab === tb.val ? " active" : "")}
              onClick={() => go({ tab: tb.val })}
            >
              {t(tb.label)}
            </button>
          ))}
        </div>
        {tab === "schedule" && (
          <div className="fbar-actions" style={{ gap: 8 }}>
            {!is_staff && staff_list.length > 1 && (
              <select
                value={staff_filter || ""}
                onChange={(e) => go({ staff: e.target.value })}
                className="btn btn-secondary"
                style={{ height: 30, padding: "0 10px", fontSize: 12 }}
              >
                <option value="">{t("All staff")}</option>
                {staff_list.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            )}
            <button type="button" className="btn btn-secondary" style={{ height: 30, padding: "0 12px", fontSize: 12 }} onClick={() => pickDate(todayStr)}>
              {t("Today")}
            </button>
          </div>
        )}
      </div>

      {tab === "history" ? (
        <div className="card">
          {visits && visits.length ? (
            <>
              <Table
                columns={[
                  { header: t("Client"), className: "col-m-primary", render: (v) => v.client_name || "—" },
                  {
                    header: t("Status"), className: "col-m-badge",
                    render: (v) => statusBadge(v.status, t),
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
              <Pagination pagination={pagination} unit={t("visits")} onPage={(p) => go({ page: p })} />
            </>
          ) : (
            <EmptyState iconName="visits" title="No visits yet" sub="Use the Create New button in the top right" />
          )}
        </div>
      ) : (
        <>
          <div className="card" style={{ padding: 16, marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <button type="button" className="btn btn-ghost" style={{ fontSize: 14 }} onClick={() => shiftMonth(-1)}>←</button>
              <div style={{ fontWeight: 600, fontSize: 15 }}>{monthLabel}</div>
              <button type="button" className="btn btn-ghost" style={{ fontSize: 14 }} onClick={() => shiftMonth(1)}>→</button>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 6 }}>
              {DAY_NAMES.map((d) => (
                <div key={d} style={{ textAlign: "center", fontSize: 11, fontWeight: 600, color: "var(--muted-foreground)", padding: "2px 0" }}>{d}</div>
              ))}
              {cells.map((d, i) => {
                if (d == null) return <div key={i} />;
                const iso = `${year}-${String(month).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
                const list = byDay[d] || [];
                const isToday = iso === todayStr;
                const isSel = iso === selDate;
                return (
                  <button
                    key={i}
                    type="button"
                    onClick={() => pickDate(iso)}
                    className="cal-cell"
                    style={{
                      border: isSel ? "1px solid var(--primary)" : "1px solid var(--border)",
                      background: isToday ? "var(--accent)" : "transparent",
                      borderRadius: 8, padding: 6, textAlign: "left", minHeight: 52, cursor: "pointer",
                    }}
                  >
                    <div style={{ fontSize: 12, fontWeight: isToday ? 700 : 500, color: isToday ? "var(--primary)" : "inherit", marginBottom: 4 }}>{d}</div>
                    {list.slice(0, 2).map((v) => (
                      <div key={v.id} title={`${v.client_name} · ${timeLabel(v)}`} style={{ marginBottom: 2 }}>
                        <span className={statusClass(v.status)} style={{ padding: "0 6px", fontSize: 10, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "100%", display: "block" }}>
                          {timeLabel(v)} {v.client_name}
                        </span>
                      </div>
                    ))}
                    {list.length > 2 && <div style={{ fontSize: 10, color: "var(--muted-foreground)" }}>+{list.length - 2} {t("more")}</div>}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="card" style={{ padding: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, flexWrap: "wrap", gap: 8 }}>
              <div className="page-title" style={{ fontSize: 15 }}>
                {new Date(selY, selM - 1, selD).toLocaleDateString("en-US", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
              </div>
              {perms.can("visits", "create") && (
                <button type="button" className="btn btn-secondary" style={{ height: 28, padding: "0 10px", fontSize: 12 }} onClick={() => openForm("/visits/new/")}>
                  {t("+ Add on this day")}
                </button>
              )}
            </div>

            {dayVisits.length === 0 && (
              <EmptyState iconName="visits" title="No visits on this day" sub="Click + Add on this day to schedule one" />
            )}

            {timed.length > 0 && (
              <div style={{ position: "relative", height: 360, marginTop: 8, borderRadius: 8, border: "1px solid var(--border)", overflow: "hidden" }}>
                {Array.from({ length: (HOUR_END - HOUR_START) + 1 }, (_, i) => HOUR_START + i).map((h) => (
                  <div key={h} style={{ position: "absolute", left: 0, right: 0, top: `${((h - HOUR_START) / (HOUR_END - HOUR_START)) * 100}%`, borderTop: h === HOUR_START ? "none" : "1px solid var(--border)" }}>
                    <span style={{ position: "absolute", left: 6, fontSize: 10, color: "var(--muted-foreground)", transform: "translateY(-50%)" }}>{String(h).padStart(2, "0")}:00</span>
                  </div>
                ))}
                {timed.map((v) => {
                  const s = blockStyle(v);
                  const c = blockColor(v.status);
                  return (
                    <div key={v.id} onClick={() => router.visit(`/visits/${v.id}/`)} title={`${v.client_name} · ${timeLabel(v)} · ${v.status}`}
                      style={{ ...s, position: "absolute", left: 56, right: 8, borderRadius: 6, padding: "2px 8px", cursor: "pointer", fontSize: 12, overflow: "hidden", background: c.bg, color: c.fg, border: c.border, display: "flex", flexDirection: "column", justifyContent: "center" }}>
                      <div style={{ fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{v.client_name}</div>
                      {s && s.height && parseFloat(s.height) > 6 && (
                        <div style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", opacity: 0.85 }}>{timeLabel(v)}</div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {untimed.length > 0 && (
              <div style={{ marginTop: 10 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "var(--muted-foreground)", marginBottom: 6 }}>{t("No time set")}</div>
                {untimed.map((v) => {
                  const c = blockColor(v.status);
                  return (
                    <div key={v.id} onClick={() => router.visit(`/visits/${v.id}/`)} style={{ display: "flex", gap: 8, alignItems: "center", borderRadius: 6, padding: "4px 8px", marginBottom: 4, cursor: "pointer", fontSize: 12, background: c.bg, color: c.fg, border: c.border }}>
                      <span className={statusClass(v.status)}>{v.status === "COMPLETED" ? t("Completed") : v.status === "CANCELLED" ? t("Cancelled") : t("Planned")}</span>
                      <span style={{ fontWeight: 600 }}>{v.client_name}</span>
                      {!is_staff && <span style={{ color: "var(--muted-foreground)" }}>{v.staff_name}</span>}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
