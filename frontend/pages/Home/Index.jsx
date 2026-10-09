import { useEffect, useRef, useState } from "react";
import { usePage } from "@inertiajs/react";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell } from "recharts";
import { fetchJson } from "../../utils/fetchJson.js";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";
import { fmt as fmtNum, fmtDateShort } from "../../utils/format.js";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import { Icon } from "../../components/icons.jsx";
import { heatColor } from "../../components/mapColors.js";
import mapSvg from "../../assets/id.svg?raw";

const CSS = `
/* Home dashboard — Homlu token set (measured off the live
   homlu-dashboard-template.vercel.app reference). Reserved hue for status
   only: KPI ink and the trend area are monochrome (--foreground/--primary),
   color is used solely for the delta badges, status pills, and the unpaid
   warning. */
.hms-home { padding: 4px 24px 40px; max-width: 1280px; }
.hms-home-head { display:flex; align-items:flex-end; justify-content:space-between; gap:20px; margin-bottom:16px; flex-wrap:wrap; }
.hms-home-title { font-size:26px; font-weight:600; letter-spacing:-.024em; line-height:1.1; color:var(--foreground); margin:0; }
.hms-home-date { font-size:12.5px; color:var(--muted-foreground); margin-top:4px; font-variant-numeric:tabular-nums; }
.hms-home-head-actions { display:flex; gap:9px; flex-shrink:0; }
.hms-btn-outline, .hms-btn-primary {
  height:38px; display:inline-flex; align-items:center; justify-content:center; gap:8px;
  padding:0 17px; border-radius:9999px; font-family:inherit; font-size:12.5px; font-weight:600;
  cursor:pointer; white-space:nowrap; text-decoration:none; transition:background .12s, border-color .12s;
}
.hms-btn-outline { border:1px solid var(--input); background:var(--card); color:var(--foreground); }
.hms-btn-outline:hover { border-color:var(--foreground); }
.hms-btn-primary { border:1px solid var(--primary); background:var(--primary); color:var(--primary-foreground); padding:0 18px; }
.hms-btn-primary:hover { background:var(--primary-hover); border-color:var(--primary-hover); }

/* "Saldo kas" strip — the row element reuses .hms-kpi-row verbatim (see
   JSX) so its width, column count and every breakpoint are byte-identical
   to the KPI board above it; this block only styles the cells inside. */
.hms-cash {
  display:flex; align-items:center; justify-content:space-between; gap:12px;
  padding:16px 18px; background:var(--card);
}
.hms-cash-label { font-size:12px; font-weight:500; color:var(--muted-foreground); }
.hms-cash-val { margin-top:7px; font-size:19px; font-weight:600; letter-spacing:-.02em; color:var(--foreground); font-variant-numeric:tabular-nums; }
.hms-cash-cur { margin-left:5px; font-size:10.5px; font-weight:600; color:var(--muted-foreground); letter-spacing:0; }
.hms-cash-badge {
  flex:none; height:22px; padding:0 10px;
  display:inline-flex; align-items:center;
  border:1px solid var(--input); border-radius:9999px;
  font-size:11px; font-weight:600; color:var(--muted-foreground); white-space:nowrap;
}
@media (max-width:600px) {
  .hms-cash { padding:13px 15px; }
  .hms-cash-val { font-size:17px; }
  .hms-cash-badge { display:none; }
}

/* Panel grid — wide chart card + recent-CLs card, Homlu's 12-col rhythm
   (lg:grid-cols-12 with a 7/5 split) approximated with fr units. Both cards
   stretch to the same height; the chart fills the slack so a taller table
   never leaves a gap under the chart. */
.hms-home-grid { display:grid; grid-template-columns:1fr; gap:20px; }
@media (min-width:900px) {
  .hms-home-grid { grid-template-columns:minmax(0,7fr) minmax(0,5fr); align-items:stretch; }
}
/* Grid stretches both cards to the row height (set by the taller one); for the
   chart to consume the slack instead of leaving a dead band, the card is a
   flex column and the body flexes — the chart-wrap then grows to fill. */
.hms-home-grid > .hms-dv-card,
.hms-home-grid2 > .hms-dv-card,
.hms-home-grid3 > .hms-dv-card { display:flex; flex-direction:column; }
.hms-home-grid > .hms-dv-card > .hms-dv-body,
.hms-home-grid2 > .hms-dv-card > .hms-dv-body,
.hms-home-grid3 > .hms-dv-card > .hms-dv-body { flex:1; }
.hms-chart-legend { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:8px; }
.hms-chart-total { font-size:22px; font-weight:600; letter-spacing:-.02em; color:var(--foreground); font-variant-numeric:tabular-nums; line-height:1.1; }
.hms-chart-total-sub { font-size:12px; color:var(--muted-foreground); margin-top:2px; }
/* Period segmented control — Homlu pill group: track in --secondary, the
   active tab lifted on --card with a soft shadow. */
.hms-chart-tabs { display:inline-flex; align-items:center; gap:2px; background:var(--secondary); border:1px solid var(--border); border-radius:9999px; padding:3px; flex-shrink:0; }
.hms-chart-tab { border:none; background:transparent; color:var(--muted-foreground); font-size:11.5px; font-weight:500; font-family:inherit; padding:4px 10px; border-radius:9999px; cursor:pointer; transition:color .12s,background .12s,box-shadow .12s; }
.hms-chart-tab:hover { color:var(--foreground); }
.hms-chart-tab.active { background:var(--card); color:var(--foreground); box-shadow:0 1px 3px rgba(0,0,0,.12); }
.hms-home-chart { min-height:400px; }
.hms-home-chart .hms-dv-body { display:flex; flex-direction:column; }
.hms-chart-wrap { width:100%; flex:1 1 auto; height:250px; margin-top:6px; }
/* Recharts axis ticks: keep the grid faint and the labels muted, exactly the
   reference's quiet gridlines. */
.hms-chart-wrap .recharts-cartesian-axis-tick text { fill:var(--muted-foreground); font-size:11px; }
.hms-chart-wrap .recharts-cartesian-grid line { stroke:var(--border); }
.hms-chart-wrap .recharts-cartesian-grid-horizontal line:first-child { display:none; }
.hms-chart-tip { background:var(--popover); border:1px solid var(--border); border-radius:12px; padding:8px 12px; box-shadow:0 10px 24px -6px rgba(0,0,0,.18), 0 4px 8px -4px rgba(0,0,0,.12); }
.hms-chart-tip-label { font-size:11px; color:var(--muted-foreground); font-weight:500; }
.hms-chart-tip-val { font-size:15px; font-weight:600; color:var(--foreground); margin-top:1px; font-variant-numeric:tabular-nums; }
.hms-home-empty { font-size:13px; color:var(--muted-foreground); padding:14px 0 6px; }

/* All dashboard panels share one padding rhythm; the card classes keep
   the mobile rule in this block so .hms-dv-body's media query still applies. */
.hms-home-card .hms-dv-body,
.hms-home-chart .hms-dv-body,
.hms-home-donut .hms-dv-body,
.hms-home-hotels .hms-dv-body,
.hms-home-map .hms-dv-body,
.hms-home-funnel .hms-dv-body { padding:24px 24px 16px; }
@media (max-width:600px) {
  .hms-home-card .hms-dv-body,
  .hms-home-chart .hms-dv-body,
  .hms-home-donut .hms-dv-body,
  .hms-home-hotels .hms-dv-body,
  .hms-home-map .hms-dv-body,
  .hms-home-funnel .hms-dv-body { padding:20px 16px 12px; }

  /* doc 01 1c: no dashboard action buttons on mobile; tighter title */
  .hms-home-head-actions { display:none; }
  .hms-home-title { font-size:20px; }
  .hms-home-head { margin-bottom:12px; }

  /* "CL terbaru" mobile: compact two-line rows (no + badge / guest + date),
     not the generic label:value collapse. */
  .hms-home-card .hms-dv-table tbody tr {
    display:grid; grid-template-columns:1fr auto; gap:4px 10px;
    padding:11px 0;
  }
  .hms-home-card .hms-dv-table tbody td { padding:0; border:0; display:block; font-size:13px; min-width:0; text-align:left; }
  .hms-home-card .hms-dv-table tbody td::before { display:none; }
  .hms-home-card .hms-dv-table tbody td .sub { display:none; }
  .hms-home-card .hms-dv-table tbody td:nth-child(1) { grid-column:1; grid-row:1; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .hms-home-card .hms-dv-table tbody td:nth-child(4) { grid-column:2; grid-row:1; justify-self:end; }
  .hms-home-card .hms-dv-table tbody td:nth-child(2) { grid-column:1; grid-row:2; font-size:12px; color:var(--muted-foreground); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .hms-home-card .hms-dv-table tbody td:nth-child(3) { grid-column:2; grid-row:2; justify-self:end; font-size:12px; white-space:nowrap; }
}

/* Bottom row — billing donut, top hotels, reservation funnel, all 3-up
   (doc 01). Customer Map moved to the Calendar/Maps batch. */
.hms-home-grid2 { display:grid; grid-template-columns:1fr; gap:14px; margin-top:14px; }
@media (min-width:900px) {
  .hms-home-grid2.cols-3 { grid-template-columns:repeat(3,minmax(0,1fr)); align-items:stretch; }
}
.hms-home-donut .hms-dv-body { display:flex; flex-direction:column; }
.hms-donut-wrap { display:flex; align-items:center; gap:16px; padding:6px 0 2px; margin:auto 0; flex-wrap:wrap; }
.hms-donut-ring { position:relative; width:104px; height:104px; flex-shrink:0; }
.hms-donut-center { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; pointer-events:none; }
.hms-donut-pct { font-size:20px; font-weight:600; letter-spacing:-.02em; color:var(--foreground); font-variant-numeric:tabular-nums; line-height:1.1; }
.hms-donut-lbl { font-size:10.5px; color:var(--muted-foreground); }
.hms-donut-legend { display:flex; flex-direction:column; gap:10px; min-width:0; flex:1; }
.hms-donut-item { display:flex; align-items:center; gap:8px; font-size:11.5px; min-width:0; }
.hms-donut-dot { width:8px; height:8px; border-radius:9999px; flex-shrink:0; }
.hms-donut-name { color:var(--muted-foreground); }
.hms-donut-val { margin-left:auto; color:var(--foreground); font-weight:600; font-variant-numeric:tabular-nums; white-space:nowrap; }
.hms-hotel-list { display:flex; flex-direction:column; gap:16px; padding:8px 0 4px; flex:1; min-height:160px; justify-content:center; }
.hms-hotel-row { display:flex; flex-direction:column; gap:7px; }
.hms-hotel-head { display:flex; align-items:baseline; justify-content:space-between; gap:8px; }
.hms-hotel-name { font-size:13px; color:var(--foreground); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.hms-hotel-count { font-size:13px; font-weight:600; color:var(--muted-foreground); font-variant-numeric:tabular-nums; }
.hms-hotel-track { height:8px; border-radius:9999px; background:var(--secondary); overflow:hidden; }
.hms-hotel-bar { height:100%; border-radius:9999px; background:var(--primary); opacity:.85; transition:width .5s cubic-bezier(.34,1.56,.64,1); }
.hms-hotel-foot { padding:10px 0 0; border-top:1px solid var(--border); font-size:11.5px; color:var(--muted-foreground); margin-top:auto; }

/* Third row — Indonesia client-region heat map (7fr) + reservation funnel
   (5fr), mirroring Homlu's world map and conversion funnel panels. */
.hms-home-grid3 { display:grid; grid-template-columns:1fr; gap:20px; margin-top:20px; }
@media (min-width:900px) {
  .hms-home-grid3 { grid-template-columns:minmax(0,7fr) minmax(0,5fr); align-items:stretch; }
}
.hms-home-map .hms-dv-body,
.hms-home-funnel .hms-dv-body { display:flex; flex-direction:column; flex:1; }
.hms-map-wrap { position:relative; display:flex; flex-direction:column; flex:1; gap:12px; padding:6px 0 2px; }
.hms-map-svg { flex:1; min-height:0; display:flex; align-items:center; justify-content:center; }
.hms-map-svg svg { width:100%; height:auto; }
.hms-map-svg path { stroke:var(--card); stroke-width:.7; transition:fill .2s,opacity .15s; }
.hms-map-svg path:hover { opacity:.85; }
/* Hover tooltip — floats above the map, shows the province name + booking count. */
.hms-map-tip { position:absolute; z-index:5; pointer-events:none; transform:translate(-50%,-112%); display:flex; flex-direction:column; align-items:center; gap:1px; padding:6px 10px; background:var(--popover); border:1px solid var(--border); border-radius:10px; box-shadow:0 10px 24px -6px rgba(0,0,0,.18), 0 4px 8px -4px rgba(0,0,0,.12); white-space:nowrap; }
.hms-map-tip::after { content:''; position:absolute; top:100%; left:50%; transform:translateX(-50%); border:5px solid transparent; border-top-color:var(--border); }
.hms-map-tip-name { font-size:12px; font-weight:600; color:var(--foreground); }
.hms-map-tip-count { font-size:10.5px; color:var(--muted-foreground); font-variant-numeric:tabular-nums; }
.hms-map-legend { display:flex; align-items:center; justify-content:center; gap:12px; flex-wrap:wrap; padding-top:2px; }
.hms-map-gradient { width:90px; height:8px; border-radius:9999px; }
.hms-map-legend-item { display:inline-flex; align-items:center; gap:6px; font-size:11.5px; color:var(--muted-foreground); }
.hms-funnel { display:flex; flex-direction:column; gap:4px; flex:1; justify-content:center; padding:8px 0 4px; }
.hms-funnel-row { display:flex; flex-direction:column; gap:7px; padding:7px 0; }
.hms-funnel-head { display:flex; align-items:baseline; justify-content:space-between; gap:10px; }
.hms-funnel-label { font-size:13px; color:var(--foreground); display:inline-flex; align-items:center; gap:8px; }
.hms-funnel-dot { width:8px; height:8px; border-radius:9999px; flex-shrink:0; }
.hms-funnel-count { font-size:14px; font-weight:600; color:var(--foreground); font-variant-numeric:tabular-nums; }
.hms-funnel-count span { font-size:11px; font-weight:500; color:var(--muted-foreground); margin-left:4px; }
.hms-funnel-track { height:8px; border-radius:9999px; background:var(--secondary); overflow:hidden; }
.hms-funnel-bar { height:100%; border-radius:9999px; background:var(--primary); opacity:.85; transition:width .6s cubic-bezier(.34,1.56,.64,1); }
.hms-funnel-row:first-child .hms-funnel-bar { background:var(--green); }
.hms-funnel-row:last-child .hms-funnel-bar { background:var(--yellow); }

/* Ask AI — rebuilt to Claude Design doc 01 (1f). The gold pulsing FAB
   becomes a plain inked pill "Ask AI" (44px, no pulse). The panel is a
   340 / radius-20 card: header with a squared spark tile, a tinted
   conversation area whose answers are bordered data cards (never loose
   paragraphs), and a footer that carries suggestion pills above a 44px
   input pill with a 32px inked send button. */
.ai-fab { position:fixed; bottom:24px; right:24px; height:44px; padding:0 16px 0 13px; border-radius:9999px; background:var(--primary); color:var(--primary-foreground); border:1px solid var(--primary); cursor:pointer; display:inline-flex; align-items:center; gap:8px; font-family:inherit; font-size:12.5px; font-weight:600; white-space:nowrap; box-shadow:0 12px 26px -12px rgba(0,0,0,.5); transition:transform .15s cubic-bezier(.34,1.56,.64,1),opacity .15s; z-index:40; }
.ai-fab:hover { transform:translateY(-1px); } .ai-fab:active { transform:scale(.97); opacity:.9; }
.ai-fab svg { width:16px; height:16px; flex:none; }
.ai-fab .fab-ic-close { display:none; }
/* Panel open → the pill retracts; the panel header X (and Esc) close it. */
.ai-fab.open { opacity:0; pointer-events:none; transform:scale(.9); }

.ai-panel { position:fixed; bottom:24px; right:24px; width:340px; max-height:min(540px, calc(100vh - 96px)); background:var(--card); border:1px solid var(--border); border-radius:20px; overflow:hidden; box-shadow:0 22px 50px -22px rgba(0,0,0,.34), 0 4px 12px -4px rgba(0,0,0,.14); display:flex; flex-direction:column; z-index:40; transform:translateY(16px) scale(.97); transform-origin:bottom right; opacity:0; pointer-events:none; transition:transform .22s cubic-bezier(.34,1.56,.64,1),opacity .16s; }
.ai-panel.open { transform:translateY(0) scale(1); opacity:1; pointer-events:all; }
@media (max-width:640px){ .ai-fab{bottom:16px;right:16px;} .ai-panel{bottom:16px;right:16px;left:16px;width:auto;} }

.ai-panel-head { display:flex; align-items:center; gap:11px; padding:14px 17px; border-bottom:1px solid var(--border); flex-shrink:0; }
.ai-head-icon { width:32px; height:32px; border-radius:10px; background:var(--secondary); border:1px solid var(--border); color:var(--foreground); display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.ai-head-text { flex:1; min-width:0; }
.ai-panel-title { font-size:13.5px; font-weight:600; color:var(--foreground); line-height:1.2; }
.ai-panel-sub { font-size:11.5px; color:var(--muted-foreground); line-height:1.35; margin-top:1px; }
.ai-panel-close { width:28px; height:28px; background:none; border:none; cursor:pointer; color:var(--muted-foreground); display:flex; align-items:center; justify-content:center; border-radius:8px; transition:color .12s,background .12s; flex-shrink:0; }
.ai-panel-close:hover { color:var(--foreground); background:var(--secondary); }

.chat-messages { flex:1; padding:16px 17px; display:flex; flex-direction:column; gap:13px; overflow-y:auto; min-height:0; background:var(--muted); }

/* Empty state — a left-aligned intro card, not a centred hero. */
.chat-empty { display:flex; flex-direction:column; gap:4px; }
.chat-empty-title { font-size:13px; font-weight:600; color:var(--foreground); }
.chat-empty-sub { font-size:12px; line-height:1.6; color:var(--muted-foreground); }
.chat-empty .chat-sugs { margin-top:12px; }

.chat-sugs { display:flex; flex-direction:column; gap:7px; }
.chat-sug { display:flex; align-items:center; height:36px; padding:0 13px; background:transparent; border:1px solid var(--input); border-radius:9999px; font-size:12.5px; font-weight:500; color:var(--foreground); font-family:inherit; text-align:left; cursor:pointer; transition:background .12s,border-color .12s; }
.chat-sug:hover { background:var(--secondary); border-color:var(--ring); }

@keyframes bubbleIn { from{opacity:0;transform:translateY(8px) scale(.96);} to{opacity:1;transform:translateY(0) scale(1);} }
.chat-bubble { padding:9px 13px; font-size:13px; line-height:1.55; max-width:82%; word-break:break-word; animation:bubbleIn .22s cubic-bezier(.34,1.56,.64,1) both; }
.bubble-user { background:var(--primary); color:var(--primary-foreground); align-self:flex-end; border-radius:14px 14px 4px 14px; }
.bubble-ai { background:var(--card); border:1px solid var(--border); color:var(--foreground); align-self:flex-start; border-radius:14px 14px 14px 4px; }

.chat-typing-row { display:flex; align-items:center; gap:8px; align-self:flex-start; animation:bubbleIn .22s cubic-bezier(.34,1.56,.64,1) both; }
.chat-typing-note { font-size:11.5px; color:var(--muted-foreground); }
.bubble-typing { display:flex; gap:4px; align-items:center; padding:9px 13px; }
.bubble-typing span { width:5px; height:5px; background:var(--muted-foreground); border-radius:50%; animation:bounce 1.2s infinite; }
.bubble-typing span:nth-child(2){animation-delay:.2s;} .bubble-typing span:nth-child(3){animation-delay:.4s;}
@keyframes bounce { 0%,60%,100%{transform:translateY(0);} 30%{transform:translateY(-4px);} }

.chat-foot { flex-shrink:0; padding:12px 17px 15px; border-top:1px solid var(--border); display:flex; flex-direction:column; gap:11px; }
.chat-foot .chat-sugs { flex-direction:row; flex-wrap:wrap; gap:7px; }
.chat-foot .chat-sug { height:28px; padding:0 11px; font-size:11.5px; color:var(--muted-foreground); }
.chat-input-pill { display:flex; align-items:center; gap:9px; background:var(--card); border:1px solid var(--input); border-radius:9999px; padding:0 6px 0 15px; height:44px; transition:border-color .15s,box-shadow .15s; }
.chat-input-pill:focus-within { border-color:var(--ring); }
/* Beats the global input reset in design.css (same idiom as .search-wrap) */
.chat-input-pill input:not([type="checkbox"]):not([type="radio"]) { flex:1; width:auto; background:transparent; border:none; outline:none; box-shadow:none; font-size:13px; font-family:inherit; color:var(--foreground); height:100%; padding:0; border-radius:0; appearance:none; -webkit-appearance:none; }
.chat-input-pill input:not([type="checkbox"]):not([type="radio"]):focus { border:none; box-shadow:none; outline:none; }
.chat-input::placeholder { color:var(--muted-foreground); }
.chat-send { background:var(--primary); color:var(--primary-foreground); border:none; border-radius:9999px; width:32px; height:32px; display:flex; align-items:center; justify-content:center; cursor:pointer; flex-shrink:0; transition:transform .15s cubic-bezier(.34,1.56,.64,1),opacity .15s; }
.chat-send:hover { transform:scale(1.06); }
.chat-send:active { transform:scale(.92); } .chat-send:disabled { opacity:.4; cursor:not-allowed; transform:none; }
.chat-send svg { width:15px; height:15px; }

.bubble-ai .ai-ul { margin:4px 0 2px 4px; padding-left:14px; display:flex; flex-direction:column; gap:3px; }
.bubble-ai .ai-ul li { font-size:13px; line-height:1.5; } .bubble-ai strong { font-weight:600; color:var(--foreground); }
/* AI data card — bordered rows, per 1f: answers are inspectable data, not prose. */
.ai-card { background:var(--card); border:1px solid var(--border); border-radius:12px; margin:3px 0; overflow:hidden; display:flex; flex-direction:column; }
.ai-card-head { display:flex; align-items:center; justify-content:space-between; gap:6px; padding:10px 13px; }
.ai-card-head + .ai-card-name { padding-top:0; }
.ai-card-num { font-size:12px; font-weight:600; color:var(--foreground); font-variant-numeric:tabular-nums; }
.ai-card-badge { font-size:10px; font-weight:600; padding:2px 8px; border-radius:9999px; flex-shrink:0; }
.ai-badge-green { background:var(--green-muted); color:var(--green); } .ai-badge-red { background:var(--red-muted); color:var(--red); }
.ai-card-name { font-size:12.5px; font-weight:500; color:var(--foreground); padding:0 13px 4px; } .ai-card-meta { font-size:11px; color:var(--muted-foreground); padding:0 13px 10px; }
`;

