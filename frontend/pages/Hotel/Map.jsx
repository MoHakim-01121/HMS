import { useEffect } from "react";
import { loadLeaflet, basemapUrl, basemapOptions } from "../../utils/leaflet.js";
import { fetchJson } from "../../utils/fetchJson.js";
import { distColor } from "../../components/mapColors.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmtDist } from "../../utils/format.js";
import { cn } from "@/lib/utils";

// Hotel map — full imperative Leaflet app ported from the original hotel_map
// template. The DOM below mirrors the original (same ids/classes); the script
// runs once on mount and exposes the handlers it needs on window so the
// dynamically-rendered hotel cards (built via innerHTML) can call them.
// The map's own chrome: the filter menu, legend and hotel list.
const SECTION = "border-b border-border px-3.5 pt-2.5 pb-0.5 [&>div]:mb-1.5";
const SECTION_TITLE = "text-[10px] font-bold tracking-[1.2px] text-muted-foreground uppercase";
const DIVIDER = "my-1.5 h-px bg-border";
const OPTION = "flex cursor-pointer items-center gap-[9px] px-3.5 py-1.5 text-[13px] font-medium text-muted-foreground transition-[background-color,color] duration-100 hover:bg-secondary hover:text-foreground [&_input]:size-3.5 [&_input]:cursor-pointer [&_input]:accent-primary";
const RADIO = cn(OPTION, "has-checked:font-semibold has-checked:text-foreground");
const CHECK = OPTION;
const SWATCH = "inline-block size-2 shrink-0 rounded-[2px]";
const STARS = "text-[12px] text-warning-text";
const TOGGLE_ROW = "group/tg flex w-full cursor-pointer items-center justify-between border-0 bg-transparent px-3.5 py-2 text-left [font:inherit] text-inherit focus-visible:rounded-[6px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring";
const TOGGLE = "relative h-[17px] w-8 shrink-0 rounded-[9px] bg-input transition-[background-color] duration-150 group-aria-checked/tg:bg-primary after:absolute after:top-[3px] after:left-[3px] after:size-[11px] after:rounded-full after:bg-primary-foreground after:transition-[left] after:duration-150 after:content-[''] group-aria-checked/tg:after:left-[18px]";
const LEG_SECTION = "mt-[9px] mb-[5px] text-[10px] font-bold tracking-[1.2px] text-muted-foreground uppercase first:mt-0";
const LEG_ROW = "mb-1 flex items-center gap-2 last:mb-0";
const COUNT = "text-[11px] font-bold tracking-[1.2px] text-muted-foreground uppercase";

const Loading = () => (
  <div className="flex items-center justify-center gap-[5px] px-5 py-12">
    {[0, 1, 2].map((i) => <span key={i} className="size-1.5 animate-dot-pulse rounded-full bg-primary [&:nth-child(2)]:[animation-delay:.2s] [&:nth-child(3)]:[animation-delay:.4s]" />)}
  </div>
);

