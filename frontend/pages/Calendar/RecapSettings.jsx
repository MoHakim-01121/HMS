import { useState, useRef } from "react";
import axios from "axios";
import PageBack from "../../components/shadcn/page-back.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Restyled 2026-07-30 onto the shadcn/Homlu token set, alongside the rest of
// the Calendar module. Everything here used to be inline style objects against
// design.css's legacy --surface/--text-*/--accent tokens; the selected-card
// state in particular was an --accent-2 border plus an --accent-muted glow,
// which is exactly the brand-hue emphasis the Homlu direction dropped. It now
// reads as a 2px --ring stroke instead.
//
// The input/textarea rule carries design.css's own :not() pair plus the page
// scope — (0,3,1) against its (0,2,1) — because that global reset is unlayered
// plain CSS and outranks any Tailwind utility no matter the specificity.
const CSS = `
.rs-page { max-width:960px; margin:0 auto; padding:28px 20px 80px; }
.rs-head { margin-bottom:26px; }

.rs-card-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(250px, 1fr)); gap:14px; margin-bottom:14px; }
.rs-card { background:var(--card); border:1px solid var(--border); border-radius:20px; padding:20px; display:flex; flex-direction:column; gap:12px; transition:border-color .15s, box-shadow .15s; }
/* Selection is a stroke change only — no colored halo. The card being edited
   is already the one with the editor panel open right below it. */
.rs-card.selected { border:2px solid var(--ring); padding:19px; }
.rs-card-title { font-size:14.5px; font-weight:600; color:var(--foreground); letter-spacing:-.01em; margin-bottom:10px; }
.rs-tags { display:flex; gap:6px; flex-wrap:wrap; }
.rs-tag { font-size:11px; font-weight:500; padding:3px 10px; border-radius:9999px; background:var(--secondary); color:var(--muted-foreground); }
.rs-card-desc { margin:0; font-size:12.5px; color:var(--muted-foreground); line-height:1.65; flex:1; }
.rs-card-foot { display:flex; align-items:center; gap:10px; padding-top:14px; border-top:1px solid var(--border); margin-top:auto; }

.rs-toggle { width:42px; height:24px; border-radius:9999px; background:var(--border); border:none; cursor:pointer; padding:0; position:relative; transition:background .18s; flex-shrink:0; outline:none; }
.rs-toggle.on { background:var(--primary); }
.rs-toggle-knob { position:absolute; top:3px; left:3px; width:18px; height:18px; border-radius:9999px; background:var(--card); box-shadow:0 1px 2px rgba(0,0,0,.2); transition:left .18s; display:block; }
.rs-toggle.on .rs-toggle-knob { left:21px; }

.rs-panel { background:var(--card); border:1px solid var(--border); border-radius:20px; padding:22px 24px; margin-bottom:14px; }
.rs-panel-head { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:20px; }
.rs-panel-title { font-size:14px; font-weight:600; color:var(--foreground); }
.rs-panel-grid { display:grid; grid-template-columns:1fr 1fr; gap:24px; }
.rs-panel-foot { display:flex; align-items:center; justify-content:flex-end; gap:10px; margin-top:20px; padding-top:16px; border-top:1px solid var(--border); }

.rs-label { font-size:10px; font-weight:600; text-transform:uppercase; letter-spacing:.08em; color:var(--muted-foreground); margin-bottom:8px; display:flex; align-items:center; gap:5px; }
.rs-vars { display:flex; flex-wrap:wrap; gap:6px; }
.rs-var { font-size:11px; padding:4px 10px; border-radius:9999px; cursor:pointer; border:1px solid var(--border); background:var(--background); color:var(--muted-foreground); font-family:var(--font-mono); transition:border-color .12s, color .12s; }
.rs-var:hover { border-color:var(--ring); color:var(--foreground); }
.rs-hint { margin-top:8px; font-size:11.5px; color:var(--muted-foreground); }
.rs-saved { font-size:12px; color:var(--green); display:inline-flex; align-items:center; gap:4px; }
.rs-error { font-size:12px; color:var(--red); }

.rs-page input:not([type="checkbox"]):not([type="radio"]),
.rs-page textarea {
  width:100%; box-sizing:border-box;
  background:var(--background); border:2px solid var(--border); border-radius:var(--radius-control,16px);
  color:var(--foreground); font-family:inherit; font-size:13px;
  box-shadow:none; transition:border-color .14s ease;
}
.rs-page input:not([type="checkbox"]):not([type="radio"]) { height:40px; padding:0 14px; }
.rs-page textarea { height:230px; padding:12px 14px; line-height:1.7; font-family:var(--font-mono); resize:vertical; }
.rs-page input:not([type="checkbox"]):not([type="radio"]):focus,
.rs-page textarea:focus { outline:none; border-color:var(--ring); box-shadow:none; }
.rs-page input::placeholder, .rs-page textarea::placeholder { color:var(--muted-foreground); }

/* WhatsApp mock keeps WhatsApp's own colors on purpose — it is a preview of
   what the recipient sees, not a surface of this app's design system. */
.rs-wa { background:#E8D5C0; border-radius:16px; padding:16px 14px 14px; min-height:230px; display:flex; flex-direction:column; justify-content:flex-end; }
.rs-wa-bubble { align-self:flex-end; max-width:90%; background:#DCFCE7; border-radius:14px 14px 3px 14px; padding:10px 12px 8px; box-shadow:0 1px 2px rgba(0,0,0,.12); }
.rs-wa-text { font-size:13px; line-height:1.65; color:#111827; white-space:pre-wrap; word-break:break-word; }
.rs-wa-empty { font-size:13px; color:#9CA3AF; font-style:italic; }
.rs-wa-meta { display:flex; align-items:center; justify-content:flex-end; gap:3px; margin-top:5px; }

.rs-targets { border:1px solid var(--border); border-radius:16px; overflow:hidden; margin-bottom:18px; }
.rs-target { display:flex; align-items:center; gap:12px; padding:12px 16px; flex-wrap:wrap; }
.rs-target + .rs-target { border-top:1px solid var(--border); }
.rs-dot { width:8px; height:8px; border-radius:9999px; flex-shrink:0; background:var(--muted-foreground); }
.rs-dot.on { background:var(--green); box-shadow:0 0 0 3px color-mix(in oklch, var(--green) 20%, transparent); }
.rs-target-label { flex:1; font-size:13px; font-weight:500; color:var(--foreground); min-width:80px; }
.rs-target-num { font-size:12px; font-family:var(--font-mono); color:var(--muted-foreground); letter-spacing:.02em; }
.rs-target-actions { display:flex; gap:6px; align-items:center; }
.rs-confirm { display:flex; align-items:center; gap:6px; font-size:12px; color:var(--muted-foreground); }

.rs-empty-targets { padding:22px; margin-bottom:18px; border-radius:16px; border:1px dashed var(--border); text-align:center; color:var(--muted-foreground); font-size:12.5px; }
.rs-add { padding:16px; border-radius:16px; border:1px solid var(--border); background:var(--background); }
.rs-add-row { display:flex; gap:10px; flex-wrap:wrap; align-items:flex-end; }
.rs-add-field { flex:1 1 150px; min-width:120px; }
.rs-add-field .rs-label { font-size:9.5px; letter-spacing:.06em; margin-bottom:5px; }
/* --card, not --background: these fields sit on the recessed add-panel, so
   they need the lighter tone to separate from it. */
.rs-add input:not([type="checkbox"]):not([type="radio"]) { background:var(--card); }

@media (max-width:760px) {
  .rs-panel-grid { grid-template-columns:1fr; gap:18px; }
}
@media (max-width:600px) {
  .rs-page { padding:16px 14px 80px; }
  .rs-panel { padding:16px; border-radius:16px; }
  .rs-card { border-radius:16px; }
}`;

