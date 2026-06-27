import { useState, useRef } from "react";
import axios from "axios";
import PageBack from "../../components/ui/PageBack.jsx";

// ── Toggle switch ─────────────────────────────────────────────
function Toggle({ active, onToggle }) {
  return (
    <button onClick={onToggle} style={{
      width: 44, height: 24, borderRadius: 12,
      background: active ? 'var(--green)' : 'var(--border-2)',
      border: 'none', cursor: 'pointer', padding: 0,
      position: 'relative', transition: 'background .2s', flexShrink: 0, outline: 'none',
    }}>
      <span style={{
        position: 'absolute', top: 2, left: active ? 22 : 2,
        width: 20, height: 20, borderRadius: 10,
        background: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,.25)',
        transition: 'left .2s', display: 'block',
      }} />
    </button>
  );
}

// ── Notification card ─────────────────────────────────────────
function NotifCard({ title, tags, description, active, onToggle, selected, onEdit }) {
  return (
    <div style={{
      background: 'var(--surface)', borderRadius: 14, padding: '20px',
      border: selected ? '2px solid var(--accent-2)' : '1px solid var(--border)',
      display: 'flex', flexDirection: 'column', gap: 12,
      boxShadow: selected
        ? '0 0 0 3px rgba(255,108,55,.1), 0 2px 8px rgba(0,0,0,.06)'
        : '0 1px 3px rgba(0,0,0,.05)',
      transition: 'border-color .15s, box-shadow .15s',
    }}>
      <div>
        <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.015em', marginBottom: 10 }}>
          {title}
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {tags.map(t => (
            <span key={t.label} style={{
              fontSize: 11, fontWeight: 500, padding: '3px 10px',
              borderRadius: 99, background: t.bg, color: t.color,
            }}>
              {t.label}
            </span>
          ))}
        </div>
      </div>
      <p style={{ margin: 0, fontSize: 13, color: 'var(--text-3)', lineHeight: 1.65, flex: 1 }}>
        {description}
      </p>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: selected ? 'flex-end' : 'space-between',
        paddingTop: 14, borderTop: '1px solid var(--border)', marginTop: 'auto',
      }}>
        {!selected && <Toggle active={active} onToggle={onToggle} />}
        <button
          onClick={onEdit}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-3)', padding: '6px', borderRadius: 7,
            display: 'flex', alignItems: 'center', transition: 'color .12s, background .12s',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-2)'; e.currentTarget.style.color = 'var(--text)'; }}
          onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = 'var(--text-3)'; }}
        >
          <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z" />
          </svg>
        </button>
      </div>
    </div>
  );
}

// ── Template data per type ─────────────────────────────────────
const GUEST_SAMPLE = {
  guest_name: 'Ahmad Fauzi', hotel_name: 'Olayan Ajyad',
  confirmation_number: 'CL-005', rooms: '2 Deluxe, 1 Triple', check_in_date: '25 Jun 2026',
};
const GUEST_VARS = [
  { key: 'guest_name',          label: 'Nama Tamu' },
  { key: 'hotel_name',          label: 'Hotel'     },
  { key: 'confirmation_number', label: 'No. CL'    },
  { key: 'rooms',               label: 'Kamar'     },
  { key: 'check_in_date',       label: 'Tgl. CI'   },
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
  { key: 'date',         label: 'Tanggal Rekap' },
  { key: 'total_guests', label: 'Total Tamu'    },
  { key: 'total_hotels', label: 'Total Hotel'   },
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
  const preview = renderPreview(text || '', sample);
  const now = new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
  return (
    <div style={{
      background: '#E8D5C0', borderRadius: 10,
      padding: '16px 14px 14px', minHeight: 200,
      display: 'flex', flexDirection: 'column', justifyContent: 'flex-end',
    }}>
      <div style={{
        alignSelf: 'flex-end', maxWidth: '90%',
        background: '#DCFCE7', borderRadius: '14px 14px 3px 14px',
        padding: '10px 12px 8px', boxShadow: '0 1px 2px rgba(0,0,0,.12)',
      }}>
        {text ? (
          <div style={{ fontSize: 13, lineHeight: 1.65, color: '#111827', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            {preview.map((p, i) => p.hi ? (
              <mark key={i} style={{ background: 'rgba(22,163,74,.18)', color: '#15803D', borderRadius: 3, padding: '0 2px' }}>
                {p.text}
              </mark>
            ) : <span key={i}>{p.text}</span>)}
          </div>
        ) : (
          <div style={{ fontSize: 13, color: '#9CA3AF', fontStyle: 'italic' }}>Template kosong.</div>
        )}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 3, marginTop: 5 }}>
          <span style={{ fontSize: 10, color: '#6B7280' }}>{now}</span>
          <span style={{ fontSize: 13, color: '#53BDEB', lineHeight: 1 }}>✓✓</span>
        </div>
      </div>
    </div>
  );
}

