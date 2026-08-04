import { useState } from "react";
import { Link } from "@inertiajs/react";
import UpcomingCheckins from "./UpcomingCheckins.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { Icon } from "../../components/icons.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Weekday initials indexed by Date#getDay() (0 = Sunday). English uses two
// letters; Indonesian needs three because Senin/Selasa/Sabtu all start with S.
const DOW_EN = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];
const DOW_ID = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"];

// Day-count–dependent grid CSS, injected per render because every
// grid-template-columns here interpolates the number of days in the month.
// Restyled 2026-07-30 onto the shadcn/Homlu token set (--card/--border/
// --foreground/--primary) — the legacy --surface/--text-*/--border-2/--r-*
// tokens this used before belong to design.css, which is the system being
// replaced. Homlu reserves hue for status only, so a *definite* reservation
// (the normal case, ~90% of blocks) is drawn in solid ink and only the
// exceptions — tentative, cancelled — carry color.
function gridCss(days) {
  return `
.cal-page { max-width:1180px; }
.cal-toolbar { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:14px; }
.cal-nav { display:flex; align-items:center; gap:2px; }
.cal-nav-btn { display:inline-flex; align-items:center; justify-content:center; width:32px; height:32px; border-radius:9999px; border:1px solid var(--border); background:var(--card); color:var(--muted-foreground); text-decoration:none; transition:background .12s,color .12s,border-color .12s; }
.cal-nav-btn:hover { background:var(--secondary); color:var(--foreground); border-color:var(--ring); }
.cal-month { font-size:15px; font-weight:600; color:var(--foreground); min-width:150px; text-align:center; letter-spacing:-.01em; font-variant-numeric:tabular-nums; }
.cal-legend { display:flex; gap:14px; align-items:center; flex-wrap:wrap; }
.cal-legend-item { display:flex; align-items:center; gap:6px; font-size:11.5px; color:var(--muted-foreground); }
.cal-legend-dot { width:9px; height:9px; border-radius:3px; flex-shrink:0; }

.cal-card { background:var(--card); border:1px solid var(--border); border-radius:20px; overflow:hidden; }
.cal-card-head { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:14px 18px; border-bottom:1px solid var(--border); flex-wrap:wrap; }
.cal-card-title { font-size:13px; font-weight:600; color:var(--foreground); }
.cal-card-sub { font-size:11.5px; color:var(--muted-foreground); }
.cal-stats { display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
.cal-stat { display:inline-flex; align-items:center; gap:5px; padding:4px 11px; border-radius:9999px; background:var(--secondary); color:var(--muted-foreground); font-size:11.5px; font-weight:400; white-space:nowrap; }
.cal-stat-val { font-weight:600; color:var(--foreground); font-variant-numeric:tabular-nums; }
.cal-stat.warn { background:color-mix(in oklch, var(--yellow) 16%, transparent); color:var(--yellow); }
.cal-stat.warn .cal-stat-val { color:var(--yellow); }
.cal-scroll { overflow-x:auto; -webkit-overflow-scrolling:touch; }

/* minmax(0,1fr), not minmax(34px,1fr): a floor of 34px made 31 day columns plus
   the hotel column add up to ~1222px inside an ~1138px card, so the month never
   fit and always needed sideways scrolling. With a zero floor the tracks divide
   whatever width there is and the whole month lands on screen at once.

   The hotel column is clamped rather than fixed: at a flat 140px two real
   hotels ("Maysan Al Maqam" / "Maysan Al Mashaer") both truncated to the same
   "Maysan Al …", but a width wide enough for them would squeeze the day tracks
   on smaller screens. clamp() spends spare width on the label when there is
   any and gives it back to the days when there is not. */
.cal-grid-template { display:grid; grid-template-columns:clamp(112px, 12vw, 182px) repeat(${days},minmax(0,1fr)); width:100%; }
.cal-hotel-th { padding:10px 14px; font-size:11px; font-weight:500; color:var(--muted-foreground); border-right:1px solid var(--border); background:var(--card); position:sticky; left:0; z-index:2; display:flex; align-items:center; }
.cal-day-th { padding:8px 0 9px; display:flex; flex-direction:column; align-items:center; gap:3px; border-right:1px solid var(--border); background:var(--card); line-height:1; min-width:0; }
.cal-day-th .dow { font-size:9px; font-weight:500; letter-spacing:.06em; text-transform:uppercase; color:var(--muted-foreground); }
.cal-day-th .num { display:flex; align-items:center; justify-content:center; min-width:20px; height:20px; padding:0 3px; border-radius:9999px; font-size:11.5px; font-weight:600; color:var(--foreground); font-variant-numeric:tabular-nums; }
/* Today marker: filled ink pill, the same monochrome emphasis Homlu uses for
   the selected day in its own date pickers — no brand hue involved. */
.cal-day-th.today .num { background:var(--primary); color:var(--primary-foreground); }
.cal-day-th.today .dow { color:var(--foreground); }

.cal-row { display:grid; grid-template-columns:clamp(112px, 12vw, 182px) repeat(${days},minmax(0,1fr)); grid-template-rows:0 1fr; border-top:1px solid var(--border); background:var(--card); width:100%; position:relative; }
.cal-row:hover .cal-hotel-name { background:var(--secondary); }
.cal-hotel-name { grid-column:1; grid-row:1 / span 2; padding:0 14px; display:flex; align-items:center; gap:7px; border-right:1px solid var(--border); position:sticky; left:0; background:var(--card); z-index:1; min-width:0; transition:background .12s; }
.cal-hotel-label { font-size:12.5px; font-weight:500; color:var(--foreground); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.cal-hotel-count { flex-shrink:0; min-width:18px; height:18px; padding:0 5px; border-radius:9999px; background:var(--secondary); color:var(--muted-foreground); font-size:10px; font-weight:600; display:flex; align-items:center; justify-content:center; font-variant-numeric:tabular-nums; }
/* Spans both template rows on purpose. .cal-row is grid-template-rows: 0 1fr
   so that .cal-blocks can overlay the day columns; auto-placed cells landed in
   that zero-height first row, which meant the vertical day separators and the
   today-column shading were being painted at 0px tall — invisible. Explicit
   placement (grid-column comes from the JSX) puts them full-height behind the
   bars instead. */
.cal-cell { grid-row:1 / span 2; border-right:1px solid var(--border); z-index:0; }
.cal-cell.today-col { background:color-mix(in oklch, var(--foreground) 9%, transparent); }

.cal-blocks { grid-column:2 / -1; grid-row:1 / span 2; display:grid; grid-template-columns:repeat(${days},minmax(0,1fr)); grid-auto-rows:26px; row-gap:4px; align-items:center; padding:9px 0; position:relative; z-index:1; min-height:48px; }
.cal-block { grid-row:1; height:26px; border-radius:8px; display:flex; align-items:center; padding:0 8px; font-size:10.5px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; text-decoration:none; margin:0 1.5px; min-width:0; transition:transform .12s cubic-bezier(.34,1.56,.64,1), box-shadow .12s, opacity .12s; }
.cal-block:hover { transform:translateY(-1px); z-index:5; box-shadow:0 4px 10px rgba(0,0,0,.16); }
/* Definite and tentative are both solid status fills. --primary-foreground is
   the label color for both, and it is doing real work rather than being a
   stylistic pick: design.css ships DARK green/amber in light mode (#15803D /
   #A16207) and BRIGHT ones in dark mode (#2ECC71 / #F5A623). --primary-foreground
   inverts on exactly the same axis — white in light, near-black in dark — so the
   label keeps 4.5:1+ against the fill in both themes. A hardcoded #fff would
   drop to roughly 2:1 on the bright dark-mode fills. */
.block-blue { background:var(--green); color:var(--primary-foreground); }
.block-yellow { background:var(--yellow); color:var(--primary-foreground); }
.block-green { background:var(--green); color:var(--primary-foreground); }
/* Cancelled stays de-emphasized: tinted surface + ring rather than a solid
   fill, so a dead booking never competes with the live ones for attention. */
.block-red { background:color-mix(in oklch, var(--red) 18%, var(--card)); color:var(--red); box-shadow:inset 0 0 0 1px color-mix(in oklch, var(--red) 42%, transparent); text-decoration:line-through; text-decoration-thickness:1px; }
.block-red:hover { box-shadow:inset 0 0 0 1px currentColor, 0 4px 10px rgba(0,0,0,.14); }

.cal-empty { display:flex; flex-direction:column; align-items:center; gap:6px; padding:64px 24px; color:var(--muted-foreground); }
.cal-empty-title { font-size:14px; font-weight:600; color:var(--foreground); }
.cal-empty-sub { font-size:12.5px; color:var(--muted-foreground); }

/* Tooltip: --popover surface + the two-layer soft shadow used by every other
   floating menu in this system (see .hms-ws-panel in tailwind.css). */
.cal-tooltip { position:fixed; background:var(--popover); border:1px solid var(--border); border-radius:16px; z-index:var(--z-overlay,500); pointer-events:none; min-width:250px; max-width:300px; box-shadow:0 10px 24px -6px rgba(0,0,0,.18), 0 4px 8px -4px rgba(0,0,0,.12); overflow:hidden; }
.tt-head { padding:13px 16px 11px; border-bottom:1px solid var(--border); display:flex; align-items:flex-start; justify-content:space-between; gap:10px; }
.tt-guest { font-size:13.5px; font-weight:600; color:var(--foreground); line-height:1.35; letter-spacing:-.01em; }
.tt-chip { flex-shrink:0; padding:2px 9px; border-radius:9999px; font-size:9.5px; font-weight:600; text-transform:uppercase; letter-spacing:.05em; background:var(--secondary); color:var(--muted-foreground); }
.tt-chip.tone-yellow { background:color-mix(in oklch, var(--yellow) 18%, transparent); color:var(--yellow); }
.tt-chip.tone-red { background:color-mix(in oklch, var(--red) 16%, transparent); color:var(--red); }
.tt-body { padding:11px 16px 13px; display:grid; grid-template-columns:66px 1fr; gap:7px 10px; align-items:baseline; }
.tt-label { font-size:11px; color:var(--muted-foreground); font-weight:400; }
.tt-val { font-size:12.5px; color:var(--foreground); font-weight:500; font-variant-numeric:tabular-nums; }
.tt-inv-section { border-top:1px solid var(--border); padding:10px 16px 12px; display:grid; grid-template-columns:66px 1fr; gap:7px 10px; align-items:baseline; }
.tt-inv-link { font-size:12.5px; font-weight:600; color:var(--foreground); text-decoration:underline; text-underline-offset:2px; }
.tt-sisa-val { font-size:12.5px; font-weight:600; font-variant-numeric:tabular-nums; }

/* Narrower desktops: the day tracks are already elastic, but the hotel column
   and the day-number pill are fixed, so they step down too — otherwise the pill
   is what stops the month from fitting at these widths. */
@media (min-width:601px) and (max-width:1150px){
  .cal-hotel-th, .cal-hotel-name { padding-left:10px; padding-right:10px; }
  .cal-hotel-label { font-size:11.5px; }
  .cal-hotel-count { display:none; }
  /* min-width:0, not a smaller fixed pill: the day number is the only fixed-size
     thing left in a day track, so any floor on it is what re-introduces overflow
     (and a scrollbar) once the elastic tracks drop below that floor. */
  .cal-day-th .num { min-width:0; height:18px; font-size:10.5px; padding:0 2px; }
  .cal-day-th .dow { font-size:8px; }
  .cal-block { padding:0 6px; font-size:10px; margin:0 1px; }
}
@media (min-width:601px) and (max-width:1000px){
  .cal-day-th .num { font-size:9.5px; padding:0 1px; }
  .cal-day-th .dow { display:none; }
  .cal-block { padding:0 4px; font-size:9.5px; }
}
@media (max-width:600px){
  .cal-page { padding:10px 0 80px; }
  .cal-toolbar { padding:0 14px; margin-bottom:10px; }
  .cal-legend { gap:10px; }
  .cal-legend-item { font-size:10.5px; }
  .cal-month { font-size:14px; min-width:120px; }
  .cal-card { border-radius:0; border-left:none; border-right:none; }
  .cal-card-head { padding:12px 14px; }
  .cal-stats { gap:5px; }
  .cal-stat { padding:3px 9px; font-size:10.5px; }
  .cal-grid-template { grid-template-columns:84px repeat(${days},minmax(32px,1fr)); min-width:calc(84px + ${days} * 32px); }
  .cal-row { grid-template-columns:84px repeat(${days},minmax(32px,1fr)); min-width:calc(84px + ${days} * 32px); }
  .cal-hotel-th { padding:8px 10px; font-size:10px; }
  .cal-hotel-name { padding:0 10px; gap:5px; }
  .cal-hotel-label { font-size:11px; }
  .cal-hotel-count { display:none; }
  .cal-day-th { padding:6px 0 7px; gap:2px; }
  .cal-day-th .dow { font-size:8px; }
  .cal-day-th .num { min-width:19px; height:19px; font-size:11px; }
  .cal-blocks { grid-template-columns:repeat(${days},minmax(32px,1fr)); grid-auto-rows:22px; row-gap:3px; min-height:40px; padding:7px 0; }
  .cal-block { font-size:9.5px; height:22px; padding:0 6px; border-radius:6px; margin:0 1px; }
  .cal-tooltip { position:fixed; bottom:80px; left:12px; right:12px; top:auto !important; max-width:100%; min-width:0; }
}`;
}

