import { useEffect } from "react";
import { loadLeaflet } from "../../utils/leaflet.js";
import { fetchJson } from "../../utils/fetchJson.js";
import { MAP, heatColor } from "../../components/mapColors.js";

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

      // Purchase volume aggregated per city, so areas with the most purchases
      // (e.g. Jogja, Surabaya) turn green, scaling down gradually through yellow
      // to black for cities with no purchases. Scale is fixed to all clients so
      // colors stay stable while filtering.
      const cityKey = (c) => ((c.city || "").trim().toLowerCase() || "other");

      function makeIcon(color, size) {
        return L.divIcon({ className: "", html: '<div style="width:' + size + "px;height:" + size + "px;border-radius:50%;background:" + color + ';border:2px solid rgba(255,255,255,.4);box-shadow:0 0 8px ' + color + '66;"></div>', iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
      }
      const fmtNum = (n) => (n ? n.toLocaleString() + " SAR" : "—");

      function renderMarkers(clients) {
        markers.forEach((m) => map.removeLayer(m));
        markers = [];
        const totals = {};
        allClients.forEach((c) => { const k = cityKey(c); totals[k] = (totals[k] || 0) + (c.total_billed || 0); });
        const maxTotal = Math.max(0, ...Object.values(totals));
        clients.forEach((c) => {
          const t = maxTotal > 0 ? (totals[cityKey(c)] || 0) / maxTotal : 0;
          const size = Math.max(10, Math.min(22, 10 + (c.score || 0) / 8));
          const m = L.marker([c.lat, c.lng], { icon: makeIcon(heatColor(t), size) });
          const waBtn = c.wa ? '<a href="https://wa.me/' + _esc(c.wa) + '" target="_blank" class="pop-btn pop-btn-wa">WhatsApp</a>' : "";
          const scoreNum = Number(c.score) || 0;
          const scoreColor = scoreNum >= 70 ? "var(--green)" : scoreNum >= 40 ? "var(--yellow)" : "var(--red)";
          const riskColor = c.risk === "high" ? "var(--red)" : c.risk === "medium" ? "var(--yellow)" : c.risk === "dormant" ? "var(--muted-foreground)" : "var(--green)";
          const riskLabel = c.risk === "high" ? "High Risk" : c.risk === "medium" ? "Watchlist" : c.risk === "dormant" ? "Dormant" : "Active";
          const popHtml =
            '<div class="pop-dossier">' +
              '<div class="pop-dossier-head">' +
                '<span class="pop-dossier-tag">Client</span>' +
                '<div class="pop-dossier-name">' + _esc(c.name) + "</div>" +
                '<div class="pop-dossier-loc">' + _esc(c.city || "—") + (c.province ? ", " + _esc(c.province) : "") + "</div>" +
              "</div>" +
              '<div class="pop-dossier-body">' +
                '<div class="pop-dossier-item"><span class="pop-dossier-key">Status</span><span class="pop-dossier-val"><span class="pop-dot" style="background:' + riskColor + '"></span>' + _esc(riskLabel) + "</span></div>" +
                '<div class="pop-dossier-item"><span class="pop-dossier-key">Outstanding</span><span class="pop-dossier-val ' + (c.outstanding > 0 ? "is-red" : "is-green") + '">' + fmtNum(c.outstanding) + "</span></div>" +
                '<div class="pop-dossier-item"><span class="pop-dossier-key">Total billed</span><span class="pop-dossier-val">' + fmtNum(c.total_billed) + "</span></div>" +
                '<div class="pop-dossier-item"><span class="pop-dossier-key">Score</span><span class="pop-dossier-val">' + scoreNum + "/100</span></div>" +
                (c.pic ? '<div class="pop-dossier-item"><span class="pop-dossier-key">PIC</span><span class="pop-dossier-val">' + _esc(c.pic) + "</span></div>" : "") +
                '<div class="pop-dossier-track"><span class="pop-dossier-track-fill" style="width:' + Math.max(0, Math.min(100, scoreNum)) + "%;background:" + scoreColor + '"></span></div>' +
              "</div>" +
              '<div class="pop-actions">' +
                '<a href="' + c.url + '" class="pop-btn pop-btn-solid">Detail</a>' + waBtn +
              "</div>" +
            "</div>";
          if (isMobile()) m.on("click", (e) => { L.DomEvent.stopPropagation(e); openSheet(popHtml); });
          else {
            m.bindTooltip(_esc(c.name), { direction: "top", offset: [0, -Math.ceil(size / 2) - 8], opacity: 1, className: "map-tip" });
            m.bindPopup(popHtml);
          }
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

      fetchJson("/clients/map/data/")
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
        <div className="leg-title">Purchase volume</div>
        <div className="leg-gradient" style={{ background: "linear-gradient(90deg, #000000, " + MAP.yellow + ", " + MAP.green + ")" }} />
        <div className="leg-labels"><span>Low</span><span>High</span></div>
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
#map-wrap { position: relative; height: calc(100vh - var(--topbar-h, 56px)); overflow: hidden; }
#map { position: absolute; inset: 0; isolation: isolate; }
.map-filter { position: absolute; top: 12px; left: 12px; z-index: var(--z-overlay); display: flex; gap: 6px; flex-wrap: wrap; max-width: calc(100% - 24px); }
.map-filter button { height: 34px; padding: 0 14px; border-radius: 999px; font-size: 12px; font-weight: 500; border: 1px solid var(--border); background: var(--card); color: var(--muted-foreground); cursor: pointer; font-family: inherit; transition: background .12s, color .12s, border-color .12s; white-space: nowrap; }
.map-filter button:hover { color: var(--foreground); border-color: var(--foreground); }
.map-filter button.active { background: var(--secondary); color: var(--foreground); border-color: var(--foreground); }
.map-back-btn { display: flex; align-items: center; justify-content: center; width: 34px; height: 34px; flex-shrink: 0; background: var(--card); border: 1px solid var(--border); border-radius: 999px; color: var(--muted-foreground); text-decoration: none; transition: color .15s, border-color .15s; }
.map-back-btn:hover { color: var(--foreground); border-color: var(--foreground); }
.map-legend { position: absolute; bottom: 20px; left: 12px; z-index: var(--z-overlay); background: color-mix(in srgb, var(--popover) 88%, transparent); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid var(--border); border-radius: 12px; padding: 10px 14px; font-size: 12px; }
.leg-title { font-size: 10px; font-weight: 600; letter-spacing: .12em; text-transform: uppercase; color: var(--muted-foreground); margin-bottom: 7px; }
.leg-gradient { height: 8px; border-radius: 4px; margin: 2px 0 4px; }
.leg-labels { display: flex; justify-content: space-between; color: var(--muted-foreground); font-size: 10px; }
.leaflet-control-zoom { border: none !important; box-shadow: none !important; }
.leaflet-control-zoom-in, .leaflet-control-zoom-out { width: 30px !important; height: 30px !important; line-height: 28px !important; font-size: 17px !important; font-weight: 600 !important; background: var(--card) !important; border: 1px solid var(--border) !important; color: var(--muted-foreground) !important; display: block !important; text-align: center !important; transition: background .15s, color .15s, border-color .15s !important; border-radius: 8px !important; }
.leaflet-control-zoom-in { margin-bottom: 4px !important; }
.leaflet-control-zoom-in:hover, .leaflet-control-zoom-out:hover { background: var(--secondary) !important; border-color: var(--foreground) !important; color: var(--foreground) !important; }
.leaflet-popup-content-wrapper { background: var(--popover); border: 1px solid var(--border); border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,.45); color: var(--foreground); }
.leaflet-popup-tip { background: var(--popover); }
.leaflet-popup-content { margin: 14px 16px; min-width: 224px; }
.pop-dossier-head { padding-bottom: 10px; border-bottom: 1px solid var(--border); }
.pop-dossier-tag { display: block; font-size: 10px; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; color: var(--muted-foreground); margin-bottom: 4px; }
.pop-dossier-name { font-size: 15px; font-weight: 700; color: var(--foreground); line-height: 1.3; letter-spacing: -0.01em; }
.pop-dossier-loc { font-size: 12px; color: var(--muted-foreground); margin-top: 2px; }
.pop-dossier-body { margin: 6px 0 2px; }
.pop-dossier-item { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 6px 0; border-bottom: 1px solid var(--border); }
.pop-dossier-key { font-family: var(--font-mono); font-size: 10px; font-weight: 500; letter-spacing: .12em; text-transform: uppercase; color: var(--muted-foreground); }
.pop-dossier-val { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; color: var(--foreground); font-variant-numeric: tabular-nums; white-space: nowrap; }
.pop-dossier-val.is-red { color: var(--red); }
.pop-dossier-val.is-green { color: var(--green); }
.pop-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.pop-dossier-track { height: 3px; background: var(--secondary); border-radius: 2px; margin-top: 8px; overflow: hidden; }
.pop-dossier-track-fill { display: block; height: 100%; border-radius: 2px; }
.pop-actions { display: flex; gap: 8px; margin-top: 12px; }
.pop-btn { flex: 1; padding: 8px 8px; border-radius: 8px; font-size: 12px; font-weight: 600; text-align: center; text-decoration: none; border: none; cursor: pointer; font-family: inherit; transition: opacity .12s, background .12s, color .12s, border-color .12s; }
.pop-btn-solid { background: var(--primary); color: var(--primary-foreground); }
.pop-btn-solid:hover { opacity: .9; }
.pop-btn-wa { background: transparent; color: var(--muted-foreground); border: 1px solid var(--border); }
.pop-btn-wa:hover { background: var(--secondary); color: var(--foreground); border-color: var(--border); }
.leaflet-tooltip { background: var(--popover) !important; border: 1px solid var(--border) !important; color: var(--foreground) !important; border-radius: 6px !important; }
.leaflet-tooltip::before { display: none !important; }
.map-tip.leaflet-tooltip { background: color-mix(in srgb, var(--popover) 92%, transparent) !important; backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); border: 1px solid var(--border) !important; border-radius: 8px !important; box-shadow: 0 4px 18px rgba(0,0,0,.35); padding: 6px 10px !important; margin: 0 !important; font-size: 12px; font-weight: 600; color: var(--foreground); white-space: nowrap; }
@media (max-width: 600px) {
  html, body { overflow: hidden; height: 100%; }
  #map-wrap { position: fixed; inset: 0; height: auto; }
  .leaflet-control-attribution { display: none !important; }
  #m-bottom-nav { display: none !important; }
  .map-filter { top: 0; left: 0; right: 0; max-width: none; padding: 10px 12px; padding-top: calc(10px + env(safe-area-inset-top)); gap: 6px; flex-wrap: nowrap; overflow-x: auto; background: color-mix(in srgb, var(--popover) 94%, transparent); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); border-bottom: 1px solid var(--border); -ms-overflow-style: none; scrollbar-width: none; }
  .map-filter::-webkit-scrollbar { display: none; }
  .map-legend { bottom: 16px; }
  .leaflet-bottom.leaflet-right { top: 64px !important; bottom: auto !important; right: 12px !important; }
}
.map-sheet { display: none; position: absolute; bottom: 0; left: 0; right: 0; background: color-mix(in srgb, var(--popover) 98%, transparent); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border: 1px solid var(--border); border-bottom: none; border-top-left-radius: 20px; border-top-right-radius: 20px; z-index: var(--z-dropdown); transform: translateY(110%); transition: transform .3s cubic-bezier(.32,.72,0,1); box-shadow: 0 -10px 36px rgba(0,0,0,.4); padding-bottom: env(safe-area-inset-bottom); }
.map-sheet.open { transform: translateY(0); }
.map-sheet-handle { width: 40px; height: 5px; background: var(--border); border-radius: 3px; margin: 10px auto 4px; cursor: pointer; }
.map-sheet-body { padding: 6px 20px 24px; }
.map-sheet-overlay { display: none; position: absolute; inset: 0; z-index: var(--z-base); background: rgba(0,0,0,.35); }
.map-sheet-overlay.open { display: block; }
@media (max-width: 600px) { .map-sheet { display: block; } }
`;