// ── Toggle switch ─────────────────────────────────────────────
function Toggle({ active, onToggle }) {
  const { t } = useI18n();
  return (
    <button type="button" className={"rs-toggle" + (active ? " on" : "")} onClick={onToggle}
      role="switch" aria-checked={active} aria-label={active ? t("Deactivate") : t("Activate")}>
      <span className="rs-toggle-knob" />
    </button>
  );
}

// ── Notification card ─────────────────────────────────────────
function NotifCard({ title, tags, description, active, onToggle, selected, onEdit }) {
  const { t } = useI18n();
  return (
    <div className={"rs-card" + (selected ? " selected" : "")}>
      <div>
        <div className="rs-card-title">{title}</div>
        <div className="rs-tags">
          {tags.map(tag => <span key={tag} className="rs-tag">{t(tag)}</span>)}
        </div>
      </div>
      <p className="rs-card-desc">{description}</p>
      <div className="rs-card-foot" style={{ justifyContent: selected ? "flex-end" : "space-between" }}>
        {!selected && <Toggle active={active} onToggle={onToggle} />}
        <Button variant="ghost" size="icon-sm" onClick={onEdit} aria-label={t("Edit {title}", { title })}>
          <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z" />
          </svg>
        </Button>
      </div>
    </div>
  );
}