// Assign each reservation a lane (row) so that overlapping periods stack below
// each other instead of rendering on top of one another. Greedy interval packing:
// a reservation joins the first lane whose last block ends before it starts.
function packLanes(reservations) {
  const items = reservations.map((res, i) => ({ res, i }));
  items.sort((a, b) => a.res.start - b.res.start || a.res.end - b.res.end);
  const laneEnds = []; // last occupied day per lane
  for (const item of items) {
    let lane = laneEnds.findIndex((end) => item.res.start > end);
    if (lane === -1) { lane = laneEnds.length; laneEnds.push(item.res.end); }
    else { laneEnds[lane] = item.res.end; }
    item.lane = lane;
  }
  return items;
}

function countdown(checkin) {
  const ci = new Date(checkin);
  const now = new Date(); now.setHours(0, 0, 0, 0);
  const diff = Math.round((ci - now) / 86400000);
  if (diff === 0) return { key: "today", color: "var(--green)" };
  if (diff === 1) return { key: "tomorrow", color: "var(--yellow)" };
  if (diff > 0) return { key: "in", n: diff, color: diff <= 3 ? "var(--yellow)" : "" };
  return { key: "ago", n: Math.abs(diff), color: "var(--muted-foreground)" };
}

const TONE_BY_COLOR = { yellow: "tone-yellow", red: "tone-red" };

