import { useEffect } from "react";
import { loadLeaflet } from "../../utils/leaflet.js";

// Hotel map — full imperative Leaflet app ported from the original hotel_map
// template. The DOM below mirrors the original (same ids/classes); the script
// runs once on mount and exposes the handlers it needs on window so the
// dynamically-rendered hotel cards (built via innerHTML) can call them.
export default function HotelMap() {
  useEffect(() => {
    let map = null;
    let disposed = false;
    const exposed = [];
    const expose = (name, fn) => { window[name] = fn; exposed.push(name); };

    loadLeaflet().then((L) => {
      if (disposed) return;

      function _esc(s) { return (s || "").toString().replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
      const HARAM = [21.420324, 39.826485];
      const HARAM_INFO = [21.4225, 39.8262];
      const NABAWI = [24.4672, 39.6112];
      map = L.map("map", { zoomControl: false }).setView(HARAM, 14);
      L.control.zoom({ position: "bottomright" }).addTo(map);

      function isMobile() { return window.innerWidth <= 600; }

      function fixMapHeight() {
        if (!isMobile()) return;
        const h = window.visualViewport ? window.visualViewport.height : window.innerHeight;
        document.getElementById("map-wrap").style.height = h + "px";
        if (map) map.invalidateSize();
      }
      if (window.visualViewport) window.visualViewport.addEventListener("resize", fixMapHeight);
      fixMapHeight();
      if (isMobile()) { const sheet = document.getElementById("mob-list-sheet"); if (sheet) sheet.style.display = "flex"; }

      function getTileUrl() {
        const theme = document.documentElement.getAttribute("data-theme");
        return "https://{s}.basemaps.cartocdn.com/" + (theme === "light" ? "light_all" : "dark_all") + "/{z}/{x}/{y}{r}.png";
      }
      const tileLayer = L.tileLayer(getTileUrl(), { attribution: "© OpenStreetMap © CartoDB", subdomains: "abcd", maxZoom: 19 }).addTo(map);
      const themeObserver = new MutationObserver(() => tileLayer.setUrl(getTileUrl()));
      themeObserver.observe(document.documentElement, { attributeFilter: ["data-theme"] });

      const refIcon = () => L.divIcon({ className: "", html: '<div style="width:12px;height:12px;border-radius:3px;background:var(--accent);border:2px solid rgba(255,255,255,.6);box-shadow:0 0 8px var(--accent);"></div>', iconSize: [12, 12], iconAnchor: [6, 6] });
      const mosqueIcon = () => L.divIcon({ className: "", html: '<div style="width:10px;height:10px;border-radius:3px;background:var(--red);border:2px solid rgba(255,255,255,.5);box-shadow:0 0 6px var(--red);"></div>', iconSize: [10, 10], iconAnchor: [5, 5] });
      L.marker(HARAM, { icon: refIcon() }).bindTooltip("Pelataran Al-Haram").addTo(map);
      L.marker(HARAM_INFO, { icon: mosqueIcon() }).bindTooltip("Masjid Al-Haram").addTo(map);
      L.marker(NABAWI, { icon: mosqueIcon() }).bindTooltip("Masjid Nabawi").addTo(map);

      let allHotels = [];
      const markerGroup = L.layerGroup().addTo(map);
      const routeGroup = L.layerGroup().addTo(map);
      let _renderCycle = 0;
      const routeTip = L.tooltip({ permanent: false, opacity: 1, className: "route-dist-tip", direction: "top", offset: [0, -10] });
      let routesVisible = !isMobile(), avgOnly = false, activeMarker = null, markerMap = {}, activeCardPk = null;

      const haversine = (lat1, lng1, lat2, lng2) => { const R = 6371000, p1 = lat1 * Math.PI / 180, p2 = lat2 * Math.PI / 180, dLat = (lat2 - lat1) * Math.PI / 180, dLng = (lng2 - lng1) * Math.PI / 180; const a = Math.sin(dLat / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dLng / 2) ** 2; return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)); };
      const fmtDist = (m) => (m < 1000 ? Math.round(m) + " M" : (m / 1000).toFixed(1) + " KM");
      const fmtDistLabel = (lbl) => (lbl ? lbl.replace(/\s*km/i, " KM").replace(/\s*m\b/i, " M") : "—");
      const distColor = (d) => (d === null ? "#4E4E5A" : d < 500 ? "#2ECC71" : d < 1500 ? "#F5A623" : "#FF453A");
      const distClass = (d) => (d === null ? "dim" : d < 500 ? "green" : d < 1500 ? "yellow" : "red");
      const starsHtml = (n) => "★".repeat(n);
      const starSize = (s) => (s >= 5 ? 14 : s >= 4 ? 12 : 10);

      function updateHud(lat, lng) {
        const el = document.getElementById("hud-coords");
        el.textContent = Math.abs(lat).toFixed(4) + "°" + (lat >= 0 ? "N" : "S") + "  " + Math.abs(lng).toFixed(4) + "°" + (lng >= 0 ? "E" : "W");
        el.classList.add("active");
      }

      function hotelIcon(color, size, pulse) {
        const s = Math.round(size * 0.72), hs = Math.round(s / 2), half = Math.round(size / 2);
        const dot = '<div style="position:absolute;top:50%;left:50%;width:' + s + "px;height:" + s + "px;margin-top:-" + hs + "px;margin-left:-" + hs + "px;border-radius:3px;background:" + color + ';border:1.5px solid rgba(255,255,255,.45);box-shadow:0 0 6px ' + color + '99;"></div>';
        if (pulse) {
          const cSize = size + 44, cHalf = Math.round(cSize / 2);
          return L.divIcon({ className: "", html:
            '<div style="position:relative;width:' + cSize + "px;height:" + cSize + 'px;">' +
            '<div style="position:absolute;top:50%;left:50%;width:' + size + "px;height:" + size + "px;margin-top:-" + half + "px;margin-left:-" + half + "px;border-radius:50%;border:1.5px solid " + color + ';animation:pulse-ring 1.4s ease-out infinite;"></div>' +
            '<div style="position:absolute;top:50%;left:50%;width:' + s + "px;height:" + s + "px;margin-top:-" + hs + "px;margin-left:-" + hs + "px;border-radius:3px;background:" + color + ';border:1.5px solid rgba(255,255,255,.55);box-shadow:0 0 10px ' + color + 'BB;"></div>' +
            "</div>", iconSize: [cSize, cSize], iconAnchor: [cHalf, cHalf] });
        }
        return L.divIcon({ className: "", html: '<div style="position:relative;width:' + size + "px;height:" + size + 'px;">' + dot + "</div>", iconSize: [size, size], iconAnchor: [half, half] });
      }

      function buildPopup(h) {
        const dist = fmtDistLabel(h.distance_label);
        const avgRow = h.avg ? '<div class="pop-row"><span class="pop-label">Avg</span><span class="pop-val">' + _esc(h.avg) + " pax/room</span></div>" : "";
        return '<div class="pop-name">' + _esc(h.name) + '</div><div class="pop-stars">' + starsHtml(h.stars) + "</div>" + (h.area ? '<div class="pop-area">' + _esc(h.area) + "</div>" : "") + '<div class="pop-row"><span class="pop-label">Distance</span><span class="pop-val ' + distClass(h.distance) + '">' + dist + "</span></div>" + avgRow;
      }

      const getCityFilter = () => { const el = document.querySelector('input[name="fp-city"]:checked'); return el ? el.value : "all"; };
      const getDistFilters = () => Array.from(document.querySelectorAll('#filter-dropdown input[type=checkbox][value=dekat],#filter-dropdown input[type=checkbox][value=sedang],#filter-dropdown input[type=checkbox][value=jauh]')).filter((cb) => cb.checked).map((cb) => cb.value);
      const getStarsFilters = () => Array.from(document.querySelectorAll('input[name="fp-stars"]:checked')).map((cb) => parseInt(cb.value, 10));
      function countActiveFilters() { let n = 0; if (getCityFilter() !== "all") n++; if (getDistFilters().length > 0) n++; if (getStarsFilters().length > 0) n++; if (avgOnly) n++; return n; }
      function updateFilterBadge() { const n = countActiveFilters(), badge = document.getElementById("filter-badge"), btn = document.getElementById("filter-open-btn"); badge.style.display = n > 0 ? "" : "none"; if (n > 0) badge.textContent = n; btn.classList.toggle("has-filter", n > 0); }
      function getFiltered() {
        const q = (document.getElementById("hotel-search").value || "").toLowerCase().trim(), city = getCityFilter(), dists = getDistFilters(), stars = getStarsFilters();
        return allHotels.filter((h) => {
          if (q && h.name.toLowerCase().indexOf(q) === -1 && !(h.area && h.area.toLowerCase().indexOf(q) !== -1)) return false;
          if (city !== "all" && h.city !== city) return false;
          if (dists.length > 0) { let ok = false; if (dists.indexOf("dekat") !== -1 && h.distance !== null && h.distance <= 500) ok = true; if (dists.indexOf("sedang") !== -1 && h.distance !== null && h.distance > 500 && h.distance <= 1500) ok = true; if (dists.indexOf("jauh") !== -1 && h.distance !== null && h.distance > 1500) ok = true; if (!ok) return false; }
          if (stars.length > 0 && stars.indexOf(h.stars) === -1) return false;
          if (avgOnly && !h.avg) return false;
          return true;
        });
      }
      const syncRadioStyles = () => ["all", "makkah", "madinah"].forEach((v) => { const l = document.getElementById("fp-city-" + v); if (l) l.classList.toggle("active", document.querySelector('input[name="fp-city"][value="' + v + '"]').checked); });

      function saveFilters() { try { localStorage.setItem("hmap_filters", JSON.stringify({ city: getCityFilter(), dists: getDistFilters(), stars: getStarsFilters(), avg: avgOnly, q: document.getElementById("hotel-search").value || "" })); } catch (e) { /* noop */ } }
      function loadFilters() {
        try {
          const s = localStorage.getItem("hmap_filters"); if (!s) return;
          const f = JSON.parse(s);
          if (f.city) { const r = document.querySelector('input[name="fp-city"][value="' + f.city + '"]'); if (r) r.checked = true; }
          (f.dists || []).forEach((v) => { const cb = document.querySelector('#filter-dropdown input[value="' + v + '"]'); if (cb) cb.checked = true; });
          (f.stars || []).forEach((v) => { const cb = document.querySelector('input[name="fp-stars"][value="' + v + '"]'); if (cb) cb.checked = true; });
          avgOnly = !!f.avg; if (avgOnly) document.getElementById("sw-avg").classList.add("on");
          if (f.q) { const inp = document.getElementById("hotel-search"); if (inp) inp.value = f.q; syncSearchClear(); }
        } catch (e) { /* noop */ }
      }

      function applyFilters() {
        const city = getCityFilter();
        saveFilters();
        if (city === "makkah") map.flyTo(HARAM, 14, { duration: 1 });
        else if (city === "madinah") map.flyTo(NABAWI, 14, { duration: 1 });
        Object.values(markerMap).forEach((e) => e.marker.setOpacity(0));
        const filtered = getFiltered();
        setTimeout(() => { renderMarkers(filtered); updateCounter(filtered.length); renderPanel(filtered); }, 120);
        updateFilterBadge(); syncRadioStyles();
      }
      function updateCounter(n) { const label = n + " Hotel"; document.getElementById("hp-count").textContent = label; const mc = document.getElementById("mob-sheet-count"); if (mc) mc.textContent = label; }

      const toggleLegend = () => { document.getElementById("leg-body").classList.toggle("hidden"); document.getElementById("leg-arrow").classList.toggle("up"); };

      let filterOpen = false;
      const toggleFilter = () => { filterOpen = !filterOpen; document.getElementById("filter-dropdown").classList.toggle("open", filterOpen); document.getElementById("filter-open-btn").classList.toggle("has-filter", filterOpen || countActiveFilters() > 0); };
      function closeFilter() { filterOpen = false; const dd = document.getElementById("filter-dropdown"); if (dd) dd.classList.remove("open"); const btn = document.getElementById("filter-open-btn"); if (btn) btn.classList.toggle("has-filter", countActiveFilters() > 0); }

      const toggleRoutes = () => { routesVisible = !routesVisible; document.getElementById("sw-route").classList.toggle("on", routesVisible); if (routesVisible) routeGroup.addTo(map); else map.removeLayer(routeGroup); };
      const toggleAvg = () => { avgOnly = !avgOnly; document.getElementById("sw-avg").classList.toggle("on", avgOnly); applyFilters(); };
      const resetFilters = () => { document.querySelector('input[name="fp-city"][value="all"]').checked = true; document.querySelectorAll("#filter-dropdown input[type=checkbox]").forEach((cb) => { cb.checked = false; }); avgOnly = false; document.getElementById("sw-avg").classList.remove("on"); document.getElementById("hotel-search").value = ""; applyFilters(); };

      function buildCardHtml(h, idx) {
        const color = distColor(h.distance), dc = distClass(h.distance);
        const dist = fmtDistLabel(h.distance_label);
        const delay = typeof idx === "number" ? idx * 22 + "ms" : "0ms";
        return '<div class="hp-card" data-pk="' + h.pk + '" style="animation-delay:' + delay + '" onclick="selectCard(' + h.pk + ')" onmouseenter="hoverCard(' + h.pk + ')" onmouseleave="hoverCard(null)">' +
          '<div class="hp-card-top">' +
          '<div class="hp-dot" style="background:' + color + ';"></div>' +
          '<span class="hp-card-name">' + _esc(h.name) + "</span>" +
          '<span class="hp-card-dist ' + dc + '">' + dist + "</span>" +
          '<a href="' + h.url + '" class="hp-card-link" onclick="event.stopPropagation()" title="Hotel details">' +
          '<svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg>' +
          "</a></div>" +
          '<div class="hp-card-sub"><span style="color:var(--yellow);letter-spacing:1px;">' + starsHtml(h.stars) + "</span>" + (h.area ? " · " + _esc(h.area) : "") + "</div></div>";
      }
      function renderPanel(hotels) {
        const empty = '<div style="padding:48px 20px 40px;text-align:center;"><div style="font-size:13px;color:var(--text-2);margin-bottom:16px;">No matching hotels</div><button onclick="resetFilters()" style="background:var(--surface-2);border:1px solid var(--border-2);border-radius:8px;padding:8px 16px;color:var(--text-2);font-size:12px;font-weight:600;cursor:pointer;font-family:inherit;">Reset Filter</button></div>';
        const html = hotels.length === 0 ? empty : hotels.map((h, i) => buildCardHtml(h, i)).join("");
        if (!isMobile()) document.getElementById("hotel-list").innerHTML = html;
        const mobList = document.getElementById("mob-sheet-list");
        if (mobList) mobList.innerHTML = html;
      }

      let panelCollapsed = false;
      function updateZoomOffset() { const el = document.querySelector(".leaflet-bottom.leaflet-right"); if (!el || isMobile()) return; el.style.right = (panelCollapsed ? "10" : "316") + "px"; }
      const togglePanel = () => { panelCollapsed = !panelCollapsed; document.getElementById("hotel-panel").classList.toggle("collapsed", panelCollapsed); updateZoomOffset(); };

      function applyMarkerOpacity(selectedPk) { Object.values(markerMap).forEach((e) => { e.marker.setOpacity(selectedPk === null ? 1 : e.h.pk === selectedPk ? 1 : 0.25); }); }
      const hoverCard = (pk) => { if (pk === null) { applyMarkerOpacity(activeCardPk || null); return; } Object.values(markerMap).forEach((e) => { e.marker.setOpacity(e.h.pk === pk ? 1 : 0.25); }); };

      const selectCard = (pk) => {
        const entry = markerMap[pk]; if (!entry) return;
        if (isMobile()) { setSheetState("closed", true); lockSheet(400); }
        if (activeMarker && activeMarker !== entry.marker) { const prev = activeMarker._hotelData; activeMarker.setIcon(hotelIcon(distColor(prev.distance), activeMarker._starSize || 10)); }
        const h = entry.h, sz = entry.marker._starSize || 10;
        entry.marker.setIcon(hotelIcon(distColor(h.distance), sz + 4, true));
        activeMarker = entry.marker;
        updateHud(h.lat, h.lng);
        map.flyTo([h.lat, h.lng], 16, { duration: 0.8 });
        applyMarkerOpacity(pk);
        if (activeCardPk === pk) {
          document.querySelectorAll(".hp-card").forEach((el) => el.classList.remove("active"));
          if (activeMarker) { const ad = activeMarker._hotelData; activeMarker.setIcon(hotelIcon(distColor(ad.distance), activeMarker._starSize || 10)); activeMarker = null; }
          applyMarkerOpacity(null); activeCardPk = null; return;
        }
        document.querySelectorAll(".hp-card").forEach((el) => el.classList.remove("active"));
        document.querySelectorAll('.hp-card[data-pk="' + pk + '"]').forEach((card) => { card.classList.add("active"); if (!isMobile() && card.offsetParent !== null) card.scrollIntoView({ behavior: "smooth", block: "nearest" }); });
        activeCardPk = pk;
      };

      function renderMarkers(hotels) {
        routeTip.remove(); markerGroup.clearLayers(); routeGroup.clearLayers(); markerMap = {}; activeMarker = null; activeCardPk = null;
        document.querySelectorAll(".hp-card").forEach((el) => el.classList.remove("active"));
        const cycle = ++_renderCycle;
        hotels.forEach((h) => {
          const color = distColor(h.distance), refLL = h.city === "madinah" ? NABAWI : HARAM, sz = starSize(h.stars);
          const m = L.marker([h.lat, h.lng], { icon: hotelIcon(color, sz) });
          m._starSize = sz; m._hotelData = h;
          m.bindTooltip(h.name, { permanent: false, direction: "top", offset: [0, -10], opacity: 0.95, className: "route-dist-tip" });
          m.bindPopup(buildPopup(h), { maxWidth: 220 });
          m.on("click", (e) => { if (isMobile()) L.DomEvent.stopPropagation(e); });
          markerMap[h.pk] = { marker: m, h }; markerGroup.addLayer(m);
          const addRouteLine = (coords) => {
            if (_renderCycle !== cycle) return;
            const line = L.polyline(coords, { color, weight: 1.5, opacity: 0.45, dashArray: "6,4" });
            line.on("mousemove", (e) => { routeTip.setLatLng(e.latlng).setContent(fmtDist(haversine(refLL[0], refLL[1], e.latlng.lat, e.latlng.lng))).addTo(map); });
            line.on("mouseout", () => routeTip.remove()); routeGroup.addLayer(line);
          };
          addRouteLine(h.route && h.route.length >= 2 ? h.route : [refLL, [h.lat, h.lng]]);
        });
        if (!routesVisible) map.removeLayer(routeGroup);
      }

      // ── Mobile list sheet ──
      let _sheetState = "closed";
      const _sheetStates = ["closed", "peek", "half", "full"];
      let _sheetLocked = false;
      function setSheetState(state, force) {
        if (_sheetLocked && !force) return;
        _sheetState = state;
        const sheet = document.getElementById("mob-list-sheet"); if (!sheet) return;
        _sheetStates.forEach((s) => sheet.classList.remove("state-" + s));
        sheet.classList.add("state-" + state);
        const hint = document.getElementById("mob-sheet-hint");
        if (hint) hint.textContent = state === "closed" ? "▲ Open list" : state === "full" ? "▼ Close" : "▲▼ Drag";
        if ((state === "half" || state === "full") && activeCardPk) { setTimeout(() => { const card = document.querySelector('#mob-sheet-list .hp-card[data-pk="' + activeCardPk + '"]'); if (card) card.scrollIntoView({ block: "nearest" }); }, 320); }
      }
      function lockSheet(ms) { _sheetLocked = true; setTimeout(() => { _sheetLocked = false; }, ms || 400); }

      let _searchTimer = null;
      const debounceSearch = () => { syncSearchClear(); clearTimeout(_searchTimer); _searchTimer = setTimeout(applyFilters, 200); };
      function syncSearchClear() { const inp = document.getElementById("hotel-search"); const btn = document.getElementById("search-clear-btn"); if (btn) btn.style.display = inp && inp.value ? "flex" : "none"; if (isMobile() && inp && inp.value && _sheetState === "closed") setSheetState("half"); }
      const clearSearch = () => {
        const inp = document.getElementById("hotel-search"); if (inp) { inp.value = ""; inp.focus(); }
        syncSearchClear(); applyFilters();
        if (activeMarker) { const ad = activeMarker._hotelData; activeMarker.setIcon(hotelIcon(distColor(ad.distance), activeMarker._starSize || 10)); activeMarker = null; }
        document.querySelectorAll(".hp-card").forEach((el) => el.classList.remove("active")); activeCardPk = null;
      };

      map.on("click", () => {
        closeFilter();
        if (activeMarker) { const ad = activeMarker._hotelData; activeMarker.setIcon(hotelIcon(distColor(ad.distance), activeMarker._starSize || 10)); activeMarker = null; }
        if (activeCardPk) { document.querySelectorAll(".hp-card").forEach((el) => el.classList.remove("active")); activeCardPk = null; applyMarkerOpacity(null); }
        if (isMobile()) { if (_sheetState === "full") setSheetState("half"); else if (_sheetState === "half") setSheetState("closed"); }
      });

      (function initSheetDrag() {
        const handle = document.getElementById("mob-sheet-handle");
        const sheet = document.getElementById("mob-list-sheet");
        if (!handle || !sheet) return;
        let startY = 0;
        handle.addEventListener("touchstart", (e) => { startY = e.touches[0].clientY; sheet.classList.add("no-anim"); }, { passive: true });
        handle.addEventListener("touchend", (e) => {
          sheet.classList.remove("no-anim");
          const dy = e.changedTouches[0].clientY - startY;
          if (dy < -40) setSheetState("half");
          else if (dy > 40) setSheetState("closed");
          else if (Math.abs(dy) < 10) setSheetState(_sheetState === "closed" || _sheetState === "peek" ? "half" : "closed");
        }, { passive: true });
        const listEl = document.getElementById("mob-sheet-list");
        let listStartY = 0;
        if (listEl) {
          listEl.addEventListener("touchstart", (e) => { listStartY = e.touches[0].clientY; }, { passive: true });
          listEl.addEventListener("touchend", (e) => {
            const dy = e.changedTouches[0].clientY - listStartY;
            if (dy < -60 && listEl.scrollTop === 0 && _sheetState === "half") setSheetState("full");
            else if (dy > 80 && listEl.scrollTop === 0 && _sheetState === "full") setSheetState("closed");
          }, { passive: true });
        }
      })();

      expose("toggleLegend", toggleLegend);
      expose("toggleFilter", toggleFilter);
      expose("toggleRoutes", toggleRoutes);
      expose("toggleAvg", toggleAvg);
      expose("resetFilters", resetFilters);
      expose("togglePanel", togglePanel);
      expose("hoverCard", hoverCard);
      expose("selectCard", selectCard);
      expose("debounceSearch", debounceSearch);
      expose("clearSearch", clearSearch);
      expose("applyFilters", applyFilters);

      fetch("/hotels/map/data/")
        .then((r) => r.json())
        .then((data) => {
          if (disposed) return;
          allHotels = data.hotels;
          loadFilters();
          updateZoomOffset();
          const filtered = getFiltered();
          renderMarkers(filtered); updateCounter(filtered.length); renderPanel(filtered);
          updateFilterBadge(); syncRadioStyles();
          map.setView(getCityFilter() === "madinah" ? NABAWI : HARAM, 14);
        });

      window.__hotelMapCleanup = () => { themeObserver.disconnect(); if (window.visualViewport) window.visualViewport.removeEventListener("resize", fixMapHeight); };
    });

    return () => {
      disposed = true;
      exposed.forEach((n) => { delete window[n]; });
      if (window.__hotelMapCleanup) { window.__hotelMapCleanup(); delete window.__hotelMapCleanup; }
      if (map) map.remove();
    };
  }, []);

  return (
    <div id="map-wrap">
      <style>{CSS}</style>
      <div id="map" />

      <div className="map-topbar">
        <a href="/hotels/" className="map-back-btn" title="Back to hotel list">
          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
        </a>
        <div className="map-search-wrap">
          <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" /><path strokeLinecap="round" d="M21 21l-4.35-4.35" /></svg>
          <input type="text" id="hotel-search" placeholder="Search hotel or area..." onInput={() => window.debounceSearch?.()} />
          <button id="search-clear-btn" onClick={() => window.clearSearch?.()} style={{ display: "none", background: "none", border: "none", cursor: "pointer", padding: 0, color: "var(--text-3)", lineHeight: 1, flexShrink: 0 }} title="Hapus">
            <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div className="filter-btn-wrap">
          <button className="map-tb-btn" id="filter-open-btn" onClick={() => window.toggleFilter?.()}>
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M3 4h18M7 8h10M10 12h4" /></svg>
            Filter
            <span id="filter-badge" style={{ display: "none", background: "var(--accent)", color: "#fff", borderRadius: 8, padding: "1px 6px", fontSize: 10, fontWeight: 800 }} />
          </button>

          <div id="filter-dropdown" className="map-filter-dropdown">
            <div className="fp-section"><div className="fp-section-title">City</div></div>
            <label className="fp-radio active" id="fp-city-all"><input type="radio" name="fp-city" value="all" defaultChecked onChange={() => window.applyFilters?.()} /> All Cities</label>
            <label className="fp-radio" id="fp-city-makkah"><input type="radio" name="fp-city" value="makkah" onChange={() => window.applyFilters?.()} /> Makkah</label>
            <label className="fp-radio" id="fp-city-madinah"><input type="radio" name="fp-city" value="madinah" onChange={() => window.applyFilters?.()} /> Madinah</label>
            <div className="fp-divider" style={{ margin: "6px 0" }} />
            <div className="fp-section"><div className="fp-section-title">Distance to Mosque</div></div>
            <label className="fp-check" id="fp-dist-dekat"><input type="checkbox" value="dekat" onChange={() => window.applyFilters?.()} /><span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--green)", display: "inline-block", flexShrink: 0 }} /> ≤ 500 M</label>
            <label className="fp-check" id="fp-dist-sedang"><input type="checkbox" value="sedang" onChange={() => window.applyFilters?.()} /><span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--yellow)", display: "inline-block", flexShrink: 0 }} /> 500 M – 1.5 KM</label>
            <label className="fp-check" id="fp-dist-jauh"><input type="checkbox" value="jauh" onChange={() => window.applyFilters?.()} /><span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--red)", display: "inline-block", flexShrink: 0 }} /> {">"} 1.5 KM</label>
            <div className="fp-divider" style={{ margin: "6px 0" }} />
            <div className="fp-section"><div className="fp-section-title">Stars</div></div>
            <label className="fp-check"><input type="checkbox" name="fp-stars" value="3" onChange={() => window.applyFilters?.()} /><span style={{ color: "var(--yellow)", fontSize: 12 }}>★★★</span></label>
            <label className="fp-check"><input type="checkbox" name="fp-stars" value="4" onChange={() => window.applyFilters?.()} /><span style={{ color: "var(--yellow)", fontSize: 12 }}>★★★★</span></label>
            <label className="fp-check"><input type="checkbox" name="fp-stars" value="5" onChange={() => window.applyFilters?.()} /><span style={{ color: "var(--yellow)", fontSize: 12 }}>★★★★★</span></label>
            <div className="fp-divider" style={{ margin: "6px 0" }} />
            <div className="fp-toggle-row" onClick={() => window.toggleAvg?.()}><span className="fp-toggle-label">Has Avg / Capacity</span><div id="sw-avg" className="fp-toggle-switch" /></div>
            <div className="fp-toggle-row" onClick={() => window.toggleRoutes?.()}><span className="fp-toggle-label">Show Routes</span><div id="sw-route" className="fp-toggle-switch on" /></div>
            <div className="fp-reset-wrap"><button className="fp-reset" onClick={() => window.resetFilters?.()}>Reset Filter</button></div>
          </div>
        </div>
      </div>

      <div className="hud-coords" id="hud-coords">---.-°N  ---.-°E</div>

      <div className="map-legend">
        <div className="leg-toggle" onClick={() => window.toggleLegend?.()}>
          <span className="leg-toggle-title">Legend</span>
          <svg className="leg-arrow" id="leg-arrow" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" /></svg>
        </div>
        <div id="leg-body">
          <div className="leg-section">Distance to Mosque</div>
          <div className="leg-row"><div className="leg-dot" style={{ background: "var(--green)" }} /> ≤ 500 M</div>
          <div className="leg-row"><div className="leg-dot" style={{ background: "var(--yellow)" }} /> 500 M – 1.5 KM</div>
          <div className="leg-row"><div className="leg-dot" style={{ background: "var(--red)" }} /> {">"} 1.5 KM</div>
          <div className="leg-section">Reference Points</div>
          <div className="leg-row"><div className="leg-dot" style={{ background: "var(--accent)" }} /> Al-Haram Plaza</div>
          <div className="leg-row"><div className="leg-dot" style={{ background: "var(--red)" }} /> Mosque</div>
        </div>
      </div>

      <div id="mob-list-sheet" className="mob-list-sheet state-closed">
        <div className="mob-sheet-handle-area" id="mob-sheet-handle">
          <div className="mob-sheet-pill" />
          <div className="mob-sheet-meta">
            <span className="mob-sheet-count" id="mob-sheet-count">0 Hotel</span>
            <span className="mob-sheet-hint" id="mob-sheet-hint">▲ Open list</span>
          </div>
        </div>
        <div className="mob-sheet-list" id="mob-sheet-list">
          <div className="map-loading" id="mob-loading"><span /><span /><span /></div>
        </div>
      </div>

      <div className="hotel-panel" id="hotel-panel">
        <button className="panel-toggle" onClick={() => window.togglePanel?.()} title="Hide / show panel">
          <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M9 18l6-6-6-6" /></svg>
        </button>
        <div className="hotel-panel-inner">
          <div className="hp-header"><div className="hp-meta"><span className="hp-count" id="hp-count">0 Hotel</span></div></div>
          <div className="hp-list" id="hotel-list">
            <div className="map-loading" id="desk-loading"><span /><span /><span /></div>
          </div>
        </div>
      </div>
    </div>
  );
}

