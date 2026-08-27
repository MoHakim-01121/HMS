import { useState, useRef } from "react";
import axios from "axios";
import { router } from "@inertiajs/react";
import { showToast } from "../../components/shadcn/toast.jsx";
import { Icon } from "../../components/icons.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Local-timezone YYYY-MM-DD; toISOString() is UTC and would mislabel
// "Today"/"Tomorrow" between 00:00 and 07:00 WIB.
const localYMD  = (d) => d.toLocaleDateString('en-CA');
const TODAY    = localYMD(new Date());
const TOMORROW = localYMD(new Date(Date.now() + 86400000));

// Compact "27 Aug" rendering for stay dates (input arrives as YYYY-MM-DD).
const fmtDate = (ymd) => {
  if (!ymd) return '';
  const d = new Date(ymd + 'T00:00:00');
  if (Number.isNaN(d.getTime())) return ymd;
  return d.toLocaleDateString('en-US', { day: 'numeric', month: 'short' }).replace('.', '');
};

// Mobile-first redesign 2026-08-26 v2: vertical timeline with swipeable
// booking cards, tappable field pills, and summary-first card hierarchy.
const CSS = `
.uc-wrap { margin-top:36px; }
.uc-card { background:var(--card); border:1px solid var(--border); border-radius:20px; padding:20px 22px 8px; }

/* ── section head ───────────────────────────────────────────── */
.uc-head { display:flex; align-items:flex-start; justify-content:space-between; gap:14px; flex-wrap:wrap; padding-bottom:16px; border-bottom:1px solid var(--border); }
.uc-title { margin:0; font-size:15px; font-weight:600; color:var(--foreground); letter-spacing:-.01em; }
.uc-sub { margin-top:4px; font-size:12px; color:var(--muted-foreground); }
.uc-head-actions { display:flex; align-items:center; gap:8px; flex-shrink:0; }

/* ═══ MOBILE TIMELINE (<=600px) ═══════════════════════════════ */
/* Vertical line down the left edge connecting day nodes. Each day is a
   self-contained section with a colored dot on the timeline. Today's
   dot is larger and uses --primary ink. */
.uc-tl { position:relative; padding-left:28px; }
.uc-tl::before { content:''; position:absolute; left:9px; top:6px; bottom:6px; width:2px; background:var(--border); border-radius:1px; }

.uc-tl-day { position:relative; padding-top:16px; }
.uc-tl-day:first-child { padding-top:0; }

/* Timeline dot */
.uc-tl-dot { position:absolute; left:-28px; top:2px; width:20px; height:20px; border-radius:9999px; border:2.5px solid var(--card); display:flex; align-items:center; justify-content:center; z-index:1; }
.uc-tl-dot::after { content:''; width:10px; height:10px; border-radius:9999px; background:var(--border); }
.uc-tl-dot.is-today { top:-1px; width:22px; height:22px; left:-29px; }
.uc-tl-dot.is-today::after { background:var(--primary); width:12px; height:12px; }

/* Day header — tap to expand/collapse */
.uc-tl-head { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:8px 12px; border-radius:12px; cursor:pointer; -webkit-tap-highlight-color:transparent; user-select:none; transition:background .12s; }
.uc-tl-head:active { background:var(--secondary); }
.uc-tl-day-left { display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; min-width:0; flex:1; }
.uc-tl-label { font-size:14px; font-weight:700; color:var(--foreground); letter-spacing:-.01em; white-space:nowrap; }
.uc-tl-label.is-today { padding:3px 12px; border-radius:9999px; background:var(--primary); color:var(--primary-foreground); }
.uc-tl-meta { font-size:12px; color:var(--muted-foreground); white-space:nowrap; }
.uc-tl-warn { display:inline-flex; align-items:center; gap:3px; font-size:11px; font-weight:600; color:var(--red); padding:2px 8px; border-radius:9999px; background:color-mix(in oklch, var(--red) 10%, transparent); white-space:nowrap; }
.uc-tl-right { display:flex; align-items:center; gap:4px; flex-shrink:0; }
.uc-tl-chevron { color:var(--muted-foreground); transition:transform .2s ease; display:flex; }
.uc-tl-chevron.open { transform:rotate(180deg); }

/* Day body — collapsible */
.uc-tl-body { overflow:hidden; transition:max-height .28s cubic-bezier(.4,0,.2,1), opacity .2s ease; }
.uc-tl-body.collapsed { max-height:0; opacity:0; pointer-events:none; }

/* ── Client group inside timeline ─────────────────────────── */
.uc-tl-client { margin-top:10px; }
.uc-tl-client + .uc-tl-client { margin-top:14px; }
.uc-tl-client-head { display:flex; align-items:center; gap:8px; padding:7px 10px; border-radius:10px; background:var(--secondary); }
.uc-tl-client-name { font-size:13px; font-weight:600; color:var(--foreground); min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.uc-tl-client-count { font-size:11px; color:var(--muted-foreground); flex-shrink:0; }

/* ── Swipeable booking card ────────────────────────────────── */
/* Each card sits in a overflow:hidden wrapper. The action panels (WA / PDF)
   are revealed by swipe. touch-action: pan-y so vertical scroll still works. */
.uc-swipe-wrap { position:relative; margin-top:8px; border-radius:20px; overflow:hidden; }
.uc-swipe-actions { position:absolute; inset:0; display:flex; }
.uc-swipe-left { flex:1; display:flex; align-items:center; justify-content:flex-end; padding-right:16px; gap:6px; background:var(--green); color:#fff; font-size:12px; font-weight:600; }
.uc-swipe-right { flex:1; display:flex; align-items:center; justify-content:flex-start; padding-left:16px; gap:6px; background:var(--muted-foreground); color:var(--card); font-size:12px; font-weight:600; }

.uc-booking { position:relative; z-index:1; background:var(--card); border:1px solid var(--border); border-radius:20px; padding:16px; touch-action:pan-y; transition:transform .2s cubic-bezier(.4,0,.2,1); }
.uc-booking.swiping { transition:none; }

.uc-booking-left { display:flex; align-items:center; gap:6px; }

/* Reminder chips */
.uc-rem { display:inline-flex; align-items:center; gap:3px; font-size:10px; font-weight:600; padding:3px 8px 3px 7px; border-radius:9999px; text-transform:uppercase; letter-spacing:.04em; white-space:nowrap; min-height:26px; }
.uc-rem svg { flex-shrink:0; }
.uc-rem.sent { background:color-mix(in oklch, var(--green) 16%, transparent); color:var(--green); }
.uc-rem.failed { background:color-mix(in oklch, var(--red) 15%, transparent); color:var(--red); }

/* Empty state */
.uc-empty { margin:22px 0 24px; padding:52px 24px; text-align:center; border:1px dashed var(--border); border-radius:16px; }
.uc-empty-title { font-size:14px; font-weight:600; color:var(--foreground); margin:10px 0 6px; }
.uc-empty-sub { font-size:12.5px; color:var(--muted-foreground); }

/* ═══ DESKTOP (>=601px) ═══════════════════════════════════════ */
/* The timeline and swipe cards above are unreachable here — desktop uses
   the original flat grid rows. */
.uc-day { border-top:1px solid var(--border); }
.uc-day-head { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:14px 0; }
.uc-day-left { display:flex; align-items:baseline; gap:9px; flex-wrap:wrap; min-width:0; flex:1; }
.uc-day-label { font-size:13px; font-weight:600; color:var(--foreground); letter-spacing:-.01em; white-space:nowrap; }
.uc-day-label.is-today { padding:3px 11px; border-radius:9999px; background:var(--primary); color:var(--primary-foreground); }
.uc-day-meta { font-size:12px; color:var(--muted-foreground); white-space:nowrap; }
.uc-day-warn { font-size:12px; font-weight:500; color:var(--red); white-space:nowrap; }
.uc-day-right { display:flex; align-items:center; gap:6px; flex-shrink:0; }
.uc-cl { font-size:13px; font-weight:600; color:var(--foreground); text-decoration:none; font-variant-numeric:tabular-nums; }
.uc-cl:hover { text-decoration:underline; text-underline-offset:2px; }
.uc-row { display:grid; grid-template-columns:82px minmax(110px,1.3fr) minmax(80px,.9fr) 96px minmax(104px,1fr) minmax(96px,.9fr) minmax(112px,auto); align-items:center; gap:12px; padding:6px 12px; border-radius:10px; }
.uc-row + .uc-row { box-shadow:inset 0 1px 0 var(--border); }
.uc-row:hover { background:var(--background); }
.uc-row:hover + .uc-row { box-shadow:none; }
.uc-cell { font-size:12px; color:var(--muted-foreground); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.uc-end { display:flex; align-items:center; justify-content:flex-end; gap:6px; }

.uc-card input:not([type="checkbox"]):not([type="radio"]) {
  width:100%; height:30px; padding:0 8px; box-sizing:border-box;
  background:transparent; border:1px solid transparent; border-radius:8px;
  color:var(--foreground); font-size:12.5px; font-family:inherit;
  box-shadow:none; transition:border-color .12s ease, background .12s ease;
}
.uc-card input:not([type="checkbox"]):not([type="radio"]):hover { border-color:var(--border); }
.uc-card input:not([type="checkbox"]):not([type="radio"]):focus {
  outline:none; background:var(--card); border-color:var(--ring);
  box-shadow:inset 0 0 0 1px var(--ring);
}
.uc-card input::placeholder { color:var(--muted-foreground); }
.uc-eta-input { font-weight:600; font-variant-numeric:tabular-nums; }
.uc-eta-input[data-empty="true"] { color:var(--red); }

/* ── Tablet (601-820px) — folding grid ─────────────────────── */
@media (max-width:820px) {
  .uc-row { grid-template-columns:minmax(0,1fr) minmax(0,1fr); column-gap:10px; row-gap:6px; padding:10px 12px; }
  .uc-cl-cell   { grid-area:1 / 1; }
  .uc-rooms     { grid-area:1 / 2; text-align:right; }
  .uc-where     { grid-area:2 / 1 / 2 / -1; }
  .uc-eta-input { grid-area:3 / 1; }
  .uc-end       { grid-area:3 / 2; }
  .uc-pic-name  { grid-area:4 / 1; }
  .uc-pic-phone { grid-area:4 / 2; }
  .uc-card input:not([type="checkbox"]):not([type="radio"]) { border-color:var(--border); background:var(--card); }
}

@media (max-width:600px) {
  .uc-wrap { margin-top:24px; padding:0 14px; }
  .uc-card { padding:16px 14px 6px; border-radius:16px; }
  .uc-head { padding-bottom:12px; }

  /* Mobile only: soft depth over the hard border.
     2-zone arrival card — identity+ETA hero, then compact status row. */
  .uc-booking {
    border-color: color-mix(in oklch, var(--border) 70%, transparent);
    box-shadow: 0 2px 10px rgba(0,0,0,.04);
  }

  /* Zone 1 — reservation number (primary) + guest */
  .uc-bb-head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
  .uc-bb-id { min-width:0; flex:1; }
  .uc-bb-conf { display:block; font-size:18px; font-weight:800; letter-spacing:-.01em; color:var(--foreground); line-height:1.2; font-variant-numeric:tabular-nums; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .uc-bb-guest { display:block; font-size:13.5px; font-weight:600; color:var(--foreground); margin-top:2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; text-decoration:none; }
  .uc-bb-guest:active { opacity:.7; }
  .uc-bb-meta { display:flex; flex-wrap:wrap; align-items:flex-start; gap:10px 18px; margin-top:10px; }
  .uc-bb-meta-item { display:flex; flex-direction:column; gap:1px; min-width:0; }
  .uc-bb-meta-k { font-size:11px; font-weight:500; color:var(--muted-foreground); text-transform:uppercase; letter-spacing:.04em; }
  .uc-bb-meta-v { font-size:13px; font-weight:600; color:var(--foreground); font-variant-numeric:tabular-nums; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

  /* Zone 2 — form fields, matched to the app's form inputs */
  .uc-bb-form { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; margin-top:14px; }
  .uc-bb-field:nth-child(1) { grid-column:1; grid-row:1; }
  .uc-bb-field:nth-child(3) { grid-column:2; grid-row:1; }
  .uc-bb-field:nth-child(2) { grid-column:1 / -1; grid-row:2; }
  .uc-bb-field { display:flex; flex-direction:column; gap:6px; min-width:0; }
  .uc-bb-label { font-size:12px; font-weight:500; color:var(--muted-foreground); }
  .uc-bb-field--view { gap:1px; }
  .uc-bb-viewval { font-size:14px; font-weight:600; color:var(--foreground); font-variant-numeric:tabular-nums; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .uc-bb-viewval.is-empty { color:var(--muted-foreground); font-weight:500; }
  .uc-bb-edit { flex-shrink:0; margin-top:2px; }

  /* Footer — reminders + save */
  .uc-bb-foot { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-top:14px; }
  .uc-bb-right { display:flex; align-items:center; gap:8px; min-width:0; }

  /* Summary strip — glanceable arrival counts */
  .uc-sum { display:flex; gap:6px; overflow-x:auto; -webkit-overflow-scrolling:touch; scrollbar-width:none; padding:2px 0 8px; }
  .uc-sum::-webkit-scrollbar { display:none; }
  .uc-sum-item { flex-shrink:0; display:inline-flex; align-items:center; gap:4px; padding:5px 12px; border-radius:9999px; background:var(--secondary); color:var(--muted-foreground); font-size:12px; font-weight:500; white-space:nowrap; }
  .uc-sum-val { font-weight:700; color:var(--foreground); font-variant-numeric:tabular-nums; }
  .uc-sum-item.warn { background:color-mix(in oklch, var(--red) 14%, transparent); color:var(--red); }
  .uc-sum-item.warn .uc-sum-val { color:var(--red); }

  /* Segmented tab control */
  .uc-tabs { display:flex; gap:4px; padding:2px; border-radius:14px; background:var(--secondary); margin-bottom:2px; }
  .uc-tab { flex:1; display:inline-flex; align-items:center; justify-content:center; gap:6px; min-height:40px; padding:0 10px; border-radius:11px; border:none; background:transparent; color:var(--muted-foreground); font-size:13px; font-weight:600; cursor:pointer; -webkit-tap-highlight-color:transparent; transition:background .12s,color .12s,box-shadow .12s; font-family:inherit; }
  .uc-tab.active { background:var(--card); color:var(--foreground); box-shadow:0 1px 3px rgba(0,0,0,.12); }
  .uc-tab-count { font-size:11px; font-weight:700; font-variant-numeric:tabular-nums; opacity:.75; }
  .uc-tab.active .uc-tab-count { opacity:1; }
}`;