// ── Template editor panel ─────────────────────────────────────
function TemplateEditorPanel({ title, body, onChange, vars, sample, onClose, onSave, saving, savedAt, error }) {
  const ref = useRef(null);

  const insertVar = (key) => {
    const el = ref.current; const token = `{${key}}`;
    if (!el) { onChange(body + token); return; }
    const s = el.selectionStart, e = el.selectionEnd;
    onChange(body.slice(0, s) + token + body.slice(e));
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(s + token.length, s + token.length); });
  };

  const microLabel = (txt, extra) => (
    <div style={{
      fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
      letterSpacing: '0.08em', color: 'var(--text-3)', marginBottom: 8,
      display: 'flex', alignItems: 'center', gap: 5,
    }}>
      {extra}{txt}
    </div>
  );

  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 14, padding: '24px 26px',
      boxShadow: '0 4px 24px rgba(0,0,0,.08)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>
          Edit: {title}
        </div>
        <button onClick={onClose} style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: 'var(--text-3)', padding: '4px', borderRadius: 6, display: 'flex',
        }}>
          <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        {/* Editor */}
        <div>
          {microLabel('Template')}
          <textarea
            ref={ref}
            value={body}
            onChange={e => onChange(e.target.value)}
            placeholder="Tulis template pesan di sini…"
            style={{
              width: '100%', height: 220, padding: '11px 13px', boxSizing: 'border-box',
              background: 'var(--surface-2)', border: '1px solid var(--border-2)',
              borderRadius: 10, color: 'var(--text)', fontFamily: "'JetBrains Mono', monospace",
              fontSize: 13, lineHeight: 1.7, resize: 'vertical', outline: 'none',
            }}
          />
          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--text-3)', marginBottom: 7 }}>
              Sisipkan variabel
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {vars.map(v => (
                <button key={v.key} onClick={() => insertVar(v.key)} title={v.label} style={{
                  fontSize: 11, padding: '4px 10px', borderRadius: 6, cursor: 'pointer',
                  border: '1px solid var(--border-2)', background: 'var(--surface)',
                  color: 'var(--text-2)', fontFamily: "'JetBrains Mono', monospace",
                }}>
                  {'{' + v.key + '}'}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* WA preview */}
        <div>
          {microLabel('Tampilan di WhatsApp',
            <svg width="10" height="10" viewBox="0 0 24 24" fill="#25D366">
              <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"/>
            </svg>
          )}
          <WhatsAppPreview text={body} sample={sample} />
          <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-3)' }}>
            Nilai variabel diganti dengan data nyata saat pengiriman.
          </div>
        </div>
      </div>

      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
        gap: 10, marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border)',
      }}>
        {savedAt && !error && (
          <span style={{ fontSize: 12, color: 'var(--green)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            Tersimpan pukul {savedAt}
          </span>
        )}
        {error && <span style={{ fontSize: 12, color: 'var(--red)' }}>{error}</span>}
        <button onClick={onClose} className="btn btn-secondary">
          Tutup
        </button>
        <button onClick={onSave} disabled={saving} className="btn btn-primary">
          {saving ? 'Menyimpan…' : 'Simpan'}
        </button>
      </div>
    </div>
  );
}

