import { useEffect, useRef } from "react";
import { useForm } from "@inertiajs/react";
import { loadLeaflet, basemapUrl, basemapOptions } from "../../utils/leaflet.js";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { useI18n } from "../../utils/i18n.jsx";

const AREAS = ["Misfalah", "Ajyad", "Ajyad Selatan", "Ajyad Utara", "Syisyah", "Kudai", "Jarwal", "Aziziyah", "Ibrahim Khalil", "Nakasa", "Bakhutmaz"];

// Native, uncontrolled <select> styled to match shadcn's Input/SelectTrigger.
// Kept as a real <select> (not the Radix Select) because the Leaflet effect
// below reads it with document.querySelector('select[name="city"]') and the
// whole form is submitted via `new FormData(formRef.current)` — a Radix
// listbox has no underlying native control for either of those to see.
const SELECT_CLASS = "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-base shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 md:text-sm";

export default function HotelForm({ hotel, edit }) {
  const { t } = useI18n();
  const h = hotel || {};
  const formRef = useRef(null);
  const api = useRef({});
  const form = useForm({});

  const submit = (e) => {
    e.preventDefault();
    const fd = new FormData(formRef.current);
    const data = {};
    fd.forEach((v, k) => { data[k] = v; });
    form.transform(() => data);
    form.post(edit ? `/hotels/${h.id}/edit/` : "/hotels/new/", { forceFormData: true });
  };

  useEffect(() => {
    let map = null;
    let disposed = false;
    loadLeaflet().then((L) => {
      if (disposed) return;
      // ───────────────────────────────────────────────────────────
      // Ported from the original hotel_form route editor (imperative).
      // ───────────────────────────────────────────────────────────
      const HARAM = [21.420324, 39.826485];
      const NABAWI = [24.4672, 39.6112];
      const inpLat = document.getElementById("inp-lat");
      const inpLng = document.getElementById("inp-lng");
      const inpRoute = document.getElementById("inp-route");
      const citySelect = document.querySelector('select[name="city"]');
      const mapWrap = document.getElementById("map-wrap");

      const getRefLL = () => (citySelect.value === "madinah" ? NABAWI : HARAM);

      const initLat = parseFloat(inpLat.value) || HARAM[0];
      const initLng = parseFloat(inpLng.value) || HARAM[1];

      map = L.map("pick-map", { zoomControl: true }).setView([initLat, initLng], 15);
      L.tileLayer(basemapUrl(document.documentElement.getAttribute("data-theme")), basemapOptions).addTo(map);

      const dot = (size, color, glow) => L.divIcon({
        className: "",
        html: '<div style="width:' + size + "px;height:" + size + "px;border-radius:50%;background:" + color + ";border:2px solid #fff;box-shadow:0 0 " + (glow || 6) + "px " + color + '99;"></div>',
        iconSize: [size, size], iconAnchor: [size / 2, size / 2],
      });
      L.marker(HARAM, { icon: dot(14, "#F5A623", 10) }).bindTooltip("Al-Haram Plaza").addTo(map);
      L.marker([21.4225, 39.8262], { icon: dot(10, "#FF453A") }).bindTooltip("Masjid Al-Haram").addTo(map);
      L.marker(NABAWI, { icon: dot(10, "#FF453A") }).bindTooltip("Masjid Nabawi").addTo(map);

      let hotelMarker = null;
      function setHotelMarker(ll) {
        if (hotelMarker) { hotelMarker.setLatLng(ll); return; }
        hotelMarker = L.marker(ll, { icon: dot(12, "#1A1A1A"), draggable: true }).addTo(map);
        hotelMarker.on("dragend", () => {
          const p = hotelMarker.getLatLng();
          inpLat.value = p.lat.toFixed(6);
          inpLng.value = p.lng.toFixed(6);
          refreshRoute();
        });
      }
      if (inpLat.value && inpLng.value) setHotelMarker([parseFloat(inpLat.value), parseFloat(inpLng.value)]);

      let routeMode = false;
      let waypoints = [];
      try { const rv = JSON.parse(inpRoute.value || "null"); waypoints = Array.isArray(rv) ? rv : []; } catch (e) { /* noop */ }

      let routeLayer = null;
      let waypointMarkers = [];
      let midpointMarkers = [];
      let previewLine = null;
      let snapRing = null;
      let suppress = false;
      const suppressNext = () => { suppress = true; setTimeout(() => { suppress = false; }, 60); };

      const haversine = (a, b) => {
        const R = 6371000, dLat = (b[0] - a[0]) * Math.PI / 180, dLng = (b[1] - a[1]) * Math.PI / 180;
        const x = Math.sin(dLat / 2) ** 2 + Math.cos(a[0] * Math.PI / 180) * Math.cos(b[0] * Math.PI / 180) * Math.sin(dLng / 2) ** 2;
        return R * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
      };
      const routeDist = (wps) => { let dist = 0; for (let i = 0; i < wps.length - 1; i++) dist += haversine(wps[i], wps[i + 1]); return dist; };

      function makeVertexIcon(idx, total) {
        const isEnd = idx === 0 || idx === total - 1;
        const s = isEnd ? 12 : 8;
        const color = idx === 0 ? "#2ECC71" : idx === total - 1 ? "#F5A623" : "#1A1A1A";
        const ring = isEnd ? '<div style="position:absolute;width:20px;height:20px;border-radius:50%;background:' + color + '22;pointer-events:none;"></div>' : "";
        return L.divIcon({
          className: "",
          html: '<div style="width:28px;height:28px;display:flex;align-items:center;justify-content:center;cursor:grab;position:relative;">' + ring + '<div style="width:' + s + "px;height:" + s + "px;border-radius:50%;background:" + color + ";border:2px solid #fff;box-shadow:0 0 6px " + color + 'CC;pointer-events:none;position:relative;"></div></div>',
          iconSize: [28, 28], iconAnchor: [14, 14],
        });
      }
      const makeMidIcon = () => L.divIcon({
        className: "",
        html: '<div style="width:24px;height:24px;display:flex;align-items:center;justify-content:center;cursor:cell;"><div style="width:7px;height:7px;border-radius:50%;background:rgba(255,255,255,.25);border:1.5px solid rgba(255,255,255,.6);box-shadow:0 1px 5px rgba(0,0,0,.5);pointer-events:none;"></div></div>',
        iconSize: [24, 24], iconAnchor: [12, 12],
      });

      function refreshRoute() {
        if (routeLayer) { map.removeLayer(routeLayer); routeLayer = null; }
        waypointMarkers.forEach((m) => map.removeLayer(m)); waypointMarkers = [];
        midpointMarkers.forEach((m) => map.removeLayer(m)); midpointMarkers = [];
        if (waypoints.length < 2) { updateRouteUI(); return; }
        routeLayer = L.polyline(waypoints, { color: "#1A1A1A", weight: 3, opacity: 0.9, dashArray: "8,6", lineCap: "round", lineJoin: "round" }).addTo(map);
        if (routeMode) {
          for (let j = 0; j < waypoints.length - 1; j++) {
            ((si) => {
              const mLat = (waypoints[si][0] + waypoints[si + 1][0]) / 2;
              const mLng = (waypoints[si][1] + waypoints[si + 1][1]) / 2;
              const mm = L.marker([mLat, mLng], { icon: makeMidIcon(), interactive: true, zIndexOffset: -10 });
              mm.on("click", (e) => {
                L.DomEvent.stopPropagation(e); suppressNext();
                waypoints.splice(si + 1, 0, [parseFloat(mLat.toFixed(6)), parseFloat(mLng.toFixed(6))]);
                refreshRoute();
              });
              midpointMarkers.push(mm.addTo(map));
            })(j);
          }
        }
        waypoints.forEach((wp, idx) => {
          const vm = L.marker(wp, { icon: makeVertexIcon(idx, waypoints.length), draggable: true, zIndexOffset: 10 });
          let dragged = false;
          vm.on("mousedown", () => { dragged = false; });
          vm.on("drag", () => { dragged = true; const ll = vm.getLatLng(); waypoints[idx] = [ll.lat, ll.lng]; routeLayer.setLatLngs(waypoints); });
          vm.on("dragend", () => { const ll = vm.getLatLng(); waypoints[idx] = [parseFloat(ll.lat.toFixed(6)), parseFloat(ll.lng.toFixed(6))]; refreshRoute(); });
          vm.on("click", (e) => { L.DomEvent.stopPropagation(e); if (!dragged) { suppressNext(); waypoints.splice(idx, 1); refreshRoute(); } });
          waypointMarkers.push(vm.addTo(map));
        });
        updateRouteUI();
      }

      function updateRouteUI() {
        const count = document.getElementById("route-count");
        const saved = document.getElementById("route-saved");
        if (waypoints.length >= 2) {
          const dist = routeDist(waypoints);
          count.textContent = waypoints.length + " " + t("points") + " · " + (dist < 1000 ? Math.round(dist) + "m" : (dist / 1000).toFixed(2) + "km");
          saved.style.display = "flex";
          inpRoute.value = JSON.stringify(waypoints);
        } else if (waypoints.length === 1) {
          count.textContent = t("1 point — click destination"); saved.style.display = "none"; inpRoute.value = "";
        } else {
          count.textContent = ""; saved.style.display = "none"; inpRoute.value = "";
        }
      }

      function snapToMarker(latlng) {
        const targets = [HARAM, NABAWI];
        if (inpLat.value && inpLng.value) targets.push([parseFloat(inpLat.value), parseFloat(inpLng.value)]);
        for (let i = 0; i < targets.length; i++) {
          const tp = map.latLngToContainerPoint(L.latLng(targets[i][0], targets[i][1]));
          const cp = map.latLngToContainerPoint(latlng);
          if (Math.sqrt((tp.x - cp.x) ** 2 + (tp.y - cp.y) ** 2) <= 24) return [targets[i][0], targets[i][1]];
        }
        return [parseFloat(latlng.lat.toFixed(6)), parseFloat(latlng.lng.toFixed(6))];
      }

      function toggleRouteMode() {
        routeMode = !routeMode;
        const btn = document.getElementById("route-toggle-btn");
        const ctrl = document.getElementById("route-controls");
        const hint = document.getElementById("route-hint");
        const lbl = document.getElementById("route-toggle-label");
        const exit = document.getElementById("route-exit-icon");
        mapWrap.classList.toggle("route-active", routeMode);
        btn.style.borderColor = routeMode ? "color-mix(in srgb, var(--foreground) 55%, transparent)" : "";
        btn.style.background = routeMode ? "var(--muted)" : "";
        btn.style.color = routeMode ? "var(--foreground)" : "";
        btn.style.boxShadow = routeMode ? "var(--shadow-accent)" : "var(--shadow-md)";
        if (lbl) lbl.textContent = t(routeMode ? "Drawing…" : "Draw Mode");
        if (exit) exit.style.display = routeMode ? "block" : "none";
        ctrl.style.display = routeMode ? "flex" : "none";
        hint.style.display = routeMode ? "block" : "none";
        document.getElementById("pick-map").style.cursor = routeMode ? "crosshair" : "";
        if (!routeMode) {
          if (previewLine) { map.removeLayer(previewLine); previewLine = null; }
          if (snapRing) { map.removeLayer(snapRing); snapRing = null; }
        }
        refreshRoute();
      }

      const startFromMosque = () => { waypoints.unshift(getRefLL().slice()); refreshRoute(); };
      const startFromHotel = () => {
        if (!inpLat.value || !inpLng.value) return;
        waypoints.unshift([parseFloat(parseFloat(inpLat.value).toFixed(6)), parseFloat(parseFloat(inpLng.value).toFixed(6))]);
        refreshRoute();
      };
      const undoRoute = () => { if (waypoints.length) { waypoints.pop(); refreshRoute(); } };
      const clearRoute = () => { waypoints = []; if (previewLine) { map.removeLayer(previewLine); previewLine = null; } refreshRoute(); inpRoute.value = ""; };

      map.on("mousemove", (e) => {
        if (!routeMode) return;
        const targets = [HARAM, NABAWI];
        if (inpLat.value && inpLng.value) targets.push([parseFloat(inpLat.value), parseFloat(inpLng.value)]);
        let found = null;
        for (let i = 0; i < targets.length; i++) {
          const tp = map.latLngToContainerPoint(L.latLng(targets[i][0], targets[i][1]));
          const cp = map.latLngToContainerPoint(e.latlng);
          if (Math.sqrt((tp.x - cp.x) ** 2 + (tp.y - cp.y) ** 2) <= 24) { found = targets[i]; break; }
        }
        if (found) {
          if (!snapRing) snapRing = L.circleMarker(found, { radius: 14, color: "#fff", weight: 1.5, fillOpacity: 0, interactive: false }).addTo(map);
          else snapRing.setLatLng(found);
        } else if (snapRing) { map.removeLayer(snapRing); snapRing = null; }
        if (waypoints.length > 0) {
          const pts = [waypoints[waypoints.length - 1], [e.latlng.lat, e.latlng.lng]];
          if (previewLine) previewLine.setLatLngs(pts);
          else previewLine = L.polyline(pts, { color: "#1A1A1A", weight: 1.5, opacity: 0.38, dashArray: "5,5", interactive: false }).addTo(map);
        } else if (previewLine) { map.removeLayer(previewLine); previewLine = null; }
      });

      map.on("click", (e) => {
        if (suppress || !routeMode) return;
        waypoints.push(snapToMarker(e.latlng));
        refreshRoute();
      });

      function syncMarker() {
        const lat = parseFloat(inpLat.value), lng = parseFloat(inpLng.value);
        if (!isNaN(lat) && !isNaN(lng)) { setHotelMarker([lat, lng]); map.setView([lat, lng], map.getZoom()); }
      }
      inpLat.addEventListener("change", syncMarker);
      inpLng.addEventListener("change", syncMarker);

      const onKey = (e) => { if (!routeMode) return; if (e.ctrlKey && (e.key === "z" || e.key === "Z")) { e.preventDefault(); undoRoute(); } };
      document.addEventListener("keydown", onKey);

      api.current = { toggleRouteMode, startFromMosque, startFromHotel, undoRoute, clearRoute, _onKey: onKey };
      refreshRoute();
      setTimeout(() => map.invalidateSize(), 100);
    });

    return () => {
      disposed = true;
      if (api.current._onKey) document.removeEventListener("keydown", api.current._onKey);
      if (map) map.remove();
    };
  }, []);

  return (
    <div className="page page-sm shadcn-root">
      <style>{CSS}</style>
      <PageBack href={edit ? `/hotels/${h.id}/` : "/hotels/"} label={t("Back")} />
      <FormHeader kicker={t("Hotel")} title={edit ? t("Edit — {name}", { name: h.name }) : t("New Hotel")} />

      <form ref={formRef} method="post" onSubmit={submit}>
        {/* ── Detail Hotel ── */}
        <div style={{ marginBottom: 16 }}>
          <FormPanel>
            <FormSection label={t("Hotel Details")}>
              <FormField label={t("Hotel Name")} name="name" required>
                <Input id="name" name="name" type="text" defaultValue={h.name || ""} required placeholder={t("e.g. Hotel Sawaaed")} />
              </FormField>
              <div className="fg-3">
                <FormField label={t("City")} name="city">
                  <select id="city" name="city" defaultValue={h.city || "makkah"} className={SELECT_CLASS}>
                    <option value="makkah">Makkah</option>
                    <option value="madinah">Madinah</option>
                  </select>
                </FormField>
                <FormField label={t("Stars")} name="stars">
                  <select id="stars" name="stars" defaultValue={h.stars || 3} className={SELECT_CLASS}>
                    {[1, 2, 3, 4, 5].map((s) => <option key={s} value={s}>{s} ★</option>)}
                  </select>
                </FormField>
                <FormField label={t("Area")} name="area">
                  <Input id="area" name="area" type="text" defaultValue={h.area || ""} placeholder={t("Misfalah, Ajyad…")} list="area-suggestions" />
                  <datalist id="area-suggestions">{AREAS.map((a) => <option key={a} value={a} />)}</datalist>
                </FormField>
              </div>
              <div className="fg-2">
                <FormField label={t("Avg People/Room")} name="avg_occupancy" hint={t("35 pilgrims ÷ 3.4 = 11 rooms")}>
                  <Input id="avg_occupancy" name="avg_occupancy" type="number" step="0.01" min="0.1" defaultValue={h.avg_occupancy ?? ""} placeholder="3.4" />
                </FormField>
                <div style={{ display: "flex", alignItems: "flex-end", paddingBottom: 3 }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", margin: 0, fontSize: 13, color: "var(--foreground)" }}>
                    <input type="checkbox" name="is_active" defaultChecked={!edit || h.is_active} style={{ width: 16, height: 16, accentColor: "var(--foreground)" }} />
                    <span>{t("Active")}</span>
                  </label>
                </div>
              </div>
            </FormSection>
          </FormPanel>
        </div>

        {/* ── Peta & Rute ── */}
        <div style={{ marginBottom: 16 }}>
          <FormPanel>
            <FormSection label={t("Map & Route")}>
              <div style={{ margin: "4px -24px -24px", borderRadius: "0 0 var(--radius-card) var(--radius-card)", overflow: "hidden" }}>
            <div id="map-wrap" style={{ position: "relative", overflow: "hidden", transition: "box-shadow .2s" }}>
              <div id="pick-map" style={{ height: 360, display: "block" }} />
              <div style={{ position: "absolute", top: 10, right: 10, zIndex: "var(--z-overlay)" }}>
                <button type="button" id="route-toggle-btn" onClick={() => api.current.toggleRouteMode?.()} style={{
                  display: "flex", alignItems: "center", gap: 7, whiteSpace: "nowrap", padding: "7px 12px", borderRadius: 8, cursor: "pointer",
                  background: "color-mix(in srgb, var(--card) 90%, transparent)", backdropFilter: "blur(14px)", WebkitBackdropFilter: "blur(14px)",
                  border: "1px solid var(--border)", color: "var(--muted-foreground)", fontSize: 12, fontWeight: 500, fontFamily: "inherit",
                  transition: "border-color .2s,color .2s,background .2s,box-shadow .2s", boxShadow: "var(--shadow-md)",
                }}>
                  <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" style={{ flexShrink: 0 }}><path strokeLinecap="round" strokeLinejoin="round" d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 000-1.41l-2.34-2.34a1 1 0 00-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z" /></svg>
                  <span id="route-toggle-label">{t("Draw Mode")}</span>
                  <svg id="route-exit-icon" style={{ display: "none", marginLeft: 1, opacity: 0.55, flexShrink: 0 }} width="10" height="10" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
                <div id="route-controls" style={{ display: "none", flexDirection: "column", gap: 6, marginTop: 6, padding: 8, background: "color-mix(in srgb, var(--card) 93%, transparent)", backdropFilter: "blur(14px)", WebkitBackdropFilter: "blur(14px)", border: "1px solid var(--border)", borderRadius: 10, boxShadow: "var(--shadow-lg)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
                    <button type="button" className="rib rib-amber" onClick={() => api.current.startFromMosque?.()} title={t("Start point: Mosque plaza")}>
                      <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><circle cx="12" cy="10" r="3" /><path strokeLinecap="round" strokeLinejoin="round" d="M12 2C8.134 2 5 5.134 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.866-3.134-7-7-7z" /></svg>
                    </button>
                    <button type="button" className="rib rib-blue" onClick={() => api.current.startFromHotel?.()} title={t("Start point: Hotel position")}>
                      <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M3 9.5L12 3l9 6.5V20a1 1 0 01-1 1H4a1 1 0 01-1-1V9.5z" /><path strokeLinecap="round" strokeLinejoin="round" d="M9 21V12h6v9" /></svg>
                    </button>
                    <div style={{ width: 1, height: 18, background: "var(--border)", margin: "0 3px", flexShrink: 0 }} />
                    <button type="button" className="rib" onClick={() => api.current.undoRoute?.()} title={t("Undo — remove last point (Ctrl+Z)")}>
                      <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M3 10h10a4 4 0 010 8H7m-4-8l4-4m-4 4l4 4" /></svg>
                    </button>
                    <button type="button" className="rib rib-red" onClick={() => api.current.clearRoute?.()} title={t("Clear all route points")}>
                      <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                    </button>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6, padding: "1px 2px 0" }}>
                    <span id="route-count" style={{ fontSize: 10.5, color: "var(--muted-foreground)", whiteSpace: "nowrap", lineHeight: 1 }} />
                    <span id="route-saved" style={{ display: "none", alignItems: "center", gap: 3, fontSize: 10.5, color: "var(--green)", fontWeight: 600, flexShrink: 0, whiteSpace: "nowrap", lineHeight: 1 }}>
                      <svg width="8" height="8" fill="none" stroke="currentColor" strokeWidth="3" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
                      {t("Saved")}
                    </span>
                  </div>
                </div>
              </div>
              <div id="route-hint" style={{ display: "none", position: "absolute", bottom: 30, left: "50%", transform: "translateX(-50%)", zIndex: "var(--z-overlay)", pointerEvents: "none", whiteSpace: "nowrap", background: "color-mix(in srgb, var(--card) 88%, transparent)", backdropFilter: "blur(10px)", WebkitBackdropFilter: "blur(10px)", border: "1px solid var(--border)", borderRadius: 99, padding: "5px 14px", fontSize: 10.5, color: "var(--muted-foreground)", letterSpacing: ".01em" }}>
                {t("Click map = add · white ○ = bend · drag = move · click point = remove")}
              </div>
            </div>

            <div style={{ padding: "10px 16px", borderTop: "1px solid var(--border)", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 12, color: "var(--muted-foreground)", fontWeight: 500, flexShrink: 0, userSelect: "none" }}>Lat</span>
                <input type="number" step="any" name="lat" id="inp-lat" defaultValue={h.lat ?? ""} placeholder="21.4225" style={{ flex: 1, minWidth: 0 }} />
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 12, color: "var(--muted-foreground)", fontWeight: 500, flexShrink: 0, userSelect: "none" }}>Lng</span>
                <input type="number" step="any" name="lng" id="inp-lng" defaultValue={h.lng ?? ""} placeholder="39.8262" style={{ flex: 1, minWidth: 0 }} />
              </div>
            </div>
                <input type="hidden" name="route" id="inp-route" defaultValue={edit && h.route ? JSON.stringify(h.route) : ""} />
              </div>
            </FormSection>
          </FormPanel>
        </div>

        {/* ── Notes ── */}
        <div style={{ marginBottom: 16 }}>
          <FormPanel>
            <FormSection label={t("Notes")}>
              <FormField name="note">
                <Textarea id="note" name="note" rows={3} defaultValue={h.note || ""} placeholder={t("Additional info…")} />
              </FormField>
            </FormSection>
          </FormPanel>
        </div>

        <FormActions
          cancelHref={edit ? `/hotels/${h.id}/` : "/hotels/"}
          submitLabel={edit ? t("Save") : t("Create Hotel")}
          processing={form.processing}
        />
      </form>
    </div>
  );
}

