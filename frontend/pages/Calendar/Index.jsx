import { useEffect, useState, useRef, useCallback } from "react";
import { Link, router } from "@inertiajs/react";
import axios from "axios";
import UpcomingCheckins from "./UpcomingCheckins.jsx";
import { ClientBlock, groupByClient } from "./UpcomingCheckins.jsx";
import ReservationSheet from "./ReservationSheet.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { Icon } from "../../components/icons.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { showToast } from "../../components/shadcn/toast.jsx";

// Same 600px check as components/shadcn/table.jsx's card-list switch — the
// occupancy grid is a Gantt chart and doesn't fit a phone screen at any
// density, so below this width it's swapped for a day-agenda view instead
// of just shrinking the grid further.
function useIsMobile(bp = 600) {
  const [m, setM] = useState(() => typeof window !== "undefined" && window.innerWidth <= bp);
  useEffect(() => {
    const mq = window.matchMedia(`(max-width:${bp}px)`);
    const fn = (e) => setM(e.matches);
    mq.addEventListener("change", fn);
    setM(mq.matches);
    return () => mq.removeEventListener("change", fn);
  }, [bp]);
  return m;
}

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

.cal-grid-template { display:grid; grid-template-columns:clamp(112px, 12vw, 182px) repeat(${days},minmax(0,1fr)); width:100%; }
.cal-hotel-th { padding:10px 14px; font-size:11px; font-weight:500; color:var(--muted-foreground); border-right:1px solid var(--border); background:var(--card); position:sticky; left:0; z-index:2; display:flex; align-items:center; }
.cal-day-th { padding:8px 0 9px; display:flex; flex-direction:column; align-items:center; gap:3px; border-right:1px solid var(--border); background:var(--card); line-height:1; min-width:0; }
.cal-day-th .dow { font-size:9px; font-weight:500; letter-spacing:.06em; text-transform:uppercase; color:var(--muted-foreground); }
.cal-day-th .num { display:flex; align-items:center; justify-content:center; min-width:20px; height:20px; padding:0 3px; border-radius:9999px; font-size:11.5px; font-weight:600; color:var(--foreground); font-variant-numeric:tabular-nums; }
.cal-day-th.today .num { background:var(--primary); color:var(--primary-foreground); }
.cal-day-th.today .dow { color:var(--foreground); }

