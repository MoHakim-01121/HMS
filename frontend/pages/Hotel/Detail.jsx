import { useEffect, useRef, useState } from "react";
import { Menu, MenuItem } from "../../components/shadcn/list-a.jsx";
import { router } from "@inertiajs/react";
import { loadLeaflet, basemapUrl, basemapOptions } from "../../utils/leaflet.js";
import { distColor, MAP } from "../../components/mapColors.js";
import { DPage, DTop, DHead, DCard, DA, DC } from "../../components/shadcn/detail-a.jsx";
import { Popover, PopoverTrigger } from "../../components/shadcn/ui/popover.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmtDist } from "../../utils/format.js";
import { cn } from "@/lib/utils";

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
  }, [hotel, t]);

  return <div ref={ref} />;
}

// A view of a room type, as a chip; it opens Edit / Remove when editable.
const CHIP = "my-0.5 mr-1 ml-0 inline-flex h-6 phone:h-8 items-center rounded-full border-0 bg-secondary px-[9px] font-sans text-[12px] leading-[normal] font-medium whitespace-nowrap text-foreground";
const STEP_BTN = "size-10 cursor-pointer rounded-full border-0 bg-secondary font-sans text-[18px] leading-[normal] font-semibold text-foreground hover:bg-input";

function RoomCalculator({ avg }) {
  const { t } = useI18n();
  const [pilgrims, setPilgrims] = useState(35);
  const rooms = pilgrims > 0 ? Math.ceil(pilgrims / avg) : null;
  return (
    <>
      <div className="mt-4 flex flex-1 flex-wrap items-center justify-between gap-4">
        <div>
          <label htmlFor="hm-pilgrims" className="block text-[12px] font-medium text-muted-foreground">{t("Pilgrims")}</label>
          <div className="mt-1.5 flex items-center gap-1.5">
            <button type="button" className={STEP_BTN} aria-label={t("Decrease")} onClick={() => setPilgrims((v) => Math.max(1, v - 1))}>−</button>
            <input id="hm-pilgrims" type="number" min="1"
              className="box-border h-10 w-[72px] appearance-[textfield] rounded-[14px] border-2 border-border bg-card text-center font-sans text-[15px] leading-[normal] font-semibold text-foreground tabular-nums focus:border-foreground focus:outline-none [&::-webkit-inner-spin-button]:m-0 [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:m-0 [&::-webkit-outer-spin-button]:appearance-none" value={pilgrims} onChange={(e) => setPilgrims(parseInt(e.target.value, 10) || 0)} />
            <button type="button" className={STEP_BTN} aria-label={t("Increase")} onClick={() => setPilgrims((v) => v + 1)}>+</button>
          </div>
        </div>
        <div className="text-right">
          <div className="text-[12px] text-muted-foreground">{t("Rooms needed")}</div>
          <div className="mt-0.5 text-[32px] leading-[1.1] font-semibold tracking-[-0.02em] tabular-nums">
            {rooms ?? "—"} <span className="text-[14px] font-medium text-muted-foreground">{t("rooms")}</span>
          </div>
        </div>
      </div>
      <div className="mt-3.5 border-t border-border pt-3 text-[13px] text-muted-foreground">
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
  if (!canEdit) return <span className={CHIP}>{label}</span>;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className={cn(CHIP, "cursor-pointer hover:bg-input aria-expanded:bg-input")} aria-label={t("{type}, {view}", { type: rt.name, view: label })}>{label}</button>
      </PopoverTrigger>
      <Menu align="start" sideOffset={4} className="w-[180px]">
        <MenuItem onClick={() => { setOpen(false); onEdit(rt); }}>{t("Edit")}</MenuItem>
        <MenuItem danger onClick={() => { setOpen(false); onRemove(rt); }}>{t("Remove")}</MenuItem>
      </Menu>
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

      <div className={DA.pair}>
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
              <div className={DA.scroll}>
                <table data-slot="detail-table" className={DA.table}>
                  <thead><tr><th>{t("Room type")}</th><th className={DC.n}>{t("Capacity")}</th><th>{t("Views")}</th></tr></thead>
                  <tbody>
                    {shown.map((g) => (
                      <tr key={g.name} className={DA.rowMid}>
                        <td className={cn(DC.strong, "align-middle whitespace-nowrap")}>{g.name}</td>
                        <td className={cn(DC.n, "align-middle")}>{g.capacity} {t("pax")}</td>
                        <td className="py-2.5">
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
                <div className="mt-auto border-t border-border px-6 pt-1 pb-4">
                  <button type="button" className="h-9 cursor-pointer border-0 bg-transparent p-0 font-sans text-[13px] leading-[normal] font-semibold text-muted-foreground hover:text-foreground" aria-expanded={showAll} onClick={() => setShowAll((v) => !v)}>
                    {showAll ? t("Show less") : t("Show all {n} types", { n: groups.length })}
                  </button>
                </div>
              ) : null}
            </>
          ) : <div className={DA.empty}>{t("This hotel has no room types yet.")}</div>}
        </DCard>

        <DCard title={t("Location")} actions={<a href="/hotels/map/">{t("See full map")} ↗</a>}>
          {hasCoords ? (
            <>
              <div role="img" aria-label={hotel.distance_label ? t("Map: {name} is {d} from Masjid Al-Haram", { name: hotel.name, d: hotel.distance_label }) : hotel.name} className={cn(DA.map, "mt-1")}>
                <HotelMiniMap hotel={hotel} />
              </div>
              <div className="px-6 pt-3 pb-[18px] text-[13px] text-muted-foreground">
                {t("Distance measured from {ref}.", { ref: hotel.ref_label })}
              </div>
            </>
          ) : <div className={DA.empty}>{t("Location not set — add coordinates on the edit page to show this hotel on the map.")}</div>}
        </DCard>
      </div>

      <div className={hotel.avg_occupancy ? DA.pair : undefined}>
        <DCard
          title={t("Meal plans")}
          actions={canEdit ? <button type="button" onClick={() => openForm(`${base}/meal-plans/`)} onPointerEnter={() => openForm.prefetch?.(`${base}/meal-plans/`)}>{t("Manage")}</button> : null}
        >
          {mealPlans.length ? (
            <div className={DA.rows}>
              {mealPlans.map((mp) => (
                <div key={mp.code}>
                  <span className="w-8 font-mono text-[13px] font-semibold text-muted-foreground">{mp.code}</span>
                  <span>{t(mp.name)}</span>
                </div>
              ))}
            </div>
          ) : <div className={DA.empty}>{t("No meal plans set — the CL form falls back to free-text Meals for this hotel.")}</div>}
        </DCard>

        {hotel.avg_occupancy ? (
          <DCard pad title={t("Room calculator")}>
            <RoomCalculator avg={hotel.avg_occupancy} />
          </DCard>
        ) : null}
      </div>

      {hotel.note ? (
        <DCard pad title={t("Notes")}>
          <p className={DA.text}>{hotel.note}</p>
        </DCard>
      ) : null}

      {confirmDialog}
    </DPage>
  );
}

