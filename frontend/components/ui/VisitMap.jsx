import { useEffect, useRef } from "react";
import { loadLeaflet } from "../../utils/leaflet.js";

// Two-pin comparison map: where the Client is on file vs. where the staff
// actually checked in from. Read-only, no filters/heat coloring — that
// richer treatment belongs to Client/Map.jsx, not a single visit's card.
export default function VisitMap({ clientLat, clientLng, checkinLat, checkinLng }) {
  const ref = useRef(null);

  useEffect(() => {
    let map = null;
    let disposed = false;

    loadLeaflet().then((L) => {
      if (disposed || !ref.current) return;
      map = L.map(ref.current, { zoomControl: true, scrollWheelZoom: false });
      L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        attribution: "© OpenStreetMap © CartoDB", subdomains: "abcd", maxZoom: 19,
      }).addTo(map);

      const points = [];
      if (clientLat != null && clientLng != null) {
        L.marker([clientLat, clientLng]).addTo(map).bindPopup("Client");
        points.push([clientLat, clientLng]);
      }
      if (checkinLat != null && checkinLng != null) {
        L.marker([checkinLat, checkinLng]).addTo(map).bindPopup("Check-in");
        points.push([checkinLat, checkinLng]);
      }
      if (points.length === 2) {
        L.polyline(points, { color: "#888", dashArray: "4 4" }).addTo(map);
        map.fitBounds(points, { padding: [30, 30] });
      } else if (points.length === 1) {
        map.setView(points[0], 14);
      } else {
        map.setView([-2.5, 118], 5);
      }
    });

    return () => { disposed = true; if (map) map.remove(); };
  }, [clientLat, clientLng, checkinLat, checkinLng]);

  return <div ref={ref} style={{ height: 220, borderRadius: 12, overflow: "hidden", border: "1px solid var(--border)" }} />;
}