const WAIcon = ({ size = 13 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" style={{ flexShrink: 0 }}>
    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"/>
  </svg>
);

const PrinterIcon = ({ size = 13 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <polyline points="6 9 6 2 18 2 18 9"/>
    <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>
    <rect x="6" y="14" width="12" height="8"/>
  </svg>
);

const PencilIcon = ({ size = 13 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
  </svg>
);

const GearIcon = ({ size = 15 }) => (
  <svg width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
  </svg>
);

const ChevronDown = ({ size = 14 }) => (
  <svg width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
  </svg>
);

function ReminderChip({ sent, failed, label }) {
  const { t } = useI18n();
  if (!sent && !failed) return null;
  return (
    <span className={"uc-rem " + (sent ? "sent" : "failed")} title={sent ? t("Sent") : t("Failed to send")}>
      <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {sent ? <polyline points="20 6 9 17 4 12" /> : <><path d="M18 6 6 18" /><path d="m6 6 12 12" /></>}
      </svg>
      {label}
    </span>
  );
}

// ── Swipeable booking card ──────────────────────────────────
// Tracks touch delta horizontally while allowing vertical scroll. When
// swiped >60px left the WA action is triggered; >60px right opens PDF.
export function SwipeBookingCard({ cl }) {
  const { t } = useI18n();
  const wrapRef = useRef(null);
  const [offset, setOffset] = useState(0);
  const [swiping, setSwiping] = useState(false);
  const startX = useRef(0);
  const startY = useRef(0);
  const locked = useRef(false);

  const [saved, setSaved] = useState({
    estimasi: cl.estimasi_tiba || '', picName: cl.pic_name || '', picPhone: cl.pic_phone || '',
  });
  const [draft, setDraft] = useState(saved);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false); // true = edit mode (inputs shown)

  const dirty = draft.estimasi !== saved.estimasi
    || draft.picName !== saved.picName
    || draft.picPhone !== saved.picPhone;

  const set = (k) => (e) => setDraft((d) => ({ ...d, [k]: e.target.value }));

  const handleSave = async () => {
    setSaving(true);
    try {
      await axios.post(
        `/calendar/cl/${cl.pk}/estimasi/`,
        new URLSearchParams({ estimasi_tiba: draft.estimasi, pic_name: draft.picName, pic_phone: draft.picPhone }),
        { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
      );
      setSaved(draft);
      setEditing(false);
      router.reload({ only: ['upcoming_checkins'] });
    } catch {
      showToast(t('Failed to save changes'), 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleTouchStart = (e) => {
    startX.current = e.touches[0].clientX;
    startY.current = e.touches[0].clientY;
    locked.current = false;
  };

  const handleTouchMove = (e) => {
    if (locked.current) return;
    const dx = e.touches[0].clientX - startX.current;
    const dy = e.touches[0].clientY - startY.current;
    // Lock after a clear horizontal move; otherwise let vertical scroll pass
    if (Math.abs(dx) > 8 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      locked.current = true;
      setSwiping(true);
    } else if (Math.abs(dy) > 8) {
      locked.current = true; // decided it's a scroll, stop tracking
    }
    if (locked.current && swiping) {
      e.preventDefault();
      setOffset(dx);
    }
  };

  const handleTouchEnd = () => {
    if (offset < -60) {
      // Swipe left → WA send
      handleSendWA();
    } else if (offset > 60) {
      // Swipe right → open PDF
      window.open(`/calendar/checkin-pdf/?date=${cl.check_in}`, '_blank');
    }
    setOffset(0);
    setSwiping(false);
  };

  const handleSendWA = async () => {
    try {
      const body = new URLSearchParams();
      body.append('cl_ids', cl.pk);
      const r = await axios.post('/calendar/send-reminder-group/', body, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });
      showToast(r.data.ok ? t("WA sent") : (r.data.message || t('Failed')), r.data.ok ? 'success' : 'error');
    } catch { showToast(t('Failed to send'), 'error'); }
  };

  const beginEdit = () => { setDraft(saved); setEditing(true); };
  const cancelEdit = () => { setDraft(saved); setEditing(false); };

  const labelFor = (k) => (k === 'eta' ? t("ETA") : k === 'phone' ? t("Phone") : t("PIC name"));
  const valueFor = (k) => (k === 'eta' ? draft.estimasi : k === 'phone' ? draft.picPhone : draft.picName);
  const emptyFor = (k) => (k === 'eta' ? t("No ETA set") : t("Not set"));

  const field = (k) => {
    const cfg = k === 'eta' ? { type: 'time', aria: t("Estimated arrival time") }
      : k === 'phone' ? { type: 'tel', placeholder: t("Phone") }
      : { type: 'text', placeholder: t("PIC name") };
    if (!editing) {
      const v = valueFor(k);
      return (
        <div className="uc-bb-field uc-bb-field--view">
          <span className="uc-bb-label">{labelFor(k)}</span>
          <span className={v ? "uc-bb-viewval" : "uc-bb-viewval is-empty"}>{v || emptyFor(k)}</span>
        </div>
      );
    }
    return (
      <div className="uc-bb-field">
        <span className="uc-bb-label">{labelFor(k)}</span>
        <Input
          autoFocus={k === 'eta'}
          type={cfg.type}
          {...(cfg.aria ? { 'aria-label': cfg.aria } : { placeholder: cfg.placeholder })}
          value={valueFor(k)}
          onChange={set(k === 'eta' ? 'estimasi' : k === 'phone' ? 'picPhone' : 'picName')}
        />
      </div>
    );
  };

  return (
    <div className="uc-swipe-wrap" ref={wrapRef}>
      {/* Reveal panels behind the card */}
      <div className="uc-swipe-actions">
        <div className="uc-swipe-left">
          <WAIcon size={16} /> WA
        </div>
        <div className="uc-swipe-right">
          <PrinterIcon size={14} /> PDF
        </div>
      </div>
      {/* Card */}
      <div className={"uc-booking" + (swiping ? " swiping" : "")}
        style={{ transform: `translateX(${offset}px)` }}
        onTouchStart={handleTouchStart} onTouchMove={handleTouchMove} onTouchEnd={handleTouchEnd}>
        {/* Zone 1 — reservation number (primary) + guest */}
        <div className="uc-bb-head">
          <div className="uc-bb-id">
            <span className="uc-bb-conf">{cl.confirmation_number}</span>
            <a className="uc-bb-guest" href={cl.url}>{cl.guest_name || t("Guest")}</a>
            <span className="uc-bb-meta">
              {cl.check_in ? (
                <span className="uc-bb-meta-item">
                  <span className="uc-bb-meta-k">{t("Stay")}</span>
                  <span className="uc-bb-meta-v">{fmtDate(cl.check_in)} – {fmtDate(cl.check_out)}</span>
                </span>
              ) : null}
              {cl.hotel_name ? (
                <span className="uc-bb-meta-item">
                  <span className="uc-bb-meta-k">{t("Hotel")}</span>
                  <span className="uc-bb-meta-v">{cl.hotel_name}</span>
                </span>
              ) : null}
              {cl.rooms ? (
                <span className="uc-bb-meta-item">
                  <span className="uc-bb-meta-k">{t("Rooms")}</span>
                  <span className="uc-bb-meta-v">{cl.rooms}</span>
                </span>
              ) : null}
            </span>
          </div>
          {!editing && (
            <Button variant="outline" size="sm" className="uc-bb-edit" onClick={beginEdit}>
              <PencilIcon size={13} /> {t("Edit")}
            </Button>
          )}
        </div>
        {/* Zone 2 — arrival details: display vs edit */}
        <div className="uc-bb-form">
          {field('eta')}
          {field('pic')}
          {field('phone')}
        </div>
        {/* Footer: reminders + edit/save */}
        <div className="uc-bb-foot">
          <div className="uc-bb-right">
            <div className="uc-booking-left">
              <ReminderChip sent={cl.h1_sent} failed={cl.h1_failed} label="H-1" />
              <ReminderChip sent={cl.h0_sent} failed={cl.h0_failed} label="H-0" />
            </div>
            {editing && (
              <>
                <Button variant="ghost" size="xs" onClick={cancelEdit} disabled={saving}>{t("Cancel")}</Button>
                <Button size="sm" onClick={handleSave} disabled={saving || !dirty}>{saving ? '…' : t("Save")}</Button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Desktop booking row (unchanged) ─────────────────────────
function DesktopBookingRow({ cl }) {
  const { t } = useI18n();
  const [saved, setSaved] = useState({
    estimasi: cl.estimasi_tiba || '', picName: cl.pic_name || '', picPhone: cl.pic_phone || '',
  });
  const [draft, setDraft] = useState(saved);
  const [saving, setSaving] = useState(false);

  const dirty = draft.estimasi !== saved.estimasi
    || draft.picName !== saved.picName
    || draft.picPhone !== saved.picPhone;

  const set = (k) => (e) => setDraft((d) => ({ ...d, [k]: e.target.value }));

  const handleSave = async () => {
    setSaving(true);
    try {
      await axios.post(
        `/calendar/cl/${cl.pk}/estimasi/`,
        new URLSearchParams({ estimasi_tiba: draft.estimasi, pic_name: draft.picName, pic_phone: draft.picPhone }),
        { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
      );
      setSaved(draft);
      router.reload({ only: ['upcoming_checkins'] });
    } catch {
      showToast(t('Failed to save changes'), 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="uc-row">
      <div className="uc-cl-cell">
        <a className="uc-cl" href={cl.url}>{cl.confirmation_number}</a>
      </div>
      <div className="uc-cell uc-where" title={cl.hotel_name || ''}>{cl.hotel_name || '—'}</div>
      <div className="uc-cell uc-rooms" title={cl.rooms || ''}>{cl.rooms || '—'}</div>
      <input
        className="uc-eta-input" type="time" value={draft.estimasi} onChange={set('estimasi')}
        data-empty={draft.estimasi ? "false" : "true"} aria-label={t("Estimated arrival time")}
      />
      <input
        className="uc-pic-name" type="text" value={draft.picName} onChange={set('picName')}
        placeholder={t("PIC name")} aria-label={t("PIC name")}
      />
      <input
        className="uc-pic-phone" type="text" value={draft.picPhone} onChange={set('picPhone')}
        placeholder={t("PIC phone no.")} aria-label={t("PIC phone no.")} inputMode="tel"
      />
      <div className="uc-end">
        {dirty ? (
          <>
            <Button variant="ghost" size="xs" onClick={() => setDraft(saved)} disabled={saving}>{t("Cancel")}</Button>
            <Button size="xs" onClick={handleSave} disabled={saving}>{saving ? '…' : t("Save")}</Button>
          </>
        ) : (
          <>
            <ReminderChip sent={cl.h1_sent} failed={cl.h1_failed} label="H-1" />
            <ReminderChip sent={cl.h0_sent} failed={cl.h0_failed} label="H-0" />
          </>
        )}
      </div>
    </div>
  );
}

// ── ClientBlock ────────────────────────────────────────────
function ClientBlock({ clientName, cls, isMobile }) {
  const { t } = useI18n();
  const [sending, setSending] = useState(false);

  const handleSend = async () => {
    setSending(true);
    try {
      const body = new URLSearchParams();
      cls.forEach(cl => body.append('cl_ids', cl.pk));
      const r = await axios.post('/calendar/send-reminder-group/', body, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });
      showToast(r.data.ok ? t("Message sent to {name}", { name: clientName }) : (r.data.message || t('Failed to send message')), r.data.ok ? 'success' : 'error');
    } catch { showToast(t('Failed to send message'), 'error'); }
    setSending(false);
  };

  return (
    <div className="uc-tl-client">
      <div className="uc-tl-client-head">
        <span className="uc-tl-client-name">{clientName}</span>
        {cls.length > 1 && <span className="uc-tl-client-count">{t("{count} bookings", { count: cls.length })}</span>}
        <Button variant="outline" size="xs" style={{ marginLeft: 'auto' }} onClick={handleSend} disabled={sending}>
          {sending ? '…' : <><WAIcon size={11} /> WA</>}
        </Button>
      </div>
      {cls.map(cl => isMobile
        ? <SwipeBookingCard key={cl.pk} cl={cl} />
        : <DesktopBookingRow key={cl.pk} cl={cl} />
      )}
    </div>
  );
}

function groupByClient(cls) {
  const nameKey = (cl) => (cl.guest_name || '').trim().toLowerCase();
  const phonesByName = {};
  cls.forEach(cl => {
    if (!cl.client_id && cl.guest_phone) {
      if (!phonesByName[nameKey(cl)]) phonesByName[nameKey(cl)] = new Set();
      phonesByName[nameKey(cl)].add(cl.guest_phone);
    }
  });
  const groups = {};
  cls.forEach(cl => {
    let key;
    if (cl.client_id) {
      key = `client-${cl.client_id}`;
    } else {
      const phones = phonesByName[nameKey(cl)] || new Set();
      key = phones.size <= 1
        ? `guest-${nameKey(cl)}-${[...phones][0] || ''}`
        : `guest-${nameKey(cl)}-${cl.guest_phone || cl.pk}`;
    }
    if (!groups[key]) groups[key] = { name: cl.client_name || cl.guest_name, items: [] };
    groups[key].items.push(cl);
  });
  return groups;
}

// ── DayBlock — timeline node on mobile, flat on desktop ─────
function DayBlock({ dateStr, cls, defaultOpen, isMobile, isLast }) {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState(defaultOpen);
  const [sending, setSending] = useState(false);

  const isToday       = dateStr === TODAY;
  const incompleteCnt = cls.filter(c => !c.estimasi_tiba).length;
  const d = new Date(dateStr + 'T00:00:00');
  const intlLocale = locale === 'id' ? 'id-ID' : 'en-US';
  const label    = isToday ? t('Today')
                 : dateStr === TOMORROW ? t('Tomorrow')
                 : d.toLocaleDateString(intlLocale, { weekday: 'long' });
  const dateFull = d.toLocaleDateString(intlLocale, { day: 'numeric', month: 'long', year: 'numeric' });

  const handleSendRecap = async () => {
    setSending(true);
    try {
      const r = await axios.post(
        '/calendar/send-recap/',
        new URLSearchParams({ date: dateStr }),
        { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
      );
      showToast(r.data.ok ? t('Recap queued.') : (r.data.message || t('Failed to send recap')), r.data.ok ? 'success' : 'error');
    } catch { showToast(t('Failed to send recap'), 'error'); }
    setSending(false);
  };

  const dayContent = Object.entries(groupByClient(cls)).map(([key, group]) =>
    <ClientBlock key={key} clientName={group.name} cls={group.items} isMobile={isMobile} />
  );

  if (isMobile) {
    return (
      <div className={"uc-tl-day" + (isLast ? " uc-tl-last" : "")}>
        <div className={"uc-tl-dot" + (isToday ? " is-today" : "")} />
        <div className="uc-tl-head" onClick={() => setOpen(o => !o)}>
          <div className="uc-tl-day-left">
            <span className={"uc-tl-label" + (isToday ? " is-today" : "")}>{label}</span>
            <span className="uc-tl-meta">{dateFull} · {cls.length}</span>
            {incompleteCnt > 0 && <span className="uc-tl-warn">⚠ {incompleteCnt} {t("ETA")}</span>}
          </div>
          <div className="uc-tl-right">
            <Button variant="ghost" size="icon-sm" onClick={(e) => { e.stopPropagation(); handleSendRecap(); }} disabled={sending}
              title={t("Send Recap")} aria-label={t("Send Recap")}>
              <WAIcon size={14} />
            </Button>
            <span className={"uc-tl-chevron" + (open ? " open" : "")}>
              <ChevronDown />
            </span>
          </div>
        </div>
        <div className={"uc-tl-body" + (open ? "" : " collapsed")}>
          {dayContent}
        </div>
      </div>
    );
  }

  // Desktop: unchanged layout
  return (
    <div className="uc-day">
      <div className="uc-day-head">
        <div className="uc-day-left">
          <span className={"uc-day-label" + (isToday ? " is-today" : "")}>{label}</span>
          <span className="uc-day-meta">{dateFull} · {t("{count} guests", { count: cls.length })}</span>
          {incompleteCnt > 0 && <span className="uc-day-warn">{t("{count} missing ETA", { count: incompleteCnt })}</span>}
        </div>
        <div className="uc-day-right">
          <Button variant="outline" size="icon-sm" asChild>
            <a href={`/calendar/checkin-pdf/?date=${dateStr}`} target="_blank" rel="noreferrer"
              title={t("Download PDF {date}", { date: dateFull })} aria-label={t("Download PDF {date}", { date: dateFull })}>
              <PrinterIcon size={13} />
            </a>
          </Button>
          <Button size="sm" onClick={handleSendRecap} disabled={sending}>
            {sending ? '…' : <><WAIcon size={12} /> {t("Send Recap")}</>}
          </Button>
        </div>
      </div>
      {dayContent}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────
export default function UpcomingCheckins({ upcoming_checkins, last_recap }) {
  const { t } = useI18n();
  const checkins = upcoming_checkins || [];
  const isMobile = typeof window !== "undefined" && window.innerWidth <= 600;
  const [mobileTab, setMobileTab] = useState("week"); // "today" | "tomorrow" | "week"

  const grouped = {};
  checkins.forEach(cl => {
    const key = cl.check_in || 'unknown';
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(cl);
  });
  const sortedDates = Object.keys(grouped).sort();
  const todayDates = sortedDates.filter(d => d === TODAY);
  const tomorrowDates = sortedDates.filter(d => d === TOMORROW);
  const todayCls = (grouped[TODAY] || []);
  const tomorrowCls = (grouped[TOMORROW] || []);
  const missingTodayEta = todayCls.filter(c => !c.estimasi_tiba).length;

  // Drive the displayed day blocks by the active mobile tab.
  let visibleDates = sortedDates;
  if (isMobile) {
    if (mobileTab === "today") visibleDates = todayDates;
    else if (mobileTab === "tomorrow") visibleDates = tomorrowDates;
  }

  return (
    <div className="uc-wrap">
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      <div className="uc-card">
        <div className="uc-head">
          <div>
            <h2 className="uc-title">{t("Upcoming Check-ins")}</h2>
            <div className="uc-sub">
              {t("{count} guests · next 7 days", { count: checkins.length })}
              {last_recap && t(" · last recap {time}", { time: last_recap.sent_at })}
            </div>
          </div>
          <div className="uc-head-actions">
            {!isMobile && (
              <Button variant="outline" size="sm" asChild>
                <a href="/calendar/checkin-pdf/" target="_blank" rel="noreferrer" title={t("Download PDF of all upcoming check-ins")}>
                  <PrinterIcon size={13} /> PDF
                </a>
              </Button>
            )}
            <Button variant="outline" size="icon-sm" asChild>
              <a href="/calendar/recap-settings/" title={t("Recap Settings")} aria-label={t("Recap Settings")}>
                <GearIcon size={15} />
              </a>
            </Button>
          </div>
        </div>

        {isMobile && (
          <>
            {/* Summary strip — what the front-desk needs at a glance */}
            <div className="uc-sum">
              <div className="uc-sum-item"><span className="uc-sum-val">{todayCls.length}</span> {t("Today")}</div>
              <div className="uc-sum-item"><span className="uc-sum-val">{tomorrowCls.length}</span> {t("Tomorrow")}</div>
              <div className="uc-sum-item"><span className="uc-sum-val">{checkins.length}</span> {t("7 days")}</div>
              {missingTodayEta > 0 && (
                <div className="uc-sum-item warn"><span className="uc-sum-val">{missingTodayEta}</span> {t("no ETA")}</div>
              )}
            </div>
            {/* Segmented tab control */}
            <div className="uc-tabs" role="tablist" aria-label={t("Filter check-ins")}>
              {[
                { k: "today", label: t("Today") },
                { k: "tomorrow", label: t("Tomorrow") },
                { k: "week", label: t("7 Days") },
              ].map(tab => (
                <button key={tab.k} type="button" role="tab" aria-selected={mobileTab === tab.k}
                  className={"uc-tab" + (mobileTab === tab.k ? " active" : "")}
                  onClick={() => setMobileTab(tab.k)}>
                  {tab.label}
                  <span className="uc-tab-count">{tab.k === "today" ? todayCls.length : tab.k === "tomorrow" ? tomorrowCls.length : checkins.length}</span>
                </button>
              ))}
            </div>
          </>
        )}

        {sortedDates.length === 0 ? (
          <div className="uc-empty">
            <div style={{ display: 'flex', justifyContent: 'center', color: 'var(--muted-foreground)' }}>
              <Icon name="calendar" size={30} strokeWidth={1.5} />
            </div>
            <div className="uc-empty-title">{t("No upcoming check-ins")}</div>
            <div className="uc-empty-sub">{t("No guests checking in within the next 7 days.")}</div>
          </div>
        ) : isMobile ? (
          /* Mobile: vertical timeline driven by the active tab */
          <div className="uc-tl">
            {(visibleDates.length ? visibleDates : sortedDates).map((dateStr, i) => (
              <DayBlock key={dateStr} dateStr={dateStr} cls={grouped[dateStr]}
                defaultOpen={dateStr === TODAY} isMobile={true} isLast={i === visibleDates.length - 1} />
            ))}
          </div>
        ) : (
          /* Desktop: flat day blocks */
          sortedDates.map((dateStr) => (
            <DayBlock key={dateStr} dateStr={dateStr} cls={grouped[dateStr]}
              defaultOpen={true} isMobile={false} isLast={false} />
          ))
        )}
      </div>
    </div>
  );
}
