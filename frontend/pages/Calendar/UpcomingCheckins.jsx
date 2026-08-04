import { useState } from "react";
import axios from "axios";
import { router } from "@inertiajs/react";
import { showToast } from "../../components/shadcn/toast.jsx";
import { Icon } from "../../components/icons.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Local-timezone YYYY-MM-DD; toISOString() is UTC and would mislabel
// "Today"/"Tomorrow" between 00:00 and 07:00 WIB.
const localYMD  = (d) => d.toLocaleDateString('en-CA');
const TODAY    = localYMD(new Date());
const TOMORROW = localYMD(new Date(Date.now() + 86400000));

// Rebuilt 2026-07-30. The previous version nested four containers deep —
// section card > date group > client CARD (in an auto-fill grid) > hotel
// eyebrow > booking row — and restated the same numbers at three of those
// levels ("n belum ETA" in the section head AND every date head; "n tamu" in
// both; a PDF button in both). Every booking also carried two permanently
// grey H-1/H-0 chips and an Edit/Tutup toggle guarding a panel of three
// fields, so a day with four arrivals rendered ~30 controls to show ~12 facts.
//
// This is one flat register instead: hotel and rooms became columns rather
// than a nesting level, the client card became a slim band (it only ever
// existed to host the group WA button), ETA/PIC are quiet inline fields edited
// in place, and status chips only render once there is a status. Save controls
// materialise on the dirty row and nowhere else.
//
// Every `input` selector below carries design.css's own :not() pair plus a
// scoping class — (0,3,1) against its (0,2,1) — because that global input
// reset is unlayered plain CSS and outranks any Tailwind utility regardless of
// specificity. Same trap documented in ui/input.jsx and RecapSettings.jsx.
const CSS = `
.uc-wrap { margin-top:36px; }
.uc-card { background:var(--card); border:1px solid var(--border); border-radius:20px; padding:20px 22px 8px; }

/* ── section head ───────────────────────────────────────────── */
.uc-head { display:flex; align-items:flex-start; justify-content:space-between; gap:14px; flex-wrap:wrap; padding-bottom:16px; border-bottom:1px solid var(--border); }
.uc-title { margin:0; font-size:15px; font-weight:600; color:var(--foreground); letter-spacing:-.01em; }
/* One summary sentence, plain text. The counts used to be repeated as red
   pills here and again on every date row; the date rows are where an operator
   actually acts on them, so this level just sets the scope. */
.uc-sub { margin-top:4px; font-size:12px; color:var(--muted-foreground); }
.uc-head-actions { display:flex; align-items:center; gap:8px; flex-shrink:0; }

/* ── day ────────────────────────────────────────────────────── */
.uc-day + .uc-day { border-top:1px solid var(--border); }
.uc-day-head { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; padding:16px 0 10px; }
.uc-day-left { display:flex; align-items:baseline; gap:9px; flex-wrap:wrap; }
.uc-day-label { font-size:12.5px; font-weight:600; color:var(--foreground); letter-spacing:-.01em; }
/* "Hari Ini" is the one day an operator has to act on now, so it gets the ink
   pill — the same monochrome emphasis the grid above gives today's column. */
.uc-day-label.is-today { padding:3px 11px; border-radius:9999px; background:var(--primary); color:var(--primary-foreground); }
.uc-day-meta { font-size:12px; color:var(--muted-foreground); }
.uc-day-warn { font-size:12px; font-weight:500; color:var(--red); }
.uc-day-actions { display:flex; align-items:center; gap:6px; }

/* ── client band ────────────────────────────────────────────── */
/* A tinted strip, not a card: grouping bookings under one client only exists
   so the WA send has a target, and a bordered box per client was reading as a
   heavier structure than the bookings inside it. */
.uc-client { display:flex; align-items:center; gap:8px; padding:6px 10px 6px 12px; border-radius:10px; background:var(--secondary); margin-top:10px; }
.uc-client-name { font-size:12.5px; font-weight:600; color:var(--foreground); min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.uc-client-count { font-size:11.5px; color:var(--muted-foreground); flex-shrink:0; }

/* ── booking row ────────────────────────────────────────────── */
/* The ETA track is 96px, not the ~74px the value needs: Chrome keeps the
   picker indicator in flow even at opacity 0, and a tighter track clipped
   "08:30" down to "08.3". */
.uc-row { display:grid; grid-template-columns:82px minmax(110px,1.3fr) minmax(80px,.9fr) 96px minmax(104px,1fr) minmax(96px,.9fr) minmax(112px,auto); align-items:center; gap:12px; padding:6px 12px; border-radius:10px; }
.uc-row + .uc-row { box-shadow:inset 0 1px 0 var(--border); }
.uc-row:hover { background:var(--background); }
.uc-row:hover + .uc-row { box-shadow:none; }
.uc-cl { font-size:12.5px; font-weight:600; color:var(--foreground); text-decoration:none; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-variant-numeric:tabular-nums; }
.uc-cl:hover { text-decoration:underline; text-underline-offset:2px; }
.uc-cell { font-size:12px; color:var(--muted-foreground); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.uc-end { display:flex; align-items:center; justify-content:flex-end; gap:6px; }

/* ── quiet inline fields ────────────────────────────────────── */
/* Transparent until touched. Three boxed 2px controls per row (what the old
   edit panel used) turned a twelve-row day into a wall of strokes; here the
   value reads as text and the field only draws itself on hover/focus. */
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
/* An empty ETA is the one gap that blocks the day, so the placeholder carries
   the warning rather than a separate chip elsewhere in the row. */
.uc-eta-input[data-empty="true"] { color:var(--red); }
.uc-card input[type="time"]::-webkit-calendar-picker-indicator { opacity:0; transition:opacity .12s; }
.uc-card input[type="time"]:hover::-webkit-calendar-picker-indicator,
.uc-card input[type="time"]:focus::-webkit-calendar-picker-indicator { opacity:.5; }

/* ── status chips ───────────────────────────────────────────── */
/* Rendered only once a reminder has actually resolved. "Not sent yet" is the
   default state of every row in the list, so drawing it was pure noise. */
.uc-rem { display:inline-flex; align-items:center; gap:3px; font-size:10px; font-weight:600; padding:2px 7px 2px 6px; border-radius:9999px; text-transform:uppercase; letter-spacing:.04em; white-space:nowrap; }
/* SVG, not a "✓"/"✗" character: Inter ships neither, so both fell back to a
   different face and the check rendered as a radical sign glued to the label. */
.uc-rem svg { flex-shrink:0; }
.uc-rem.sent { background:color-mix(in oklch, var(--green) 16%, transparent); color:var(--green); }
.uc-rem.failed { background:color-mix(in oklch, var(--red) 15%, transparent); color:var(--red); }

.uc-empty { margin:22px 0 24px; padding:52px 24px; text-align:center; border:1px dashed var(--border); border-radius:16px; }
.uc-empty-title { font-size:14px; font-weight:600; color:var(--foreground); margin:10px 0 6px; }
.uc-empty-sub { font-size:12.5px; color:var(--muted-foreground); }

.uc-day:last-child { padding-bottom:14px; }

/* Below 820px the seven tracks stop fitting, so the row folds into a 2×4 block.
   Every child is placed explicitly — leaving any of them to auto-placement is
   what scattered the first attempt (ETA landed under the status chips, four
   rows down from its own label context). */
@media (max-width:820px) {
  .uc-row { grid-template-columns:minmax(0,1fr) minmax(0,1fr); column-gap:10px; row-gap:6px; padding:10px 12px; }
  .uc-cl-cell   { grid-area:1 / 1; }
  .uc-rooms     { grid-area:1 / 2; text-align:right; }
  .uc-where     { grid-area:2 / 1 / 2 / -1; }
  .uc-eta-input { grid-area:3 / 1; }
  .uc-end       { grid-area:3 / 2; }
  .uc-pic-name  { grid-area:4 / 1; }
  .uc-pic-phone { grid-area:4 / 2; }
  /* Touch has no hover, so the fields have to advertise themselves. */
  .uc-card input:not([type="checkbox"]):not([type="radio"]) { border-color:var(--border); background:var(--card); }
  .uc-card input[type="time"]::-webkit-calendar-picker-indicator { opacity:.5; }
}
@media (max-width:600px) {
  .uc-wrap { margin-top:24px; padding:0 14px; }
  .uc-card { padding:16px 14px 6px; border-radius:16px; }
  .uc-day-head { padding:14px 0 8px; }
  .uc-client { padding-left:10px; }
  .uc-row { padding:10px; }
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

const GearIcon = ({ size = 15 }) => (
  <svg width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
  </svg>
);

// Only a resolved reminder is worth a chip — see the .uc-rem note in CSS.
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

// ── BookingRow — one CL, edited in place ──────────────────────
function BookingRow({ cl }) {
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

// ── ClientBlock — the band exists to host the group WA send ───
function ClientBlock({ clientName, cls }) {
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
    <div>
      <div className="uc-client">
        <span className="uc-client-name">{clientName}</span>
        {cls.length > 1 && <span className="uc-client-count">{t("{count} booking", { count: cls.length })}</span>}
        {/* Inline margin, not `ml-auto`: design.css's `* { margin: 0 }` reset is
            unlayered and outranks every Tailwind margin utility (same cascade
            trap documented for button padding in tailwind.css). */}
        <Button variant="outline" size="xs" style={{ marginLeft: 'auto' }} onClick={handleSend} disabled={sending}>
          {sending ? '…' : <><WAIcon size={11} /> WA</>}
        </Button>
      </div>
      {cls.map(cl => <BookingRow key={cl.pk} cl={cl} />)}
    </div>
  );
}

// Mirror of backend group_guests (hw/services/recap.py): client bookings group
// by client_id; client-less bookings group by guest name, where a blank phone
// acts as a wildcard and merges with the name's single known phone. Two distinct
// non-blank phones under the same name stay apart (different people).
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

// ── DayBlock ──────────────────────────────────────────────────
function DayBlock({ dateStr, cls }) {
  const { t, locale } = useI18n();
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

  return (
    <div className="uc-day">
      <div className="uc-day-head">
        <div className="uc-day-left">
          <span className={"uc-day-label" + (isToday ? " is-today" : "")}>{label}</span>
          <span className="uc-day-meta">{dateFull} · {t("{count} guests", { count: cls.length })}</span>
          {incompleteCnt > 0 && <span className="uc-day-warn">{t("{count} missing ETA", { count: incompleteCnt })}</span>}
        </div>
        <div className="uc-day-actions">
          {/* Icon-only: the labelled "PDF" lives once in the section head, and
              this repeats per day. */}
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

      {Object.entries(groupByClient(cls)).map(([key, group]) =>
        <ClientBlock key={key} clientName={group.name} cls={group.items} />
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────
export default function UpcomingCheckins({ upcoming_checkins, last_recap }) {
  const { t } = useI18n();
  const checkins = upcoming_checkins || [];

  const grouped = {};
  checkins.forEach(cl => {
    const key = cl.check_in || 'unknown';
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(cl);
  });
  const sortedDates = Object.keys(grouped).sort();

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
            <Button variant="outline" size="sm" asChild>
              <a href="/calendar/checkin-pdf/" target="_blank" rel="noreferrer" title={t("Download PDF of all upcoming check-ins")}>
                <PrinterIcon size={13} /> PDF
              </a>
            </Button>
            <Button variant="outline" size="icon-sm" asChild>
              <a href="/calendar/recap-settings/" title={t("Recap Settings")} aria-label={t("Recap Settings")}>
                <GearIcon size={15} />
              </a>
            </Button>
          </div>
        </div>

        {sortedDates.length === 0 ? (
          <div className="uc-empty">
            <div style={{ display: 'flex', justifyContent: 'center', color: 'var(--muted-foreground)' }}>
              <Icon name="calendar" size={30} strokeWidth={1.5} />
            </div>
            <div className="uc-empty-title">{t("No upcoming check-ins")}</div>
            <div className="uc-empty-sub">{t("No guests checking in within the next 7 days.")}</div>
          </div>
        ) : (
          sortedDates.map((dateStr) => (
            <DayBlock key={dateStr} dateStr={dateStr} cls={grouped[dateStr]} />
          ))
        )}
      </div>
    </div>
  );
}
