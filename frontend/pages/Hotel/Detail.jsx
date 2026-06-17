import { useEffect, useRef, useState } from "react";
import { loadLeaflet } from "../../utils/leaflet.js";

function distClass(d) {
  if (d === null || d === undefined) return "";
  if (d < 500) return "ht-green";
  if (d < 1500) return "ht-yellow";
  return "ht-red";
}

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
      const color = d === null ? "#5A5A6A" : d < 500 ? "#26C281" : d < 1500 ? "#F0A429" : "#E5534B";

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

      L.marker(refLL, { icon: dot("#F0A429", 12) }).bindTooltip(hotel.ref_label).addTo(map);
      if (hotel.city !== "madinah") {
        L.marker([21.4225, 39.8262], { icon: dot("#E5534B", 10) }).bindTooltip("Masjid Al-Haram").addTo(map);
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

  return <div ref={ref} id="mini-map" style={{ height: 460, borderRadius: "0 0 var(--r-lg) var(--r-lg)", overflow: "hidden" }} />;
}

function RoomCalculator({ avg }) {
  const [jamaah, setJamaah] = useState(35);
  const rooms = jamaah > 0 ? Math.ceil(jamaah / avg) : "—";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="field">
        <label>Jumlah Jamaah</label>
        <input type="number" min="1" value={jamaah} onChange={(e) => setJamaah(parseInt(e.target.value) || 0)} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 16px", background: "var(--surface-2)", borderRadius: "var(--r-lg)" }}>
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1.5, textTransform: "uppercase", color: "var(--text-3)" }}>Kamar Dibutuhkan</div>
          <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 3 }}>avg {avg} org/kamar</div>
        </div>
        <div style={{ fontSize: 32, fontWeight: 700, color: "var(--accent-2)", fontVariantNumeric: "tabular-nums" }}>{rooms}</div>
      </div>
    </div>
  );
}

export default function Detail({ hotel }) {
  const hasCoords = hotel.lat != null && hotel.lng != null;
  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title">{hotel.name}</div>
        <div>{hotel.is_active ? <span className="badge badge-green">Aktif</span> : <span className="badge badge-gray">Nonaktif</span>}</div>
      </div>

      <div className="detail-grid-eq">
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card" style={{ marginBottom: 0 }}>
            <div className="card-header"><span className="card-title">Info</span></div>
            <div className="card-body" style={{ padding: "0 20px" }}>
              <div className="ht-row"><span className="ht-key">Kota</span><span className="ht-val">{hotel.city_display}</span></div>
              {hotel.area && <div className="ht-row"><span className="ht-key">Area</span><span className="ht-val">{hotel.area}</span></div>}
              <div className="ht-row"><span className="ht-key">Bintang</span><span className="ht-val" style={{ color: "var(--yellow)", fontWeight: 600 }}>{hotel.stars}★</span></div>
              <div className="ht-row"><span className="ht-key">Jarak</span><span className={"ht-val ht-dist " + distClass(hotel.distance)}>{hotel.distance_label}</span></div>
              <div className="ht-row"><span className="ht-key">Avg/Kamar</span><span className="ht-val">{hotel.avg_occupancy ? `${hotel.avg_occupancy} org` : <span style={{ color: "var(--text-3)" }}>—</span>}</span></div>
              {hotel.note ? <div className="ht-row" style={{ borderBottom: "none" }}><span className="ht-key">Catatan</span><span className="ht-val" style={{ whiteSpace: "pre-wrap" }}>{hotel.note}</span></div> : <div style={{ height: 8 }} />}
            </div>
          </div>

          <div className="card" style={{ marginBottom: 0 }}>
            <div className="card-header"><span className="card-title">Kalkulator Kamar</span></div>
            <div className="card-body">
              {hotel.avg_occupancy
                ? <RoomCalculator avg={hotel.avg_occupancy} />
                : <div className="empty" style={{ padding: 28 }}><div className="empty-title">Hotel ini tidak memiliki average</div></div>}
            </div>
          </div>
        </div>

        {hasCoords ? (
          <div className="card" style={{ marginBottom: 0, position: "sticky", top: 16 }}>
            <div className="card-header">
              <span className="card-title">Lokasi</span>
              <a href="/hotels/map/" className="btn btn-ghost btn-sm">Peta Lengkap</a>
            </div>
            <HotelMiniMap hotel={hotel} />
          </div>
        ) : (
          <div className="card" style={{ marginBottom: 0 }}>
            <div className="card-body">
              <div className="empty" style={{ padding: 48 }}>
                <div className="empty-title">Koordinat belum diset</div>
                <div className="empty-sub">Tambahkan koordinat di halaman edit</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
