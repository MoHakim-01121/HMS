import { useEffect, useRef, useState } from "react";
import { loadLeaflet, basemapUrl, basemapOptions } from "../../utils/leaflet.js";
import { distColor, MAP } from "../../components/mapColors.js";
import { RvBack, RvHero, RvFigure, RvCard, RvSection, RvRail } from "../../components/shadcn/record-view.jsx";
import { Icon } from "../../components/icons.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

function haversine(lat1, lng1, lat2, lng2) {
  const R = 6371000, p1 = lat1 * Math.PI / 180, p2 = lat2 * Math.PI / 180;
  const dLat = (lat2 - lat1) * Math.PI / 180, dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}
const fmtDist = (m) => (m < 1000 ? Math.round(m) + " m" : (m / 1000).toFixed(2) + " km");

// Leaflet mini-map ported from hotel_detail.html.
function HotelMiniMap({ hotel }) {
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
      L.marker(hotelLL, { icon: dot(color, 12) }).bindTooltip(hotel.name, { permanent: true, direction: "top", offset: [0, -8] }).addTo(map);

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

  return <div ref={ref} id="mini-map" style={{ height: 380 }} />;
}

function RoomCalculator({ avg }) {
  const { t } = useI18n();
  const [jamaah, setJamaah] = useState(35);
  const rooms = jamaah > 0 ? Math.ceil(jamaah / avg) : null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 6, maxWidth: 260 }}>
        <label htmlFor="pilgrims" className="hms-dv-mlabel">{t("Number of Pilgrims")}</label>
        <Input
          id="pilgrims"
          type="number"
          min="1"
          value={jamaah}
          onChange={(e) => setJamaah(parseInt(e.target.value) || 0)}
        />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, padding: "14px 16px", border: "1px solid var(--border)", borderRadius: 14, background: "var(--secondary)" }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 500 }}>{t("Rooms needed")}</div>
          <div style={{ fontSize: 12, color: "var(--muted-foreground)", marginTop: 2 }}>{t("avg {avg} pax/room", { avg })}</div>
        </div>
        <div style={{ fontSize: 30, fontWeight: 600, letterSpacing: "-.02em", fontVariantNumeric: "tabular-nums" }}>{rooms}</div>
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

  const sections = [];
  sections.push({
    title: t("Room Calculator"),
    body: hotel.avg_occupancy
      ? <RoomCalculator avg={hotel.avg_occupancy} />
      : <div className="hms-dv-empty">{t("This hotel has no average set")}</div>,
  });
  sections.push({
    title: t("Location"),
    meta: hasCoords ? <a className="hms-dv-act" href="/hotels/map/">{t("Full map")}</a> : undefined,
    body: hasCoords ? (
      <div style={{ borderRadius: 14, overflow: "hidden", border: "1px solid var(--border)" }}>
        <HotelMiniMap hotel={hotel} />
      </div>
    ) : (
      <div className="hms-dv-empty">{t("Coordinates not set yet. Add coordinates on the edit page.")}</div>
    ),
  });
  if (hotel.note) {
    sections.push({ title: t("Notes"), body: <div className="hms-rv-railtext">{hotel.note}</div> });
  }

  return (
    <div className="page shadcn-root hms-rv-page">
      <RvBack href="/hotels/" label={t("Back")} />

      <RvHero
        badge={hotel.is_active ? { label: t("Active"), tone: "green" } : { label: t("Inactive"), tone: "gray" }}
        title={hotel.name}
        side={
          hotel.distance_label ? (
            <RvFigure label={t("Distance")} value={hotel.distance_label} color={distTone} />
          ) : null
        }
        note={
          !hasCoords
            ? {
                icon: <Icon name="alert-circle" size={13} strokeWidth={2} />,
                iconBg: "var(--yellow)",
                title: t("Location not set"),
                text: t("Add coordinates on the edit page to show this hotel on the map."),
              }
            : undefined
        }
        actions={
          perms.can("hotels", "edit") ? (
            <button type="button" className="hms-rv-btn primary" onClick={() => openForm(`/hotels/${hotel.id}/edit/`)}>
              {t("Edit")}
            </button>
          ) : null
        }
      />

      <div className="hms-rv-grid">
        <div className="hms-rv-col">
          <RvCard>
            {sections.map((s, i) => (
              <RvSection key={s.title} title={s.title} meta={s.meta} first={i === 0}>
                {s.body}
              </RvSection>
            ))}
          </RvCard>
        </div>

        <RvRail
          rows={[
            { k: t("Location"), v: `${hotel.city_display}${hotel.area ? `, ${hotel.area}` : ""}` },
            hotel.stars ? { k: t("Stars"), v: `${hotel.stars}★` } : null,
            hotel.avg_occupancy ? { k: t("Avg Occupancy"), v: `${hotel.avg_occupancy} pax/room` } : null,
          ].filter(Boolean)}
        />
      </div>
    </div>
  );
}