// ── AI reply formatter (ported from home.html) ──
const esc = (s) => String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const bold = (s) => s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
function makeCard(raw) {
  const p = raw.split("|").map((s) => s.trim());
  const [nomor = "", nama = "", total = "", sisa = "", status = ""] = p;
  const lunas = /^lunas$/i.test(status);
  return '<div class="ai-card"><div class="ai-card-head"><span class="ai-card-num">' + esc(nomor) +
    '</span><span class="ai-card-badge ' + (lunas ? "ai-badge-green" : "ai-badge-red") + '">' + esc(status) +
    '</span></div><div class="ai-card-name">' + esc(nama) + '</div><div class="ai-card-meta">' + esc(total) +
    " &middot; Remaining " + esc(sisa) + "</div></div>";
}
function formatAI(text) {
  const lines = String(text || "").split("\n");
  let html = "", inList = false;
  for (const line of lines) {
    const cardMatch = line.match(/\[inv:\s*([^\]]+)\]/);
    if (cardMatch) {
      if (inList) { html += "</ul>"; inList = false; }
      html += makeCard(cardMatch[1]);
    } else if (/^[-•]\s+/.test(line)) {
      if (!inList) { html += '<ul class="ai-ul">'; inList = true; }
      html += "<li>" + bold(esc(line.replace(/^[-•]\s+/, ""))) + "</li>";
    } else {
      if (inList) { html += "</ul>"; inList = false; }
      const e = bold(esc(line));
      html += e ? "<span>" + e + "</span><br>" : "<br>";
    }
  }
  if (inList) html += "</ul>";
  return html;
}

