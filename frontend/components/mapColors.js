// Hex colors for Leaflet map markers. Leaflet renders its markers outside the CSS
// cascade (inline SVG / divIcon HTML), so it can't read CSS variables — these values
// mirror the design tokens by hex so maps stay consistent with the rest of the app.
export const MAP = {
  none:   "#4E4E5A", // --text-3
  green:  "#2ECC71", // --green
  yellow: "#F5A623", // --yellow
  red:    "#FF453A", // --red
  accent: "#FF6C37", // --accent
};

// Distance-to-landmark color bands, shared by all hotel/client maps so the
// scale is identical everywhere (previously each map redefined its own hex).
export function distColor(d) {
  if (d === null || d === undefined) return MAP.none;
  if (d < 500) return MAP.green;
  if (d < 1500) return MAP.yellow;
  return MAP.red;
}
