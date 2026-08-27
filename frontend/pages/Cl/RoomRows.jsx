import { Icon } from "../../components/icons.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

const ROOM_TYPES = ["Double", "Triple", "Quad", "Quint"];
const EMPTY_ROOM = { room_type: "", meals: "", quantity: 1, price: "" };

export default function RoomRows({ rooms, onChange, nights }) {
  const { t } = useI18n();
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
        <>
          {/* Wide layout — same editable table as the Invoice form's
              Reservations/Payments (styles live in Cl/Form.jsx's CSS block). */}
          <div className="cl-rooms-desktop">
            <div className="cl-tbl-wrap">
              <div className="cl-tbl-scroll">
                <table className="cl-tbl cl-tbl-rooms">
                  <colgroup>
                    <col style={{ width: 160 }} />
                    <col />
                    <col style={{ width: 74 }} />
                    <col style={{ width: 124 }} />
                    <col style={{ width: 118 }} />
                    <col style={{ width: 48 }} />
                  </colgroup>
                  <thead>
                    <tr>
                      <th>{t("Room Type")}</th>
                      <th>{t("Meals")}</th>
                      <th className="r">{t("Qty")}</th>
                      <th className="r">{t("Price/night")}</th>
                      <th className="r">{t("Subtotal")}</th>
                      <th aria-label={t("Actions")} />
                    </tr>
                  </thead>
                  <tbody>
                    {rooms.map((r, i) => {
                      const sub = (nights || 1) * (Number(r.quantity) || 0) * (Number(r.price) || 0);
                      return (
                        <tr key={i}>
                          <td>
                            <span className="c-sel">
                              <select className="c-in c-strong" value={r.room_type} onChange={(e) => update(i, "room_type", e.target.value)} aria-label={t("Room type")}>
                                <option value="">{t("— Select —")}</option>
                                {ROOM_TYPES.map((rt) => <option key={rt} value={rt}>{rt}</option>)}
                              </select>
                            </span>
                          </td>
                          <td><input className="c-in" type="text" value={r.meals} onChange={(e) => update(i, "meals", e.target.value)} placeholder="BB, HB…" aria-label={t("Meals")} /></td>
                          <td><input className="c-in c-num" type="number" min="1" value={r.quantity} onChange={(e) => update(i, "quantity", e.target.value)} aria-label={t("Quantity")} /></td>
                          <td><input className="c-in c-num" type="number" min="0" step="0.01" value={r.price} onChange={(e) => update(i, "price", e.target.value)} placeholder="0.00" aria-label={t("Price per night")} /></td>
                          {/* Computed from nights × qty × price — never typed. */}
                          <td className="c-calc">{fmt(sub)}</td>
                          <td className="c-act">
                            <button type="button" className="cl-row-del" title={t("Delete")} aria-label={t("Remove room")} onClick={() => remove(i)}>
                              <Icon name="trash" size={13} />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <button type="button" className="cl-tbl-add" onClick={add}>{t("+ Add room")}</button>
            </div>
          </div>

          <div className="cl-rooms-cards">
            {rooms.map((r, i) => {
              const sub = (nights || 1) * (Number(r.quantity) || 0) * (Number(r.price) || 0);
              return (
                <div key={i} className="cl-room-flat">
                  <div className="cl-room-flat-head">
                    <select className="cl-room-card-type" value={r.room_type} onChange={(e) => update(i, "room_type", e.target.value)}>
                      <option value="">{t("— Select —")}</option>
                      {ROOM_TYPES.map((rt) => <option key={rt} value={rt}>{rt}</option>)}
                    </select>
                    <button type="button" className="cl-room-card-trash" title={t("Delete")} onClick={() => remove(i)}>
                      <Icon name="trash" size={13} />
                    </button>
                  </div>
                  <input
                    className="cl-room-card-meals" type="text" value={r.meals}
                    onChange={(e) => update(i, "meals", e.target.value)} placeholder={t("Meal plan (BB, HB…)")}
                  />
                  <div className="cl-room-card-calc">
                    <input type="number" min="1" value={r.quantity} onChange={(e) => update(i, "quantity", e.target.value)} />
                    <span>{t("rooms")} ×</span>
                    <input type="number" min="0" step="0.01" value={r.price} onChange={(e) => update(i, "price", e.target.value)} placeholder="0.00" />
                    <span>/{t("night")}</span>
                    <span className="cl-room-card-eq">{fmt(sub)}<span className="cur">SAR</span></span>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* No desktop add button out here: it lives in the last row of the table
          frame above, where the new row will actually appear. This one is the
          phone layout's, which has no frame to sit in. */}
      <button type="button" className="btn-add-row cl-room-add-mobile" onClick={add}>
        <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
        {t("Add room")}
      </button>
    </div>
  );
}