// ── WA Recipients section ─────────────────────────────────────
function WATargetSection({ initialTargets, highlighted }) {
  const [targets, setTargets] = useState(initialTargets || []);
  const [label,   setLabel]   = useState('');
  const [target,  setTarget]  = useState('');
  const [adding,  setAdding]  = useState(false);
  const [error,   setError]   = useState('');
  const [confirm, setConfirm] = useState(null);

  const handleAdd = async () => {
    if (!label.trim() || !target.trim()) { setError('Label dan nomor wajib diisi'); return; }
    setAdding(true); setError('');
    try {
      const r = await axios.post(
        '/calendar/wa-targets/',
        new URLSearchParams({ label, target }),
        { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
      );
      if (r.data.ok) { setTargets(prev => [...prev, { ...r.data, is_active: true }]); setLabel(''); setTarget(''); }
      else setError(r.data.error || 'Gagal menambah nomor');
    } catch { setError('Network error'); }
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

  const inp = {
    padding: '8px 12px', fontSize: 13, borderRadius: 8,
    border: '1px solid var(--border-2)', background: 'var(--surface-2)',
    color: 'var(--text)', fontFamily: 'inherit', outline: 'none',
    width: '100%', boxSizing: 'border-box',
  };

  return (
    <div style={{
      background: 'var(--surface)',
      border: highlighted ? '2px solid var(--accent-2)' : '1px solid var(--border)',
      borderRadius: 14, padding: '20px 26px',
      boxShadow: highlighted ? '0 0 0 3px rgba(255,108,55,.1)' : '0 1px 3px rgba(0,0,0,.05)',
      transition: 'border-color .15s, box-shadow .15s',
    }}>
      <div style={{ marginBottom: 18 }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)', marginBottom: 4 }}>
          Penerima Rekap
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-3)' }}>
          Rekap harian dikirim ke semua nomor aktif di bawah ini.
        </div>
      </div>

      {targets.length > 0 ? (
        <div style={{ marginBottom: 20, borderRadius: 10, border: '1px solid var(--border)', overflow: 'hidden' }}>
          {targets.map((t, i) => (
            <div key={t.id} style={{
              display: 'flex', alignItems: 'center', gap: 12,
              padding: '12px 16px', background: 'var(--surface)',
              borderTop: i > 0 ? '1px solid var(--border)' : 'none', flexWrap: 'wrap',
            }}>
              <span style={{
                width: 9, height: 9, borderRadius: '50%', flexShrink: 0,
                background: t.is_active ? 'var(--green)' : 'var(--text-3)',
                boxShadow: t.is_active ? '0 0 0 3px rgba(46,204,113,.18)' : 'none',
                transition: 'background .2s, box-shadow .2s',
              }} />
              <span style={{ flex: 1, fontSize: 13, fontWeight: 600, color: 'var(--text)', minWidth: 80 }}>
                {t.label}
              </span>
              <span style={{ fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-3)', letterSpacing: '0.03em' }}>
                {t.target}
              </span>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <button onClick={() => handleToggle(t.id)} style={{
                  fontSize: 11, fontWeight: 600, padding: '4px 12px', borderRadius: 99, cursor: 'pointer',
                  border: t.is_active ? '1px solid rgba(46,204,113,.3)' : '1px solid var(--border-2)',
                  background: t.is_active ? 'var(--green-muted)' : 'var(--surface)',
                  color: t.is_active ? 'var(--green)' : 'var(--text-3)', transition: 'all .15s',
                }}>
                  {t.is_active ? 'Aktif' : 'Nonaktif'}
                </button>
                {confirm === t.id ? (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
                    <span style={{ color: 'var(--text-3)' }}>Hapus?</span>
                    <button onClick={() => handleDelete(t.id)} style={{ fontWeight: 700, color: 'var(--red)', background: 'none', border: 'none', cursor: 'pointer', padding: '0 2px', fontSize: 12 }}>Ya</button>
                    <button onClick={() => setConfirm(null)} style={{ color: 'var(--text-3)', background: 'none', border: 'none', cursor: 'pointer', padding: '0 2px', fontSize: 12 }}>Batal</button>
                  </span>
                ) : (
                  <button onClick={() => setConfirm(t.id)} style={{
                    fontSize: 11, fontWeight: 500, padding: '4px 10px', borderRadius: 99, cursor: 'pointer',
                    border: '1px solid rgba(255,69,58,.25)', background: 'var(--red-muted)', color: 'var(--red)',
                  }}>
                    Hapus
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div style={{
          padding: '20px', marginBottom: 20, borderRadius: 10,
          border: '2px dashed var(--border)', textAlign: 'center', color: 'var(--text-3)', fontSize: 13,
        }}>
          Belum ada nomor terdaftar. Tambah penerima di bawah.
        </div>
      )}

      <div style={{ padding: '16px', borderRadius: 10, border: '1px solid var(--border)', background: 'var(--surface-2)' }}>
        <div style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-3)', marginBottom: 12 }}>
          Tambah Penerima
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ flex: '1 1 130px', minWidth: 110 }}>
            <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-3)', marginBottom: 5 }}>Label</div>
            <input type="text" placeholder="Grup Ops Makkah" value={label} onChange={e => setLabel(e.target.value)} style={inp} />
          </div>
          <div style={{ flex: '1 1 160px', minWidth: 130 }}>
            <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-3)', marginBottom: 5 }}>Nomor WA / Grup ID</div>
            <input type="text" placeholder="628xxx..." value={target} onChange={e => setTarget(e.target.value)} style={inp} onKeyDown={e => e.key === 'Enter' && handleAdd()} />
          </div>
          <button onClick={handleAdd} disabled={adding} className="btn btn-primary"
            style={{ height: 37, flexShrink: 0, alignSelf: 'flex-end' }}>
            {adding ? '…' : '+ Tambah'}
          </button>
        </div>
        {error && <p style={{ margin: '8px 0 0', fontSize: 12, color: 'var(--red)' }}>{error}</p>}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────
export default function RecapSettings({
  wa_targets = [], h1_template = '', h0_template = '', recap_template = '',
}) {
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
      setSavedAt(new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }));
    } catch { setError('Gagal menyimpan.'); }
    setSaving(false);
  };

  const TAMU_WA = [
    { label: 'Tamu',     bg: 'var(--accent-muted)', color: 'var(--accent-2)' },
    { label: 'WhatsApp', bg: 'var(--green-muted)',  color: 'var(--green)' },
  ];
  const GRUP_WA = [
    { label: 'Grup Ops', bg: 'var(--purple-muted)', color: 'var(--purple)' },
    { label: 'WhatsApp', bg: 'var(--green-muted)',  color: 'var(--green)' },
  ];

  const editorProps = {
    h1:    { title: 'Pengingat H-1', body: h1, onChange: setH1, vars: GUEST_VARS,  sample: GUEST_SAMPLE  },
    h0:    { title: 'Pengingat H-0', body: h0, onChange: setH0, vars: GUEST_VARS,  sample: GUEST_SAMPLE  },
    recap: { title: 'Rekap Harian',  body: recap, onChange: setRecap, vars: RECAP_VARS, sample: RECAP_SAMPLE },
  };

  return (
    <div style={{ maxWidth: 920, margin: '40px auto 80px', padding: '0 16px' }}>

      {/* Page header */}
      <div style={{ marginBottom: 32 }}>
        <PageBack href="/calendar/" label="Kembali ke Kalender" />
        <h2 style={{ margin: '0 0 4px', fontSize: 20, fontWeight: 800, color: 'var(--text)', letterSpacing: '-0.03em' }}>
          Pengaturan Rekap WA
        </h2>
        <p style={{ margin: 0, fontSize: 13, color: 'var(--text-3)' }}>
          Kelola template pesan dan penerima rekap check-in harian.
        </p>
      </div>

      {/* Notification cards grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
        gap: 14, marginBottom: 14,
      }}>
        <NotifCard
          title="Pengingat H-1"
          tags={TAMU_WA}
          description="Kirim pesan WhatsApp ke tamu sehari sebelum check-in. Gunakan Edit untuk mengatur isi pesan."
          active={h1Active}
          onToggle={() => setH1Active(v => !v)}
          selected={selected === 'h1'}
          onEdit={() => toggleCard('h1')}
        />
        <NotifCard
          title="Pengingat H-0"
          tags={TAMU_WA}
          description="Kirim pesan WhatsApp ke tamu di hari check-in. Aktifkan untuk mengingatkan tamu pada hari kedatangan."
          active={h0Active}
          onToggle={() => setH0Active(v => !v)}
          selected={selected === 'h0'}
          onEdit={() => toggleCard('h0')}
        />
        <NotifCard
          title="Rekap Harian"
          tags={GRUP_WA}
          description="Rekap daftar tamu check-in yang dikirim ke grup operator. Gunakan {guest_list} untuk menyisipkan daftar otomatis."
          active={true}
          onToggle={() => {}}
          selected={selected === 'recap'}
          onEdit={() => toggleCard('recap')}
        />
      </div>

      {/* Inline editor — muncul saat salah satu card dipilih */}
      {selected && selected !== null && (
        <div style={{ marginBottom: 14 }}>
          <TemplateEditorPanel
            {...editorProps[selected]}
            onClose={() => setSelected(null)}
            onSave={handleSave}
            saving={saving}
            savedAt={savedAt}
            error={error}
          />
        </div>
      )}

      {/* WA Recipients — highlighted saat card Rekap Harian dipilih */}
      <WATargetSection initialTargets={wa_targets} highlighted={selected === 'recap'} />
    </div>
  );
}
