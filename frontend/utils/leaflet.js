// Lazily inject Leaflet from the CDN (same version the Django pages use) and
// resolve with window.L. Avoids bundling Leaflet into the main JS for a feature
// used on only a couple of pages.
let promise = null;

export function loadLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  if (promise) return promise;
  promise = new Promise((resolve, reject) => {
    if (!document.querySelector('link[data-leaflet]')) {
      const css = document.createElement("link");
      css.rel = "stylesheet";
      css.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      css.setAttribute("data-leaflet", "");
      document.head.appendChild(css);
    }
    const s = document.createElement("script");
    s.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
    s.onload = () => resolve(window.L);
    s.onerror = reject;
    document.head.appendChild(s);
  });
  return promise;
}

// Keyless basemap tiles. CARTO's basemaps.cartocdn.com began serving an
// "API KEY REQUIRED" watermark tile in 2026; Esri's World Gray Canvas is the
// closest keyless look-alike — a muted dark/light base that lets the markers
// carry the map. Esri serves z/y/x (not z/x/y) and tops out at native z16.
export function basemapUrl(theme) {
  const style = theme === "light" ? "World_Light_Gray_Base" : "World_Dark_Gray_Base";
  return `https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/${style}/MapServer/tile/{z}/{y}/{x}`;
}

export const basemapOptions = { attribution: "© Esri", maxZoom: 19, maxNativeZoom: 16 };
