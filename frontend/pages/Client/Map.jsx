import { useEffect } from "react";
import { loadLeaflet } from "../../utils/leaflet.js";
import { MAP } from "../../components/mapColors.js";

// Client map — imperative Leaflet app ported from the original client_map
// template. DOM mirrors the original; handlers used by inline elements are
// exposed on window for the lifetime of the page.
export default function ClientMap() {
  useEffect(() => {
    let map = null;
    let disposed = false;
    const exposed = [];
    const expose = (name, fn) => { window[name] = fn; exposed.push(name); };

    loadLeaflet().then((L) => {
      if (disposed) return;

      function _esc(s) { return (s || "").toString().replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
      map = L.map("map", { zoomControl: false }).setView([-2.5, 118], 5);
      L.control.zoom({ position: "bottomright" }).addTo(map);
      function isMobile() { return window.innerWidth <= 600; }

      function fixMapHeight() {
        if (!isMobile()) return;
        const h = window.visualViewport ? window.visualViewport.height : window.innerHeight;
        document.getElementById("map-wrap").style.height = h + "px";
        map.invalidateSize();
      }
      if (window.visualViewport) window.visualViewport.addEventListener("resize", fixMapHeight);
      fixMapHeight();

      function openSheet(html) {
        document.getElementById("map-sheet-body").innerHTML = html;
        document.getElementById("map-sheet").classList.add("open");
        document.getElementById("map-sheet-overlay").classList.add("open");
      }
      const closeSheet = () => {
        document.getElementById("map-sheet").classList.remove("open");
        document.getElementById("map-sheet-overlay").classList.remove("open");
      };
      map.on("click", () => { if (isMobile()) closeSheet(); });

      function getTileUrl() {
        const theme = document.documentElement.getAttribute("data-theme");
        return "https://{s}.basemaps.cartocdn.com/" + (theme === "light" ? "light_all" : "dark_all") + "/{z}/{x}/{y}{r}.png";
      }
      const tileLayer = L.tileLayer(getTileUrl(), { attribution: "© OpenStreetMap © CartoDB", subdomains: "abcd", maxZoom: 19 }).addTo(map);
      const themeObserver = new MutationObserver(() => tileLayer.setUrl(getTileUrl()));
      themeObserver.observe(document.documentElement, { attributeFilter: ["data-theme"] });

      let allClients = [];
      let markers = [];
      const COLORS = { ok: MAP.green, medium: MAP.yellow, high: MAP.red, dormant: MAP.none };

      function makeIcon(risk, score) {
        const color = COLORS[risk] || COLORS.ok;
        const size = Math.max(10, Math.min(22, 10 + score / 8));
        return L.divIcon({ className: "", html: '<div style="width:' + size + "px;height:" + size + "px;border-radius:50%;background:" + color + ';border:2px solid rgba(255,255,255,.35);box-shadow:0 0 7px ' + color + '66;"></div>', iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
      }
      const fmtNum = (n) => (n ? n.toLocaleString() + " SAR" : "—");

      function renderMarkers(clients) {
        markers.forEach((m) => map.removeLayer(m));
        markers = [];
        clients.forEach((c) => {
          const m = L.marker([c.lat, c.lng], { icon: makeIcon(c.risk, c.score) });
          const waBtn = c.wa ? '<a href="https://wa.me/' + _esc(c.wa) + '" target="_blank" class="pop-btn pop-btn-wa">WhatsApp</a>' : "";
          const popHtml =
            '<div class="pop-name">' + _esc(c.name) + "</div>" +
            '<div class="pop-city">' + _esc(c.city || "") + (c.province ? ", " + _esc(c.province) : "") + "</div>" +
            '<div class="pop-row"><span class="pop-label">Outstanding</span><span class="pop-val ' + (c.outstanding > 0 ? "red" : "green") + '">' + fmtNum(c.outstanding) + "</span></div>" +
            '<div class="pop-row"><span class="pop-label">Total Billed</span><span class="pop-val">' + fmtNum(c.total_billed) + "</span></div>" +
            '<div class="pop-row"><span class="pop-label">Score</span><span class="pop-val">' + _esc(String(c.score)) + "/100</span></div>" +
            (c.pic ? '<div class="pop-row"><span class="pop-label">PIC</span><span class="pop-val">' + _esc(c.pic) + "</span></div>" : "") +
            '<div class="pop-actions"><a href="' + c.url + '" class="pop-btn pop-btn-detail">Detail →</a>' + waBtn + "</div>";
          if (isMobile()) m.on("click", (e) => { L.DomEvent.stopPropagation(e); openSheet(popHtml); });
          else m.bindPopup(popHtml);
          m.addTo(map);
          markers.push(m);
        });
      }

      const setFilter = (f, btn) => {
        document.querySelectorAll(".map-filter button").forEach((b) => b.classList.remove("active"));
        if (btn) btn.classList.add("active");
        let filtered = allClients;
        if (f === "risk") filtered = allClients.filter((c) => c.risk === "high" || c.risk === "medium");
        if (f === "outstanding") filtered = allClients.filter((c) => c.outstanding > 0);
        if (f === "dormant") filtered = allClients.filter((c) => c.risk === "dormant");
        renderMarkers(filtered);
      };

      expose("setFilter", setFilter);
      expose("closeSheet", closeSheet);

      fetch("/clients/map/data/")
        .then((r) => r.json())
        .then((data) => {
          if (disposed) return;
          allClients = data.clients;
          renderMarkers(allClients);
          if (allClients.length === 0) {
            map.setView([-2.5, 118], 5);
          } else if (allClients.length > 1) {
            const lats = allClients.map((c) => c.lat);
            const lngs = allClients.map((c) => c.lng);
            map.fitBounds([[Math.min(...lats), Math.min(...lngs)], [Math.max(...lats), Math.max(...lngs)]], { padding: [50, 50], maxZoom: 11 });
          } else {
            map.setView([allClients[0].lat, allClients[0].lng], 11);
          }
        });

      window.__clientMapCleanup = () => { themeObserver.disconnect(); if (window.visualViewport) window.visualViewport.removeEventListener("resize", fixMapHeight); };
    });

    return () => {
      disposed = true;
      exposed.forEach((n) => { delete window[n]; });
      if (window.__clientMapCleanup) { window.__clientMapCleanup(); delete window.__clientMapCleanup; }
      if (map) map.remove();
    };
  }, []);

  return (
    <div id="map-wrap">
      <style>{CSS}</style>
      <div id="map" />

      <div className="map-filter">
        <a href="/clients/" className="map-back-btn" title="Back to client list">
          <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
        </a>
        <button className="active" data-filter="all" onClick={(e) => window.setFilter?.("all", e.currentTarget)}>All</button>
        <button data-filter="risk" onClick={(e) => window.setFilter?.("risk", e.currentTarget)}>Risk</button>
        <button data-filter="outstanding" onClick={(e) => window.setFilter?.("outstanding", e.currentTarget)}>Outstanding</button>
        <button data-filter="dormant" onClick={(e) => window.setFilter?.("dormant", e.currentTarget)}>Dormant</button>
      </div>

      <div className="map-legend">
        <div className="leg-title">Status</div>
        <div className="leg-row"><div className="leg-dot" style={{ background: "var(--green)" }} /> OK / Paid</div>
        <div className="leg-row"><div className="leg-dot" style={{ background: "var(--yellow)" }} /> Outstanding</div>
        <div className="leg-row"><div className="leg-dot" style={{ background: "var(--red)" }} /> High Risk</div>
        <div className="leg-row"><div className="leg-dot" style={{ background: "var(--text-3)" }} /> Dormant</div>
      </div>

      <div id="map-sheet-overlay" className="map-sheet-overlay" onClick={() => window.closeSheet?.()} />
      <div id="map-sheet" className="map-sheet">
        <div className="map-sheet-handle" onClick={() => window.closeSheet?.()} />
        <div id="map-sheet-body" className="map-sheet-body" />
      </div>
    </div>
  );
}

const CSS = `
@media (max-width: 600px) { .m-topbar { display: none !important; } }
#map-wrap { position: relative; height: calc(100vh - 48px); overflow: hidden; }
#map { position: absolute; inset: 0; isolation: isolate; }
.map-filter { position: absolute; top: 12px; left: 12px; z-index: var(--z-overlay); display: flex; gap: 6px; flex-wrap: wrap; max-width: calc(100% - 24px); }
.map-filter button { height: 34px; padding: 0 14px; border-radius: 18px; font-size: 12px; font-weight: 600; border: 1px solid var(--border-2); background: rgba(20,20,23,.9); background: color-mix(in srgb, var(--surface) 90%, transparent); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); color: var(--text-2); cursor: pointer; font-family: inherit; transition: all .12s; white-space: nowrap; }
.map-filter button:hover { color: var(--text); border-color: var(--text-3); }
.map-filter button.active { background: var(--accent-muted); color: var(--accent); border-color: var(--accent); }
.map-back-btn { display: none; align-items: center; justify-content: center; width: 30px; height: 34px; flex-shrink: 0; background: none; border: none; color: var(--text-2); text-decoration: none; transition: color .15s; }
.map-back-btn:hover { color: var(--text); }
@media (max-width: 600px) { .map-back-btn { display: flex; } }
.map-legend { position: absolute; bottom: 20px; left: 12px; z-index: var(--z-overlay); background: rgba(20,20,23,.85); background: color-mix(in srgb, var(--surface) 85%, transparent); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid var(--border); border-radius: 10px; padding: 10px 14px; font-size: 12px; }
.leg-title { font-size: 10px; font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase; color: var(--text-3); margin-bottom: 7px; }
.leg-row { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; color: var(--text-2); }
.leg-row:last-child { margin-bottom: 0; }
.leg-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.leaflet-control-zoom { border: none !important; box-shadow: none !important; }
.leaflet-control-zoom-in, .leaflet-control-zoom-out { width: 30px !important; height: 30px !important; line-height: 28px !important; font-size: 17px !important; font-weight: 600 !important; background: rgba(20,20,23,.9) !important; background: color-mix(in srgb, var(--surface) 90%, transparent) !important; backdrop-filter: blur(8px); border: 1px solid var(--border-2) !important; color: var(--text-2) !important; display: block !important; text-align: center !important; transition: background .15s, color .15s, border-color .15s !important; border-radius: 8px !important; }
.leaflet-control-zoom-in { margin-bottom: 4px !important; }
.leaflet-control-zoom-in:hover, .leaflet-control-zoom-out:hover { background: var(--accent-muted) !important; border-color: var(--accent) !important; color: var(--accent) !important; }
.leaflet-popup-content-wrapper { background: var(--surface); border: 1px solid var(--border-2); border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,.45); color: var(--text); }
.leaflet-popup-tip { background: var(--surface); }
.leaflet-popup-content { margin: 14px 16px; min-width: 190px; }
.pop-name { font-size: 14px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
.pop-city { font-size: 12px; color: var(--text-3); margin-bottom: 10px; }
.pop-row { display: flex; justify-content: space-between; align-items: center; font-size: 12px; margin-bottom: 5px; }
.pop-label { color: var(--text-3); font-size: 11px; }
.pop-val { font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
.pop-val.red { color: var(--red); }
.pop-val.green { color: var(--green); }
.pop-actions { display: flex; gap: 6px; margin-top: 12px; }
.pop-btn { flex: 1; padding: 7px 8px; border-radius: 8px; font-size: 12px; font-weight: 600; text-align: center; text-decoration: none; border: none; cursor: pointer; font-family: inherit; transition: filter .12s; }
.pop-btn:hover { filter: brightness(1.08); }
.pop-btn-detail { background: var(--accent); color: #fff; }
.pop-btn-wa { background: var(--green-muted); color: var(--green); }
.leaflet-tooltip { background: var(--surface-2) !important; border: 1px solid var(--border-2) !important; color: var(--text) !important; border-radius: 6px !important; }
.leaflet-tooltip::before { display: none !important; }
@media (max-width: 600px) {
  html, body { overflow: hidden; height: 100%; }
  #map-wrap { position: fixed; inset: 0; height: auto; }
  .leaflet-control-attribution { display: none !important; }
  #bottom-nav { display: none !important; }
  .map-filter { top: 0; left: 0; right: 0; max-width: none; padding: 10px 12px; padding-top: calc(10px + env(safe-area-inset-top)); gap: 6px; flex-wrap: nowrap; overflow-x: auto; background: rgba(20,20,23,.94); background: color-mix(in srgb, var(--surface) 94%, transparent); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); border-bottom: 1px solid var(--border); -ms-overflow-style: none; scrollbar-width: none; }
  .map-filter::-webkit-scrollbar { display: none; }
  .map-legend { bottom: 16px; }
  .leaflet-bottom.leaflet-right { top: 64px !important; bottom: auto !important; right: 12px !important; }
}
.map-sheet { display: none; position: absolute; bottom: 0; left: 0; right: 0; background: rgba(20,20,23,.98); background: color-mix(in srgb, var(--surface) 98%, transparent); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border: 1px solid var(--border); border-bottom: none; border-top-left-radius: 18px; border-top-right-radius: 18px; z-index: var(--z-dropdown); transform: translateY(110%); transition: transform .3s cubic-bezier(.32,.72,0,1); box-shadow: 0 -10px 36px rgba(0,0,0,.4); padding-bottom: env(safe-area-inset-bottom); }
.map-sheet.open { transform: translateY(0); }
.map-sheet-handle { width: 40px; height: 5px; background: var(--border-2); border-radius: 3px; margin: 10px auto 4px; cursor: pointer; }
.map-sheet-body { padding: 6px 20px 24px; }
.map-sheet-overlay { display: none; position: absolute; inset: 0; z-index: var(--z-base); background: rgba(0,0,0,.35); }
.map-sheet-overlay.open { display: block; }
@media (max-width: 600px) { .map-sheet { display: block; } }
`;
