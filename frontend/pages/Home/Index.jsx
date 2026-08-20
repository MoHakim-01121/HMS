import { useEffect, useRef, useState } from "react";
import { usePage } from "@inertiajs/react";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell } from "recharts";
import { fetchJson } from "../../utils/fetchJson.js";
import { useI18n } from "../../utils/i18n.jsx";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import { heatColor } from "../../components/mapColors.js";
import mapSvg from "../../assets/id.svg?raw";

const CSS = `
/* Home dashboard — Homlu token set (measured off the live
   homlu-dashboard-template.vercel.app reference). Reserved hue for status
   only: KPI ink and the trend area are monochrome (--foreground/--primary),
   color is used solely for the delta badges, status pills, and the unpaid
   warning. */
.hms-home { padding: 4px 24px 40px; max-width: 1280px; }
.hms-home-head { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:20px; flex-wrap:wrap; }
.hms-home-title { font-size:30px; font-weight:600; letter-spacing:-.025em; line-height:1.2; color:var(--foreground); margin:0; }
.hms-home-date { font-size:13px; color:var(--muted-foreground); margin-top:5px; }

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
}

/* Second row — payment donut (5fr) + top hotels by CL volume (7fr). */
.hms-home-grid2 { display:grid; grid-template-columns:1fr; gap:20px; margin-top:20px; }
@media (min-width:900px) {
  .hms-home-grid2 { grid-template-columns:minmax(0,5fr) minmax(0,7fr); align-items:stretch; }
}
.hms-home-donut .hms-dv-body { display:flex; flex-direction:column; }
.hms-donut-wrap { display:flex; align-items:center; gap:18px; padding:6px 0 2px; margin:auto 0; }
.hms-donut-ring { position:relative; width:132px; height:132px; flex-shrink:0; }
.hms-donut-center { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; pointer-events:none; }
.hms-donut-pct { font-size:20px; font-weight:600; letter-spacing:-.02em; color:var(--foreground); font-variant-numeric:tabular-nums; line-height:1.1; }
.hms-donut-lbl { font-size:10.5px; color:var(--muted-foreground); }
.hms-donut-legend { display:flex; flex-direction:column; gap:10px; min-width:0; flex:1; }
.hms-donut-item { display:flex; align-items:center; gap:8px; font-size:12px; min-width:0; }
.hms-donut-dot { width:8px; height:8px; border-radius:9999px; flex-shrink:0; }
.hms-donut-name { color:var(--muted-foreground); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
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

/* Ask AI — same Homlu surfaces as the other floating menus (--popover + the
   two-layer soft shadow), primary FAB instead of the brand-orange gradient. */
@keyframes fabPulse { 0%,100%{box-shadow:0 4px 16px rgba(0,0,0,.16);} 50%{box-shadow:0 4px 22px rgba(0,0,0,.26);} }
.ai-fab { position:fixed; bottom:56px; right:24px; width:52px; height:52px; border-radius:50%; background:var(--primary); color:var(--primary-foreground); border:1px solid var(--border); cursor:pointer; display:flex; align-items:center; justify-content:center; animation:fabPulse 3.5s ease-in-out infinite; transition:transform .2s cubic-bezier(.34,1.56,.64,1),opacity .15s; z-index:10; }
.ai-fab:hover { transform:scale(1.08) rotate(6deg); } .ai-fab:active { transform:scale(.93); opacity:.85; }
.ai-fab svg { width:21px; height:21px; position:absolute; transition:opacity .18s,transform .25s cubic-bezier(.34,1.56,.64,1); }
.ai-fab .fab-ic-close { opacity:0; transform:rotate(-90deg) scale(.5); }
.ai-fab.open .fab-ic-spark { opacity:0; transform:rotate(90deg) scale(.5); }
.ai-fab.open .fab-ic-close { opacity:1; transform:rotate(0deg) scale(1); }
.ai-panel { position:fixed; bottom:120px; right:24px; width:340px; max-height:480px; background:var(--popover); border:1px solid var(--border); border-radius:20px; overflow:hidden; box-shadow:0 10px 24px -6px rgba(0,0,0,.18), 0 4px 8px -4px rgba(0,0,0,.12); display:flex; flex-direction:column; z-index:10; transform:translateY(16px) scale(.95); transform-origin:bottom right; opacity:0; pointer-events:none; transition:transform .22s cubic-bezier(.34,1.56,.64,1),opacity .16s; }
.ai-panel.open { transform:translateY(0) scale(1); opacity:1; pointer-events:all; }
@media (max-width:640px){ .ai-fab{bottom:108px;right:16px;} .ai-panel{bottom:172px;right:16px;left:16px;width:auto;} }
.ai-panel-head { display:flex; align-items:center; gap:10px; padding:12px 14px; border-bottom:1px solid var(--border); flex-shrink:0; }
.ai-head-icon { width:30px; height:30px; border-radius:10px; background:var(--secondary); color:var(--foreground); display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.ai-head-text { flex:1; min-width:0; }
.ai-panel-title { font-size:13px; font-weight:600; color:var(--foreground); line-height:1.2; }
.ai-panel-sub { font-size:11px; color:var(--muted-foreground); line-height:1.3; }
.ai-panel-close { background:none; border:none; cursor:pointer; color:var(--muted-foreground); padding:4px; display:flex; align-items:center; border-radius:8px; transition:color .12s,background .12s; }
.ai-panel-close:hover { color:var(--foreground); background:var(--secondary); }
.chat-messages { flex:1; padding:12px; display:flex; flex-direction:column; gap:8px; overflow-y:auto; min-height:0; }
.chat-empty { margin:auto; display:flex; flex-direction:column; align-items:center; gap:6px; padding:18px 14px; text-align:center; }
.chat-empty-icon { width:38px; height:38px; border-radius:50%; background:var(--secondary); color:var(--foreground); display:flex; align-items:center; justify-content:center; margin-bottom:2px; }
.chat-empty-title { font-size:13px; font-weight:600; color:var(--foreground); }
.chat-empty-sub { font-size:11.5px; color:var(--muted-foreground); }
.chat-sugs { display:flex; flex-wrap:wrap; justify-content:center; gap:6px; margin-top:8px; }
.chat-sug { background:var(--secondary); border:1px solid var(--border); border-radius:9999px; padding:5px 11px; font-size:11.5px; font-weight:500; color:var(--foreground); cursor:pointer; transition:background .12s,color .12s,border-color .12s; }
.chat-sug:hover { background:var(--surface-hover); border-color:var(--ring); }
@keyframes bubbleIn { from{opacity:0;transform:translateY(8px) scale(.96);} to{opacity:1;transform:translateY(0) scale(1);} }
.chat-bubble { padding:8px 12px; border-radius:16px; font-size:13px; line-height:1.5; max-width:88%; word-break:break-word; animation:bubbleIn .22s cubic-bezier(.34,1.56,.64,1) both; }
.bubble-user { background:var(--primary); color:var(--primary-foreground); align-self:flex-end; border-bottom-right-radius:4px; }
.bubble-ai { background:var(--secondary); border:1px solid var(--border); color:var(--foreground); align-self:flex-start; border-bottom-left-radius:4px; }
.bubble-typing { display:flex; gap:4px; align-items:center; padding:10px 14px; }
.bubble-typing span { width:5px; height:5px; background:var(--muted-foreground); border-radius:50%; animation:bounce 1.2s infinite; }
.bubble-typing span:nth-child(2){animation-delay:.2s;} .bubble-typing span:nth-child(3){animation-delay:.4s;}
@keyframes bounce { 0%,60%,100%{transform:translateY(0);} 30%{transform:translateY(-4px);} }
.chat-input-row { display:flex; align-items:center; padding:2px 12px 12px; gap:8px; flex-shrink:0; }
.chat-input-pill { flex:1; display:flex; align-items:center; background:var(--secondary); border:1px solid var(--border); border-radius:9999px; padding:0 14px; height:36px; transition:border-color .15s,box-shadow .15s; }
.chat-input-pill:focus-within { border-color:var(--ring); box-shadow:0 0 0 3px var(--surface-hover); }
/* Beats the global input reset in design.css (same idiom as .search-wrap) */
.chat-input-pill input:not([type="checkbox"]):not([type="radio"]) { flex:1; width:auto; background:transparent; border:none; outline:none; box-shadow:none; font-size:13px; font-family:inherit; color:var(--foreground); height:100%; padding:0; border-radius:0; appearance:none; -webkit-appearance:none; }
.chat-input-pill input:not([type="checkbox"]):not([type="radio"]):focus { border:none; box-shadow:none; outline:none; }
.chat-input::placeholder { color:var(--muted-foreground); }
.chat-send { background:var(--primary); color:var(--primary-foreground); border:none; border-radius:50%; width:36px; height:36px; display:flex; align-items:center; justify-content:center; cursor:pointer; transition:transform .15s cubic-bezier(.34,1.56,.64,1),opacity .15s,box-shadow .15s; flex-shrink:0; }
.chat-send:hover { transform:scale(1.08); box-shadow:0 2px 12px rgba(0,0,0,.18); }
.chat-send:active { transform:scale(.92); } .chat-send:disabled { opacity:.4; cursor:not-allowed; transform:none; box-shadow:none; }
.chat-send svg { width:14px; height:14px; }
.bubble-ai .ai-ul { margin:4px 0 2px 4px; padding-left:14px; display:flex; flex-direction:column; gap:3px; }
.bubble-ai .ai-ul li { font-size:13px; line-height:1.5; } .bubble-ai strong { font-weight:600; color:var(--foreground); }
.ai-card { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:8px 10px; margin:3px 0; display:flex; flex-direction:column; gap:3px; }
.ai-card-head { display:flex; align-items:center; justify-content:space-between; gap:6px; }
.ai-card-num { font-size:11px; font-weight:700; color:var(--foreground); font-variant-numeric:tabular-nums; }
.ai-card-badge { font-size:10px; font-weight:600; padding:1px 7px; border-radius:9999px; flex-shrink:0; }
.ai-badge-green { background:var(--green-muted); color:var(--green); } .ai-badge-red { background:var(--red-muted); color:var(--red); }
.ai-card-name { font-size:12px; font-weight:500; color:var(--foreground); } .ai-card-meta { font-size:11px; color:var(--muted-foreground); }
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

const fmtNum = (n) => new Intl.NumberFormat("en-US").format(n || 0);
const fmtDate = (iso) => iso ? new Date(iso).toLocaleDateString("en-US", { day: "2-digit", month: "short" }) : "—";

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

function Dashboard({ kpis, clTrend, clDaily, recentCls, paymentSnapshot, topHotels, topHotelsTotal, regionData, reservationFunnel }) {
  const { t } = useI18n();
  const [period, setPeriod] = useState("6M");
  const today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" });
  const remittance = kpis?.remittance_pending != null;
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
      </div>

      <div className="hms-kpi-row">
        <KpiCard
          label={t("CL This Month")}
          value={fmtNum(kpis?.cl_month)}
          icon="cl"
          trend={deltas.cl_month}
          sparkline={monthly.slice(-6)}
          sparkKey="count"
          foot={t("{n} last month", { n: fmtNum(deltas.cl_month?.prev ?? 0) })}
        />
        <KpiCard
          label={t("Check-ins Next 7 Days")}
          value={fmtNum(kpis?.upcoming_checkins)}
          icon="calendar"
          trend={deltas.checkins}
          foot={t("{n} last 7 days", { n: fmtNum(deltas.checkins?.prev ?? 0) })}
        />
        <KpiCard
          label={t("Unpaid Invoices")}
          value={fmtNum(kpis?.unpaid_invoices)}
          icon="invoice"
          tone={kpis?.unpaid_invoices > 0 ? "yellow" : "green"}
          trend={deltas.unpaid}
          trendGood={false}
          foot={t("{amount} SAR outstanding", { amount: fmtNum(kpis?.unpaid_total) })}
        />
        <KpiCard
          label={remittance ? t("Remittance Pending") : t("Outstanding")}
          value={remittance ? fmtNum(kpis?.remittance_pending) : fmtNum(kpis?.unpaid_total)}
          icon="remittance"
          tone={remittance && kpis?.remittance_pending > 0 ? "yellow" : undefined}
          trend={remittance ? deltas.remittance : deltas.unpaid}
          trendGood={false}
          foot={remittance
            ? t("{n} last month", { n: fmtNum(deltas.remittance?.prev ?? 0) })
            : t("{n} invoices unpaid", { n: fmtNum(kpis?.unpaid_invoices) })}
        />
      </div>

      {/* Finance summary row */}
      <div className="hms-home-grid" style={{ marginTop: 20 }}>
        <div className="hms-dv-card">
          <div className="hms-dv-body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--foreground)' }}>{t("Finance Summary")}</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
              <div style={{ padding: '12px 16px', background: 'var(--card)', borderRadius: 10, border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 12, color: 'var(--muted-foreground)' }}>{t("Kas Surabaya")}</div>
                <div style={{ fontSize: 20, fontWeight: 600, fontVariantNumeric: 'tabular-nums', marginTop: 4 }}>
                  {fmtNum(props.finance_summary?.kas_sby || 0)} <span style={{ fontSize: 12, fontWeight: 400 }}>SAR</span>
                </div>
              </div>
              <div style={{ padding: '12px 16px', background: 'var(--card)', borderRadius: 10, border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 12, color: 'var(--muted-foreground)' }}>{t("Kas Pusat")}</div>
                <div style={{ fontSize: 20, fontWeight: 600, fontVariantNumeric: 'tabular-nums', marginTop: 4 }}>
                  {fmtNum(props.finance_summary?.kas_pusat || 0)} <span style={{ fontSize: 12, fontWeight: 400 }}>SAR</span>
                </div>
              </div>
              <div style={{ padding: '12px 16px', background: 'var(--card)', borderRadius: 10, border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 12, color: 'var(--muted-foreground)' }}>{t("Total Piutang")}</div>
                <div style={{ fontSize: 20, fontWeight: 600, fontVariantNumeric: 'tabular-nums', marginTop: 4 }}>
                  {fmtNum(props.finance_summary?.total_piutang || 0)} <span style={{ fontSize: 12, fontWeight: 400 }}>SAR</span>
                </div>
              </div>
              <div style={{ padding: '12px 16px', background: 'var(--card)', borderRadius: 10, border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 12, color: 'var(--muted-foreground)' }}>{t("Payments This Month")}</div>
                <div style={{ fontSize: 20, fontWeight: 600, fontVariantNumeric: 'tabular-nums', marginTop: 4 }}>
                  {fmtNum(props.finance_summary?.payments_this_month || 0)}
                </div>
                <div style={{ fontSize: 11, color: props.finance_summary?.payments_pending > 0 ? '#eab308' : 'var(--muted-foreground)', marginTop: 2 }}>
                  {props.finance_summary?.payments_pending || 0} {t("pending")}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="hms-home-grid">
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
                          <td data-label={t("Check-in")}>{fmtDate(cl.check_in)}</td>
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
      </div>

      <div className="hms-home-grid2">
        <div className="hms-dv-card hms-home-donut">
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
                      <Cell fill="var(--yellow)" />
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
                  <span className="hms-donut-dot" style={{ background: "var(--yellow)" }} />
                  <span className="hms-donut-name">{t("Outstanding")}</span>
                  <span className="hms-donut-val">{fmtNum(outstanding)} {t("SAR")}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="hms-dv-card hms-home-hotels">
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
        </div>
      </div>

      <div className="hms-home-grid3">
        <div className="hms-dv-card hms-home-map">
          <div className="hms-dv-body">
            <div className="hms-dv-sech">
              <span className="hms-dv-sec-title">{t("Customer Map")}</span>
              <span className="hms-dv-count">{regionData.length} {t("regions")}</span>
            </div>
            <MapIndonesia regionData={regionData} />
          </div>
        </div>

        <div className="hms-dv-card hms-home-funnel">
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
                  const colors = ["var(--green)", "var(--primary)", "var(--yellow)"];
                  return (
                    <div className="hms-funnel-row" key={f.label}>
                      <div className="hms-funnel-head">
                        <span className="hms-funnel-label">
                          <span className="hms-funnel-dot" style={{ background: colors[i] }} />
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
        </div>
      </div>
    </>
  );
}

export default function Home() {
  const { props } = usePage();
  const kpis = props.kpis || {};
  const clTrend = props.cl_trend || [];
  const recentCls = props.recent_cls || [];
  const { t } = useI18n();
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

      <Dashboard kpis={kpis} clTrend={clTrend} clDaily={props.cl_daily || []} recentCls={recentCls} paymentSnapshot={props.payment_snapshot} topHotels={props.top_hotels || []} topHotelsTotal={props.top_hotels_total || 0} regionData={props.region_data || []} reservationFunnel={props.reservation_funnel || []} />

      <button className={"ai-fab" + (open ? " open" : "")} title="Ask AI" aria-label="Ask AI" aria-haspopup="true" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <svg className="fab-ic-spark" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">{SPARK}</svg>
        <svg className="fab-ic-close" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
      </button>

      <div className={"ai-panel" + (open ? " open" : "")}>
        <div className="ai-panel-head">
          <div className="ai-head-icon"><svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">{SPARK}</svg></div>
          <div className="ai-head-text">
            <div className="ai-panel-title">{t("Ask AI")}</div>
            <div className="ai-panel-sub">{t("Instant answers from your data")}</div>
          </div>
          <button className="ai-panel-close" onClick={() => setOpen(false)}>
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
        <div className="chat-messages" ref={msgRef} aria-live="polite">
          {messages.length === 0 && !typing && (
            <div className="chat-empty">
              <div className="chat-empty-icon"><svg width="17" height="17" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">{SPARK}</svg></div>
              <div className="chat-empty-title">{t("Ask anything")}</div>
              <div className="chat-empty-sub">{t("Invoices, reservations, or clients — answered from your data")}</div>
              <div className="chat-sugs">
                {[t("Unpaid invoices"), t("Reservations this month"), t("Total outstanding")].map((s) => (
                  <button key={s} type="button" className="chat-sug" onClick={() => send(s)}>{s}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            m.type === "user"
              ? <div key={i} className="chat-bubble bubble-user">{m.text}</div>
              : <div key={i} className="chat-bubble bubble-ai" dangerouslySetInnerHTML={{ __html: m.html }} />
          ))}
          {typing && <div className="chat-bubble bubble-ai bubble-typing"><span></span><span></span><span></span></div>}
        </div>
        <div className="chat-input-row">
          <div className="chat-input-pill">
            <input ref={inputRef} type="text" className="chat-input" placeholder={t("Ask about your data…")} autoComplete="off"
              value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") send(); }} />
          </div>
          <button className="chat-send" title={t("Send")} disabled={typing} onClick={() => send()}>
            <svg fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" /></svg>
          </button>
        </div>
      </div>
    </div>
  );
}