export default function Calendar(props) {
  const { t, locale } = useI18n();
  const { year, month, month_name, days, today_day, hotels, prev_year, prev_month, next_year, next_month,
    total_reservations, checkins_today, checkouts_today, tentative_count, active_today,
    upcoming_checkins = [], last_recap = null } = props;
  const [tip, setTip] = useState(null); // { res, x, y }

  const show = (e, res) => setTip({ res, x: e.clientX, y: e.clientY });
  const move = (e) => setTip((t) => (t ? { ...t, x: e.clientX, y: e.clientY } : t));
  const hide = () => setTip(null);

  let tx = 0, ty = 0;
  if (tip) {
    tx = tip.x + 14; ty = tip.y + 14;
    if (tx + 300 > window.innerWidth) tx = tip.x - 310;
    if (ty + 220 > window.innerHeight) ty = tip.y - 230;
  }
  const cd = tip?.res.check_in ? countdown(tip.res.check_in) : null;
  const cdText = cd
    ? (cd.key === "today" ? t("Today")
      : cd.key === "tomorrow" ? t("Tomorrow")
      : cd.key === "in" ? t("in {n} days", { n: cd.n })
      : t("{n} days ago", { n: cd.n }))
    : null;

  const DOW = locale === "id" ? DOW_ID : DOW_EN;
  const dowLabel = days.map((d) => DOW[new Date(year, month - 1, d).getDay()]);

  return (
    <div className="page shadcn-root cal-page">
      <style dangerouslySetInnerHTML={{ __html: gridCss(days.length) }} />

      <PageBack />

      <div className="page-header">
        <div>
          <div className="page-title">{t("Calendar")}</div>
          <div className="page-sub">{t("{count} reservations · {hotels} hotels", { count: total_reservations, hotels: hotels.length })}</div>
        </div>
        <div className="page-actions">
          {!today_day && (
            <Button variant="outline" size="sm" asChild>
              <Link href="/calendar/">{t("Today")}</Link>
            </Button>
          )}
        </div>
      </div>

      <div className="cal-toolbar">
        <div className="cal-nav">
          <Link className="cal-nav-btn" href={`/calendar/?year=${prev_year}&month=${prev_month}`} title={t("Previous month")} aria-label={t("Previous month")}>
            <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
          </Link>
          <span className="cal-month">{month_name} {year}</span>
          <Link className="cal-nav-btn" href={`/calendar/?year=${next_year}&month=${next_month}`} title={t("Next month")} aria-label={t("Next month")}>
            <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
          </Link>
        </div>
        <div className="cal-legend">
          <div className="cal-legend-item"><span className="cal-legend-dot" style={{ background: "var(--green)" }} />{t("Definite")}</div>
          <div className="cal-legend-item"><span className="cal-legend-dot" style={{ background: "var(--yellow)" }} />{t("Tentative")}</div>
          <div className="cal-legend-item"><span className="cal-legend-dot" style={{ background: "var(--red)" }} />{t("Cancelled")}</div>
        </div>
      </div>

      <div className="cal-card">
        <div className="cal-card-head">
          <div>
            <div className="cal-card-title">{t("Occupancy per Hotel")}</div>
            <div className="cal-card-sub">{t("Hover a bar to see reservation details")}</div>
          </div>
          {/* Today-relative counts, as a quiet stat strip rather than cards —
              they're context for the grid, not the point of the page. Browsing
              a past/future month they'd read as zeros instead of "n/a", so the
              three today-scoped ones are suppressed outside the current month. */}
          <div className="cal-stats">
            <span className="cal-stat"><span className="cal-stat-val">{total_reservations}</span> {t("reservations")}</span>
            {today_day && <span className="cal-stat"><span className="cal-stat-val">{active_today}</span> {t("active")}</span>}
            {today_day && <span className="cal-stat"><span className="cal-stat-val">{checkins_today}</span> {t("check-in")}</span>}
            {today_day && <span className="cal-stat"><span className="cal-stat-val">{checkouts_today}</span> {t("check-out")}</span>}
            {tentative_count > 0 && <span className="cal-stat warn"><span className="cal-stat-val">{tentative_count}</span> {t("tentative")}</span>}
          </div>
        </div>

        {hotels.length ? (
          <div className="cal-scroll">
            <div className="cal-grid-template" style={{ borderBottom: "1px solid var(--border)" }}>
              <div className="cal-hotel-th">{t("Hotel")}</div>
              {days.map((d, di) => (
                <div key={d} className={"cal-day-th" + (d === today_day ? " today" : "")}>
                  <span className="dow">{dowLabel[di]}</span>
                  <span className="num">{d}</span>
                </div>
              ))}
            </div>

            {hotels.map((hotel, hi) => (
              <div className="cal-row" key={hi}>
                <div className="cal-hotel-name" title={hotel.name}>
                  <span className="cal-hotel-label">{hotel.name}</span>
                  <span className="cal-hotel-count">{hotel.reservations.length}</span>
                </div>
                {days.map((d, di) => (
                  <div key={d} style={{ gridColumn: di + 2 }}
                    className={"cal-cell" + (d === today_day ? " today-col" : "")} />
                ))}
                <div className="cal-blocks">
                  {packLanes(hotel.reservations).map(({ res, i, lane }) => (
                    <a key={i} href={res.url} className={`cal-block block-${res.color}`}
                      style={{ gridColumn: `${res.start} / ${res.end + 1}`, gridRow: lane + 1 }}
                      onMouseEnter={(e) => show(e, res)} onMouseMove={move} onMouseLeave={hide}>
                      {res.guest || res.ref || t("No name")}
                    </a>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="cal-empty">
            <Icon name="calendar" size={34} strokeWidth={1.5} />
            <div className="cal-empty-title">{t("No reservations yet")}</div>
            <div className="cal-empty-sub">{month_name} {year}</div>
          </div>
        )}
      </div>

      {tip && (
        <div className="cal-tooltip" style={{ left: tx, top: ty }}>
          <div className="tt-head">
            <div className="tt-guest">{tip.res.guest || tip.res.ref || t("No name")}</div>
            <span className={"tt-chip " + (TONE_BY_COLOR[tip.res.color] || "")}>{tip.res.status}</span>
          </div>
          <div className="tt-body">
            <span className="tt-label">{t("CL No")}</span><span className="tt-val">{tip.res.ref}</span>
            <span className="tt-label">{t("CI / CO")}</span><span className="tt-val">{tip.res.start} – {tip.res.end} {month_name}</span>
            <span className="tt-label">{t("Check-in")}</span><span className="tt-val" style={{ color: cd?.color || undefined }}>{cdText}</span>
            <span className="tt-label">{t("Nights")}</span><span className="tt-val">{t("{n} nights", { n: tip.res.nights })}</span>
            <span className="tt-label">{t("Total")}</span><span className="tt-val">{tip.res.total}</span>
          </div>
          {tip.res.inv_number && (
            <div className="tt-inv-section">
              <span className="tt-label">{t("Invoice")}</span><a className="tt-inv-link" href={tip.res.inv_url || "#"}>{tip.res.inv_number}</a>
              <span className="tt-label">{t("Remaining")}</span>
              <span className="tt-sisa-val" style={{ color: (tip.res.inv_remaining && tip.res.inv_remaining !== "0 SAR") ? "var(--red)" : "var(--green)" }}>{tip.res.inv_remaining || "—"}</span>
            </div>
          )}
        </div>
      )}

      <UpcomingCheckins upcoming_checkins={upcoming_checkins} last_recap={last_recap} />
    </div>
  );
}
