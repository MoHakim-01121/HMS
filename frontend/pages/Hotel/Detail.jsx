import { useEffect, useRef, useState } from "react";
import { loadLeaflet } from "../../utils/leaflet.js";
import { distColor, MAP } from "../../components/mapColors.js";
import DetailHero from "../../components/detail/DetailHero.jsx";
import FloatCard from "../../components/detail/FloatCard.jsx";
import Section from "../../components/detail/Section.jsx";

function haversine(lat1, lng1, lat2, lng2) {
  const R = 6371000, p1 = lat1 * Math.PI / 180, p2 = lat2 * Math.PI / 180;
  const dLat = (lat2 - lat1) * Math.PI / 180, dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}
const fmtDist = (m) => (m < 1000 ? Math.round(m) + " m" : (m / 1000).toFixed(2) + " km");

// Leaflet mini-map ported from hotel_detail.html.
function HotelMiniMap({ hotel }) {
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

      const tileUrl = () => {
        const theme = document.documentElement.getAttribute("data-theme");
        return "https://{s}.basemaps.cartocdn.com/" + (theme === "light" ? "light_all" : "dark_all") + "/{z}/{x}/{y}{r}.png";
      };
      const tileLayer = L.tileLayer(tileUrl(), { attribution: "© OpenStreetMap © CartoDB", subdomains: "abcd", maxZoom: 19 }).addTo(map);
      observer = new MutationObserver(() => tileLayer.setUrl(tileUrl()));
      observer.observe(document.documentElement, { attributeFilter: ["data-theme"] });

      const routeTip = L.tooltip({ permanent: false, opacity: 1, className: "route-dist-tip", direction: "top", offset: [0, -8] });
      const dot = (c, sz) => L.divIcon({ className: "", html: `<div style="width:${sz}px;height:${sz}px;border-radius:50%;background:${c};border:2px solid #fff;box-shadow:0 0 6px ${c}99;"></div>`, iconSize: [sz, sz], iconAnchor: [sz / 2, sz / 2] });

      L.marker(refLL, { icon: dot(MAP.yellow, 12) }).bindTooltip(hotel.ref_label).addTo(map);
      if (hotel.city !== "madinah") {
        L.marker([21.4225, 39.8262], { icon: dot(MAP.red, 10) }).bindTooltip("Masjid Al-Haram").addTo(map);
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
  const [jamaah, setJamaah] = useState(35);
  const rooms = jamaah > 0 ? Math.ceil(jamaah / avg) : "—";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="field">
        <label>Number of Pilgrims</label>
        <input type="number" min="1" value={jamaah} onChange={(e) => setJamaah(parseInt(e.target.value) || 0)} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 16px", background: "var(--surface-2)", borderRadius: "var(--r-lg)" }}>
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1.5, textTransform: "uppercase", color: "var(--text-3)" }}>Rooms Needed</div>
          <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 3 }}>avg {avg} pax/room</div>
        </div>
        <div style={{ fontSize: 32, fontWeight: 700, color: "var(--accent-2)", fontVariantNumeric: "tabular-nums" }}>{rooms}</div>
      </div>
    </div>
  );
}

export default function Detail({ hotel }) {
  const hasCoords = hotel.lat != null && hotel.lng != null;
  const distStyle =
    hotel.distance == null ? undefined :
    hotel.distance < 500 ? { color: "var(--green)" } :
    hotel.distance < 1500 ? { color: "var(--yellow)" } : { color: "var(--red)" };
  const subLines = [];
  if (hotel.stars) subLines.push(`${hotel.stars}★ hotel`);
  if (hotel.avg_occupancy) subLines.push(`Avg ${hotel.avg_occupancy} pax/room`);
  return (
    <div className="page dv-page">
      <a href="/hotels/" className="page-back">
        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 12H5m7-7l-7 7 7 7" />
        </svg>
        Back
      </a>

      <DetailHero
        kicker="Hotel"
        title={hotel.name}
        sub={`${hotel.city_display}${hotel.area ? `, ${hotel.area}` : ""}`}
        pill={hotel.is_active ? { label: "Active", tone: "green" } : { label: "Inactive", tone: "gray" }}
        menuItems={[{ label: "Edit", href: `/hotels/${hotel.id}/edit/` }]}
      />

      <FloatCard
        right={
          hotel.distance_label ? (
            <div className="dv-amtbox">
              <div className="dv-l">Distance</div>
              <div className="dv-amtbox-num" style={{ fontSize: 19, ...distStyle }}>{hotel.distance_label}</div>
            </div>
          ) : null
        }
      >
        <div className="dv-l">Info</div>
        <div className="dv-float-name">{hotel.city_display}{hotel.area ? `, ${hotel.area}` : ""}</div>
        {subLines.length ? (
          <div className="dv-item-sub">
            {subLines.map((l, i) => <span key={i}>{i > 0 ? <br /> : null}{l}</span>)}
          </div>
        ) : null}
      </FloatCard>

      <div className="dv-body">
      <Section label="Room Calculator">
        <div style={{ marginTop: 10 }}>
          {hotel.avg_occupancy
            ? <RoomCalculator avg={hotel.avg_occupancy} />
            : <div className="dv-empty">This hotel has no average set</div>}
        </div>
      </Section>

      <Section
        label="Location"
        action={hasCoords ? <a className="dv-sec-action" href="/hotels/map/">Full Map</a> : null}
      >
        {hasCoords ? (
          <div style={{ marginTop: 10, borderRadius: 14, overflow: "hidden", border: "1px solid var(--border)" }}>
            <HotelMiniMap hotel={hotel} />
          </div>
        ) : (
          <div className="dv-empty">Coordinates not set yet. Add coordinates on the edit page.</div>
        )}
      </Section>

      {hotel.note ? (
        <Section label="Notes">
          <div className="dv-item-sub" style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{hotel.note}</div>
        </Section>
      ) : null}
      </div>
    </div>
  );
}
