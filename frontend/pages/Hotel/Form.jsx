import { useEffect, useRef } from "react";
import { useForm } from "@inertiajs/react";
import { loadLeaflet } from "../../utils/leaflet.js";

const AREAS = ["Misfalah", "Ajyad", "Ajyad Selatan", "Ajyad Utara", "Syisyah", "Kudai", "Jarwal", "Aziziyah", "Ibrahim Khalil", "Nakasa", "Bakhutmaz"];

export default function HotelForm({ hotel, edit }) {
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
      L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        attribution: "© OpenStreetMap © CartoDB", subdomains: "abcd", maxZoom: 19,
      }).addTo(map);

      const dot = (size, color, glow) => L.divIcon({
        className: "",
        html: '<div style="width:' + size + "px;height:" + size + "px;border-radius:50%;background:" + color + ";border:2px solid #fff;box-shadow:0 0 " + (glow || 6) + "px " + color + '99;"></div>',
        iconSize: [size, size], iconAnchor: [size / 2, size / 2],
      });
      L.marker(HARAM, { icon: dot(14, "#F0A429", 10) }).bindTooltip("Pelataran Al-Haram").addTo(map);
      L.marker([21.4225, 39.8262], { icon: dot(10, "#E5534B") }).bindTooltip("Masjid Al-Haram").addTo(map);
      L.marker(NABAWI, { icon: dot(10, "#E5534B") }).bindTooltip("Masjid Nabawi").addTo(map);

      let hotelMarker = null;
      function setHotelMarker(ll) {
        if (hotelMarker) { hotelMarker.setLatLng(ll); return; }
        hotelMarker = L.marker(ll, { icon: dot(12, "#FF6C37"), draggable: true }).addTo(map);
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
      const routeDist = (wps) => { let t = 0; for (let i = 0; i < wps.length - 1; i++) t += haversine(wps[i], wps[i + 1]); return t; };

      function makeVertexIcon(idx, total) {
        const isEnd = idx === 0 || idx === total - 1;
        const s = isEnd ? 12 : 8;
        const color = idx === 0 ? "#3FB950" : idx === total - 1 ? "#F0A429" : "#FF6C37";
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
        routeLayer = L.polyline(waypoints, { color: "#FF6C37", weight: 3, opacity: 0.9, dashArray: "8,6", lineCap: "round", lineJoin: "round" }).addTo(map);
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
          count.textContent = waypoints.length + " titik · " + (dist < 1000 ? Math.round(dist) + "m" : (dist / 1000).toFixed(2) + "km");
          saved.style.display = "flex";
          inpRoute.value = JSON.stringify(waypoints);
        } else if (waypoints.length === 1) {
          count.textContent = "1 titik — klik tujuan"; saved.style.display = "none"; inpRoute.value = "";
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
        btn.style.borderColor = routeMode ? "rgba(94,106,210,.55)" : "";
        btn.style.background = routeMode ? "rgba(94,106,210,.18)" : "";
        btn.style.color = routeMode ? "var(--accent-2)" : "";
        btn.style.boxShadow = routeMode ? "0 2px 16px rgba(94,106,210,.25)" : "0 2px 16px rgba(0,0,0,.45)";
        if (lbl) lbl.textContent = routeMode ? "Sedang Gambar" : "Mode Gambar";
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
          else previewLine = L.polyline(pts, { color: "#FF6C37", weight: 1.5, opacity: 0.38, dashArray: "5,5", interactive: false }).addTo(map);
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
    <div className="page page-sm">
      <style>{CSS}</style>
      <div className="page-header">
        <div className="page-title">{edit ? `Edit — ${h.name}` : "Hotel Baru"}</div>
      </div>

      <form ref={formRef} method="post" onSubmit={submit}>
        {/* ── Detail Hotel ── */}
        <div className="card">
          <div className="card-header"><span className="card-title">Detail Hotel</span></div>
          <div className="card-body">
            <div className="field" style={{ marginBottom: 14 }}>
              <label>Nama Hotel *</label>
              <input type="text" name="name" defaultValue={h.name || ""} required placeholder="Contoh: Hotel Sawaaed" />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 14 }}>
              <div className="field">
                <label>Kota *</label>
                <select name="city" defaultValue={h.city || "makkah"}>
                  <option value="makkah">Makkah</option>
                  <option value="madinah">Madinah</option>
                </select>
              </div>
              <div className="field">
                <label>Bintang</label>
                <select name="stars" defaultValue={h.stars || 3}>
                  {[1, 2, 3, 4, 5].map((s) => <option key={s} value={s}>{s} ★</option>)}
                </select>
              </div>
              <div className="field">
                <label>Area</label>
                <input type="text" name="area" defaultValue={h.area || ""} placeholder="Misfalah, Ajyad…" list="area-suggestions" />
                <datalist id="area-suggestions">{AREAS.map((a) => <option key={a} value={a} />)}</datalist>
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div className="field">
                <label>Avg Orang/Kamar</label>
                <input type="number" step="0.01" min="0.1" name="avg_occupancy" defaultValue={h.avg_occupancy ?? ""} placeholder="3.4" />
                <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 4 }}>35 jamaah ÷ 3.4 = 11 kamar</div>
              </div>
              <div className="field" style={{ display: "flex", alignItems: "flex-end", paddingBottom: 3 }}>
                <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", margin: 0 }}>
                  <input type="checkbox" name="is_active" defaultChecked={!edit || h.is_active} />
                  <span>Aktif</span>
                </label>
              </div>
            </div>
          </div>
        </div>

        {/* ── Peta & Rute ── */}
        <div className="card">
          <div className="card-header"><span className="card-title">Peta & Rute</span></div>
          <div className="card-body" style={{ padding: 0 }}>
            <div id="map-wrap" style={{ position: "relative", overflow: "hidden", transition: "box-shadow .2s" }}>
              <div id="pick-map" style={{ height: 360, display: "block" }} />
              <div style={{ position: "absolute", top: 10, right: 10, zIndex: "var(--z-overlay)" }}>
                <button type="button" id="route-toggle-btn" onClick={() => api.current.toggleRouteMode?.()} style={{
                  display: "flex", alignItems: "center", gap: 7, whiteSpace: "nowrap", padding: "7px 12px", borderRadius: 8, cursor: "pointer",
                  background: "rgba(13,13,15,.90)", backdropFilter: "blur(14px)", WebkitBackdropFilter: "blur(14px)",
                  border: "1px solid rgba(255,255,255,.11)", color: "var(--text-2)", fontSize: 12, fontWeight: 500, fontFamily: "inherit",
                  transition: "border-color .2s,color .2s,background .2s,box-shadow .2s", boxShadow: "0 2px 16px rgba(0,0,0,.45)",
                }}>
                  <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" style={{ flexShrink: 0 }}><path strokeLinecap="round" strokeLinejoin="round" d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 000-1.41l-2.34-2.34a1 1 0 00-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z" /></svg>
                  <span id="route-toggle-label">Mode Gambar</span>
                  <svg id="route-exit-icon" style={{ display: "none", marginLeft: 1, opacity: 0.55, flexShrink: 0 }} width="10" height="10" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
                <div id="route-controls" style={{ display: "none", flexDirection: "column", gap: 6, marginTop: 6, padding: 8, background: "rgba(12,12,14,.93)", backdropFilter: "blur(14px)", WebkitBackdropFilter: "blur(14px)", border: "1px solid rgba(255,255,255,.11)", borderRadius: 10, boxShadow: "0 8px 32px rgba(0,0,0,.6),0 0 0 1px rgba(255,255,255,.03) inset" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
                    <button type="button" className="rib rib-amber" onClick={() => api.current.startFromMosque?.()} title="Titik awal: Pelataran Masjid">
                      <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><circle cx="12" cy="10" r="3" /><path strokeLinecap="round" strokeLinejoin="round" d="M12 2C8.134 2 5 5.134 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.866-3.134-7-7-7z" /></svg>
                    </button>
                    <button type="button" className="rib rib-blue" onClick={() => api.current.startFromHotel?.()} title="Titik awal: Posisi Hotel">
                      <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M3 9.5L12 3l9 6.5V20a1 1 0 01-1 1H4a1 1 0 01-1-1V9.5z" /><path strokeLinecap="round" strokeLinejoin="round" d="M9 21V12h6v9" /></svg>
                    </button>
                    <div style={{ width: 1, height: 18, background: "rgba(255,255,255,.09)", margin: "0 3px", flexShrink: 0 }} />
                    <button type="button" className="rib" onClick={() => api.current.undoRoute?.()} title="Undo — hapus titik terakhir (Ctrl+Z)">
                      <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M3 10h10a4 4 0 010 8H7m-4-8l4-4m-4 4l4 4" /></svg>
                    </button>
                    <button type="button" className="rib rib-red" onClick={() => api.current.clearRoute?.()} title="Hapus semua titik rute">
                      <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                    </button>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6, padding: "1px 2px 0" }}>
                    <span id="route-count" style={{ fontSize: 10.5, color: "var(--text-3)", whiteSpace: "nowrap", lineHeight: 1 }} />
                    <span id="route-saved" style={{ display: "none", alignItems: "center", gap: 3, fontSize: 10.5, color: "var(--green)", fontWeight: 600, flexShrink: 0, whiteSpace: "nowrap", lineHeight: 1 }}>
                      <svg width="8" height="8" fill="none" stroke="currentColor" strokeWidth="3" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
                      Tersimpan
                    </span>
                  </div>
                </div>
              </div>
              <div id="route-hint" style={{ display: "none", position: "absolute", bottom: 30, left: "50%", transform: "translateX(-50%)", zIndex: "var(--z-overlay)", pointerEvents: "none", whiteSpace: "nowrap", background: "rgba(12,12,14,.88)", backdropFilter: "blur(10px)", WebkitBackdropFilter: "blur(10px)", border: "1px solid rgba(255,255,255,.09)", borderRadius: 99, padding: "5px 14px", fontSize: 10.5, color: "var(--text-2)", letterSpacing: ".01em" }}>
                Klik peta = tambah &nbsp;·&nbsp; ○ putih = bengkok &nbsp;·&nbsp; seret = pindah &nbsp;·&nbsp; klik titik = hapus
              </div>
            </div>

            <div style={{ padding: "10px 16px", borderTop: "1px solid var(--border)", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 9.5, letterSpacing: ".08em", color: "var(--text-3)", fontWeight: 700, fontFamily: "monospace", flexShrink: 0, userSelect: "none", textTransform: "uppercase" }}>Lat</span>
                <input type="number" step="any" name="lat" id="inp-lat" defaultValue={h.lat ?? ""} placeholder="21.4225" style={{ flex: 1, minWidth: 0 }} />
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 9.5, letterSpacing: ".08em", color: "var(--text-3)", fontWeight: 700, fontFamily: "monospace", flexShrink: 0, userSelect: "none", textTransform: "uppercase" }}>Lng</span>
                <input type="number" step="any" name="lng" id="inp-lng" defaultValue={h.lng ?? ""} placeholder="39.8262" style={{ flex: 1, minWidth: 0 }} />
              </div>
            </div>
            <input type="hidden" name="route" id="inp-route" defaultValue={edit && h.route ? JSON.stringify(h.route) : ""} />
          </div>
        </div>

        {/* ── Catatan ── */}
        <div className="card">
          <div className="card-header"><span className="card-title">Catatan</span></div>
          <div className="card-body">
            <textarea name="note" rows={3} defaultValue={h.note || ""} placeholder="Info tambahan…" />
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 4 }}>
          <a href={edit ? `/hotels/${h.id}/` : "/hotels/"} className="btn btn-ghost">Batal</a>
          <button type="submit" className="btn btn-primary" disabled={form.processing}>{edit ? "Simpan" : "Buat Hotel"}</button>
        </div>
      </form>
    </div>
  );
}