// ── Template data per type ─────────────────────────────────────
const GUEST_SAMPLE = {
  client_name: 'PT Amanah Wisata', check_in_date: '25 Jun 2026', hari_relatif: 'tomorrow',
  booking_blocks:
    '*OLAYAN AJYAD*\n' +
    '1. #RSV : CL-005\n' +
    '   Room(s) : 2 Deluxe, 1 Triple\n' +
    '\n' +
    '2. #RSV : CL-006\n' +
    '   Room(s) : 1 Quad',
};
const GUEST_VARS = [
  { key: 'client_name',    label: 'Client/Guest name'      },
  { key: 'booking_blocks', label: 'Booking list'           },
  { key: 'check_in_date',  label: 'Check-in date (H-1 only)' },
  { key: 'hari_relatif',   label: 'Relative day (H-1 only)' },
];

const RECAP_SAMPLE = {
  date:          '24 JUN 2026',
  total_guests:  '3',
  total_hotels:  '2',
  guest_list:
    '*OLAYAN AJYAD*\n' +
    '1. RSVN     : CL-005\n' +
    '   Guest    : Ahmad Fauzi\n' +
    '   Check-in : 25 Jun 2026\n' +
    '   Room(s)  : 2 Deluxe, 1 Triple\n' +
    '   ETA      : 14:00\n' +
    '   PIC      : Budi\n' +
    '   PIC No.  : 0812xxx\n',
};
const RECAP_VARS = [
  { key: 'date',         label: 'Recap date' },
  { key: 'total_guests', label: 'Total guests' },
  { key: 'total_hotels', label: 'Total hotels' },
];

function renderPreview(text, sample) {
  const parts = []; const regex = /\{(\w+)\}/g; let last = 0, m;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) parts.push({ text: text.slice(last, m.index), hi: false });
    const val = sample[m[1]];
    parts.push({ text: val !== undefined ? val : m[0], hi: val !== undefined });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last), hi: false });
  return parts;
}

// ── WhatsApp preview bubble ────────────────────────────────────
function WhatsAppPreview({ text, sample }) {
  const { t } = useI18n();
  const preview = renderPreview(text || '', sample);
  const now = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  return (
    <div className="rs-wa">
      <div className="rs-wa-bubble">
        {text ? (
          <div className="rs-wa-text">
            {preview.map((p, i) => p.hi ? (
              <mark key={i} style={{ background: 'rgba(22,163,74,.18)', color: '#15803D', borderRadius: 3, padding: '0 2px' }}>
                {p.text}
              </mark>
            ) : <span key={i}>{p.text}</span>)}
          </div>
        ) : (
          <div className="rs-wa-empty">{t("Empty template.")}</div>
        )}
        <div className="rs-wa-meta">
          <span style={{ fontSize: 10, color: '#6B7280' }}>{now}</span>
          <span style={{ fontSize: 13, color: '#53BDEB', lineHeight: 1 }}>✓✓</span>
        </div>
      </div>
    </div>
  );
}

