import { useEffect, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { loadLeaflet, basemapUrl, basemapOptions } from "../../utils/leaflet.js";
import { distColor, MAP } from "../../components/mapColors.js";
import { DPage, DTop, DHead, DCard } from "../../components/shadcn/detail-a.jsx";
import { Popover, PopoverContent, PopoverTrigger } from "../../components/shadcn/ui/popover.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmtDist } from "../../utils/format.js";

// Hotel detail, the "Hotel Detail" artboard on the Record View HMS canvas:
// the head card, then Room types (one row per type, its views as chips) beside
// the map, then Meal plans beside the room calculator, then notes.

function haversine(lat1, lng1, lat2, lng2) {
  const R = 6371000, p1 = lat1 * Math.PI / 180, p2 = lat2 * Math.PI / 180;
  const dLat = (lat2 - lat1) * Math.PI / 180, dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// Leaflet map ported from hotel_detail.html; it fills its parent.
function HotelMiniMap({ hotel }) {
  const { t } = useI18n();
  const ref = useRef(null);
  useEffect(() => {
    let map, observer;
    let cancelled = false;
    loadLeaflet().then((L) => {
      if (cancelled || !ref.current) return;
      const refLL = hotel.city === "madinah" ? [24.4672, 39.6112] : [21.420324, 39.826485];
      const hotelLL = [hotel.lat, hotel.lng];
      const color = distColor(hotel.distance);

      map = L.map(ref.current, { zoomControl: false, scrollWheelZoom: false, dragging: true });
      L.control.zoom({ position: "bottomright" }).addTo(map);

      const tileUrl = () => basemapUrl(document.documentElement.getAttribute("data-theme"));
      const tileLayer = L.tileLayer(tileUrl(), basemapOptions).addTo(map);
      observer = new MutationObserver(() => tileLayer.setUrl(tileUrl()));
      observer.observe(document.documentElement, { attributeFilter: ["data-theme"] });

      const routeTip = L.tooltip({ permanent: false, opacity: 1, className: "route-dist-tip", direction: "top", offset: [0, -8] });
      const dot = (c, sz) => L.divIcon({ className: "", html: `<div style="width:${sz}px;height:${sz}px;border-radius:50%;background:${c};border:2px solid #fff;box-shadow:0 0 6px ${c}99;"></div>`, iconSize: [sz, sz], iconAnchor: [sz / 2, sz / 2] });

      // Leaflet renders a string tooltip as HTML; text nodes keep names plain.
      const text = (s) => document.createTextNode(s || "");
      L.marker(refLL, { icon: dot(MAP.yellow, 12) }).bindTooltip(text(hotel.ref_label)).addTo(map);
      if (hotel.city !== "madinah") {
        L.marker([21.4225, 39.8262], { icon: dot(MAP.red, 10) }).bindTooltip(t("Masjid Al-Haram")).addTo(map);
      }
      L.marker(hotelLL, { icon: dot(color, 12) }).bindTooltip(text(hotel.name), { direction: "top", offset: [0, -8] }).addTo(map);

      const coords = hotel.route && hotel.route.length >= 2 ? hotel.route : [refLL, hotelLL];
      map.fitBounds(coords.map((c) => L.latLng(c[0], c[1])), { padding: [40, 40] });
      const line = L.polyline(coords, { color, weight: 2.5, opacity: 0.75, dashArray: "8,5" }).addTo(map);
      line.on("mousemove", (e) => routeTip.setLatLng(e.latlng).setContent(fmtDist(haversine(refLL[0], refLL[1], e.latlng.lat, e.latlng.lng))).addTo(map));
      line.on("mouseout", () => routeTip.remove());
    });
    return () => {
      cancelled = true;
      if (observer) observer.disconnect();
      if (map) map.remove();
    };
  }, [hotel]);

  return <div ref={ref} />;
}

function RoomCalculator({ avg }) {
  const { t } = useI18n();
  const [pilgrims, setPilgrims] = useState(35);
  const rooms = pilgrims > 0 ? Math.ceil(pilgrims / avg) : null;
  return (
    <>
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap", marginTop: 16 }}>
        <div>
          <label htmlFor="hm-pilgrims" style={{ display: "block", fontSize: 12, color: "var(--muted-foreground)" }}>{t("Pilgrims")}</label>
          <div className="hm-step">
            <button type="button" aria-label={t("Decrease")} onClick={() => setPilgrims((v) => Math.max(1, v - 1))}>−</button>
            <input id="hm-pilgrims" type="number" min="1" value={pilgrims} onChange={(e) => setPilgrims(parseInt(e.target.value, 10) || 0)} />
            <button type="button" aria-label={t("Increase")} onClick={() => setPilgrims((v) => v + 1)}>+</button>
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 12, color: "var(--muted-foreground)" }}>{t("Rooms needed")}</div>
          <div style={{ marginTop: 2, fontSize: 32, fontWeight: 600, letterSpacing: "-0.02em", lineHeight: 1.1, fontVariantNumeric: "tabular-nums" }}>
            {rooms ?? "—"} <span style={{ fontSize: 14, fontWeight: 500, color: "var(--muted-foreground)" }}>{t("rooms")}</span>
          </div>
        </div>
      </div>
      <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px solid var(--border)", fontSize: 13, color: "var(--muted-foreground)" }}>
        {t("Based on an average of {avg} pax per room.", { avg })}
      </div>
    </>
  );
}

