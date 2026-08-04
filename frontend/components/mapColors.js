// Hex colors for Leaflet map markers. Leaflet renders its markers outside the CSS
// cascade (inline SVG / divIcon HTML), so it can't read CSS variables — these values
// mirror the design tokens by hex so maps stay consistent with the rest of the app.
export const MAP = {
  none:   "#4E4E5A", // --text-3
  green:  "#2ECC71", // --green
  yellow: "#F5A623", // --yellow
  red:    "#FF453A", // --red
  accent: "#1A1A1A", // --accent (monochrome brand, Homlu direction — static hex since Leaflet can't read CSS vars)
};

// Distance-to-landmark color bands, shared by all hotel/client maps so the
// scale is identical everywhere (previously each map redefined its own hex).
export function distColor(d) {
  if (d === null || d === undefined) return MAP.none;
  if (d < 500) return MAP.green;
  if (d < 1500) return MAP.yellow;
  return MAP.red;
}

// Gradual concentration gradient: black (no bookings) -> yellow (medium) ->
// green (most bookings). Interpolates t in [0,1] along the two stops so the
// dashboard heat map and the client map share the exact same scale.
export const HEAT = {
  none: "#000000",
  mid: MAP.yellow,
  peak: MAP.green,
};

function hexToRgb(h) { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function rgbToHex(r, g, b) { return "#" + ((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1); }

export function heatColor(t) {
  t = Math.max(0, Math.min(1, t));
  const a = t < 0.5 ? hexToRgb(HEAT.none) : hexToRgb(HEAT.mid);
  const b = t < 0.5 ? hexToRgb(HEAT.mid) : hexToRgb(HEAT.peak);
  const k = t < 0.5 ? t * 2 : (t - 0.5) * 2;
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * k));
  return rgbToHex(c[0], c[1], c[2]);
}