const CSS = `
.rib { width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:7px;cursor:pointer;flex-shrink:0;font-family:inherit;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.09);color:var(--text-2);transition:background .12s,border-color .12s,transform .1s; }
.rib:hover  { background:rgba(255,255,255,.11); }
.rib:active { transform:scale(.92); }
.rib.rib-amber { color:#F0A429;background:rgba(240,164,41,.09);border-color:rgba(240,164,41,.26); }
.rib.rib-amber:hover { background:rgba(240,164,41,.18); }
.rib.rib-blue  { color:var(--accent-2);background:rgba(94,106,210,.09);border-color:rgba(94,106,210,.26); }
.rib.rib-blue:hover  { background:rgba(94,106,210,.18); }
.rib.rib-red   { color:var(--red);background:rgba(229,83,75,.07);border-color:rgba(229,83,75,.18); }
.rib.rib-red:hover   { background:rgba(229,83,75,.16); }
@keyframes _panelIn { from { opacity:0; transform:translateY(-5px) scale(.97); } to { opacity:1; transform:translateY(0) scale(1); } }
#route-controls { animation:_panelIn .18s cubic-bezier(.34,1.4,.64,1); }
#map-wrap.route-active { box-shadow:inset 0 0 0 2px rgba(94,106,210,.45); }
`;
