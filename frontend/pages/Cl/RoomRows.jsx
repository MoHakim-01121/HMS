const ROOM_TYPES = ["Double", "Triple", "Quad", "Quint"];
const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

export default function RoomRows({ rooms, onChange, nights }) {
  const update = (i, key, val) => {
    const next = rooms.map((r, idx) => (idx === i ? { ...r, [key]: val } : r));
    onChange(next);
  };
  const add = () => onChange([...rooms, { room_type: "", meals: "", quantity: 1, price: "" }]);
  const remove = (i) => onChange(rooms.filter((_, idx) => idx !== i));

  return (
    <div>
      {rooms.map((r, i) => {
        const sub = (nights || 1) * (Number(r.quantity) || 0) * (Number(r.price) || 0);
        return (
          <div key={i} className="fg-2" style={{ gridTemplateColumns: "1.2fr 1fr .7fr 1fr auto", alignItems: "end", gap: 8, marginBottom: 8 }}>
            <div className="ff">
              <label>Tipe Kamar</label>
              <select value={r.room_type} onChange={(e) => update(i, "room_type", e.target.value)}>
                <option value="">— Pilih —</option>
                {ROOM_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className="ff"><label>Makan</label><input type="text" value={r.meals} onChange={(e) => update(i, "meals", e.target.value)} placeholder="BB, HB…" /></div>
            <div className="ff"><label>Jml</label><input type="number" min="1" value={r.quantity} onChange={(e) => update(i, "quantity", e.target.value)} /></div>
            <div className="ff"><label>Harga/malam</label><input type="number" min="0" step="0.01" value={r.price} onChange={(e) => update(i, "price", e.target.value)} placeholder="0.00" /></div>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => remove(i)} title="Hapus" style={{ marginBottom: 2 }}>×</button>
            <div style={{ gridColumn: "1 / -1", fontSize: 11, color: "var(--text-3)", marginTop: -2 }}>Subtotal: {fmt(sub)} SAR</div>
          </div>
        );
      })}
      <button type="button" className="btn btn-secondary btn-sm" onClick={add} style={{ marginTop: 4 }}>
        <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
        Tambah kamar
      </button>
    </div>
  );
}
