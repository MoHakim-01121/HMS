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