const SPARK = <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />;

function heroPill(s) {
  if (s === "DEFINITE") return { label: "Definite", tone: "green" };
  if (s === "CANCELLED") return { label: "Cancelled", tone: "red" };
  return { label: "Tentative", tone: "yellow" };
}

const FUNNEL_LABELS = { total: "Total", confirmed: "Confirmed", completed: "Completed" };

function ChartTip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="hms-chart-tip">
      <div className="hms-chart-tip-label">{label}</div>
      <div className="hms-chart-tip-val">{fmtNum(payload[0]?.value)}</div>
    </div>
  );
}

// Ask AI starter prompts (doc 01 1f) — shown as pills in the empty state and
// again above the input once a conversation has started.
const SUGGESTIONS = ["Check-ins in the next 7 days", "Overdue invoices", "Outstanding remittance to HQ"];

const PERIODS = ["7D", "30D", "6M", "12M"];
const PERIOD_SUB = { "7D": "last 7 days", "30D": "last 30 days", "6M": "last 6 months", "12M": "last 12 months" };

// SimpleMaps Indonesia (assets/id.svg) province ids, keyed by the Indonesian
// province names the Client.province field is filled with (aliases included).
const PROVINCE_TO_ID = {
  "aceh": "IDAC", "sumatera utara": "IDSU", "sumatra utara": "IDSU", "sumatera barat": "IDSB", "sumatra barat": "IDSB",
  "riau": "IDRI", "kepulauan riau": "IDKR", "kep. riau": "IDKR", "jambi": "IDJA", "bengkulu": "IDBE",
  "sumatera selatan": "IDSS", "sumatra selatan": "IDSS", "bangka belitung": "IDBB", "bangka-belitung": "IDBB", "babel": "IDBB",
  "lampung": "IDLA",
  "dki jakarta": "IDJK", "jakarta": "IDJK", "jakarta raya": "IDJK", "banten": "IDBT", "jawa barat": "IDJB",
  "jawa tengah": "IDJT", "di yogyakarta": "IDYO", "yogyakarta": "IDYO", "jawa timur": "IDJI",
  "bali": "IDBA", "nusa tenggara barat": "IDNB", "ntb": "IDNB", "nusa tenggara timur": "IDNT", "ntt": "IDNT",
  "kalimantan barat": "IDKB", "kalimantan tengah": "IDKT", "kalimantan selatan": "IDKS", "kalimantan timur": "IDKI", "kalimantan utara": "IDKU",
  "sulawesi utara": "IDSA", "gorontalo": "IDGO", "sulawesi tengah": "IDST", "sulawesi barat": "IDSR", "sulawesi selatan": "IDSN", "sulawesi tenggara": "IDSG",
  "maluku": "IDMA", "maluku utara": "IDMU", "papua barat": "IDPB", "papua": "IDPA",
};