const CSS = `
.rib { width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:7px;cursor:pointer;flex-shrink:0;font-family:inherit;background:var(--muted);border:1px solid var(--border);color:var(--muted-foreground);transition:background .12s,border-color .12s,transform .1s; }
.rib:hover  { background:var(--secondary); }
.rib:active { transform:scale(.92); }
.rib.rib-amber { color:var(--yellow);background:color-mix(in srgb, var(--yellow) 14%, transparent);border-color:color-mix(in srgb, var(--yellow) 26%, transparent); }
.rib.rib-amber:hover { background:color-mix(in srgb, var(--yellow) 18%, transparent); }
.rib.rib-blue  { color:var(--foreground);background:var(--muted);border-color:var(--border); }
.rib.rib-blue:hover  { background:var(--secondary); }
.rib.rib-red   { color:var(--red);background:var(--red-muted);border-color:color-mix(in srgb, var(--red) 18%, transparent); }
.rib.rib-red:hover   { background:color-mix(in srgb, var(--red) 16%, transparent); }
@keyframes _panelIn { from { opacity:0; transform:translateY(-5px) scale(.97); } to { opacity:1; transform:translateY(0) scale(1); } }
#route-controls { animation:_panelIn .18s cubic-bezier(.34,1.4,.64,1); }
#map-wrap.route-active { box-shadow:inset 0 0 0 2px color-mix(in srgb, var(--foreground) 45%, transparent); }
`;
