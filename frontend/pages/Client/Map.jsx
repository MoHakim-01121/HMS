import { useEffect } from "react";
import { loadLeaflet, basemapUrl, basemapOptions } from "../../utils/leaflet.js";
import { fetchJson } from "../../utils/fetchJson.js";
import { MAP } from "../../components/mapColors.js";

// Client map — imperative Leaflet app ported from the original client_map
// template. DOM mirrors the original; handlers used by inline elements are
// exposed on window for the lifetime of the page.
const FILTER = "h-[34px] cursor-pointer rounded-full border border-border bg-card px-3.5 font-[inherit] text-[12px] font-medium whitespace-nowrap text-muted-foreground transition-[background-color,color,border-color] duration-[120ms] hover:border-foreground hover:text-foreground aria-pressed:border-foreground aria-pressed:bg-secondary aria-pressed:text-foreground";

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
      function isMobile() { return window.matchMedia("(max-width: 600px), (max-height: 500px) and (pointer: coarse)").matches; }

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
        document.getElementById("map-sheet").dataset.open = "true";
        document.getElementById("map-sheet-overlay").dataset.open = "true";
      }
      const closeSheet = () => {
        delete document.getElementById("map-sheet").dataset.open;
        delete document.getElementById("map-sheet-overlay").dataset.open;
      };
      map.on("click", () => { if (isMobile()) closeSheet(); });

      const getTileUrl = () => basemapUrl(document.documentElement.getAttribute("data-theme"));
      const tileLayer = L.tileLayer(getTileUrl(), basemapOptions).addTo(map);
      const themeObserver = new MutationObserver(() => tileLayer.setUrl(getTileUrl()));
      themeObserver.observe(document.documentElement, { attributeFilter: ["data-theme"] });

      let allClients = [];
      let markers = [];

      function makeIcon(color, size) {
        return L.divIcon({ className: "", html: '<div style="width:' + size + "px;height:" + size + "px;border-radius:50%;background:" + color + ';border:2px solid rgba(255,255,255,.4);box-shadow:0 0 8px ' + color + '66;"></div>', iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
      }
      // Client is information only: markers show active/inactive, nothing
      // derived from money (no billed volume, outstanding, or score).
      function renderMarkers(clients) {
        markers.forEach((m) => map.removeLayer(m));
        markers = [];
        clients.forEach((c) => {
          const size = 14;
          const color = c.is_active ? MAP.green : MAP.none;
          const m = L.marker([c.lat, c.lng], { icon: makeIcon(color, size) });
          const waBtn = c.wa ? '<a href="https://wa.me/' + _esc(c.wa) + '" target="_blank" class="flex-1 cursor-pointer rounded-[8px] border-0 p-2 text-center font-[inherit] text-[12px] font-semibold no-underline transition-[opacity,background-color,color,border-color] duration-[120ms] border border-solid border-border bg-transparent text-muted-foreground! hover:bg-secondary hover:text-foreground!">WhatsApp</a>' : "";
          const popHtml =
            '<div>' +
              '<div class="border-b border-border pb-2.5">' +
                '<span class="mb-1 block text-[10px] font-semibold tracking-[.14em] text-muted-foreground uppercase">Client</span>' +
                '<div class="text-[15px] leading-[1.3] font-bold tracking-[-0.01em] text-foreground">' + _esc(c.name) + "</div>" +
                '<div class="mt-0.5 text-[12px] text-muted-foreground">' + _esc(c.city || "—") + (c.province ? ", " + _esc(c.province) : "") + "</div>" +
              "</div>" +
              '<div class="mt-1.5 mb-0.5">' +
                '<div class="flex items-center justify-between gap-3.5 border-b border-border py-1.5"><span class="font-mono text-[10px] font-medium tracking-[.12em] text-muted-foreground uppercase">Status</span><span class="inline-flex items-center gap-1.5 text-[13px] font-semibold whitespace-nowrap text-foreground tabular-nums"><span class="size-[7px] shrink-0 rounded-full" style="background:' + color + '"></span>' + (c.is_active ? "Active" : "Inactive") + "</span></div>" +
                (c.brand ? '<div class="flex items-center justify-between gap-3.5 border-b border-border py-1.5"><span class="font-mono text-[10px] font-medium tracking-[.12em] text-muted-foreground uppercase">Brand</span><span class="inline-flex items-center gap-1.5 text-[13px] font-semibold whitespace-nowrap text-foreground tabular-nums">' + _esc(c.brand) + "</span></div>" : "") +
                (c.pic ? '<div class="flex items-center justify-between gap-3.5 border-b border-border py-1.5"><span class="font-mono text-[10px] font-medium tracking-[.12em] text-muted-foreground uppercase">PIC</span><span class="inline-flex items-center gap-1.5 text-[13px] font-semibold whitespace-nowrap text-foreground tabular-nums">' + _esc(c.pic) + "</span></div>" : "") +
              "</div>" +
              '<div class="mt-3 flex gap-2">' +
                '<a href="' + c.url + '" class="flex-1 cursor-pointer rounded-[8px] border-0 p-2 text-center font-[inherit] text-[12px] font-semibold no-underline transition-[opacity,background-color,color,border-color] duration-[120ms] bg-primary text-primary-foreground! hover:opacity-90">Detail</a>' + waBtn +
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
        document.querySelectorAll("[data-filter]").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
        let filtered = allClients;
        if (f === "active") filtered = allClients.filter((c) => c.is_active);
        if (f === "inactive") filtered = allClients.filter((c) => !c.is_active);
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
    <div id="map-wrap" data-map="clients" className="relative h-[calc(100vh-var(--topbar-h,56px))] overflow-hidden phone:fixed phone:inset-0 phone:h-auto">
      <div id="map" className="absolute inset-0 isolate" />

      <div className="absolute top-3 left-3 z-(--z-overlay) flex max-w-[calc(100%-24px)] flex-wrap gap-1.5 phone:inset-x-0 phone:top-0 phone:max-w-none phone:flex-nowrap phone:overflow-x-auto phone:border-b phone:border-border phone:bg-popover phone:px-3 phone:pt-[calc(10px+env(safe-area-inset-top))] phone:pb-2.5 phone:[scrollbar-width:none] phone:[&::-webkit-scrollbar]:hidden">
        <a href="/clients/" className="flex size-[34px] shrink-0 items-center justify-center rounded-full border border-border bg-card text-muted-foreground no-underline transition-[color,border-color] duration-150 hover:border-foreground hover:text-foreground" title="Back to client list">
          <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
        </a>
        <button type="button" className={FILTER} aria-pressed="true" data-filter="all" onClick={(e) => window.setFilter?.("all", e.currentTarget)}>All</button>
        <button type="button" className={FILTER} aria-pressed="false" data-filter="active" onClick={(e) => window.setFilter?.("active", e.currentTarget)}>Active</button>
        <button type="button" className={FILTER} aria-pressed="false" data-filter="inactive" onClick={(e) => window.setFilter?.("inactive", e.currentTarget)}>Inactive</button>
      </div>


      <div id="map-sheet-overlay" className="absolute inset-0 z-(--z-base) hidden bg-scrim-soft data-open:block" onClick={() => window.closeSheet?.()} />
      <div id="map-sheet" className="absolute inset-x-0 bottom-0 z-(--z-dropdown) hidden translate-y-[110%] rounded-t-[20px] border border-b-0 border-border bg-popover pb-[env(safe-area-inset-bottom)] shadow-sheet transition-[translate] duration-300 ease-drawer data-open:translate-y-0 phone:block">
        <div className="mx-auto mt-2.5 mb-1 h-[5px] w-10 cursor-pointer rounded-[3px] bg-border" onClick={() => window.closeSheet?.()} />
        <div id="map-sheet-body" className="px-5 pt-1.5 pb-6" />
      </div>
    </div>
  );
}