function MapIndonesia({ regionData }) {
  const { t } = useI18n();
  const wrapRef = useRef(null);
  const [tip, setTip] = useState(null);
  const rows = regionData || [];
  const byProvince = {};
  rows.forEach((r) => { byProvince[PROVINCE_TO_ID[String(r.province).toLowerCase().trim()]] = r.count; });
  const max = Math.max(1, ...rows.map((r) => r.count));

  useEffect(() => {
    const svg = wrapRef.current?.querySelector("svg");
    if (!svg) return;
    svg.querySelector("#points")?.remove();
    svg.querySelector("#label_points")?.remove();
    const onMove = (p, count, e) => {
      const rect = wrapRef.current.getBoundingClientRect();
      const name = p.getAttribute("name") || p.getAttribute("id");
      setTip({ name, count, x: e.clientX - rect.left, y: e.clientY - rect.top });
    };
    svg.querySelectorAll("path[id]").forEach((p) => {
      const count = byProvince[p.getAttribute("id")] || 0;
      p.style.fill = heatColor(max > 0 ? count / max : 0);
      p.onmousemove = (e) => onMove(p, count, e);
      p.onmouseleave = () => setTip(null);
    });
  }, [regionData, byProvince, max]);

  return (
    <div className="hms-map-wrap">
      <div className="hms-map-svg" ref={wrapRef} dangerouslySetInnerHTML={{ __html: mapSvg }} />
      {tip && (
        <div className="hms-map-tip" style={{ left: tip.x, top: tip.y }}>
          <span className="hms-map-tip-name">{tip.name}</span>
          <span className="hms-map-tip-count">{fmtNum(tip.count)} {t("bookings")}</span>
        </div>
      )}
      <div className="hms-map-legend">
        <span className="hms-map-legend-item">{t("Rare")}</span>
        <div className="hms-map-gradient" style={{ background: `linear-gradient(90deg, ${heatColor(0)}, ${heatColor(0.5)}, ${heatColor(1)})` }} />
        <span className="hms-map-legend-item">{t("Many")}</span>
      </div>
    </div>
  );
}

