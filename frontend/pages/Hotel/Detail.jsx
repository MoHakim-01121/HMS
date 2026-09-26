import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { loadLeaflet, basemapUrl, basemapOptions } from "../../utils/leaflet.js";
import { distColor, MAP } from "../../components/mapColors.js";
import { RvBack } from "../../components/shadcn/record-view.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import KebabMenu from "../../components/shadcn/kebab-menu.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmtDist } from "../../utils/format.js";
import { Icon } from "../../components/icons.jsx";

function haversine(lat1, lng1, lat2, lng2) {
  const R = 6371000, p1 = lat1 * Math.PI / 180, p2 = lat2 * Math.PI / 180;
  const dLat = (lat2 - lat1) * Math.PI / 180, dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// Leaflet map ported from hotel_detail.html. Height is set through the wrapper.
function HotelMiniMap({ hotel, height = 320 }) {
  const { t } = useI18n();
  const ref = useRef(null);
  useEffect(() => {
    let map, observer;
    let cancelled = false;
    loadLeaflet().then((L) => {
      if (cancelled || !ref.current) return;
      const refLL = hotel.city === "madinah" ? [24.4672, 39.6112] : [21.420324, 39.826485];
      const hotelLL = [hotel.lat, hotel.lng];
      const d = hotel.distance;
      const color = distColor(d);

      map = L.map(ref.current, { zoomControl: false, scrollWheelZoom: false, dragging: true });
      L.control.zoom({ position: "bottomright" }).addTo(map);

      const tileUrl = () => basemapUrl(document.documentElement.getAttribute("data-theme"));
      const tileLayer = L.tileLayer(tileUrl(), basemapOptions).addTo(map);
      observer = new MutationObserver(() => tileLayer.setUrl(tileUrl()));
      observer.observe(document.documentElement, { attributeFilter: ["data-theme"] });

      const routeTip = L.tooltip({ permanent: false, opacity: 1, className: "route-dist-tip", direction: "top", offset: [0, -8] });
      const dot = (c, sz) => L.divIcon({ className: "", html: `<div style="width:${sz}px;height:${sz}px;border-radius:50%;background:${c};border:2px solid #fff;box-shadow:0 0 6px ${c}99;"></div>`, iconSize: [sz, sz], iconAnchor: [sz / 2, sz / 2] });

      L.marker(refLL, { icon: dot(MAP.yellow, 12) }).bindTooltip(hotel.ref_label).addTo(map);
      if (hotel.city !== "madinah") {
        L.marker([21.4225, 39.8262], { icon: dot(MAP.red, 10) }).bindTooltip(t("Masjid Al-Haram")).addTo(map);
      }
      L.marker(hotelLL, { icon: dot(color, 12) }).bindTooltip(hotel.name, { direction: "top", offset: [0, -8] }).addTo(map);

      const coords = hotel.route && hotel.route.length >= 2 ? hotel.route : [refLL, hotelLL];
      map.fitBounds(coords.map((c) => L.latLng(c[0], c[1])), { padding: [40, 40] });
      const line = L.polyline(coords, { color, weight: 2.5, opacity: 0.75, dashArray: "8,5" }).addTo(map);
      line.on("mousemove", (e) => routeTip.setLatLng(e.latlng).setContent(fmtDist(haversine(refLL[0], refLL[1], e.latlng.lat, e.latlng.lng))).addTo(map));
      line.on("mouseout", () => routeTip.remove());
    });
    return () => {
      cancelled = true;
      if (observer) observer.disconnect();
      if (map) map.remove();
    };
  }, [hotel]);

  return <div ref={ref} style={{ height }} />;
}

function RoomCalculator({ avg }) {
  const { t } = useI18n();
  const [jamaah, setJamaah] = useState(35);
  const rooms = jamaah > 0 ? Math.ceil(jamaah / avg) : null;
  return (
    <div className="hms-hm-calc">
      <div className="hms-hm-crow">
        <span className="lbl">{t("Pilgrims")}</span>
        <div className="hms-hm-stepper">
          <button type="button" className="stp" aria-label={t("Decrease")} onClick={() => setJamaah((v) => Math.max(1, v - 1))}>−</button>
          <Input
            aria-label={t("Pilgrims")}
            className="hms-hm-inp"
            type="number"
            min="1"
            value={jamaah}
            onChange={(e) => setJamaah(parseInt(e.target.value) || 0)}
          />
          <button type="button" className="stp" aria-label={t("Increase")} onClick={() => setJamaah((v) => v + 1)}>+</button>
        </div>
      </div>
      <div className="hms-hm-cresult">
        <span className="lbl">{t("Rooms needed")}</span>
        <span className="val">
          {rooms ?? "—"}
          <span className="u">{t("Rooms")}</span>
        </span>
      </div>
      <div className="hms-hm-cavg">
        {t("Avg {avg} pax/room", { avg })}
      </div>
    </div>
  );
}

export default function Detail({ hotel }) {
  const { t } = useI18n();
  const openForm = useFormModal();
  const perms = usePerms();
  const hasCoords = hotel.lat != null && hotel.lng != null;
  const distTone =
    hotel.distance == null ? undefined :
    hotel.distance < 500 ? "var(--green)" :
    hotel.distance < 1500 ? "var(--yellow)" : "var(--red)";

  const canEdit = perms.can("hotels", "edit");
  const [confirm, confirmDialog] = useConfirm();
  const delHotel = () => confirm({
    title: t("Delete hotel"),
    message: t("Delete hotel {name}?", { name: hotel.name }),
    onConfirm: () => router.post(`/hotels/${hotel.id}/delete/`),
  });

  const roomTypes = [...(hotel.room_types || [])].sort(
    (a, b) => (a.capacity || 0) - (b.capacity || 0) || String(a.name).localeCompare(String(b.name))
  );
  const mealPlans = hotel.meal_plans || [];
  const locationText = `${hotel.city_display}${hotel.area ? `, ${hotel.area}` : ""}`;

  const removeRoomType = (rt) => confirm({
    title: t("Remove room type"),
    message: t("Remove {name} from this hotel?", { name: rt.name }),
    detail: t("CLs that already use it keep their rooms unchanged."),
    confirmLabel: "Remove",
    danger: true,
    onConfirm: () => router.post(`/hotels/${hotel.id}/room-types/${rt.id}/delete/`),
  });

  return (
    <div className="page shadcn-root hms-rv-page hms-hm-main">
      <RvBack href="/hotels/" label={t("Back")} />
      <div className="hms-hm-cards">
        <section className="hms-hm-card hms-hm-info">
          <div className="hms-hm-top">
            <h1>{hotel.name}</h1>
            <div className="hms-hm-topacts">
              <span className={`hms-dv-pill hms-rv-badge tone-${hotel.is_active ? "green" : "gray"}`}>
                {hotel.is_active ? t("Active") : t("Inactive")}
              </span>
              {canEdit ? (
                <button
                  type="button" className="hms-rv-btn"
                  onClick={() => openForm(`/hotels/${hotel.id}/edit/`)}
                  onPointerEnter={() => openForm.prefetch?.(`/hotels/${hotel.id}/edit/`)}
                >
                  {t("Edit")}
                </button>
              ) : null}
              <KebabMenu items={[perms.can("hotels", "delete") && { label: t("Delete"), onClick: delHotel, danger: true }]} />
            </div>
          </div>

          <div className="hms-hm-sub">{locationText}</div>

          <div className="hms-hm-meta">
            <div>
              <div className="k">{t("Stars")}</div>
              <div className="v">{hotel.stars ? `${hotel.stars}★` : "—"}</div>
            </div>
            <div>
              <div className="k">{t("Distance to Masjid Al-Haram")}</div>
              <div className="v" style={{ color: distTone }}>{hasCoords && hotel.distance_label ? hotel.distance_label : "—"}</div>
            </div>
            <div>
              <div className="k">{t("Average occupancy")}</div>
              <div className="v">{hotel.avg_occupancy ? `${hotel.avg_occupancy} pax/room` : "—"}</div>
            </div>
            <div>
              <div className="k">{t("Reference")}</div>
              <div className="v sub">{hasCoords ? hotel.ref_label : "—"}</div>
            </div>
          </div>

          {hotel.note ? (
            <div className="hms-hm-notebox">
              <div className="hms-hm-sec-lbl">
                <h2>{t("Notes")}</h2>
              </div>
              <div className="hms-hm-note-text">{hotel.note}</div>
            </div>
          ) : null}
        </section>

        <div className="hms-hm-pair">
          <section className="hms-hm-card hms-hm-rt">
            <div className="hms-hm-sec-lbl">
              <h2>{t("Room types")}</h2>
              {canEdit ? (
                <span className="right">
                  <button
                    type="button" className="hms-dv-act"
                    onClick={() => openForm(`/hotels/${hotel.id}/room-types/bulk/`)}
                    onPointerEnter={() => openForm.prefetch?.(`/hotels/${hotel.id}/room-types/bulk/`)}
                  >
                    <Icon name="plus" size={13} />
                    {t("Bulk Add Room Types")}
                  </button>
                  <button
                    type="button" className="hms-dv-act"
                    onClick={() => openForm(`/hotels/${hotel.id}/room-types/new/`)}
                    onPointerEnter={() => openForm.prefetch?.(`/hotels/${hotel.id}/room-types/new/`)}
                  >
                    {t("+ Add Room Type")}
                  </button>
                </span>
              ) : null}
            </div>
            {roomTypes.length ? (
              <div className="hms-hm-table">
              <table className="hms-hm-rtbl">
                <thead>
                  <tr>
                    <th>{t("Room type")}</th>
                    {/* "View" alone translates as the Lihat action; the noun
                        key is "Room View". Order follows the form. */}
                    <th>{t("Room View")}</th>
                    <th>{t("Capacity")}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {roomTypes.map((rt) => (
                    <tr key={rt.id}>
                      <td className="nm">{rt.name}</td>
                      <td className="mut">{rt.view ? t(rt.view) : "—"}</td>
                      <td className="mut">{rt.capacity} {t("pax")}</td>
                      {canEdit ? (
                        <td className="ac-wrap">
                          <span className="ac">
                            <RowActions
                              actions={[
                                { icon: "edit", label: t("Edit"), onClick: () => openForm(`/hotels/${hotel.id}/room-types/${rt.id}/edit/`) },
                                { icon: "trash", label: t("Remove"), variant: "red", onClick: () => removeRoomType(rt) },
                              ]}
                            />
                          </span>
                        </td>
                      ) : null}
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            ) : (
              <div className="hms-hm-empty">{t("This hotel has no room types yet.")}</div>
            )}
          </section>

          <section className="hms-hm-card hms-hm-meal">
            <div className="hms-hm-sec-lbl">
              <h2>{t("Meal plans")}</h2>
              {canEdit ? (
                <span className="right">
                  <button
                    type="button" className="hms-dv-act"
                    onClick={() => openForm(`/hotels/${hotel.id}/meal-plans/`)}
                    onPointerEnter={() => openForm.prefetch?.(`/hotels/${hotel.id}/meal-plans/`)}
                  >
                    {t("Manage")}
                  </button>
                </span>
              ) : null}
            </div>
            {mealPlans.length ? (
              <div className="hms-hm-rows">
                {mealPlans.map((mp) => (
                  <div key={mp.code} className="hms-hm-row">
                    <span className="cd">{mp.code}</span>
                    <span>{t(mp.name)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="hms-hm-empty">{t("No meal plans set — the CL form falls back to free-text Meals for this hotel.")}</div>
            )}

            {hotel.avg_occupancy ? (
              <div className="hms-hm-calc-sec">
                <div className="hms-hm-sec-lbl">
                  <h2>{t("Room calculator")}</h2>
                </div>
                <RoomCalculator avg={hotel.avg_occupancy} />
              </div>
            ) : null}
          </section>
        </div>

        <section className="hms-hm-card hms-hm-loccard">
          <div className="hms-hm-loctop">
            <div className="hms-hm-sec-lbl">
              <h2>{t("Location")}</h2>
            </div>
            <a className="hms-hm-maplink" href="/hotels/map/">
              <Icon name="map-pin" size={13} />
              {t("See full map")}
            </a>
          </div>
          {hasCoords ? (
            <div className="hms-hm-map">
              <HotelMiniMap hotel={hotel} height={260} />
            </div>
          ) : (
            <div className="hms-hm-note">{t("Location not set — add coordinates on the edit page to show this hotel on the map.")}</div>
          )}
        </section>
      </div>

      {confirmDialog}
    </div>
  );
}