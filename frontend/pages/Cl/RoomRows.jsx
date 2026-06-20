import { Icon } from "../../components/icons.jsx";

const ROOM_TYPES = ["Double", "Triple", "Quad", "Quint"];
const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");
const EMPTY_ROOM = { room_type: "", meals: "", quantity: 1, price: "" };

export default function RoomRows({ rooms, onChange, nights }) {
  const update = (i, key, val) => {
    const next = rooms.map((r, idx) => (idx === i ? { ...r, [key]: val } : r));
    onChange(next);
  };
  const add = () => onChange([...rooms, { ...EMPTY_ROOM }]);
  // Always keep at least one row — removing the last one just clears it.
  const remove = (i) =>
    onChange(rooms.length > 1 ? rooms.filter((_, idx) => idx !== i) : [{ ...EMPTY_ROOM }]);

  return (
    <div>
      {rooms.length > 0 && (
        <div className="cl-rooms">
          <div className="cl-rooms-head">
            <span>Room Type</span>
            <span>Meals</span>
            <span className="col-c">Qty</span>
            <span className="col-r">Price/night</span>
            <span className="col-r">Subtotal</span>
            <span />
          </div>

          {rooms.map((r, i) => {
            const sub = (nights || 1) * (Number(r.quantity) || 0) * (Number(r.price) || 0);
            return (
              <div key={i} className="cl-room-row">
                <div className="ff">
                  <select value={r.room_type} onChange={(e) => update(i, "room_type", e.target.value)}>
                    <option value="">— Select —</option>
                    {ROOM_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div className="ff"><input type="text" value={r.meals} onChange={(e) => update(i, "meals", e.target.value)} placeholder="BB, HB…" /></div>
                <div className="ff"><input className="num-c" type="number" min="1" value={r.quantity} onChange={(e) => update(i, "quantity", e.target.value)} /></div>
                <div className="ff"><input className="num-r" type="number" min="0" step="0.01" value={r.price} onChange={(e) => update(i, "price", e.target.value)} placeholder="0.00" /></div>
                <div className="cl-room-sub">{fmt(sub)}</div>
                <button type="button" className="btn btn-ghost btn-icon btn-icon-red" title="Delete" onClick={() => remove(i)}>
                  <Icon name="trash" size={14} />
                </button>
              </div>
            );
          })}
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 10 }}>
        <button type="button" className="btn btn-secondary btn-sm" onClick={add}>
          <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
          Add room
        </button>
      </div>
    </div>
  );
}