// "Saldo kas" tile (doc 01) — label + figure on the left, an outline badge
// on the right. Sits in the same divided card as the KPI board.
function CashTile({ label, value, meta, plain }) {
  return (
    <div className="hms-cash">
      <div>
        <div className="hms-cash-label">{label}</div>
        <div className="hms-cash-val">
          {typeof value === "number" ? value.toLocaleString("en-US") : value}
          {!plain && <span className="hms-cash-cur">SAR</span>}
        </div>
      </div>
      {meta && <span className="hms-cash-badge">{meta}</span>}
    </div>
  );
}

// Panels arrive as null when the user may not view their module (the server
// does not compute them); a null panel is not drawn.
function Dashboard({ kpis, clTrend, clDaily, recentCls, paymentSnapshot, financeSummary, topHotels, topHotelsTotal, regionData, reservationFunnel }) {
  const { t } = useI18n();
  const perms = usePerms();
  const showCl = clTrend != null;
  const showInvoice = paymentSnapshot != null;
  recentCls = recentCls || [];
  topHotels = topHotels || [];
  reservationFunnel = reservationFunnel || [];
  const [period, setPeriod] = useState("6M");
  const today = new Date().toLocaleDateString("en-GB", { weekday: "long", month: "long", day: "numeric", year: "numeric" });
  const remittance = kpis?.remittance_pending != null;
  const showPending = financeSummary != null || remittance;
  const monthly = clTrend || [];
  const daily = clDaily || [];
  const series = period === "7D" ? daily.slice(-7)
    : period === "30D" ? daily
    : period === "12M" ? monthly
    : monthly.slice(-6);
  const seriesTotal = series.reduce((s, m) => s + m.count, 0);
  const gradId = "hmsHomeArea";
  const deltas = kpis?.deltas || {};

  const billed = paymentSnapshot?.billed || 0;
  const collected = paymentSnapshot?.collected || 0;
  const outstanding = paymentSnapshot?.outstanding || 0;
  const collectedPct = billed ? Math.round((collected / billed) * 100) : 0;
  const donutData = [
    { name: t("Collected"), value: collected },
    { name: t("Outstanding"), value: outstanding },
  ];
  const maxHotel = Math.max(1, ...(topHotels || []).map((h) => h.count));
  const funnelMax = Math.max(1, ...(reservationFunnel || []).map((f) => f.value));

  return (
    <>
      <div className="hms-home-head">
        <div>
          <h1 className="hms-home-title">{t("Dashboard")}</h1>
          <div className="hms-home-date">{today}</div>
        </div>
        <div className="hms-home-head-actions">
          {perms.can("cl", "export") && <a className="hms-btn-outline" href="/cl/export/csv/">{t("Export recap")}</a>}
          {perms.can("cl", "create") && (
            <a className="hms-btn-primary" href="/cl/new/">
              <Icon name="plus" size={15} strokeWidth={1.9} />{t("New CL")}
            </a>
          )}
        </div>
      </div>

      {(showCl || showInvoice || showPending) && (
        <div className="hms-kpi-row">
          {showCl && (
            <KpiCard
              label={t("CL This Month")}
              value={fmtNum(kpis?.cl_month)}
              trend={deltas.cl_month}
              foot={t("{n} last month", { n: fmtNum(deltas.cl_month?.prev ?? 0) })}
            />
          )}
          {showCl && (
            <KpiCard
              label={t("Check-ins Next 7 Days")}
              value={fmtNum(kpis?.upcoming_checkins)}
              trend={deltas.checkins}
              foot={t("{n} last 7 days", { n: fmtNum(deltas.checkins?.prev ?? 0) })}
            />
          )}
          {showInvoice && (
            <KpiCard
              label={t("Unpaid Invoices")}
              value={fmtNum(kpis?.unpaid_invoices)}
              trend={deltas.unpaid}
              trendGood={false}
              foot={t("{amount} SAR outstanding", { amount: fmtNum(kpis?.unpaid_total) })}
            />
          )}
          {showPending && (
            <KpiCard
              label={t("Payments Pending")}
              value={fmtNum(financeSummary?.payments_pending ?? kpis?.remittance_pending ?? 0)}
              trend={remittance ? deltas.remittance : undefined}
              trendGood={false}
              foot={t("needs review")}
            />
          )}
        </div>
      )}

      {financeSummary && (
        <div className="hms-kpi-row hms-cash-row">
          <CashTile label={t("Cash Surabaya")} value={financeSummary.kas_sby} meta="SAR" />
          <CashTile label={t("Cash HQ")} value={financeSummary.kas_pusat} meta="SAR" />
          <CashTile label={t("Total Receivable")} value={financeSummary.total_piutang} meta="SAR" />
          <CashTile
            label={t("Payments This Month")}
            value={financeSummary.payments_this_month}
            plain
            meta={t("{n} pending", { n: fmtNum(financeSummary.payments_pending || 0) })}
          />
        </div>
      )}

      {showCl && <div className="hms-home-grid">
        <div className="hms-dv-card hms-home-chart">
          <div className="hms-dv-body">
            <div className="hms-chart-legend">
              <div>
                <div className="hms-chart-total">{t("CL Trend")}</div>
                <div className="hms-chart-total-sub">{t(PERIOD_SUB[period])} · {fmtNum(seriesTotal)} {t("total")}</div>
              </div>
              <div className="hms-chart-tabs" role="tablist" aria-label={t("Chart period")}>
                {PERIODS.map((p) => (
                  <button key={p} type="button" role="tab" aria-selected={period === p}
                    className={"hms-chart-tab" + (period === p ? " active" : "")}
                    onClick={() => setPeriod(p)}>{p}</button>
                ))}
              </div>
            </div>
            {series.length === 0 ? (
              <div className="hms-home-empty">{t("No data yet.")}</div>
            ) : (
              <div className="hms-chart-wrap">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={series} margin={{ top: 8, right: 6, left: -14, bottom: 0 }}>
                    <defs>
                      <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--foreground)" stopOpacity={0.14} />
                        <stop offset="100%" stopColor="var(--foreground)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} strokeDasharray="0" />
                    <XAxis dataKey="label" axisLine={false} tickLine={false} tickMargin={10} />
                    <YAxis allowDecimals={false} axisLine={false} tickLine={false} tickMargin={6} width={44} tickCount={8} />
                    <Tooltip content={<ChartTip />} cursor={{ stroke: "var(--border)", strokeDasharray: "4 4" }} />
                    <Area type="monotone" dataKey="count" stroke="var(--foreground)" strokeWidth={1.5} fill={`url(#${gradId})`} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </div>

        <div className="hms-dv-card hms-home-card">
          <div className="hms-dv-body">
            <div className="hms-dv-sech">
              <span className="hms-dv-sec-title">{t("Recent CLs")} <span className="hms-dv-count">{recentCls.length}</span></span>
              <span className="hms-dv-sec-actions"><a className="hms-dv-act" href="/cl/">{t("View all")}</a></span>
            </div>
            {recentCls.length === 0 ? (
              <div className="hms-home-empty">{t("No confirmation letters yet")}</div>
            ) : (
              <div className="hms-dv-table-wrap">
                <table className="hms-dv-table">
                  <thead>
                    <tr>
                      <th>{t("No.")}</th>
                      <th>{t("Guest")}</th>
                      <th>{t("Check-in")}</th>
                      <th>{t("Status")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentCls.map((cl) => {
                      const pill = heroPill(cl.reservation_status);
                      return (
                        <tr key={cl.id}>
                          <td data-label={t("No.")}><a className="strong" href={`/cl/${cl.id}/`}>{cl.confirmation_number}</a></td>
                          <td className="strong" data-label={t("Guest")}>{cl.guest_name}<span className="sub">{cl.hotel_name}</span></td>
                          <td data-label={t("Check-in")}>{fmtDateShort(cl.check_in)}</td>
                          <td data-label={t("Status")}><StatusPill small label={t(pill.label)} tone={pill.tone} /></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>}

      {(showCl || showInvoice) && <div className="hms-home-grid2 cols-3">
        {showInvoice && <div className="hms-dv-card hms-home-donut">
          <div className="hms-dv-body">
            <div className="hms-dv-sech">
              <span className="hms-dv-sec-title">{t("Payment Collection")}</span>
              <span className="hms-dv-count">{collectedPct}%</span>
            </div>
            <div className="hms-donut-wrap">
              <div className="hms-donut-ring">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={donutData} dataKey="value" nameKey="name" innerRadius="72%" outerRadius="96%"
                      paddingAngle={3} stroke="none" startAngle={90} endAngle={-270} isAnimationActive={false}>
                      <Cell fill="var(--primary)" />
                      <Cell fill="var(--border)" />
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="hms-donut-center">
                  <span className="hms-donut-pct">{collectedPct}%</span>
                  <span className="hms-donut-lbl">{t("collected")}</span>
                </div>
              </div>
              <div className="hms-donut-legend">
                <div className="hms-donut-item">
                  <span className="hms-donut-dot" style={{ background: "var(--primary)" }} />
                  <span className="hms-donut-name">{t("Collected")}</span>
                  <span className="hms-donut-val">{fmtNum(collected)} {t("SAR")}</span>
                </div>
                <div className="hms-donut-item">
                  <span className="hms-donut-dot" style={{ background: "var(--border)" }} />
                  <span className="hms-donut-name">{t("Outstanding")}</span>
                  <span className="hms-donut-val">{fmtNum(outstanding)} {t("SAR")}</span>
                </div>
              </div>
            </div>
          </div>
        </div>}

        {showCl && <div className="hms-dv-card hms-home-hotels">
          <div className="hms-dv-body">
            <div className="hms-dv-sech">
              <span className="hms-dv-sec-title">{t("Top Hotels")} <span className="hms-dv-count">{fmtNum(topHotelsTotal)} {t("total")}</span></span>
            </div>
            {topHotels.length === 0 ? (
              <div className="hms-home-empty">{t("No data yet.")}</div>
            ) : (
              <div className="hms-hotel-list">
                {topHotels.map((h) => (
                  <div className="hms-hotel-row" key={h.hotel}>
                    <div className="hms-hotel-head">
                      <span className="hms-hotel-name">{h.hotel}</span>
                      <span className="hms-hotel-count">{h.count}</span>
                    </div>
                    <div className="hms-hotel-track">
                      <div className="hms-hotel-bar" style={{ width: `${(h.count / maxHotel) * 100}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="hms-hotel-foot">{t("{n} reservations", { n: fmtNum(topHotelsTotal) })}</div>
          </div>
        </div>}

        {showCl && <div className="hms-dv-card hms-home-funnel">
          <div className="hms-dv-body">
            <div className="hms-dv-sech">
              <span className="hms-dv-sec-title">{t("Reservation Funnel")}</span>
              <span className="hms-dv-count">{t("all time")}</span>
            </div>
            {reservationFunnel.length === 0 ? (
              <div className="hms-home-empty">{t("No data yet.")}</div>
            ) : (
              <div className="hms-funnel">
                {reservationFunnel.map((f, i) => {
                  const prev = i === 0 ? f.value : reservationFunnel[i - 1].value;
                  const pct = prev ? Math.round((f.value / prev) * 100) : 100;
                  return (
                    <div className="hms-funnel-row" key={f.label}>
                      <div className="hms-funnel-head">
                        <span className="hms-funnel-label">
                          {t(FUNNEL_LABELS[f.label] || f.label)}
                        </span>
                        <span className="hms-funnel-count">{fmtNum(f.value)}<span>{i === 0 ? "100%" : `${pct}%`}</span></span>
                      </div>
                      <div className="hms-funnel-track">
                        <div className="hms-funnel-bar" style={{ width: `${Math.max((f.value / funnelMax) * 100, 3)}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>}
      </div>}
    </>
  );
}

export default function Home() {
  const { props } = usePage();
  const kpis = props.kpis || {};
  const { t } = useI18n();
  const perms = usePerms();
  // The assistant answers from invoices, services and CLs (hw/ai.py).
  const canAsk = ["invoice", "services", "cl"].some((m) => perms.can(m, "view"));
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [typing, setTyping] = useState(false);
  const [input, setInput] = useState("");
  const inputRef = useRef(null);
  const msgRef = useRef(null);

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 180); }, [open]);
  useEffect(() => { if (msgRef.current) msgRef.current.scrollTop = msgRef.current.scrollHeight; }, [messages, typing]);

  const send = async (preset) => {
    const text = (preset ?? input).trim();
    if (!text || typing) return;
    setInput("");
    setMessages((m) => [...m, { type: "user", text }]);
    setTyping(true);
    try {
      const data = await fetchJson("/ai/chat/", { method: "POST", json: { message: text } });
      setMessages((m) => [...m, { type: "ai", html: formatAI(data.reply) }]);
    } catch {
      setMessages((m) => [...m, { type: "ai", html: formatAI("Failed to connect to server.") }]);
    } finally {
      setTyping(false);
      inputRef.current?.focus();
    }
  };

  return (
    <div className="page shadcn-root hms-home">
      <style dangerouslySetInnerHTML={{ __html: CSS }} />

      <Dashboard kpis={kpis} clTrend={props.cl_trend} clDaily={props.cl_daily} recentCls={props.recent_cls} paymentSnapshot={props.payment_snapshot} financeSummary={props.finance_summary} topHotels={props.top_hotels} topHotelsTotal={props.top_hotels_total || 0} regionData={props.region_data || []} reservationFunnel={props.reservation_funnel} />

      {canAsk && (<>
        <button className={"ai-fab" + (open ? " open" : "")} title={t("Ask AI")} aria-label={t("Ask AI")} aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          <svg className="fab-ic-spark" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">{SPARK}</svg>
          <svg className="fab-ic-close" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
          <span>{t("Ask AI")}</span>
        </button>

        <div className={"ai-panel" + (open ? " open" : "")}>
          <div className="ai-panel-head">
            <div className="ai-head-icon"><svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">{SPARK}</svg></div>
            <div className="ai-head-text">
              <div className="ai-panel-title">{t("Ask AI")}</div>
              <div className="ai-panel-sub">{t("Reads only the data you're allowed to see")}</div>
            </div>
            <button className="ai-panel-close" onClick={() => setOpen(false)}>
              <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
          <div className="chat-messages" ref={msgRef} aria-live="polite">
            {messages.length === 0 && !typing && (
              <div className="chat-empty">
                <div className="chat-empty-title">{t("Ask anything about today's data")}</div>
                <div className="chat-empty-sub">{t("Every answer carries the figures and links to the source records, so you can check it yourself.")}</div>
                <div className="chat-sugs">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} type="button" className="chat-sug" onClick={() => send(t(s))}>{t(s)}</button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m, i) => (
              m.type === "user"
                ? <div key={i} className="chat-bubble bubble-user">{m.text}</div>
                : <div key={i} className="chat-bubble bubble-ai" dangerouslySetInnerHTML={{ __html: m.html }} />
            ))}
            {typing && (
              <div className="chat-typing-row">
                <div className="chat-bubble bubble-ai bubble-typing"><span></span><span></span><span></span></div>
                <span className="chat-typing-note">{t("Reading your records…")}</span>
              </div>
            )}
          </div>
          <div className="chat-foot">
            {messages.length > 0 && (
              <div className="chat-sugs">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" className="chat-sug" disabled={typing} onClick={() => send(t(s))}>{t(s)}</button>
                ))}
              </div>
            )}
            <div className="chat-input-pill">
              <input ref={inputRef} type="text" className="chat-input" placeholder={t("Ask about invoices, rooms, or remittances")} autoComplete="off"
                value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") send(); }} />
              <button className="chat-send" title={t("Send")} disabled={typing || !input.trim()} onClick={() => send()}>
                <svg fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M5 12h13M12 6l6 6-6 6" /></svg>
              </button>
            </div>
          </div>
        </div>
      </>)}
    </div>
  );
}