.cal-row { display:grid; grid-template-columns:clamp(112px, 12vw, 182px) repeat(${days},minmax(0,1fr)); grid-template-rows:0 1fr; border-top:1px solid var(--border); background:var(--card); width:100%; position:relative; }
.cal-row:hover .cal-hotel-name { background:var(--secondary); }
.cal-hotel-name { grid-column:1; grid-row:1 / span 2; padding:0 14px; display:flex; align-items:center; gap:7px; border-right:1px solid var(--border); position:sticky; left:0; background:var(--card); z-index:1; min-width:0; transition:background .12s; }
.cal-hotel-label { font-size:12.5px; font-weight:500; color:var(--foreground); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.cal-hotel-count { flex-shrink:0; min-width:18px; height:18px; padding:0 5px; border-radius:9999px; background:var(--secondary); color:var(--muted-foreground); font-size:10px; font-weight:600; display:flex; align-items:center; justify-content:center; font-variant-numeric:tabular-nums; }
.cal-cell { grid-row:1 / span 2; border-right:1px solid var(--border); z-index:0; }
.cal-cell.today-col { background:color-mix(in oklch, var(--foreground) 9%, transparent); }

.cal-blocks { grid-column:2 / -1; grid-row:1 / span 2; display:grid; grid-template-columns:repeat(${days},minmax(0,1fr)); grid-auto-rows:26px; row-gap:4px; align-items:center; padding:9px 0; position:relative; z-index:1; min-height:48px; }
.cal-block { grid-row:1; height:26px; border-radius:8px; display:flex; align-items:center; padding:0 8px; font-size:10.5px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; text-decoration:none; margin:0 1.5px; min-width:0; transition:transform .12s cubic-bezier(.34,1.56,.64,1), box-shadow .12s, opacity .12s; }
.cal-block:hover { transform:translateY(-1px); z-index:5; box-shadow:0 4px 10px rgba(0,0,0,.16); }
.block-blue { background:var(--green); color:var(--primary-foreground); }
.block-yellow { background:var(--yellow); color:var(--primary-foreground); }
.block-green { background:var(--green); color:var(--primary-foreground); }
.block-red { background:color-mix(in oklch, var(--red) 18%, var(--card)); color:var(--red); box-shadow:inset 0 0 0 1px color-mix(in oklch, var(--red) 42%, transparent); text-decoration:line-through; text-decoration-thickness:1px; }
.block-red:hover { box-shadow:inset 0 0 0 1px currentColor, 0 4px 10px rgba(0,0,0,.14); }

.cal-empty { display:flex; flex-direction:column; align-items:center; gap:6px; padding:64px 24px; color:var(--muted-foreground); }
.cal-empty-title { font-size:14px; font-weight:600; color:var(--foreground); }
.cal-empty-sub { font-size:12.5px; color:var(--muted-foreground); }

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

@media (min-width:601px) and (max-width:1150px){
  .cal-hotel-th, .cal-hotel-name { padding-left:10px; padding-right:10px; }
  .cal-hotel-label { font-size:11.5px; }
  .cal-hotel-count { display:none; }
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
  .cal-page { padding:0 0 80px; }
  .cal-card { border-radius:0; border-left:none; border-right:none; border-top:none; }
  .cal-card-head { display:none; }
  .cal-legend { gap:10px; }
  .cal-legend-item { font-size:10.5px; }
  .cal-month { font-size:14px; min-width:120px; }
}

/* ── Mobile day-agenda (<=600px, swapped in by useIsMobile) ────────────── */
.cal-mob-wrap { display:flex; flex-direction:column; min-height:100dvh; }

/* Sticky month nav — stays pinned while user scrolls the agenda below */
.cal-mob-header { position:sticky; top:0; z-index:20; background:var(--background); padding:10px 14px 0; }
.cal-mob-nav { display:flex; align-items:center; justify-content:space-between; gap:8px; }
.cal-mob-nav-btn { display:inline-flex; align-items:center; justify-content:center; width:44px; height:44px; border-radius:12px; border:1px solid var(--border); background:var(--card); color:var(--muted-foreground); text-decoration:none; transition:background .12s,color .12s,border-color .12s; -webkit-tap-highlight-color:transparent; }
.cal-mob-nav-btn:active { background:var(--secondary); color:var(--foreground); transform:scale(.96); }
.cal-mob-month { font-size:16px; font-weight:700; color:var(--foreground); letter-spacing:-.02em; }

/* Stats strip — compact floating pills above day strip */
.cal-mob-stats { display:flex; gap:6px; padding:8px 14px 6px; overflow-x:auto; -webkit-overflow-scrolling:touch; scrollbar-width:none; }
.cal-mob-stats::-webkit-scrollbar { display:none; }
.cal-mob-stat { flex-shrink:0; display:inline-flex; align-items:center; gap:4px; padding:5px 12px; border-radius:9999px; background:var(--secondary); color:var(--muted-foreground); font-size:12px; font-weight:500; white-space:nowrap; }
.cal-mob-stat-val { font-weight:700; color:var(--foreground); font-variant-numeric:tabular-nums; }
.cal-mob-stat.warn { background:color-mix(in oklch, var(--yellow) 16%, transparent); color:var(--yellow); }
.cal-mob-stat.warn .cal-mob-stat-val { color:var(--yellow); }

/* Month grid — 7 columns, standard mobile calendar (Mantine MobileMonthView,
   iOS / Material 3). Weekday header + leading blanks; each day cell is a
   ~48px touch target. Days with an arrival show a subtle count marker. */
.cal-mgrid { padding:4px 12px 8px; }
.cal-mgrid-week { display:grid; grid-template-columns:repeat(7,1fr); margin-bottom:4px; }
.cal-mgrid-dow { text-align:center; font-size:10px; font-weight:600; letter-spacing:.05em; text-transform:uppercase; color:var(--muted-foreground); padding:4px 0; }
.cal-mgrid-cells { display:grid; grid-template-columns:repeat(7,1fr); gap:4px; }
.cal-mcell { position:relative; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:2px; aspect-ratio:1/.92; min-height:44px; border-radius:12px; border:1.5px solid transparent; background:none; cursor:pointer; -webkit-tap-highlight-color:transparent; transition:background .12s,border-color .12s,transform .1s; padding:0; }
.cal-mcell.blank { aspect-ratio:auto; min-height:44px; pointer-events:none; }
.cal-mcell:active { transform:scale(.94); }
.cal-mcell .num { font-size:14.5px; font-weight:600; color:var(--foreground); font-variant-numeric:tabular-nums; }
.cal-mcell .ev { position:absolute; top:4px; right:4px; min-width:15px; height:15px; padding:0 3px; border-radius:9999px; font-size:9px; font-weight:700; line-height:15px; text-align:center; font-variant-numeric:tabular-nums; }
.cal-mcell .ev.has { background:var(--primary); color:var(--primary-foreground); }
.cal-mcell.today { border-color:var(--border); }
.cal-mcell.today .num { color:var(--primary); font-weight:700; }
.cal-mcell.selected { background:var(--primary); border-color:var(--primary); }
.cal-mcell.selected .num { color:var(--primary-foreground); }
.cal-mcell.selected .ev.has { background:color-mix(in oklch, var(--primary-foreground) 24%, transparent); color:var(--primary-foreground); }
.cal-mcell:not(.blank):not(.selected):not(.today):hover { background:var(--secondary); }
/* Agenda header — full selected-date + quick "Today" jump */
.cal-agenda-head { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:14px 14px 4px; border-top:1px solid var(--border); }
.cal-agenda-head-date { font-size:15px; font-weight:700; color:var(--foreground); letter-spacing:-.01em; text-transform:capitalize; }
.cal-agenda-head-actions { display:flex; align-items:center; gap:8px; flex-shrink:0; }
.cal-agenda-today { flex-shrink:0; padding:7px 14px; border-radius:9999px; border:1px solid var(--border); background:var(--card); color:var(--foreground); font-size:12px; font-weight:600; cursor:pointer; -webkit-tap-highlight-color:transparent; transition:background .12s,border-color .12s,transform .1s; font-family:inherit; }
.cal-agenda-today:active { transform:scale(.96); background:var(--secondary); }
/* Agenda list */
.cal-agenda { padding:0 14px 16px; border-top:1px solid var(--border); flex:1; }

/* Unified agenda sections — "Check-ins" then "Staying" */
.cal-agenda-section + .cal-agenda-section { margin-top:22px; }
.cal-agenda-section-head { display:flex; align-items:center; gap:8px; margin:16px 2px 10px; }
.cal-agenda-section-title { font-size:13px; font-weight:700; color:var(--foreground); letter-spacing:-.01em; }
.cal-agenda-section-count { display:inline-flex; align-items:center; justify-content:center; min-width:20px; height:20px; padding:0 6px; border-radius:9999px; background:var(--secondary); color:var(--muted-foreground); font-size:11px; font-weight:600; font-variant-numeric:tabular-nums; }
.cal-agenda-section:first-child .cal-agenda-section-head { margin-top:4px; }

/* ── Check-in card (shared with UpcomingCheckins) ──────────────────────────
   Injected here too so BookingCard works when rendered directly in
   the unified agenda, not only inside the UpcomingCheckins DOM tree. */
.uc-booking { display:flex; flex-direction:column; background:var(--card); border:1px solid var(--border); border-radius:16px; padding:13px 14px; cursor:pointer; -webkit-tap-highlight-color:transparent; transition:transform .1s, border-color .12s; box-shadow:0 1px 2px rgba(0,0,0,.04); }
.uc-booking:active { transform:scale(.99); border-color:var(--ring); }
.uc-booking + .uc-booking { margin-top:10px; }

/* "Readiness" card — three checks (ETA / PIC / Reminder), green when done,
   red when outstanding. Tapping a row jumps to fixing it; tapping the card
   opens the detail sheet. */
.uc-bk-top { display:flex; align-items:baseline; justify-content:space-between; gap:10px; }
.uc-bk-hotel { font-size:14px; font-weight:600; color:var(--foreground); line-height:1.25; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.uc-bk-ref { flex-shrink:0; font-size:11px; font-weight:600; color:var(--muted-foreground); letter-spacing:.02em; font-variant-numeric:tabular-nums; }
.uc-bk-rooms { margin-top:2px; font-size:11.5px; color:var(--muted-foreground); }

.uc-bk-checks { margin-top:11px; display:flex; flex-direction:column; gap:5px; }
.uc-chk { display:flex; align-items:center; gap:8px; width:100%; min-height:34px; padding:2px 0; border:none; background:none; font-family:inherit; font-size:12px; text-align:left; color:var(--foreground); cursor:pointer; -webkit-tap-highlight-color:transparent; }
.uc-chk:disabled { cursor:default; }
.uc-chk-ico { flex-shrink:0; width:17px; height:17px; border-radius:9999px; display:flex; align-items:center; justify-content:center; }
.uc-chk.done .uc-chk-ico { background:color-mix(in oklch, var(--green) 16%, transparent); color:var(--green); }
.uc-chk.todo .uc-chk-ico { background:color-mix(in oklch, var(--red) 14%, transparent); color:var(--red); }
.uc-chk-k { color:var(--muted-foreground); }
.uc-chk-v { margin-left:auto; font-weight:600; font-variant-numeric:tabular-nums; max-width:60%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.uc-chk.todo .uc-chk-v { color:var(--red); font-weight:700; }
.uc-chk:not(:disabled):active .uc-chk-v { opacity:.55; }

/* Booking detail bottom sheet (rendered by imported BookingCard) */
.bs-head { padding:4px 4px 14px; display:flex; align-items:flex-start; justify-content:space-between; gap:10px; }
.bs-guest { font-size:17px; font-weight:700; color:var(--foreground); line-height:1.3; letter-spacing:-.02em; }
.bs-rsv { flex-shrink:0; font-size:12px; font-weight:600; color:var(--muted-foreground); padding:4px 10px; border-radius:9999px; background:var(--secondary); margin-top:2px; font-variant-numeric:tabular-nums; }
.bs-grid { padding:0 4px 14px; display:grid; grid-template-columns:84px 1fr; gap:10px 12px; align-items:baseline; }
.bs-label { font-size:12px; color:var(--muted-foreground); }
.bs-val { font-size:14px; color:var(--foreground); font-weight:500; font-variant-numeric:tabular-nums; }
.bs-val.is-empty { color:var(--muted-foreground); }
.bs-actions { display:flex; gap:8px; flex-wrap:wrap; padding:2px 4px 14px; }
.bs-act { flex:1; min-height:44px; }
.bs-editbar { display:flex; gap:10px; justify-content:flex-end; margin-top:4px; padding:12px 4px calc(4px + env(safe-area-inset-bottom)); border-top:1px solid var(--border); }
.bs-editbar > button { min-height:44px; padding-left:18px; padding-right:18px; }
.bs-form { display:flex; flex-direction:column; gap:12px; padding:0 4px 14px; }
.bs-form .uc-bb-field input { width:100%; height:40px; padding:0 10px; border:1px solid var(--border); border-radius:10px; background:var(--background); }
.bs-form .uc-bb-field input:focus { outline:none; border-color:var(--ring); }

/* Per-client group header (ClientBlock) */
.uc-tl-client { margin-top:8px; }
.uc-tl-client + .uc-tl-client { margin-top:16px; }
.uc-tl-client-head { display:flex; align-items:center; gap:8px; padding:0 2px 8px; }
.uc-tl-client-name { font-size:13.5px; font-weight:700; color:var(--foreground); letter-spacing:-.01em; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.uc-tl-client-count { font-size:11px; color:var(--muted-foreground); flex-shrink:0; }

/* 2-zone arrival card: reservation number (primary) + guest + form fields */
.uc-bb-head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.uc-bb-id { min-width:0; flex:1; }
.uc-bb-conf { display:block; font-size:18px; font-weight:800; letter-spacing:-.01em; color:var(--foreground); line-height:1.2; font-variant-numeric:tabular-nums; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.uc-bb-guest { display:block; font-size:13.5px; font-weight:600; color:var(--foreground); margin-top:2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; text-decoration:none; }
.uc-bb-guest:active { opacity:.7; }
.uc-bb-form { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); column-gap:14px; row-gap:8px; margin-top:12px; align-items:start; }
.uc-bb-field--full { grid-column:1 / -1; }
.uc-bb-field { display:flex; flex-direction:column; gap:2px; min-width:0; }
.uc-bb-label { font-size:11.5px; font-weight:500; color:var(--muted-foreground); }
.uc-bb-viewval { font-size:13.5px; font-weight:600; color:var(--foreground); font-variant-numeric:tabular-nums; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.uc-bb-viewval.is-empty { color:var(--muted-foreground); font-weight:500; }
.uc-bb-edit { flex-shrink:0; margin-top:2px; min-height:44px; padding:0 14px; }
.uc-booking-left .uc-bb-action, .uc-tl-client-head .uc-bb-action { min-height:44px; padding:0 14px; }
.uc-bb-foot { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-top:12px; }
.uc-bb-right { display:flex; align-items:center; gap:8px; min-width:0; margin-left:auto; }
.uc-rem { display:inline-flex; align-items:center; gap:3px; font-size:10px; font-weight:600; padding:3px 8px 3px 7px; border-radius:9999px; text-transform:uppercase; letter-spacing:.04em; white-space:nowrap; min-height:26px; }
.uc-rem svg { flex-shrink:0; }
.uc-rem.sent { background:color-mix(in oklch, var(--green) 16%, transparent); color:var(--green); }
.uc-rem.failed { background:color-mix(in oklch, var(--red) 15%, transparent); color:var(--red); }

.cal-agenda-empty { padding:48px 24px; text-align:center; color:var(--muted-foreground); }
.cal-agenda-empty-icon { display:flex; justify-content:center; color:var(--muted-foreground); opacity:.5; margin-bottom:8px; }
.cal-agenda-empty-title { font-size:15px; font-weight:600; color:var(--foreground); margin-bottom:4px; }
.cal-agenda-empty-sub { font-size:12.5px; color:var(--muted-foreground); margin-bottom:16px; }

/* Full-width reservation cards instead of compact rows */
.cal-agenda-card { display:flex; align-items:center; gap:12px; padding:14px; border-radius:16px; background:var(--secondary); text-decoration:none; min-height:56px; transition:background .12s,transform .1s,box-shadow .12s; -webkit-tap-highlight-color:transparent; box-shadow:inset 0 0 0 1px transparent; }
.cal-agenda-card:active { transform:scale(.985); background:color-mix(in oklch, var(--secondary) 70%, var(--foreground)); }
.cal-agenda-card + .cal-agenda-card { margin-top:8px; }
.cal-agenda-dot { width:10px; height:10px; border-radius:9999px; flex-shrink:0; }
.cal-agenda-dot.dot-green { background:var(--green); }
.cal-agenda-dot.dot-yellow { background:var(--yellow); }
.cal-agenda-dot.dot-red { background:var(--red); }
.cal-agenda-main { min-width:0; flex:1; }
.cal-agenda-guest { display:block; font-size:14px; font-weight:600; color:var(--foreground); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; line-height:1.3; }
.cal-agenda-card.cancelled .cal-agenda-guest { color:var(--red); text-decoration:line-through; text-decoration-thickness:1px; }
.cal-agenda-info { display:block; font-size:13px; font-weight:500; color:var(--foreground); margin-top:2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.cal-agenda-dates { display:block; font-size:11.5px; font-weight:400; color:var(--muted-foreground); margin-top:2px; font-variant-numeric:tabular-nums; }
.cal-agenda-due { flex-shrink:0; padding:4px 10px; border-radius:9999px; background:color-mix(in oklch, var(--red) 12%, transparent); font-size:12px; font-weight:600; color:var(--red); }
.cal-agenda-chevron { flex-shrink:0; color:var(--muted-foreground); opacity:.4; }

/* Pull-to-refresh indicator */
.cal.ptr-indicator { display:flex; align-items:center; justify-content:center; height:0; overflow:hidden; color:var(--muted-foreground); font-size:12px; transition:height .2s ease; }
.cal.ptr-indicator.visible { height:40px; }
.cal.ptr-spinner { width:18px; height:18px; border:2px solid var(--border); border-top-color:var(--foreground); border-radius:9999px; animation:cal-spin .6s linear infinite; margin-right:8px; }
@keyframes cal-spin { to { transform:rotate(360deg); } }
`;
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

  const isMobile = useIsMobile();
  const [selectedDay, setSelectedDay] = useState(() => today_day || days[0]);
  const [sheetRes, setSheetRes] = useState(null); // bottom sheet reservation
  const [ptrActive, setPtrActive] = useState(false); // pull-to-refresh
  const daystripRef = useRef(null);
  const touchStartY = useRef(0);
  const touchStartX = useRef(0);
  const [sendingRecap, setSendingRecap] = useState(false);

  // Unified day-centric mobile view: the calendar month + upcoming check-ins
  // share one screen. Selecting a day reveals both who is STAYING that day
  // (occupancy) and who ARRIVES that day (check-ins) in a single agenda.
  const pad = (n) => String(n).padStart(2, "0");
  const dayYMD = (d) => `${year}-${pad(month)}-${pad(d)}`;
  const arrivalsByDay = {};
  upcoming_checkins.forEach((cl) => {
    const k = cl.check_in || "";
    (arrivalsByDay[k] = arrivalsByDay[k] || []).push(cl);
  });
  const arrivalsThisDay = arrivalsByDay[dayYMD(selectedDay)] || [];

  // Front-desk grouping for the selected day — mirrors the industry-standard
  // Arrivals / Departures / In-house queue used by Cloudbeds, Opera, TwikPMS,
  // QloApps and Willba mobile apps (see research 2026-08-27).
  const dayRes = [];
  hotels.forEach((h) => h.reservations.forEach((r) => dayRes.push({ ...r, hotel: h.name })));
  const departuresThisDay = dayRes.filter((r) => r.end === selectedDay);
  const inHouseThisDay = dayRes.filter((r) => r.start < selectedDay && r.end > selectedDay);

  // Arrivals prefer the rich check-in cards (ETA/PIC/reminders) when available
  // (only the next-7-day window carries them); otherwise fall back to the
  // occupancy rows that start on the selected day.
  const arrivalsFallback = dayRes.filter((r) => r.start === selectedDay);

  // ── Month grid (mobile best practice): 7-column calendar with leading
  //    blanks, like Mantine MobileMonthView / iOS / Material 3 calendars.
  //    Every day with an arrival carries a small count badge; tapping a cell
  //    drives the agenda below. ──
  const daysInMonth = new Date(year, month, 0).getDate();
  const firstWeekday = new Date(year, month - 1, 1).getDay(); // 0 = Sunday ↔ DOW
  const arrivalsByMonthDay = {};
  hotels.forEach((h) => h.reservations.forEach((r) => {
    if (r.color !== "red" && r.start >= 1 && r.start <= daysInMonth) {
      arrivalsByMonthDay[r.start] = (arrivalsByMonthDay[r.start] || 0) + 1;
    }
  }));
  upcoming_checkins.forEach((cl) => {
    const ymd = cl.check_in || "";
    if (ymd.startsWith(`${year}-${pad(month)}-`)) {
      const d = parseInt(ymd.slice(8), 10);
      if (!Number.isNaN(d)) arrivalsByMonthDay[d] = (arrivalsByMonthDay[d] || 0) + 1;
    }
  });
  const hasArrival = (d) => (arrivalsByMonthDay[d] || 0) > 0;
  const arrivalCount = (d) => arrivalsByMonthDay[d] || 0;
  const gridCells = [];
  for (let i = 0; i < firstWeekday; i++) gridCells.push(null); // leading blanks
  for (let d = 1; d <= daysInMonth; d++) gridCells.push(d);
  const isTodaySelected = selectedDay === today_day;

  // Re-anchor when navigating months
  useEffect(() => { setSelectedDay(today_day || days[0]); }, [year, month]);

  // Auto-scroll the month grid so the selected day stays in view
  useEffect(() => {
    if (!isMobile || !daystripRef.current) return;
    const cells = daystripRef.current.querySelectorAll(".cal-mcell");
    const idx = gridCells.findIndex((d) => d === selectedDay);
    if (idx >= 0 && cells[idx]) {
      cells[idx].scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [isMobile, selectedDay, year, month]);

  // Desktop tooltip handlers
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
  const selectedDateLabel = `${DOW[new Date(year, month - 1, selectedDay).getDay()]}, ${selectedDay} ${month_name} ${year}`;

  // ── Mobile: swipe horizontal = month nav, swipe vertical = pull-to-refresh ──
  const handleTouchStart = useCallback((e) => {
    touchStartX.current = e.touches[0].clientX;
    touchStartY.current = e.touches[0].clientY;
  }, []);

  const handleTouchEnd = useCallback((e) => {
    const dx = e.changedTouches[0].clientX - touchStartX.current;
    const dy = e.changedTouches[0].clientY - touchStartY.current;
    const onSwipeCard = e.target.closest(".uc-booking") || e.target.closest(".cal-agenda-card");
    // Arrival cards and agenda cards own their horizontal gesture; only the
    // header / day strip should drive month navigation.
    if (onSwipeCard) return;
    // Only trigger if horizontal swipe is dominant (>80px) and vertical is small
    if (Math.abs(dx) > 80 && Math.abs(dy) < 50) {
      if (dx < 0) {
        // Swipe left → next month
        router.visit(`/calendar/?year=${next_year}&month=${next_month}`, { preserveState: true, replace: true });
      } else {
        // Swipe right → prev month
        router.visit(`/calendar/?year=${prev_year}&month=${prev_month}`, { preserveState: true, replace: true });
      }
    }
    // Pull-to-refresh: swipe down when scrolled to top
    if (dy > 100 && Math.abs(dx) < 30 && window.scrollY < 10) {
      setPtrActive(true);
      router.reload({ onFinish: () => setPtrActive(false) });
    }
  }, [next_year, next_month, prev_year, prev_month]);

  const handleSendRecap = async () => {
    if (sendingRecap) return;
    setSendingRecap(true);
    try {
      const r = await axios.post(
        '/calendar/send-recap/',
        new URLSearchParams({ date: dayYMD(selectedDay) }),
        { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
      );
      showToast(r.data.ok ? t('Recap queued.') : (r.data.message || t('Failed to send recap')), r.data.ok ? 'success' : 'error');
    } catch { showToast(t('Failed to send recap'), 'error'); }
    setSendingRecap(false);
  };

  // Bottom sheet countdown
  const sheetCd = sheetRes?.check_in ? countdown(sheetRes.check_in) : null;

  const handleAgendaTap = (e, res) => {
    e.preventDefault();
    setSheetRes(res);
  };

  // Occupancy card shown in the Arrivals/Departures/In-house sections (tap
  // opens the bottom sheet; elsewhere these are grouped by hotel).
  const OccCard = (res) => {
    const due = res.inv_number && res.inv_remaining && res.inv_remaining !== "0 SAR";
    return (
      <a key={res.ref + res.start} href={res.url} className={"cal-agenda-card" + (res.color === "red" ? " cancelled" : "")}
        onClick={(e) => handleAgendaTap(e, res)}>
        <span className={"cal-agenda-dot dot-" + res.color} />
        <span className="cal-agenda-main">
          <span className="cal-agenda-guest">{res.guest || res.ref || t("No name")}</span>
          <span className="cal-agenda-info">
            {res.hotel}
            <span className="cal-agenda-dates">{res.start}–{res.end} {month_name} · {t("{n} nights", { n: res.nights })}</span>
          </span>
        </span>
        {due && <span className="cal-agenda-due">{res.inv_remaining}</span>}
        <span className="cal-agenda-chevron">
          <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
        </span>
      </a>
    );
  };

  return (
    <div className="page shadcn-root cal-page">
      <style dangerouslySetInnerHTML={{ __html: gridCss(days.length) }} />

      <PageBack />

      {isMobile ? (
        /* ═══ MOBILE LAYOUT ═══
           Unified day-centric view (2026-08-27): calendar month and upcoming
           check-ins live on ONE screen. Swipe/select a day in the strip to see,
           in a single agenda: who ARRIVES that day (swipeable check-in cards)
           and who STAYS that day (occupancy, grouped by hotel). */
        <div className="cal-mob-wrap"
          onTouchStart={handleTouchStart} onTouchEnd={handleTouchEnd}>
          {/* Pull-to-refresh indicator */}
          <div className={"cal ptr-indicator" + (ptrActive ? " visible" : "")}>
            <span className="cal ptr-spinner" />{t("Refreshing…")}
          </div>

          {/* Sticky header: month nav + compact stats */}
          <div className="cal-mob-header">
            <div className="cal-mob-nav">
              <Link className="cal-mob-nav-btn" href={`/calendar/?year=${prev_year}&month=${prev_month}`}
                aria-label={t("Previous month")}>
                <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
              </Link>
              <span className="cal-mob-month">{month_name} {year}</span>
              <Link className="cal-mob-nav-btn" href={`/calendar/?year=${next_year}&month=${next_month}`}
                aria-label={t("Next month")}>
                <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
              </Link>
            </div>
            <div className="cal-mob-stats">
              <span className="cal-mob-stat"><span className="cal-mob-stat-val">{total_reservations}</span> {t("reservations")}</span>
              {today_day && <span className="cal-mob-stat"><span className="cal-mob-stat-val">{checkins_today}</span> {t("check-in")}</span>}
              {today_day && <span className="cal-mob-stat"><span className="cal-mob-stat-val">{checkouts_today}</span> {t("check-out")}</span>}
              {tentative_count > 0 && <span className="cal-mob-stat warn"><span className="cal-mob-stat-val">{tentative_count}</span> {t("tentative")}</span>}
            </div>
          </div>

          {/* Month grid — the mobile calendar (grid + day agenda pattern). */}
          <div className="cal-mgrid" ref={daystripRef} role="grid" aria-label={t("Select day")} aria-colcount="7">
            <div className="cal-mgrid-week" role="row">
              {DOW.map((d, i) => <span key={i} role="columnheader" className="cal-mgrid-dow">{d}</span>)}
            </div>
            <div className="cal-mgrid-cells">
              {gridCells.map((d, gi) =>
                d === null ? (
                  <span key={`b${gi}`} role="gridcell" className="cal-mcell blank" />
                ) : (
                  <button key={d} type="button" role="gridcell"
                    aria-selected={d === selectedDay}
                    aria-label={`${d} ${month_name}${hasArrival(d) ? `, ${arrivalCount(d)} ${t("Arrival")}` : ""}`}
                    className={"cal-mcell" + (d === selectedDay ? " selected" : "") + (d === today_day ? " today" : "")}
                    onClick={() => setSelectedDay(d)}>
                    <span className="num">{d}</span>
                    <span className={"ev" + (hasArrival(d) ? " has" : "")}>{hasArrival(d) ? arrivalCount(d) : ""}</span>
                  </button>
                )
              )}
            </div>
          </div>

          {/* Front-desk agenda for the selected day: Arrivals / Departures /
              In-house — the same three buckets a PMS must show the operator. */}
          <div className="cal-agenda-head">
            <span className="cal-agenda-head-date">{selectedDateLabel}</span>
            <div className="cal-agenda-head-actions">
              <Button variant="outline" size="sm" onClick={handleSendRecap} disabled={sendingRecap}>
                {sendingRecap ? '…' : <><Icon name="message" className="size-3.5" /> {t("Send Recap")}</>}
              </Button>
              {!isTodaySelected && today_day && (
                <button type="button" className="cal-agenda-today" onClick={() => setSelectedDay(today_day)}>
                  {t("Today")}
                </button>
              )}
            </div>
          </div>
          <div className="cal-agenda">
            {(arrivalsThisDay.length || arrivalsFallback.length || departuresThisDay.length || inHouseThisDay.length) ? (
              <>
                    {arrivalsThisDay.length > 0 && (
                      <div className="cal-agenda-section">
                        <div className="cal-agenda-section-head">
                          <span className="cal-agenda-section-title">{t("Arrivals")}</span>
                          <span className="cal-agenda-section-count">{arrivalsThisDay.length}</span>
                        </div>
                        {Object.entries(groupByClient(arrivalsThisDay)).map(([key, group]) => (
                          <ClientBlock key={key} clientName={group.name} cls={group.items} isMobile />
                        ))}
                      </div>
                    )}
                {arrivalsThisDay.length === 0 && arrivalsFallback.length > 0 && (
                  <div className="cal-agenda-section">
                    <div className="cal-agenda-section-head">
                      <span className="cal-agenda-section-title">{t("Arrivals")}</span>
                      <span className="cal-agenda-section-count">{arrivalsFallback.length}</span>
                    </div>
                    {arrivalsFallback.map((res) => OccCard(res))}
                  </div>
                )}
                {inHouseThisDay.length > 0 && (
                  <div className="cal-agenda-section">
                    <div className="cal-agenda-section-head">
                      <span className="cal-agenda-section-title">{t("In-house")}</span>
                      <span className="cal-agenda-section-count">{inHouseThisDay.length}</span>
                    </div>
                    {inHouseThisDay.map((res) => OccCard(res))}
                  </div>
                )}
                {departuresThisDay.length > 0 && (
                  <div className="cal-agenda-section">
                    <div className="cal-agenda-section-head">
                      <span className="cal-agenda-section-title">{t("Departures")}</span>
                      <span className="cal-agenda-section-count">{departuresThisDay.length}</span>
                    </div>
                    {departuresThisDay.map((res) => OccCard(res))}
                  </div>
                )}
              </>
            ) : (
              <div className="cal-agenda-empty">
                <div className="cal-agenda-empty-icon">
                  <Icon name="calendar" size={36} strokeWidth={1.2} />
                </div>
                <div className="cal-agenda-empty-title">{t("Nothing this day")}</div>
                <div className="cal-agenda-empty-sub">{t("No arrivals, departures or in-house guests on this day")}</div>
              </div>
            )}
          </div>

          {/* Bottom sheet for reservation details */}
          {sheetRes && (
            <ReservationSheet res={sheetRes} cd={sheetCd} onClose={() => setSheetRes(null)} />
          )}
        </div>
      ) : (
        /* ═══ DESKTOP LAYOUT (unchanged) ═══ */
        <>
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
        </>
      )}

      {!isMobile && <UpcomingCheckins upcoming_checkins={upcoming_checkins} last_recap={last_recap} />}
    </div>
  );
}
