import { Icon } from "../../components/icons.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

const EMPTY_ROOM = { room_type: "", room_type_id: "", meals: "", meal_plan_code: "", quantity: 1, price: "" };

// Placeholder <option> value for Meals text that predates the dropdown and
// matches no code the hotel sells ("BB + late checkout"). Picking it changes
// nothing, so re-saving an old CL never silently drops what was typed.
const LEGACY = "__legacy__";

// `roomTypes`: null = hotel not linked to the catalog (free text upstream —
// rooms can't be added until it is); [] = linked but the hotel has no
// room types yet; a populated array = the dropdown's actual options.
// `mealPlans` follows the same null / [] / populated convention as
// `roomTypes`; anything but a populated array keeps Meals as free text.
export default function RoomRows({ rooms, onChange, nights, roomTypes, mealPlans, addHotelHref, editHotelHref }) {
  const { t } = useI18n();
  const hasRoomTypes = Array.isArray(roomTypes) && roomTypes.length > 0;
  const roomTypeOptions = roomTypes || [];

  const update = (i, key, val) => {
    const next = rooms.map((r, idx) => (idx === i ? { ...r, [key]: val } : r));
    onChange(next);
  };
  const add = () => { if (hasRoomTypes) onChange([...rooms, { ...EMPTY_ROOM }]); };
  // Always keep at least one row — removing the last one just clears it.
  const remove = (i) =>
    onChange(rooms.length > 1 ? rooms.filter((_, idx) => idx !== i) : [{ ...EMPTY_ROOM }]);

  // Reads `rooms` from this closure at call time (not the one captured when
  // the <select> was rendered) — a stale `rooms` reference here would drop
  // the room_type_id write whenever a re-render raced the onChange.
  const onRoomTypeSelect = (i, roomTypeId) => {
    const rt = roomTypeOptions.find((t) => String(t.id) === roomTypeId);
    const next = rooms.map((r, idx) => (idx === i ? { ...r, room_type_id: roomTypeId, room_type: rt ? rt.name : "" } : r));
    onChange(next);
  };

  const mealCodes = Array.isArray(mealPlans) ? mealPlans.map((mp) => mp.code) : [];
  const hasMealPlans = mealCodes.length > 0;
  const mealValue = (r) => {
    if (r.meal_plan_code && mealCodes.includes(r.meal_plan_code)) return r.meal_plan_code;
    if (mealCodes.includes(r.meals)) return r.meals;
    return r.meals ? LEGACY : "";
  };
  // Same read-at-call-time closure as onRoomTypeSelect: code and label land
  // in one onChange, so neither can be dropped by a racing re-render.
  const onMealSelect = (i, code) => {
    if (code === LEGACY) return;
    onChange(rooms.map((r, idx) => (idx === i ? { ...r, meal_plan_code: code, meals: code } : r)));
  };
  const mealSelect = (r, i, className, ariaLabel) => (
    <select className={className} value={mealValue(r)} onChange={(e) => onMealSelect(i, e.target.value)} aria-label={ariaLabel}>
      <option value="">{t("— Select —")}</option>
      {/* Code only: the Meals column is narrow and "BB — Bed & Breakfast"
          truncated to "BB — Be". The code is also what operators always
          typed here and what the PDF prints; the name rides on the tooltip. */}
      {mealPlans.map((mp) => <option key={mp.code} value={mp.code} title={t(mp.name)}>{mp.code}</option>)}
      {mealValue(r) === LEGACY && <option value={LEGACY}>{r.meals} ({t("old entry")})</option>}
    </select>
  );

  const hintStyle = {
    padding: "10px 14px", marginBottom: 12, borderRadius: "var(--radius-control, 12px)",
    background: "var(--muted)", color: "var(--muted-foreground)", fontSize: 13,
  };

  return (
    <div>
      {!roomTypes && (
        <div style={hintStyle}>
          {t("Select a hotel from the catalog to add rooms.")}{" "}
          <a href={addHotelHref} target="_blank" rel="noreferrer">{t("+ Add this hotel")}</a>
        </div>
      )}
      {roomTypes && roomTypes.length === 0 && (
        <div style={hintStyle}>
          {t("This hotel has no room types yet.")}{" "}
          <a href={editHotelHref} target="_blank" rel="noreferrer">{t("Add room types on the hotel's edit page")}</a>
        </div>
      )}

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
                              <select
                                className="c-in c-strong" value={r.room_type_id || ""}
                                onChange={(e) => onRoomTypeSelect(i, e.target.value)}
                                disabled={!hasRoomTypes} aria-label={t("Room type")}
                              >
                                <option value="">{t("— Select —")}</option>
                                {roomTypeOptions.map((rt) => <option key={rt.id} value={rt.id}>{rt.name}</option>)}
                              </select>
                            </span>
                          </td>
                          <td>
                            {hasMealPlans ? (
                              <span className="c-sel">{mealSelect(r, i, "c-in", t("Meals"))}</span>
                            ) : (
                              <input className="c-in" type="text" value={r.meals} onChange={(e) => update(i, "meals", e.target.value)} placeholder="BB, HB…" aria-label={t("Meals")} />
                            )}
                          </td>
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
              <button type="button" className="cl-tbl-add" onClick={add} disabled={!hasRoomTypes}>{t("+ Add room")}</button>
            </div>
          </div>

          <div className="cl-rooms-cards">
            {rooms.map((r, i) => {
              const sub = (nights || 1) * (Number(r.quantity) || 0) * (Number(r.price) || 0);
              return (
                <div key={i} className="cl-room-flat">
                  <div className="cl-room-flat-head">
                    <select
                      className="cl-room-card-type" value={r.room_type_id || ""}
                      onChange={(e) => onRoomTypeSelect(i, e.target.value)}
                      disabled={!hasRoomTypes}
                    >
                      <option value="">{t("— Select —")}</option>
                      {roomTypeOptions.map((rt) => <option key={rt.id} value={rt.id}>{rt.name}</option>)}
                    </select>
                    <button type="button" className="cl-room-card-trash" title={t("Delete")} onClick={() => remove(i)}>
                      <Icon name="trash" size={13} />
                    </button>
                  </div>
                  {hasMealPlans ? (
                    mealSelect(r, i, "cl-room-card-meals", t("Meals"))
                  ) : (
                    <input
                      className="cl-room-card-meals" type="text" value={r.meals}
                      onChange={(e) => update(i, "meals", e.target.value)} placeholder={t("Meal plan (BB, HB…)")}
                    />
                  )}
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
      <button type="button" className="btn-add-row cl-room-add-mobile" onClick={add} disabled={!hasRoomTypes}>
        <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
        {t("Add room")}
      </button>
    </div>
  );
}
