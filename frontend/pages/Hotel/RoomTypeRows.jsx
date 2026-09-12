import { Icon } from "../../components/icons.jsx";
import { useI18n } from "../../utils/i18n.jsx";

const EMPTY_ROOM_TYPE = { name: "", capacity: 2, occupancy: "", view: "" };

const OCCUPANCY = ["double", "triple", "quad", "quint"];
const VIEW = ["non_view", "city", "kaaba", "haram", "other"];
const OCCUPANCY_LABEL = { double: "Double", triple: "Triple", quad: "Quad", quint: "Quint" };
const VIEW_LABEL = { non_view: "Non View", city: "City View", kaaba: "Kaaba View", haram: "Haram View", other: "Other" };

export default function RoomTypeRows({ roomTypes, onChange }) {
  const { t } = useI18n();
  const update = (i, key, val) => {
    const next = roomTypes.map((rt, idx) => (idx === i ? { ...rt, [key]: val } : rt));
    onChange(next);
  };
  const add = () => onChange([...roomTypes, { ...EMPTY_ROOM_TYPE }]);
  const remove = (i) => onChange(roomTypes.filter((_, idx) => idx !== i));

  return (
    <div>
      {roomTypes.length > 0 && (
        <div className="cl-rooms">
          <div className="cl-rooms-head">
            <span>{t("Room Type Name")}</span>
            <span className="col-c">{t("Capacity (guests)")}</span>
            <span>{t("Occupancy")}</span>
            <span>{t("View")}</span>
            <span />
          </div>
          {roomTypes.map((rt, i) => (
            <div key={rt.id ?? `new-${i}`} className="cl-room-row">
              <div className="ff">
                <input type="text" value={rt.name} onChange={(e) => update(i, "name", e.target.value)} placeholder={t("e.g. Double View Kaaba")} />
              </div>
              <div className="ff"><input className="num-c" type="number" min="1" value={rt.capacity} onChange={(e) => update(i, "capacity", e.target.value)} /></div>
              <div className="ff">
                <select value={rt.occupancy || ""} onChange={(e) => update(i, "occupancy", e.target.value)}>
                  <option value="">{t("— Optional —")}</option>
                  {OCCUPANCY.map((o) => <option key={o} value={o}>{t(OCCUPANCY_LABEL[o])}</option>)}
                </select>
              </div>
              <div className="ff">
                <select value={rt.view || ""} onChange={(e) => update(i, "view", e.target.value)}>
                  <option value="">{t("— Optional —")}</option>
                  {VIEW.map((v) => <option key={v} value={v}>{t(VIEW_LABEL[v])}</option>)}
                </select>
              </div>
              <button type="button" className="btn btn-ghost btn-icon btn-icon-red" title={t("Remove")} onClick={() => remove(i)}>
                <Icon name="trash" size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 10 }}>
        <button type="button" className="btn btn-secondary btn-sm" onClick={add}>
          <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
          {t("Add room type")}
        </button>
      </div>
    </div>
  );
}