const CSS = `
@media (max-width: 600px) { .m-topbar { display: none !important; } }
#map-wrap { position: relative; height: calc(100vh - 48px); overflow: hidden; }
#map { position: absolute; inset: 0; isolation: isolate; }
.hotel-panel { position: absolute; top: 0; right: 0; bottom: 0; width: 300px; background: rgba(20,20,23,.92); background: color-mix(in srgb, var(--surface) 92%, transparent); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); border-left: 1px solid var(--border); display: flex; flex-direction: column; overflow: visible; z-index: var(--z-dropdown); transition: transform .25s cubic-bezier(.4,0,.2,1); }
.hotel-panel.collapsed { transform: translateX(300px); }
.hotel-panel-inner { display: flex; flex-direction: column; flex: 1; overflow: hidden; position: relative; z-index: 1; }
.panel-toggle { position: absolute; left: -26px; top: 50%; transform: translateY(-50%); width: 26px; height: 52px; background: rgba(20,20,23,.92); background: color-mix(in srgb, var(--surface) 92%, transparent); backdrop-filter: blur(16px); border: 1px solid var(--border); border-right: none; border-radius: 8px 0 0 8px; cursor: pointer; display: flex; align-items: center; justify-content: center; color: var(--text-3); transition: color .15s; z-index: 1; }
.panel-toggle:hover { color: var(--text); }
.panel-toggle svg { transition: transform .25s cubic-bezier(.4,0,.2,1); }
.hotel-panel.collapsed .panel-toggle svg { transform: rotate(180deg); }
.hp-header { padding: 14px 14px 10px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.hp-meta { display: flex; align-items: center; justify-content: space-between; }
.hp-count { font-size: 11px; font-weight: 700; letter-spacing: 1.2px; color: var(--text-3); text-transform: uppercase; }
.hp-list { flex: 1; overflow-y: auto; min-height: 0; }
.hp-list::-webkit-scrollbar { width: 3px; }
.hp-list::-webkit-scrollbar-track { background: transparent; }
.hp-list::-webkit-scrollbar-thumb { background: var(--border-2); border-radius: 2px; }
.hp-card { padding: 10px 14px; border-bottom: 1px solid var(--border); cursor: pointer; border-left: 2px solid transparent; transition: background .12s, border-color .12s; animation: card-in .18s ease both; }
.hp-card:hover { background: var(--surface-2); }
.hp-card.active { background: var(--accent-muted); border-left-color: var(--accent); }
.hp-card-top { display: flex; align-items: center; gap: 9px; }
.hp-dot { width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; transition: box-shadow .15s; }
.hp-card:hover .hp-dot, .hp-card.active .hp-dot { box-shadow: 0 0 6px currentColor; }
.hp-card-name { font-size: 13px; font-weight: 600; color: var(--text); line-height: 1.3; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hp-card-dist { font-size: 11px; font-weight: 700; font-variant-numeric: tabular-nums; flex-shrink: 0; letter-spacing: .3px; }
.hp-card-dist.green  { color: var(--green); }
.hp-card-dist.yellow { color: var(--yellow); }
.hp-card-dist.red    { color: var(--red); }
.hp-card-dist.dim    { color: var(--text-3); }
.hp-card-link { display: flex; align-items: center; justify-content: center; width: 24px; height: 24px; flex-shrink: 0; margin-left: 2px; color: var(--text-3); text-decoration: none; border-radius: 6px; transition: color .15s, background .15s; }
.hp-card:hover .hp-card-link { color: var(--text-2); }
.hp-card-link:hover { color: var(--accent) !important; background: var(--accent-muted); }
.hp-card-sub { font-size: 10.5px; color: var(--text-3); padding-left: 17px; margin-top: 2px; letter-spacing: .3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.map-legend { position: absolute; top: 60px; left: 12px; z-index: var(--z-overlay); background: rgba(20,20,23,.85); background: color-mix(in srgb, var(--surface) 85%, transparent); backdrop-filter: blur(10px); border: 1px solid var(--border); border-radius: 10px; padding: 10px 14px; font-size: 11px; min-width: 140px; color: var(--text-2); }
.leg-toggle { display:flex; align-items:center; justify-content:space-between; cursor:pointer; user-select:none; margin-bottom:8px; }
.leg-toggle-title { font-size:10px; font-weight:700; letter-spacing:1.2px; text-transform:uppercase; color:var(--text-3); }
.leg-arrow { color:var(--text-3); transition:transform .2s; }
.leg-arrow.up { transform:rotate(-180deg); }
#leg-body { overflow:hidden; max-height:200px; transition:max-height .25s ease, opacity .2s; opacity:1; }
#leg-body.hidden { max-height:0; opacity:0; }
.leg-section { font-size:10px; font-weight:700; letter-spacing:1.2px; text-transform:uppercase; color:var(--text-3); margin-bottom:5px; margin-top:9px; }
.leg-section:first-child { margin-top:0; }
.leg-row { display:flex; align-items:center; gap:8px; margin-bottom:4px; }
.leg-row:last-child { margin-bottom:0; }
.leg-dot { width:8px; height:8px; border-radius:2px; flex-shrink:0; }
.map-topbar { position: absolute; top: 12px; left: 12px; z-index: var(--z-overlay); display: flex; align-items: center; gap: 8px; }
.filter-btn-wrap { position: relative; }
.map-tb-btn { display: flex; align-items: center; gap: 6px; height: 36px; padding: 0 16px; background: rgba(20,20,23,.9); background: color-mix(in srgb, var(--surface) 90%, transparent); backdrop-filter: blur(10px); border: 1px solid var(--border-2); border-radius: 20px; color: var(--text); font-size: 12px; font-weight: 600; cursor: pointer; white-space: nowrap; transition: all .15s; }
.map-tb-btn:hover { border-color: var(--text-3); }
.map-tb-btn.has-filter { color: var(--accent); border-color: var(--accent); background: var(--accent-muted); }
.map-search-wrap { display: flex; align-items: center; gap: 8px; height: 36px; padding: 0 12px; min-width: 220px; background: rgba(20,20,23,.88); background: color-mix(in srgb, var(--surface) 88%, transparent); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid var(--border-2); border-radius: 20px; box-shadow: 0 2px 12px rgba(0,0,0,.3); }
.map-search-wrap:focus-within { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-muted), 0 2px 12px rgba(0,0,0,.3); }
.map-search-wrap:focus-within svg { color: var(--accent); }
.map-search-wrap svg { color: var(--text-3); flex-shrink: 0; }
.map-search-wrap input, .map-search-wrap input:focus { background: transparent !important; border: none !important; border-color: transparent !important; outline: none !important; box-shadow: none !important; -webkit-box-shadow: none !important; padding: 0 !important; margin: 0; border-radius: 0 !important; color: var(--text); font-size: 13px; font-family: inherit; width: 100%; height: 100%; -webkit-appearance: none; appearance: none; -webkit-tap-highlight-color: transparent; }
.map-search-wrap input::placeholder { color: var(--text-3); }
.map-filter-dropdown { position: absolute; top: calc(100% + 6px); left: 0; width: 240px; background: rgba(20,20,23,.96); background: color-mix(in srgb, var(--surface) 96%, transparent); backdrop-filter: blur(12px); border: 1px solid var(--border-2); border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,.4); z-index: var(--z-overlay); opacity: 0; pointer-events: none; transform: translateY(-6px) scale(.98); transform-origin: top left; transition: opacity .18s, transform .18s; overflow: hidden; padding-top: 4px; }
.map-filter-dropdown.open { opacity: 1; pointer-events: all; transform: none; }
.fp-section { padding: 10px 14px 2px; }
.fp-section-title { font-size: 10px; font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase; color: var(--text-3); margin-bottom: 6px; }
.fp-divider { height: 1px; background: var(--border); margin: 4px 0; }
.fp-radio, .fp-check { display: flex; align-items: center; gap: 9px; padding: 6px 14px; cursor: pointer; font-size: 13px; color: var(--text-2); transition: background .1s, color .1s; }
.fp-radio:hover, .fp-check:hover { background: var(--surface-2); color: var(--text); }
.fp-radio input[type=radio], .fp-check input[type=checkbox] { accent-color: var(--accent); width: 14px; height: 14px; cursor: pointer; }
.fp-radio.active { color: var(--text); font-weight: 600; }
.fp-toggle-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 14px; cursor: pointer; }
.fp-toggle-label { font-size: 13px; color: var(--text-2); }
.fp-toggle-switch { width: 32px; height: 17px; border-radius: 9px; background: var(--border-2); position: relative; transition: background .15s; flex-shrink: 0; }
.fp-toggle-switch.on { background: var(--accent); }
.fp-toggle-switch::after { content:''; position:absolute; width:11px; height:11px; border-radius:50%; background:#fff; top:3px; left:3px; transition:left .15s; }
.fp-toggle-switch.on::after { left: 18px; }
.fp-reset-wrap { padding: 10px 14px 12px; }
.fp-reset { width: 100%; padding: 8px; border-radius: 8px; border: 1px solid var(--border-2); background: transparent; color: var(--text-3); font-size: 12px; font-weight: 600; cursor: pointer; transition: all .15s; }
.fp-reset:hover { border-color: var(--text-3); color: var(--text-2); }
.hud-coords { position: absolute; bottom: 20px; left: 12px; z-index: var(--z-overlay); font-variant-numeric: tabular-nums; font-size: 10.5px; letter-spacing: .6px; color: var(--text-2); background: rgba(20,20,23,.8); background: color-mix(in srgb, var(--surface) 80%, transparent); backdrop-filter: blur(8px); border: 1px solid var(--border); border-radius: 8px; padding: 5px 10px; pointer-events: none; transition: color .2s, border-color .2s; }
.hud-coords.active { color: var(--accent); border-color: var(--accent); }
.route-dist-tip { background:var(--surface-2) !important; border:1px solid var(--border-2) !important; color:var(--text) !important; font-size:11px !important; font-weight:700 !important; font-variant-numeric:tabular-nums; letter-spacing:.3px !important; padding:4px 9px !important; border-radius:6px !important; white-space:nowrap; pointer-events:none; box-shadow:0 2px 10px rgba(0,0,0,.3); }
.route-dist-tip::before { display:none !important; }
.leaflet-popup-content-wrapper { background:var(--surface); backdrop-filter:blur(12px); border:1px solid var(--border-2); border-radius:12px; box-shadow:0 8px 32px rgba(0,0,0,.45); color:var(--text); animation:popup-in .15s cubic-bezier(.34,1.56,.64,1) both; }
.leaflet-popup-tip { background:var(--surface); }
.leaflet-popup-content { margin:12px 16px; min-width:160px; }
.pop-name  { font-size:13px; font-weight:700; color:var(--text); margin-bottom:2px; }
.pop-stars { font-size:11px; color:var(--yellow); letter-spacing:2px; margin-bottom:6px; }
.pop-area  { font-size:10.5px; color:var(--text-3); margin-bottom:6px; }
.pop-row   { display:flex; justify-content:space-between; align-items:center; font-size:11px; margin-bottom:4px; }
.pop-label { font-size:10px; font-weight:600; letter-spacing:.5px; text-transform:uppercase; color:var(--text-3); }
.pop-val   { font-weight:700; color:var(--text); font-variant-numeric:tabular-nums; }
.pop-val.green  { color:var(--green); }
.pop-val.yellow { color:var(--yellow); }
.pop-val.red    { color:var(--red); }
@keyframes pulse-ring { 0%{transform:scale(1);opacity:.6} 100%{transform:scale(2.6);opacity:0} }
@keyframes card-in   { from{opacity:0;transform:translateX(8px)} to{opacity:1;transform:translateX(0)} }
@keyframes popup-in  { from{opacity:0;transform:scale(.94) translateY(6px)} to{opacity:1;transform:scale(1) translateY(0)} }
@keyframes dot-bounce { 0%,80%,100%{transform:translateY(0);opacity:.3} 40%{transform:translateY(-6px);opacity:1} }
.map-loading { display:flex; align-items:center; justify-content:center; gap:5px; padding:48px 20px; }
.map-loading span { width:6px; height:6px; border-radius:50%; background:var(--accent); animation:dot-bounce 1.2s ease-in-out infinite; }
.map-loading span:nth-child(2) { animation-delay:.2s; }
.map-loading span:nth-child(3) { animation-delay:.4s; }
.leaflet-marker-icon { transition: opacity .25s ease; }
.leaflet-bottom.leaflet-right { transition: right .25s cubic-bezier(.4,0,.2,1), bottom .25s cubic-bezier(.4,0,.2,1); }
.leaflet-control-zoom { border: none !important; box-shadow: none !important; }
.leaflet-control-zoom-in, .leaflet-control-zoom-out { width: 30px !important; height: 30px !important; line-height: 28px !important; font-size: 17px !important; font-weight: 600 !important; background: rgba(20,20,23,.9) !important; background: color-mix(in srgb, var(--surface) 90%, transparent) !important; backdrop-filter: blur(8px); border: 1px solid var(--border-2) !important; color: var(--text-2) !important; display: block !important; text-align: center !important; transition: background .15s, color .15s, border-color .15s !important; border-radius: 8px !important; }
.leaflet-control-zoom-in { margin-bottom: 4px !important; }
.leaflet-control-zoom-in:hover, .leaflet-control-zoom-out:hover { background: var(--accent-muted) !important; border-color: var(--accent) !important; color: var(--accent) !important; }
.leaflet-tooltip { background:var(--surface-2) !important; border:1px solid var(--border-2) !important; color:var(--text) !important; }
@media (max-width: 600px) {
  html, body { overflow: hidden; height: 100%; }
  #map-wrap { position: fixed; top: 0; left: 0; right: 0; bottom: 0; height: auto; }
  .leaflet-control-attribution { display: none !important; }
  #bottom-nav { display: none !important; }
  .hotel-panel { display: none !important; }
  .hud-coords  { display: none; }
  .map-legend  { display: none; }
  .map-topbar { top: 0; left: 0; right: 0; padding: 10px 12px; padding-top: calc(10px + env(safe-area-inset-top)); gap: 8px; background: rgba(20,20,23,.94); background: color-mix(in srgb, var(--surface) 94%, transparent); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); border-bottom: 1px solid var(--border); border-radius: 0; }
  .map-search-wrap { flex: 1; min-width: 0; box-shadow: none; }
  .map-search-wrap input, .map-search-wrap input:focus { font-size: 16px !important; }
  .filter-btn-wrap, .map-tb-btn { flex-shrink: 0; }
  .map-filter-dropdown { width: calc(100vw - 24px); left: auto; right: 0; max-height: 55dvh; overflow-y: auto; }
  .leaflet-bottom.leaflet-right { bottom: auto !important; top: 66px !important; right: 12px !important; }
}
.map-back-btn { display: none; align-items: center; justify-content: center; width: 28px; height: 36px; flex-shrink: 0; background: none; border: none; color: var(--text-2); text-decoration: none; transition: color .15s; }
.map-back-btn:hover { color: var(--text); }
@media (max-width: 600px) { .map-back-btn { display: flex; } }
.mob-list-sheet { display: none; position: absolute; left: 0; right: 0; bottom: 0; height: calc(100% - 57px - env(safe-area-inset-top)); background: rgba(20,20,23,.98); background: color-mix(in srgb, var(--surface) 98%, transparent); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border-top-left-radius: 16px; border-top-right-radius: 16px; border: 1px solid var(--border); border-bottom: none; z-index: var(--z-dropdown); transition: transform .35s cubic-bezier(.175,.885,.32,1.1); box-shadow: 0 -6px 28px rgba(0,0,0,.4); flex-direction: column; overflow: hidden; }
@media (max-width: 600px) { .mob-list-sheet { display: flex; } }
.mob-list-sheet.state-closed { transform: translateY(calc(100% - 62px)); }
.mob-list-sheet.state-half   { transform: translateY(45%); }
.mob-list-sheet.state-full   { transform: translateY(0); }
.mob-list-sheet.no-anim      { transition: none; }
.mob-sheet-handle-area { flex-shrink: 0; padding: 10px 16px 8px; touch-action: none; user-select: none; cursor: row-resize; border-bottom: 1px solid var(--border); background: var(--surface-2); }
.mob-sheet-pill { width: 40px; height: 5px; background: var(--border-2); border-radius: 3px; margin: 0 auto 10px; }
.mob-sheet-meta { display: flex; align-items: center; justify-content: space-between; }
.mob-sheet-count { font-size: 11px; font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase; color: var(--text-2); }
.mob-sheet-hint  { font-size: 11px; color: var(--text-3); letter-spacing: .3px; }
.mob-sheet-list  { flex: 1; overflow-y: auto; -webkit-overflow-scrolling: touch; min-height: 0; position: relative; }
.mob-sheet-list::-webkit-scrollbar { display: none; }
.mob-sheet-list::after { content: ''; pointer-events: none; position: sticky; bottom: 0; left: 0; right: 0; height: 48px; display: block; background: linear-gradient(to bottom, transparent, var(--surface)); margin-top: -48px; }
`;
