import { useState } from "react";
import axios from "axios";
import { showToast } from "../../components/shell/Toast.jsx";

const TODAY    = new Date().toISOString().split('T')[0];
const TOMORROW = new Date(Date.now() + 86400000).toISOString().split('T')[0];

function dayLabel(dateStr) {
  if (dateStr === TODAY)    return 'Hari Ini';
  if (dateStr === TOMORROW) return 'Besok';
  return new Date(dateStr + 'T00:00:00').toLocaleDateString('id-ID', {
    weekday: 'long', day: 'numeric', month: 'long',
  });
}

const WAIcon = ({ size = 11 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" style={{ flexShrink: 0 }}>
    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"/>
  </svg>
);

function ReminderBadge({ sent, failed, label }) {
  const cfg = sent   ? { bg: 'rgba(34,197,94,.15)',  color: '#22C55E', icon: '✓' }
            : failed ? { bg: 'rgba(239,68,68,.12)',  color: '#EF4444', icon: '✗' }
                     : { bg: 'rgba(148,163,184,.1)', color: '#94A3B8', icon: '·' };
  return (
    <span title={sent ? 'Terkirim' : failed ? 'Gagal' : 'Belum terkirim'} style={{
      display: 'inline-flex', alignItems: 'center', gap: 3,
      fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 99,
      background: cfg.bg, color: cfg.color,
      textTransform: 'uppercase', letterSpacing: '0.04em',
    }}>
      <span style={{ fontSize: 11 }}>{cfg.icon}</span>{label}
    </span>
  );
}

// ── CheckinCard ───────────────────────────────────────────────
function CheckinCard({ cl }) {
  const [editing,    setEditing]    = useState(!cl.estimasi_tiba);
  const [estimasi,   setEstimasi]   = useState(cl.estimasi_tiba || '');
  const [picName,    setPicName]    = useState(cl.pic_name  || '');
  const [picPhone,   setPicPhone]   = useState(cl.pic_phone || '');
  const [saving,  setSaving]  = useState(false);
  const [sending, setSending] = useState(false);

  const isToday = cl.check_in === TODAY;
  const hasETA  = Boolean(estimasi);
  const waSent  = cl.h0_sent || cl.h1_sent;

  const badge = !hasETA
    ? { text: 'Belum ETA', bg: 'rgba(239,68,68,.15)',  color: '#EF4444' }
    : waSent
    ? { text: 'WA Terkirim', bg: 'rgba(34,197,94,.15)', color: '#22C55E' }
    : { text: 'ETA OK', bg: 'rgba(99,102,241,.12)', color: 'var(--accent-2)' };

  const handleSave = async () => {
    setSaving(true);
    await axios.post(
      `/calendar/cl/${cl.pk}/estimasi/`,
      new URLSearchParams({ estimasi_tiba: estimasi, pic_name: picName, pic_phone: picPhone }),
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
    );
    setSaving(false); setEditing(false);
  };

  const handleCancel = () => {
    setEstimasi(cl.estimasi_tiba || '');
    setPicName(cl.pic_name  || '');
    setPicPhone(cl.pic_phone || '');
    setEditing(false);
  };

  const handleSend = async () => {
    setSending(true);
    try {
      const r = await axios.post(`/calendar/send-reminder/${cl.pk}/`);
      showToast(r.data.ok ? `Pesan terkirim ke ${cl.guest_name}` : (r.data.message || 'Gagal mengirim pesan'), r.data.ok ? 'success' : 'error');
    } catch { showToast('Gagal mengirim pesan', 'error'); }
    setSending(false);
  };

  const handleSaveAndSend = async () => {
    setSaving(true);
    try {
      await axios.post(
        `/calendar/cl/${cl.pk}/estimasi/`,
        new URLSearchParams({ estimasi_tiba: estimasi, pic_name: picName, pic_phone: picPhone }),
        { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
      );
    } catch { setSaving(false); return; }
    setSaving(false); setEditing(false);
    setSending(true);
    try {
      const r = await axios.post(`/calendar/send-reminder/${cl.pk}/`);
      showToast(r.data.ok ? `Pesan terkirim ke ${cl.guest_name}` : (r.data.message || 'Gagal mengirim pesan'), r.data.ok ? 'success' : 'error');
    } catch { showToast('Gagal mengirim pesan', 'error'); }
    setSending(false);
  };

  const fi = { // field input style
    width: '100%', padding: '6px 8px', fontSize: 12, borderRadius: 6,
    border: '1px solid var(--border-2)', background: 'var(--surface)',
    color: 'var(--text)', outline: 'none', boxSizing: 'border-box',
    fontFamily: 'inherit',
  };

  return (
    <div style={{
      background: 'var(--surface-2)',
      borderRadius: 12,
      border: '1px solid var(--border)',
      borderTop: isToday && !hasETA ? '2px solid #EF4444' : undefined,
      padding: '16px',
      display: 'flex', flexDirection: 'column', gap: 12,
    }}>
      {/* Header: icon + name + badge */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, minWidth: 0, flex: 1 }}>
          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8"
            viewBox="0 0 24 24" style={{ color: isToday ? '#EF4444' : 'var(--text-3)', flexShrink: 0, marginTop: 2 }}>
            <circle cx="12" cy="12" r="10"/>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6l4 2"/>
          </svg>
          <div style={{ minWidth: 0 }}>
            <a href={cl.url} style={{
              fontSize: 13, fontWeight: 700, color: 'var(--text)',
              textDecoration: 'none', letterSpacing: '-0.01em',
              display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {cl.guest_name}
            </a>
            <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {cl.hotel_name}
            </div>
          </div>
        </div>
        <span style={{
          fontSize: 9, fontWeight: 700, padding: '3px 8px', borderRadius: 99,
          background: badge.bg, color: badge.color, flexShrink: 0,
          textTransform: 'uppercase', letterSpacing: '0.05em',
        }}>
          {badge.text}
        </span>
      </div>

      {!editing ? (
        <>
          {/* Data fields */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <div style={{ fontSize: 9, color: 'var(--text-3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>
                ETA
              </div>
              <div style={{
                fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em',
                color: hasETA ? 'var(--text)' : '#EF4444',
                fontVariantNumeric: 'tabular-nums', lineHeight: 1,
              }}>
                {hasETA ? estimasi : '—'}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 9, color: 'var(--text-3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>
                Kamar
              </div>
              <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-2)', lineHeight: 1.4 }}>
                {cl.rooms || '—'}
              </div>
            </div>
            {(picName || picPhone) && (
              <>
                <div>
                  <div style={{ fontSize: 9, color: 'var(--text-3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>
                    PIC
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-2)', lineHeight: 1.4 }}>
                    {picName || '—'}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 9, color: 'var(--text-3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>
                    No. HP PIC
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-2)', lineHeight: 1.4 }}>
                    {picPhone || '—'}
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Footer: badges + actions */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 4,
            paddingTop: 8, borderTop: '1px solid var(--border)',
          }}>
            <ReminderBadge sent={cl.h1_sent} failed={cl.h1_failed} label="H-1" />
            <ReminderBadge sent={cl.h0_sent} failed={cl.h0_failed} label="H-0" />
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 5 }}>
              <button onClick={() => setEditing(true)} style={{
                fontSize: 10, fontWeight: 500, padding: '4px 10px', borderRadius: 6,
                border: '1px solid var(--border-2)', background: 'none',
                color: 'var(--text-3)', cursor: 'pointer',
              }}>
                Edit
              </button>
              <button onClick={handleSend} disabled={sending} style={{
                fontSize: 10, fontWeight: 700, padding: '4px 10px', borderRadius: 6,
                border: 'none', cursor: sending ? 'default' : 'pointer',
                background: '#25D366', color: '#fff', opacity: sending ? .75 : 1,
                display: 'inline-flex', alignItems: 'center', gap: 4,
              }}>
                {sending ? '…' : <><WAIcon /> WA</>}
              </button>
            </div>
          </div>
        </>
      ) : (
        /* Edit mode */
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div>
              <div style={{ fontSize: 9, color: 'var(--text-3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>ETA</div>
              <input type="time" value={estimasi} onChange={e => setEstimasi(e.target.value)} style={fi} />
            </div>
            <div>
              <div style={{ fontSize: 9, color: 'var(--text-3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>Nama PIC</div>
              <input type="text" value={picName} onChange={e => setPicName(e.target.value)} placeholder="Nama PIC" style={fi} />
            </div>
          </div>
          <div>
            <div style={{ fontSize: 9, color: 'var(--text-3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>No. HP PIC</div>
            <input type="text" value={picPhone} onChange={e => setPicPhone(e.target.value)} placeholder="0812…" style={fi} />
          </div>
          <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end', paddingTop: 2 }}>
            <button onClick={handleCancel} style={{ fontSize: 11, padding: '5px 10px', borderRadius: 6, border: '1px solid var(--border-2)', background: 'none', color: 'var(--text-3)', cursor: 'pointer' }}>
              Batal
            </button>
            <button onClick={handleSave} disabled={saving} style={{ fontSize: 11, fontWeight: 500, padding: '5px 14px', borderRadius: 6, border: '1px solid var(--border-2)', background: 'none', cursor: saving ? 'default' : 'pointer', color: 'var(--text-2)', opacity: saving ? .7 : 1 }}>
              {saving ? '…' : 'Simpan'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── DateGroup ─────────────────────────────────────────────────
function DateGroup({ dateStr, cls }) {
  const [sending,     setSending]     = useState(false);
  const [recapResult, setRecapResult] = useState(null);

  const isToday       = dateStr === TODAY;
  const incompleteCnt = cls.filter(c => !c.estimasi_tiba).length;
  const d = new Date(dateStr + 'T00:00:00');
  const label    = isToday ? 'Hari Ini'
                 : dateStr === TOMORROW ? 'Besok'
                 : d.toLocaleDateString('id-ID', { weekday: 'long' });
  const dateFull = d.toLocaleDateString('id-ID', { day: 'numeric', month: 'long', year: 'numeric' });

  const handleSendRecap = async () => {
    setSending(true); setRecapResult(null);
    try {
      const r = await axios.post(
        '/calendar/send-recap/',
        new URLSearchParams({ date: dateStr }),
        { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
      );
      setRecapResult(r.data);
    } catch { setRecapResult({ ok: false, errors: ['Network error'] }); }
    setSending(false);
  };

  return (
    <div style={{ marginBottom: 28 }}>
      {/* Date header row */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: 12, marginBottom: 14, flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{
            fontSize: 12, fontWeight: 800, textTransform: 'uppercase',
            letterSpacing: '0.08em', color: isToday ? '#EF4444' : 'var(--text)',
          }}>
            {label}
          </span>
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>{dateFull}</span>
          {incompleteCnt > 0 && (
            <span style={{
              fontSize: 9, fontWeight: 700, padding: '2px 8px', borderRadius: 99,
              background: 'rgba(239,68,68,.12)', color: '#EF4444',
              textTransform: 'uppercase', letterSpacing: '0.04em',
            }}>
              {incompleteCnt} belum ETA
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            fontSize: 11, color: 'var(--text-3)',
            background: 'var(--surface)', padding: '3px 10px',
            borderRadius: 99, border: '1px solid var(--border)',
          }}>
            {cls.length} tamu
          </span>
          <button onClick={handleSendRecap} disabled={sending} style={{
            padding: '5px 12px', fontSize: 11, fontWeight: 700, borderRadius: 8,
            border: 'none', cursor: sending ? 'default' : 'pointer',
            background: '#25D366', color: '#fff', opacity: sending ? .7 : 1,
            display: 'inline-flex', alignItems: 'center', gap: 4,
          }}>
            {sending ? '…' : <><WAIcon size={10} /> Kirim Rekap</>}
          </button>
        </div>
      </div>

      {recapResult && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '9px 14px',
          borderRadius: 8, marginBottom: 12, fontSize: 12,
          background: recapResult.ok ? 'rgba(34,197,94,.08)' : 'rgba(239,68,68,.08)',
          color: recapResult.ok ? '#22C55E' : '#EF4444',
          border: `1px solid ${recapResult.ok ? 'rgba(34,197,94,.2)' : 'rgba(239,68,68,.2)'}`,
        }}>
          <span style={{ fontWeight: 700 }}>{recapResult.ok ? '✓' : '✗'}</span>
          <span>{recapResult.ok ? 'Rekap berhasil dikirim.' : recapResult.errors?.join(', ') || recapResult.message || 'Terjadi kesalahan.'}</span>
        </div>
      )}

      {/* Card grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
        gap: 12,
      }}>
        {cls.map(cl => <CheckinCard key={cl.pk} cl={cl} />)}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────
export default function UpcomingCheckins({ upcoming_checkins, last_recap }) {
  const checkins = upcoming_checkins || [];

  const grouped = {};
  checkins.forEach(cl => {
    const key = cl.check_in || 'unknown';
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(cl);
  });
  const sortedDates     = Object.keys(grouped).sort();
  const totalIncomplete = checkins.filter(cl => !cl.estimasi_tiba).length;

  return (
    <div style={{ marginTop: 40 }}>
      {/* Outer card — mirip pola Attendance History */}
      <div style={{
        background: 'var(--surface)',
        borderRadius: 16,
        border: '1px solid var(--border-2)',
        padding: '24px',
        boxShadow: '0 2px 12px rgba(0,0,0,.06)',
      }}>
        {/* Card header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginBottom: 24, flexWrap: 'wrap', gap: 12,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {/* Left accent bar */}
            <div style={{ width: 4, height: 26, borderRadius: 2, background: '#22C55E', flexShrink: 0 }} />
            <div>
              <h2 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.02em' }}>
                Check-in Mendatang
              </h2>
              <div style={{ marginTop: 3, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
                  {checkins.length} tamu · 7 hari ke depan
                </span>
                {totalIncomplete > 0 && (
                  <span style={{
                    fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 99,
                    background: 'rgba(239,68,68,.12)', color: '#EF4444',
                  }}>
                    {totalIncomplete} belum ETA
                  </span>
                )}
                {last_recap && (
                  <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
                    · Rekap terakhir: {last_recap.sent_at}
                  </span>
                )}
              </div>
            </div>
          </div>
          <a href="/calendar/recap-settings/" title="Pengaturan Rekap" style={{
            textDecoration: 'none', padding: '7px', borderRadius: 9,
            border: '1px solid var(--border-2)', background: 'var(--surface-2)',
            display: 'inline-flex', alignItems: 'center', color: 'var(--text-2)',
          }}>
            <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </a>
        </div>

        {/* Empty state */}
        {sortedDates.length === 0 && (
          <div style={{
            padding: '56px 24px', textAlign: 'center',
            background: 'var(--surface-2)', borderRadius: 12, border: '1px solid var(--border)',
          }}>
            <div style={{ fontSize: 32, marginBottom: 12, opacity: .4 }}>📭</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 6 }}>
              Tidak ada check-in mendatang
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-3)' }}>
              Tidak ada tamu check-in dalam 7 hari ke depan.
            </div>
          </div>
        )}

        {/* Date groups */}
        {sortedDates.map((dateStr, idx) => (
          <div key={dateStr}>
            {idx > 0 && <div style={{ borderTop: '1px solid var(--border)', marginBottom: 28 }} />}
            <DateGroup dateStr={dateStr} cls={grouped[dateStr]} />
          </div>
        ))}
      </div>
    </div>
  );
}