// One view of a room type: a chip that opens Edit / Remove.
function ViewChip({ rt, canEdit, onEdit, onRemove }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const label = rt.view ? t(rt.view) : t("Standard");
  if (!canEdit) return <span className="hm-chip static">{label}</span>;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className="hm-chip" aria-label={t("{type}, {view}", { type: rt.name, view: label })}>{label}</button>
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={4} className="la-menu" style={{ width: 180 }}>
        <div role="menu">
          <button type="button" role="menuitem" className="la-mi" onClick={() => { setOpen(false); onEdit(rt); }}>{t("Edit")}</button>
          <button type="button" role="menuitem" className="la-mi danger" onClick={() => { setOpen(false); onRemove(rt); }}>{t("Remove")}</button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

const SHOWN = 6;

export default function Detail({ hotel }) {
  const { t } = useI18n();
  const openForm = useFormModal();
  const perms = usePerms();
  const [confirm, confirmDialog] = useConfirm();
  const [showAll, setShowAll] = useState(false);
  const hasCoords = hotel.lat != null && hotel.lng != null;
  const canEdit = perms.can("hotels", "edit");
  const base = `/hotels/${hotel.id}`;

  const delHotel = () => confirm({
    title: t("Delete hotel"),
    message: t("Delete hotel {name}?", { name: hotel.name }),
    detail: t("This cannot be undone. Deactivate it instead to hide it from new CLs and keep its history."),
    danger: true,
    onConfirm: () => router.post(`${base}/delete/`),
  });
  const removeRoomType = (rt) => confirm({
    title: t("Remove room type"),
    message: t("Remove {name} from this hotel?", { name: rt.view ? `${rt.name}, ${t(rt.view)}` : rt.name }),
    detail: t("CLs that already use it keep their rooms unchanged."),
    confirmLabel: "Remove",
    danger: true,
    onConfirm: () => router.post(`${base}/room-types/${rt.id}/delete/`),
  });

  // One row per type name; each row of the hotel's room types is a view chip.
  const groups = [];
  for (const rt of hotel.room_types || []) {
    let g = groups.find((x) => x.name === rt.name);
    if (!g) groups.push((g = { name: rt.name, capacity: rt.capacity, items: [] }));
    g.items.push(rt);
    g.capacity = Math.max(g.capacity || 0, rt.capacity || 0);
  }
  groups.sort((a, b) => (a.capacity || 0) - (b.capacity || 0) || String(a.name).localeCompare(String(b.name)));
  const shown = showAll ? groups : groups.slice(0, SHOWN);
  const mealPlans = hotel.meal_plans || [];

  const distTone = hotel.distance == null ? undefined : hotel.distance < 500 ? "success" : hotel.distance < 1500 ? "warning" : "danger";

  return (
    <DPage>
      <style>{CSS}</style>
      <DTop href="/hotels/" />

      <DHead
        title={hotel.name}
        badge={hotel.is_active ? { label: t("Active"), tone: "green" } : { label: t("Inactive"), tone: "gray" }}
        menu={[
          canEdit && { label: t("Edit"), icon: "edit", onClick: () => openForm(`${base}/edit/`) },
          canEdit && (hotel.is_active
            ? { label: t("Deactivate"), icon: "close", onClick: () => router.post(`${base}/active/`) }
            : { label: t("Activate"), icon: "check", onClick: () => router.post(`${base}/active/`) }),
          perms.can("hotels", "delete") && { label: t("Delete hotel…"), icon: "trash", danger: true, separator: true, onClick: delHotel },
        ]}
        cols={4}
        facts={[
          { k: t("Location"), v: [hotel.city_display, hotel.area].filter(Boolean).join(" · ") },
          { k: t("Stars"), v: hotel.stars ? `${hotel.stars}★` : t("Not set") },
          { k: t("Allotment"), v: hotel.has_allotment ? t("Allotment") : t("No allotment") },
          { k: t("Distance to Masjid Al-Haram"), v: hasCoords && hotel.distance_label ? hotel.distance_label : t("Not set"), tone: hasCoords ? distTone : undefined },
          { k: t("Average occupancy"), v: hotel.avg_occupancy ? t("{n} pax/room", { n: hotel.avg_occupancy }) : t("Not set") },
        ]}
      />

      <div className="da-pair">
        <DCard
          title={t("Room types")}
          count={groups.length || null}
          actions={canEdit ? (
            <>
              <button type="button" onClick={() => openForm(`${base}/room-types/bulk/`)} onPointerEnter={() => openForm.prefetch?.(`${base}/room-types/bulk/`)}>{t("Bulk add")}</button>
              <button type="button" onClick={() => openForm(`${base}/room-types/new/`)} onPointerEnter={() => openForm.prefetch?.(`${base}/room-types/new/`)}>{t("+ Add")}</button>
            </>
          ) : null}
        >
          {groups.length ? (
            <>
              <div className="da-scroll">
                <table className="da-t mid">
                  <thead><tr><th>{t("Room type")}</th><th className="n">{t("Capacity")}</th><th>{t("Views")}</th></tr></thead>
                  <tbody>
                    {shown.map((g) => (
                      <tr key={g.name} className="mid">
                        <td className="strong" style={{ whiteSpace: "nowrap", verticalAlign: "middle" }}>{g.name}</td>
                        <td className="n" style={{ verticalAlign: "middle" }}>{g.capacity} {t("pax")}</td>
                        <td style={{ paddingTop: 10, paddingBottom: 10 }}>
                          {g.items.map((rt) => (
                            <ViewChip key={rt.id} rt={rt} canEdit={canEdit} onEdit={(x) => openForm(`${base}/room-types/${x.id}/edit/`)} onRemove={removeRoomType} />
                          ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {groups.length > SHOWN ? (
                <div style={{ marginTop: "auto", padding: "4px 24px 16px", borderTop: "1px solid var(--border)" }}>
                  <button type="button" className="hm-more" aria-expanded={showAll} onClick={() => setShowAll((v) => !v)}>
                    {showAll ? t("Show less") : t("Show all {n} types", { n: groups.length })}
                  </button>
                </div>
              ) : null}
            </>
          ) : <div className="da-empty">{t("This hotel has no room types yet.")}</div>}
        </DCard>

        <DCard title={t("Location")} actions={<a href="/hotels/map/">{t("See full map")} ↗</a>}>
          {hasCoords ? (
            <>
              <div className="da-map" role="img" aria-label={hotel.distance_label ? t("Map: {name} is {d} from Masjid Al-Haram", { name: hotel.name, d: hotel.distance_label }) : hotel.name} style={{ marginTop: 4 }}>
                <HotelMiniMap hotel={hotel} />
              </div>
              <div style={{ padding: "12px 24px 18px", fontSize: 13, color: "var(--muted-foreground)" }}>
                {t("Distance measured from {ref}.", { ref: hotel.ref_label })}
              </div>
            </>
          ) : <div className="da-empty">{t("Location not set — add coordinates on the edit page to show this hotel on the map.")}</div>}
        </DCard>
      </div>

      <div className={hotel.avg_occupancy ? "da-pair" : undefined}>
        <DCard
          title={t("Meal plans")}
          actions={canEdit ? <button type="button" onClick={() => openForm(`${base}/meal-plans/`)} onPointerEnter={() => openForm.prefetch?.(`${base}/meal-plans/`)}>{t("Manage")}</button> : null}
        >
          {mealPlans.length ? (
            <div className="da-rows">
              {mealPlans.map((mp) => (
                <div key={mp.code}>
                  <span style={{ width: 32, fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 600, color: "var(--muted-foreground)" }}>{mp.code}</span>
                  <span>{t(mp.name)}</span>
                </div>
              ))}
            </div>
          ) : <div className="da-empty">{t("No meal plans set — the CL form falls back to free-text Meals for this hotel.")}</div>}
        </DCard>

        {hotel.avg_occupancy ? (
          <DCard pad title={t("Room calculator")}>
            <RoomCalculator avg={hotel.avg_occupancy} />
          </DCard>
        ) : null}
      </div>

      {hotel.note ? (
        <DCard pad title={t("Notes")}>
          <p className="da-text">{hotel.note}</p>
        </DCard>
      ) : null}

      {confirmDialog}
    </DPage>
  );
}

const CSS = `
.hm-chip { display: inline-flex; align-items: center; height: 24px; padding: 0 9px; margin: 2px 4px 2px 0; border: 0; border-radius: 9999px; background: var(--secondary); color: var(--foreground); font: 500 12px var(--font-sans); cursor: pointer; white-space: nowrap; }
.hm-chip:hover, .hm-chip[aria-expanded="true"] { background: var(--input); }
.hm-chip.static { cursor: default; }
.hm-chip.static:hover { background: var(--secondary); }
.hm-more { height: 36px; padding: 0; border: 0; background: none; color: var(--muted-foreground); font: 600 13px var(--font-sans); cursor: pointer; }
.hm-more:hover { color: var(--foreground); }
.hm-step { margin-top: 6px; display: flex; align-items: center; gap: 6px; }
.hm-step button { width: 40px; height: 40px; border: 0; border-radius: 9999px; background: var(--secondary); color: var(--foreground); font: 600 18px var(--font-sans); cursor: pointer; }
.hm-step button:hover { background: var(--input); }
.hm-step input { width: 72px; height: 40px; box-sizing: border-box; text-align: center; border: 2px solid var(--border); border-radius: 14px; background: var(--card); color: var(--foreground); font: 600 15px var(--font-sans); font-variant-numeric: tabular-nums; -moz-appearance: textfield; }
.hm-step input::-webkit-outer-spin-button, .hm-step input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.hm-step input:focus { outline: none; border-color: var(--foreground); }
`;