export default function HotelMap() {
  const { t } = useI18n();
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

      const getTileUrl = () => basemapUrl(document.documentElement.getAttribute("data-theme"));
      const tileLayer = L.tileLayer(getTileUrl(), basemapOptions).addTo(map);
      const themeObserver = new MutationObserver(() => tileLayer.setUrl(getTileUrl()));
      themeObserver.observe(document.documentElement, { attributeFilter: ["data-theme"] });

      const refIcon = () => L.divIcon({ className: "", html: '<div style="width:12px;height:12px;border-radius:3px;background:var(--primary);border:2px solid rgba(255,255,255,.6);box-shadow:0 0 8px var(--primary);"></div>', iconSize: [12, 12], iconAnchor: [6, 6] });
      const mosqueIcon = () => L.divIcon({ className: "", html: '<div style="width:10px;height:10px;border-radius:3px;background:var(--danger);border:2px solid rgba(255,255,255,.5);box-shadow:0 0 6px var(--danger);"></div>', iconSize: [10, 10], iconAnchor: [5, 5] });
      L.marker(HARAM, { icon: refIcon() }).bindTooltip(t("Pelataran Al-Haram")).addTo(map);
      L.marker(HARAM_INFO, { icon: mosqueIcon() }).bindTooltip(t("Masjid Al-Haram")).addTo(map);
      L.marker(NABAWI, { icon: mosqueIcon() }).bindTooltip(t("Masjid Nabawi")).addTo(map);

      let allHotels = [];
      const markerGroup = L.layerGroup().addTo(map);
      const routeGroup = L.layerGroup().addTo(map);
      let _renderCycle = 0;
      const routeTip = L.tooltip({ permanent: false, opacity: 1, className: "route-dist-tip", direction: "top", offset: [0, -10] });
      let routesVisible = !isMobile(), avgOnly = false, activeMarker = null, markerMap = {}, activeCardPk = null;

      const haversine = (lat1, lng1, lat2, lng2) => { const R = 6371000, p1 = lat1 * Math.PI / 180, p2 = lat2 * Math.PI / 180, dLat = (lat2 - lat1) * Math.PI / 180, dLng = (lng2 - lng1) * Math.PI / 180; const a = Math.sin(dLat / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dLng / 2) ** 2; return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)); };
      const distClass = (d) => (d === null ? "text-muted-foreground" : d < 500 ? "text-success-text" : d < 1500 ? "text-warning-text" : "text-danger-text");
      const starsHtml = (n) => "★".repeat(n);
      const starSize = (s) => (s >= 5 ? 14 : s >= 4 ? 12 : 10);

      function updateHud(lat, lng) {
        const el = document.getElementById("hud-coords");
        el.textContent = Math.abs(lat).toFixed(4) + "°" + (lat >= 0 ? "N" : "S") + "  " + Math.abs(lng).toFixed(4) + "°" + (lng >= 0 ? "E" : "W");
        el.dataset.active = "true";
      }

      function hotelIcon(color, size, pulse) {
        const s = Math.round(size * 0.72), hs = Math.round(s / 2), half = Math.round(size / 2);
        const dot = '<div style="position:absolute;top:50%;left:50%;width:' + s + "px;height:" + s + "px;margin-top:-" + hs + "px;margin-left:-" + hs + "px;border-radius:3px;background:" + color + ';border:1.5px solid rgba(255,255,255,.45);box-shadow:0 0 6px ' + color + '99;"></div>';
        if (pulse) {
          const cSize = size + 44, cHalf = Math.round(cSize / 2);
          return L.divIcon({ className: "", html:
            '<div style="position:relative;width:' + cSize + "px;height:" + cSize + 'px;">' +
            '<div style="position:absolute;top:50%;left:50%;width:' + size + "px;height:" + size + "px;margin-top:-" + half + "px;margin-left:-" + half + "px;border-radius:50%;border:1.5px solid " + color + ';" class="animate-pulse-ring"></div>' +
            '<div style="position:absolute;top:50%;left:50%;width:' + s + "px;height:" + s + "px;margin-top:-" + hs + "px;margin-left:-" + hs + "px;border-radius:3px;background:" + color + ';border:1.5px solid rgba(255,255,255,.55);box-shadow:0 0 10px ' + color + 'BB;"></div>' +
            "</div>", iconSize: [cSize, cSize], iconAnchor: [cHalf, cHalf] });
        }
        return L.divIcon({ className: "", html: '<div style="position:relative;width:' + size + "px;height:" + size + 'px;">' + dot + "</div>", iconSize: [size, size], iconAnchor: [half, half] });
      }

      function buildPopup(h) {
        const dist = h.distance_label || "—";
        const row = '<div class="mb-1 flex items-center justify-between text-[11px]"><span class="text-[10px] font-semibold tracking-[.5px] text-muted-foreground uppercase">';
        const val = "font-bold tabular-nums ";
        const avgRow = h.avg ? row + t("Avg") + '</span><span class="' + val + 'text-foreground">' + _esc(h.avg) + " pax/room</span></div>" : "";
        return '<div class="mb-0.5 text-[13px] font-bold text-foreground">' + _esc(h.name) + '</div><div class="mb-1.5 text-[11px] tracking-[2px] text-warning-text">' + starsHtml(h.stars) + "</div>" + (h.area ? '<div class="mb-1.5 text-[10.5px] text-muted-foreground">' + _esc(h.area) + "</div>" : "") + row + t("Distance") + '</span><span class="' + val + (h.distance === null ? "text-foreground" : distClass(h.distance)) + '">' + dist + "</span></div>" + avgRow;
      }

      const getCityFilter = () => { const el = document.querySelector('input[name="fp-city"]:checked'); return el ? el.value : "all"; };
      const getDistFilters = () => Array.from(document.querySelectorAll('#filter-dropdown input[type=checkbox][value=dekat],#filter-dropdown input[type=checkbox][value=sedang],#filter-dropdown input[type=checkbox][value=jauh]')).filter((cb) => cb.checked).map((cb) => cb.value);
      const getStarsFilters = () => Array.from(document.querySelectorAll('input[name="fp-stars"]:checked')).map((cb) => parseInt(cb.value, 10));
      function countActiveFilters() { let n = 0; if (getCityFilter() !== "all") n++; if (getDistFilters().length > 0) n++; if (getStarsFilters().length > 0) n++; if (avgOnly) n++; return n; }
      function updateFilterBadge() { const n = countActiveFilters(), badge = document.getElementById("filter-badge"), btn = document.getElementById("filter-open-btn"); badge.style.display = n > 0 ? "inline" : "none"; if (n > 0) badge.textContent = n; btn.toggleAttribute("data-active", n > 0); }
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
      
      function saveFilters() { try { localStorage.setItem("hmap_filters", JSON.stringify({ city: getCityFilter(), dists: getDistFilters(), stars: getStarsFilters(), avg: avgOnly, q: document.getElementById("hotel-search").value || "" })); } catch { /* noop */ } }
      function loadFilters() {
        try {
          const s = localStorage.getItem("hmap_filters"); if (!s) return;
          const f = JSON.parse(s);
          if (f.city) { const r = document.querySelector('input[name="fp-city"][value="' + f.city + '"]'); if (r) r.checked = true; }
          (f.dists || []).forEach((v) => { const cb = document.querySelector('#filter-dropdown input[value="' + v + '"]'); if (cb) cb.checked = true; });
          (f.stars || []).forEach((v) => { const cb = document.querySelector('input[name="fp-stars"][value="' + v + '"]'); if (cb) cb.checked = true; });
          avgOnly = !!f.avg; document.getElementById("tg-avg").setAttribute("aria-checked", String(avgOnly));
          if (f.q) { const inp = document.getElementById("hotel-search"); if (inp) inp.value = f.q; syncSearchClear(); }
        } catch { /* noop */ }
      }

      function applyFilters() {
        const city = getCityFilter();
        saveFilters();
        if (city === "makkah") map.flyTo(HARAM, 14, { duration: 1 });
        else if (city === "madinah") map.flyTo(NABAWI, 14, { duration: 1 });
        Object.values(markerMap).forEach((e) => e.marker.setOpacity(0));
        const filtered = getFiltered();
        setTimeout(() => { renderMarkers(filtered); updateCounter(filtered.length); renderPanel(filtered); }, 120);
        updateFilterBadge();
      }
      function updateCounter(n) { const label = n + " " + t("Hotel"); document.getElementById("hp-count").textContent = label; const mc = document.getElementById("mob-sheet-count"); if (mc) mc.textContent = label; }

      const toggleLegend = () => { const body = document.getElementById("leg-body"); const hidden = body.toggleAttribute("data-collapsed"); document.getElementById("leg-toggle").setAttribute("aria-expanded", String(!hidden)); };

      let filterOpen = false;
      const toggleFilter = () => { filterOpen = !filterOpen; document.getElementById("filter-dropdown").toggleAttribute("data-open", filterOpen); document.getElementById("filter-open-btn").toggleAttribute("data-active", filterOpen || countActiveFilters() > 0); };
      function closeFilter() { filterOpen = false; const dd = document.getElementById("filter-dropdown"); if (dd) dd.removeAttribute("data-open"); const btn = document.getElementById("filter-open-btn"); if (btn) btn.toggleAttribute("data-active", countActiveFilters() > 0); }

      const toggleRoutes = () => { routesVisible = !routesVisible; document.getElementById("tg-route").setAttribute("aria-checked", String(routesVisible)); if (routesVisible) routeGroup.addTo(map); else map.removeLayer(routeGroup); };
      const toggleAvg = () => { avgOnly = !avgOnly; document.getElementById("tg-avg").setAttribute("aria-checked", String(avgOnly)); applyFilters(); };
      const resetFilters = () => { document.querySelector('input[name="fp-city"][value="all"]').checked = true; document.querySelectorAll("#filter-dropdown input[type=checkbox]").forEach((cb) => { cb.checked = false; }); avgOnly = false; document.getElementById("tg-avg").setAttribute("aria-checked", "false"); document.getElementById("hotel-search").value = ""; applyFilters(); };

      function buildCardHtml(h) {
        const color = distColor(h.distance), dc = distClass(h.distance);
        const dist = h.distance_label || "—";
        return '<div class="cursor-pointer border-b border-border px-3.5 py-2.5 transition-[background-color] duration-[120ms] hover:bg-secondary data-active:bg-secondary data-active:shadow-[inset_0_0_0_1px_var(--input)]" data-pk="' + h.pk + '" onclick="selectCard(' + h.pk + ')" onmouseenter="hoverCard(' + h.pk + ')" onmouseleave="hoverCard(null)">' +
          '<div class="flex items-center gap-[9px]">' +
          '<div class="size-2 shrink-0 rounded-[2px]" style="background:' + color + ';"></div>' +
          '<span class="min-w-0 flex-1 truncate text-[13px] leading-[1.3] font-semibold text-foreground">' + _esc(h.name) + "</span>" +
          '<span class="shrink-0 text-[11px] font-bold tracking-[.3px] tabular-nums ' + dc + '">' + dist + "</span>" +
          '<a href="' + h.url + '" class="ml-0.5 flex size-6 shrink-0 items-center justify-center rounded-[6px] text-muted-foreground no-underline transition-[color,background-color] duration-150 hover:bg-secondary hover:text-primary" onclick="event.stopPropagation()" title="' + t("Hotel details") + '">' +
          '<svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg>' +
          "</a></div>" +
          '<div class="mt-0.5 truncate pl-[17px] text-[10.5px] tracking-[.3px] text-muted-foreground"><span class="tracking-[1px] text-warning-text">' + starsHtml(h.stars) + "</span>" + (h.area ? " · " + _esc(h.area) : "") + "</div></div>";
      }
      function renderPanel(hotels) {
        const empty = '<div class="px-5 pt-12 pb-10 text-center"><div class="mb-4 text-[13px] text-muted-foreground">' + t("No matching hotels") + '</div><button onclick="resetFilters()" class="cursor-pointer rounded-[8px] border border-input bg-secondary px-4 py-2 font-[inherit] text-[12px] font-semibold text-muted-foreground">' + t("Reset Filter") + "</button></div>";
        const html = hotels.length === 0 ? empty : hotels.map((h) => buildCardHtml(h)).join("");
        if (!isMobile()) document.getElementById("hotel-list").innerHTML = html;
        const mobList = document.getElementById("mob-sheet-list");
        if (mobList) mobList.innerHTML = html;
      }

      let panelCollapsed = false;
      function updateZoomOffset() { const el = document.querySelector(".leaflet-bottom.leaflet-right"); if (!el || isMobile()) return; el.style.right = (panelCollapsed ? "10" : "316") + "px"; }
      const togglePanel = () => { panelCollapsed = !panelCollapsed; document.getElementById("hotel-panel").toggleAttribute("data-collapsed", panelCollapsed); updateZoomOffset(); };

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
          document.querySelectorAll("[data-pk]").forEach((el) => delete el.dataset.active);
          if (activeMarker) { const ad = activeMarker._hotelData; activeMarker.setIcon(hotelIcon(distColor(ad.distance), activeMarker._starSize || 10)); activeMarker = null; }
          applyMarkerOpacity(null); activeCardPk = null; return;
        }
        document.querySelectorAll("[data-pk]").forEach((el) => delete el.dataset.active);
        document.querySelectorAll('[data-pk="' + pk + '"]').forEach((card) => { card.dataset.active = "true"; if (!isMobile() && card.offsetParent !== null) card.scrollIntoView({ behavior: "smooth", block: "nearest" }); });
        activeCardPk = pk;
      };

      function renderMarkers(hotels) {
        routeTip.remove(); markerGroup.clearLayers(); routeGroup.clearLayers(); markerMap = {}; activeMarker = null; activeCardPk = null;
        document.querySelectorAll("[data-pk]").forEach((el) => delete el.dataset.active);
        const cycle = ++_renderCycle;
        hotels.forEach((h) => {
          const color = distColor(h.distance), refLL = h.city === "madinah" ? NABAWI : HARAM, sz = starSize(h.stars);
          const m = L.marker([h.lat, h.lng], { icon: hotelIcon(color, sz) });
          m._starSize = sz; m._hotelData = h;
          m.bindTooltip(_esc(h.name), { permanent: false, direction: "top", offset: [0, -10], opacity: 0.95, className: "route-dist-tip" });
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
            let _sheetLocked = false;
      function setSheetState(state, force) {
        if (_sheetLocked && !force) return;
        _sheetState = state;
        const sheet = document.getElementById("mob-list-sheet"); if (!sheet) return;
        sheet.dataset.state = state;
        const hint = document.getElementById("mob-sheet-hint");
        if (hint) hint.textContent = state === "closed" ? t("▲ Open list") : state === "full" ? t("▼ Close") : t("▲▼ Drag");
        if ((state === "half" || state === "full") && activeCardPk) { setTimeout(() => { const card = document.querySelector('#mob-sheet-list [data-pk="' + activeCardPk + '"]'); if (card) card.scrollIntoView({ block: "nearest" }); }, 320); }
      }
      function lockSheet(ms) { _sheetLocked = true; setTimeout(() => { _sheetLocked = false; }, ms || 400); }

      let _searchTimer = null;
      const debounceSearch = () => { syncSearchClear(); clearTimeout(_searchTimer); _searchTimer = setTimeout(applyFilters, 200); };
      function syncSearchClear() { const inp = document.getElementById("hotel-search"); const btn = document.getElementById("search-clear-btn"); if (btn) btn.style.display = inp && inp.value ? "flex" : "none"; if (isMobile() && inp && inp.value && _sheetState === "closed") setSheetState("half"); }
      const clearSearch = () => {
        const inp = document.getElementById("hotel-search"); if (inp) { inp.value = ""; inp.focus(); }
        syncSearchClear(); applyFilters();
        if (activeMarker) { const ad = activeMarker._hotelData; activeMarker.setIcon(hotelIcon(distColor(ad.distance), activeMarker._starSize || 10)); activeMarker = null; }
        document.querySelectorAll("[data-pk]").forEach((el) => delete el.dataset.active); activeCardPk = null;
      };

      map.on("click", () => {
        closeFilter();
        if (activeMarker) { const ad = activeMarker._hotelData; activeMarker.setIcon(hotelIcon(distColor(ad.distance), activeMarker._starSize || 10)); activeMarker = null; }
        if (activeCardPk) { document.querySelectorAll("[data-pk]").forEach((el) => delete el.dataset.active); activeCardPk = null; applyMarkerOpacity(null); }
        if (isMobile()) { if (_sheetState === "full") setSheetState("half"); else if (_sheetState === "half") setSheetState("closed"); }
      });

      (function initSheetDrag() {
        const handle = document.getElementById("mob-sheet-handle");
        const sheet = document.getElementById("mob-list-sheet");
        if (!handle || !sheet) return;
        let startY = 0;
        handle.addEventListener("touchstart", (e) => { startY = e.touches[0].clientY; sheet.dataset.dragging = "true"; }, { passive: true });
        handle.addEventListener("touchend", (e) => {
          delete sheet.dataset.dragging;
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

      fetchJson("/hotels/map/data/")
        .then((data) => {
          if (disposed) return;
          allHotels = data.hotels;
          loadFilters();
          updateZoomOffset();
          const filtered = getFiltered();
          renderMarkers(filtered); updateCounter(filtered.length); renderPanel(filtered);
          updateFilterBadge();
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
  }, [t]);

  return (
    <div id="map-wrap" data-map="hotels" className="relative h-[calc(100vh-48px)] overflow-hidden max-[600px]:fixed max-[600px]:inset-0 max-[600px]:h-auto">
      <div id="map" className="absolute inset-0 isolate" />

      <div className="absolute top-3 left-3 z-(--z-overlay) flex items-center gap-2 max-[600px]:inset-x-0 max-[600px]:top-0 max-[600px]:rounded-none max-[600px]:border-b max-[600px]:border-border max-[600px]:bg-card max-[600px]:px-3 max-[600px]:pt-[calc(10px+env(safe-area-inset-top))] max-[600px]:pb-2.5">
        <a href="/hotels/" className="flex size-9 shrink-0 items-center justify-center rounded-full border border-border bg-card text-muted-foreground no-underline transition-[color,border-color] duration-150 hover:border-foreground hover:text-foreground" title={t("Back to hotel list")}>
          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
        </a>
        <div className="group/search flex h-9 min-w-[220px] items-center gap-2 rounded-[20px] border border-input bg-card px-3 shadow-[0_1px_2px_rgb(0_0_0/.06),0_4px_12px_rgb(0_0_0/.06)] focus-within:border-primary focus-within:shadow-[0_0_0_3px_color-mix(in_oklch,var(--ring)_35%,transparent)] max-[600px]:min-w-0 max-[600px]:flex-1 max-[600px]:shadow-none">
          <svg className="shrink-0 text-muted-foreground group-focus-within/search:text-primary" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" /><path strokeLinecap="round" d="M21 21l-4.35-4.35" /></svg>
          <input type="text" id="hotel-search" placeholder={t("Search hotel or area...")} onInput={() => window.debounceSearch?.()}
            className="m-0 size-full appearance-none rounded-none border-0 bg-transparent p-0 font-[inherit] text-[13px] text-foreground shadow-none outline-none [-webkit-tap-highlight-color:transparent] placeholder:text-muted-foreground focus:border-0 focus:shadow-none max-[600px]:text-[16px]" />
          <button id="search-clear-btn" onClick={() => window.clearSearch?.()} className="hidden shrink-0 cursor-pointer border-0 bg-transparent p-0 leading-none text-muted-foreground" title={t("Clear")}>
            <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div className="relative max-[600px]:shrink-0">
          <button id="filter-open-btn" onClick={() => window.toggleFilter?.()}
            className="flex h-9 cursor-pointer items-center gap-1.5 rounded-[20px] border border-input bg-card px-4 text-[12px] font-semibold whitespace-nowrap text-foreground transition-all duration-150 hover:border-muted-foreground data-active:border-primary data-active:bg-secondary data-active:text-primary max-[600px]:shrink-0">
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M3 4h18M7 8h10M10 12h4" /></svg>
            {t("Filter")}
            <span id="filter-badge" className="hidden rounded-[8px] bg-primary px-1.5 py-px text-[10px] font-extrabold text-primary-foreground" />
          </button>

          <div id="filter-dropdown" className="pointer-events-none absolute top-[calc(100%+6px)] left-0 z-(--z-overlay) w-60 origin-top-left -translate-y-1.5 scale-[.98] overflow-hidden rounded-[12px] border border-input bg-card pt-1 opacity-0 shadow-[0_4px_24px_rgb(0_0_0/.12)] transition-[opacity,translate,scale] duration-[180ms] data-open:pointer-events-auto data-open:translate-y-0 data-open:scale-100 data-open:opacity-100 max-[600px]:right-0 max-[600px]:left-auto max-[600px]:max-h-[55dvh] max-[600px]:w-[calc(100vw-24px)] max-[600px]:overflow-y-auto">
            <div className={SECTION}><div className={SECTION_TITLE}>{t("City")}</div></div>
            <label className={RADIO}><input type="radio" name="fp-city" value="all" defaultChecked onChange={() => window.applyFilters?.()} /> {t("All Cities")}</label>
            <label className={RADIO}><input type="radio" name="fp-city" value="makkah" onChange={() => window.applyFilters?.()} /> Makkah</label>
            <label className={RADIO}><input type="radio" name="fp-city" value="madinah" onChange={() => window.applyFilters?.()} /> Madinah</label>
            <div className={DIVIDER} />
            <div className={SECTION}><div className={SECTION_TITLE}>{t("Distance to Mosque")}</div></div>
            <label className={CHECK}><input type="checkbox" value="dekat" onChange={() => window.applyFilters?.()} /><span className={cn(SWATCH, "bg-success")} /> {t("≤ 500 M")}</label>
            <label className={CHECK}><input type="checkbox" value="sedang" onChange={() => window.applyFilters?.()} /><span className={cn(SWATCH, "bg-warning")} /> {t("500 M – 1.5 KM")}</label>
            <label className={CHECK}><input type="checkbox" value="jauh" onChange={() => window.applyFilters?.()} /><span className={cn(SWATCH, "bg-danger")} /> {t("> 1.5 KM")}</label>
            <div className={DIVIDER} />
            <div className={SECTION}><div className={SECTION_TITLE}>{t("Stars")}</div></div>
            <label className={CHECK}><input type="checkbox" name="fp-stars" value="3" onChange={() => window.applyFilters?.()} /><span className={STARS}>★★★</span></label>
            <label className={CHECK}><input type="checkbox" name="fp-stars" value="4" onChange={() => window.applyFilters?.()} /><span className={STARS}>★★★★</span></label>
            <label className={CHECK}><input type="checkbox" name="fp-stars" value="5" onChange={() => window.applyFilters?.()} /><span className={STARS}>★★★★★</span></label>
            <div className={DIVIDER} />
            <button type="button" id="tg-avg" role="switch" aria-checked="false" className={TOGGLE_ROW} onClick={() => window.toggleAvg?.()}><span className="text-[13px] text-muted-foreground">{t("Has Avg / Capacity")}</span><span className={TOGGLE} /></button>
            <button type="button" id="tg-route" role="switch" aria-checked="true" className={TOGGLE_ROW} onClick={() => window.toggleRoutes?.()}><span className="text-[13px] text-muted-foreground">{t("Show Routes")}</span><span className={TOGGLE} /></button>
            <div className="px-3.5 pt-2.5 pb-3"><button type="button" className="w-full cursor-pointer rounded-[8px] border border-input bg-transparent p-2 text-[12px] font-semibold text-muted-foreground transition-all duration-150 hover:border-muted-foreground" onClick={() => window.resetFilters?.()}>{t("Reset Filter")}</button></div>
          </div>
        </div>
      </div>

      <div id="hud-coords" className="pointer-events-none absolute bottom-5 left-3 z-(--z-overlay) rounded-[8px] border border-border bg-card px-2.5 py-[5px] text-[10.5px] tracking-[.6px] text-muted-foreground tabular-nums transition-[color,border-color] duration-200 data-active:border-primary data-active:text-primary max-[600px]:hidden">---.-°N  ---.-°E</div>

      <div className="absolute top-[60px] left-3 z-(--z-overlay) min-w-[140px] rounded-[10px] border border-border bg-card px-3.5 py-2.5 text-[11px] text-muted-foreground max-[600px]:hidden">
        <button type="button" id="leg-toggle" aria-expanded="true" aria-controls="leg-body" onClick={() => window.toggleLegend?.()}
          className="group/leg mb-2 flex w-full cursor-pointer items-center justify-between border-0 bg-transparent p-0 [font:inherit] text-inherit select-none focus-visible:rounded-[6px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring">
          <span className={SECTION_TITLE}>{t("Legend")}</span>
          <svg className="text-muted-foreground transition-[rotate] duration-200 group-aria-[expanded=false]/leg:-rotate-180" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" /></svg>
        </button>
        <div id="leg-body" className="data-collapsed:hidden">
          <div className={LEG_SECTION}>{t("Distance to Mosque")}</div>
          <div className={LEG_ROW}><div className={cn(SWATCH, "bg-success")} /> {t("≤ 500 M")}</div>
          <div className={LEG_ROW}><div className={cn(SWATCH, "bg-warning")} /> {t("500 M – 1.5 KM")}</div>
          <div className={LEG_ROW}><div className={cn(SWATCH, "bg-danger")} /> {t("> 1.5 KM")}</div>
          <div className={LEG_SECTION}>{t("Reference Points")}</div>
          <div className={LEG_ROW}><div className={cn(SWATCH, "bg-primary")} /> Al-Haram Plaza</div>
          <div className={LEG_ROW}><div className={cn(SWATCH, "bg-danger")} /> {t("Mosque")}</div>
        </div>
      </div>

      <div id="mob-list-sheet" data-state="closed"
        className="absolute inset-x-0 bottom-0 z-(--z-dropdown) hidden h-[calc(100%-57px-env(safe-area-inset-top))] flex-col overflow-hidden rounded-t-2xl border border-b-0 border-border bg-card shadow-sheet transition-[translate] duration-[320ms] ease-drawer data-dragging:transition-none data-[state=closed]:translate-y-[calc(100%-62px)] data-[state=full]:translate-y-0 data-[state=half]:translate-y-[45%] max-[600px]:flex">
        <div id="mob-sheet-handle" className="shrink-0 cursor-row-resize touch-none border-b border-border bg-secondary px-4 pt-2.5 pb-2 select-none">
          <div className="mx-auto mb-2.5 h-[5px] w-10 rounded-[3px] bg-input" />
          <div className="flex items-center justify-between">
            <span id="mob-sheet-count" className={COUNT}>{t("0 Hotel")}</span>
            <span id="mob-sheet-hint" className="text-[11px] tracking-[.3px] text-muted-foreground">{t("▲ Open list")}</span>
          </div>
        </div>
        <div id="mob-sheet-list" className="relative min-h-0 flex-1 overflow-y-auto [-webkit-overflow-scrolling:touch] after:pointer-events-none after:sticky after:inset-x-0 after:bottom-0 after:-mt-12 after:block after:h-12 after:bg-linear-to-b after:from-transparent after:to-card after:content-[''] [&::-webkit-scrollbar]:hidden">
          <Loading />
        </div>
      </div>

      <div id="hotel-panel" className="group/panel absolute top-0 right-0 bottom-0 z-(--z-dropdown) flex w-[300px] flex-col overflow-visible border-l border-border bg-card transition-[translate] duration-250 ease-[cubic-bezier(.4,0,.2,1)] data-collapsed:translate-x-[300px] max-[600px]:hidden!">
        <button onClick={() => window.togglePanel?.()} title={t("Hide / show panel")}
          className="absolute top-1/2 -left-[26px] z-1 flex h-[52px] w-[26px] -translate-y-1/2 cursor-pointer items-center justify-center rounded-l-[8px] border border-r-0 border-border bg-card text-muted-foreground transition-[color] duration-150 hover:text-foreground">
          <svg className="transition-[rotate] duration-250 ease-[cubic-bezier(.4,0,.2,1)] group-data-collapsed/panel:rotate-180" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M9 18l6-6-6-6" /></svg>
        </button>
        <div className="relative z-1 flex flex-1 flex-col overflow-hidden">
          <div className="shrink-0 border-b border-border px-3.5 pt-3.5 pb-2.5"><div className="flex items-center justify-between"><span id="hp-count" className={COUNT}>{t("0 Hotel")}</span></div></div>
          <div id="hotel-list" className="min-h-0 flex-1 overflow-y-auto [&::-webkit-scrollbar]:w-[3px] [&::-webkit-scrollbar-thumb]:rounded-[2px] [&::-webkit-scrollbar-thumb]:bg-input [&::-webkit-scrollbar-track]:bg-transparent">
            <Loading />
          </div>
        </div>
      </div>
    </div>
  );
}