// ── Template editor panel ─────────────────────────────────────
function TemplateEditorPanel({ title, body, onChange, vars, sample, onClose, onSave, saving, savedAt, error }) {
  const { t } = useI18n();
  const ref = useRef(null);

  const insertVar = (key) => {
    const el = ref.current; const token = `{${key}}`;
    if (!el) { onChange(body + token); return; }
    const s = el.selectionStart, e = el.selectionEnd;
    onChange(body.slice(0, s) + token + body.slice(e));
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(s + token.length, s + token.length); });
  };

  return (
    <div className="rs-panel">
      <div className="rs-panel-head">
        <div className="rs-panel-title">{t("Edit: {title}", { title })}</div>
        <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label={t("Close editor")}>
          <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </Button>
      </div>

      <div className="rs-panel-grid">
        {/* Editor */}
        <div>
          <div className="rs-label">{t("Template")}</div>
          <textarea
            ref={ref}
            value={body}
            onChange={e => onChange(e.target.value)}
            placeholder={t("Write your message template here…")}
          />
          <div style={{ marginTop: 12 }}>
            <div className="rs-label">{t("Insert variable")}</div>
            <div className="rs-vars">
              {vars.map(v => (
                <button type="button" key={v.key} className="rs-var" onClick={() => insertVar(v.key)} title={t(v.label)}>
                  {'{' + v.key + '}'}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* WA preview */}
        <div>
          <div className="rs-label">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="#25D366">
              <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"/>
            </svg>
            {t("WhatsApp preview")}
          </div>
          <WhatsAppPreview text={body} sample={sample} />
          <div className="rs-hint">{t("Variables are replaced with real data when sent.")}</div>
        </div>
      </div>

      <div className="rs-panel-foot">
        {savedAt && !error && (
          <span className="rs-saved">
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            {t("Saved at {time}", { time: savedAt })}
          </span>
        )}
        {error && <span className="rs-error">{error}</span>}
        <Button variant="outline" size="sm" onClick={onClose}>{t("Close")}</Button>
        <Button size="sm" onClick={onSave} disabled={saving}>{saving ? t('Saving…') : t('Save')}</Button>
      </div>
    </div>
  );
}

// ── WA Recipients section ─────────────────────────────────────
function WATargetSection({ initialTargets, highlighted }) {
  const { t } = useI18n();
  const [targets, setTargets] = useState(initialTargets || []);
  const [label,   setLabel]   = useState('');
  const [target,  setTarget]  = useState('');
  const [adding,  setAdding]  = useState(false);
  const [error,   setError]   = useState('');
  const [confirm, setConfirm] = useState(null);

  const handleAdd = async () => {
    if (!label.trim() || !target.trim()) { setError(t('Label and number are required')); return; }
    setAdding(true); setError('');
    try {
      const r = await axios.post(
        '/calendar/wa-targets/',
        new URLSearchParams({ label, target }),
        { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
      );
      if (r.data.ok) { setTargets(prev => [...prev, { ...r.data, is_active: true }]); setLabel(''); setTarget(''); }
      else setError(r.data.error || t('Failed to add number'));
    } catch { setError(t('Network error')); }
    setAdding(false);
  };

  const handleToggle = async (id) => {
    const r = await axios.post(`/calendar/wa-targets/${id}/toggle/`).catch(() => null);
    if (r?.data?.ok) setTargets(prev => prev.map(t => t.id === id ? { ...t, is_active: r.data.is_active } : t));
  };

  const handleDelete = async (id) => {
    const r = await axios.post(`/calendar/wa-targets/${id}/delete/`).catch(() => null);
    if (r?.data?.ok) { setTargets(prev => prev.filter(t => t.id !== id)); setConfirm(null); }
  };

  return (
    <div className="rs-panel"
      style={highlighted ? { border: "2px solid var(--ring)", padding: "21px 23px" } : undefined}>
      <div style={{ marginBottom: 18 }}>
        <div className="rs-panel-title" style={{ marginBottom: 4 }}>{t("Recap Recipients")}</div>
        <div className="rs-hint" style={{ marginTop: 0 }}>{t("The daily recap is sent to every active number below.")}</div>
      </div>

      {targets.length > 0 ? (
        <div className="rs-targets">
          {targets.map((tg) => (
            <div className="rs-target" key={tg.id}>
              <span className={"rs-dot" + (tg.is_active ? " on" : "")} />
              <span className="rs-target-label">{tg.label}</span>
              <span className="rs-target-num">{tg.target}</span>
              <div className="rs-target-actions">
                <Button variant={tg.is_active ? "default" : "outline"} size="xs" onClick={() => handleToggle(tg.id)}>
                  {tg.is_active ? t('Active') : t('Inactive')}
                </Button>
                {confirm === tg.id ? (
                  <span className="rs-confirm">
                    {t("Delete?")}
                    <Button variant="destructive" size="xs" onClick={() => handleDelete(tg.id)}>{t("Yes")}</Button>
                    <Button variant="ghost" size="xs" onClick={() => setConfirm(null)}>{t("Cancel")}</Button>
                  </span>
                ) : (
                  <Button variant="ghost" size="xs" onClick={() => setConfirm(tg.id)} style={{ color: 'var(--destructive)' }}>
                    {t("Delete")}
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="rs-empty-targets">{t("No numbers registered yet. Add a recipient below.")}</div>
      )}

      <div className="rs-add">
        <div className="rs-label">{t("Add Recipient")}</div>
        <div className="rs-add-row">
          <div className="rs-add-field">
            <div className="rs-label">{t("Label")}</div>
            <input type="text" placeholder={t("Makkah ops group")} value={label} onChange={e => setLabel(e.target.value)} />
          </div>
          <div className="rs-add-field">
            <div className="rs-label">{t("WA Number / Group ID")}</div>
            <input type="text" placeholder="628xxx…" value={target} onChange={e => setTarget(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleAdd()} />
          </div>
          <Button size="lg" onClick={handleAdd} disabled={adding}>{adding ? '…' : '+ ' + t('Add')}</Button>
        </div>
        {error && <p className="rs-error" style={{ margin: '8px 0 0' }}>{error}</p>}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────
export default function RecapSettings({
  wa_targets = [], h1_template = '', h0_template = '', recap_template = '',
}) {
  const { t } = useI18n();
  const [h1,       setH1]       = useState(h1_template);
  const [h0,       setH0]       = useState(h0_template);
  const [recap,    setRecap]    = useState(recap_template);
  const [selected, setSelected] = useState(null); // 'h1' | 'h0' | 'recap' | null
  const [h1Active, setH1Active] = useState(true);
  const [h0Active, setH0Active] = useState(true);
  const [saving,   setSaving]   = useState(false);
  const [savedAt,  setSavedAt]  = useState(null);
  const [error,    setError]    = useState('');

  const toggleCard = (key) => setSelected(prev => prev === key ? null : key);

  const handleSave = async () => {
    setSaving(true); setError('');
    try {
      await axios.post(
        '/calendar/message-templates/',
        new URLSearchParams({ h1_template: h1, h0_template: h0, recap_template: recap }),
        { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
      );
      setSavedAt(new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }));
    } catch { setError('Failed to save.'); }
    setSaving(false);
  };

  const TAMU_WA = ['Guest', 'WhatsApp'];
  const GRUP_WA = ['Ops Group', 'WhatsApp'];

  const editorProps = {
    h1:    { title: 'H-1 Reminder', body: h1, onChange: setH1, vars: GUEST_VARS,  sample: GUEST_SAMPLE  },
    h0:    { title: 'H-0 Reminder', body: h0, onChange: setH0, vars: GUEST_VARS,  sample: GUEST_SAMPLE  },
    recap: { title: 'Daily Recap',  body: recap, onChange: setRecap, vars: RECAP_VARS, sample: RECAP_SAMPLE },
  };

  return (
    <div className="shadcn-root rs-page">
      <style dangerouslySetInnerHTML={{ __html: CSS }} />

      <div className="rs-head">
        <PageBack href="/calendar/" label={t("Back to Calendar")} />
        <div className="page-title">{t("WA Recap Settings")}</div>
        <div className="page-sub">{t("Manage message templates and recipients for daily check-in recaps.")}</div>
      </div>

      <div className="rs-card-grid">
        <NotifCard
          title={t("H-1 Reminder")}
          tags={TAMU_WA}
          description={t("Send a WhatsApp message to the guest one day before check-in. Use Edit to adjust the message content.")}
          active={h1Active}
          onToggle={() => setH1Active(v => !v)}
          selected={selected === 'h1'}
          onEdit={() => toggleCard('h1')}
        />
        <NotifCard
          title={t("H-0 Reminder")}
          tags={TAMU_WA}
          description={t("Send a WhatsApp message to the guest on check-in day. Enable to remind guests on the day of arrival.")}
          active={h0Active}
          onToggle={() => setH0Active(v => !v)}
          selected={selected === 'h0'}
          onEdit={() => toggleCard('h0')}
        />
        <NotifCard
          title={t("Daily Recap")}
          tags={GRUP_WA}
          description={t("A recap of check-in guests sent to the operator group. Use {guest_list} to insert the automatic list.")}
          active={true}
          onToggle={() => {}}
          selected={selected === 'recap'}
          onEdit={() => toggleCard('recap')}
        />
      </div>

      {/* Inline editor — muncul saat salah satu card dipilih */}
      {selected && (
        <TemplateEditorPanel
          {...editorProps[selected]}
          onClose={() => setSelected(null)}
          onSave={handleSave}
          saving={saving}
          savedAt={savedAt}
          error={error}
        />
      )}

      {/* WA Recipients — highlighted saat card Rekap Harian dipilih */}
      <WATargetSection initialTargets={wa_targets} highlighted={selected === 'recap'} />
    </div>
  );
}
