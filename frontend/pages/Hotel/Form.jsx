import { useForm } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import { FormA, Field, Picker, TextIn, NoteField, Foot, FA, SwitchRow } from "../../components/shadcn/form-a.jsx";
import { useI18n } from "../../utils/i18n.jsx";

const AREAS = ["Misfalah", "Ajyad", "Ajyad Selatan", "Ajyad Utara", "Syisyah", "Kudai", "Jarwal", "Aziziyah", "Ibrahim Khalil", "Nakasa", "Bakhutmaz"];

// The reference points hw/models/hotel.py measures distance_to_haram from.
const REF = {
  makkah: { lat: 21.420324, lng: 39.826485, label: "Masjid Al-Haram" },
  madinah: { lat: 24.4672, lng: 39.6112, label: "Masjid Nabawi" },
};

// "21.41816, 39.82877", or a Google Maps link that carries the point
// (…/@21.41,39.82,17z, …?q=21.41,39.82, …!3d21.41!4d39.82). Null when unreadable.
export function parseCoords(raw) {
  const s = String(raw || "");
  const m = s.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/) || s.match(/@(-?\d+\.\d+),\s*(-?\d+\.\d+)/)
    || s.match(/(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)/);
  if (!m) return null;
  const lat = Number(m[1]), lng = Number(m[2]);
  return Math.abs(lat) <= 90 && Math.abs(lng) <= 180 ? { lat, lng } : null;
}

function metersBetween(a, b) {
  const R = 6371000, r = Math.PI / 180;
  const h = Math.sin((b.lat - a.lat) * r / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin((b.lng - a.lng) * r / 2) ** 2;
  return Math.floor(2 * R * Math.asin(Math.sqrt(h))); // int() on the server: the form and the lists agree
}
const distLabel = (m) => (m < 1000 ? `${m} m` : `${(m / 1000).toFixed(1)} km`);
// Six decimals is about 10 cm; the stored floats carry many more.
const coordText = (lat, lng) => `${Number(lat.toFixed(6))}, ${Number(lng.toFixed(6))}`;
// Further than this from the city's mosque means the pin or the city is wrong.
const FAR_M = 30000;

const PinIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0113 0C18.5 15.4 12 21 12 21z" /><circle cx="12" cy="10" r="2.3" /></svg>
);

// New / edit hotel, the "Hotel Form, pilihan 2" artboard on the Record View
// HMS canvas. The location is only coordinates with a link out to Google Maps;
// the old map and route editor are gone. A saved route is left as it is.
function HotelFormBody({ hotel, edit, error }) {
  const { t } = useI18n();
  const h = hotel || {};
  const form = useForm({
    name: h.name || new URLSearchParams(window.location.search).get("name") || "",
    city: h.city || "",
    stars: h.stars || "",
    area: h.area || "",
    avg_occupancy: h.avg_occupancy ?? "",
    coords: h.lat != null && h.lng != null ? coordText(h.lat, h.lng) : "",
    has_allotment: !!h.has_allotment,
    is_active: h.is_active ?? true,
    note: h.note || "",
  });
  const d = form.data;
  const set = (k) => (v) => form.setData(k, v);

  const point = parseCoords(d.coords);
  const coordsBad = !!d.coords.trim() && !point;
  const ref = REF[d.city] || null;
  const dist = point && ref ? metersBetween(point, ref) : null;
  const occ = parseFloat(d.avg_occupancy);

  const why = !d.name.trim() ? t("Enter the hotel name.")
    : !d.city ? t("Choose the city.")
      : !d.stars ? t("Choose the stars.")
        : coordsBad ? t("Fix the coordinates, or leave them empty.")
      : "";

  const submit = (e) => {
    e.preventDefault();
    if (why) return;
    form.transform((x) => ({
      name: x.name, city: x.city, stars: String(x.stars), area: x.area,
      avg_occupancy: String(x.avg_occupancy ?? ""), note: x.note,
      lat: point ? String(point.lat) : "", lng: point ? String(point.lng) : "",
      has_allotment: x.has_allotment ? "on" : "",
      is_active: x.is_active ? "on" : "",
    }));
    // forceFormData: Django reads request.POST, which a JSON body leaves empty.
    form.post(edit ? `/hotels/${h.id}/edit/` : "/hotels/new/", { forceFormData: true });
  };

  const stars = (n) => (n === 1 ? t("1 star") : t("{n} stars", { n }));

  return (
    <FormA title={edit ? t("Edit hotel") : t("New hotel")} onSubmit={submit} error={error ? t(error) : null}>
      <div className={FA.fields}>
        <Field label={t("Hotel name")} required className={FA.wide}>
          <TextIn value={d.name} onChange={set("name")} placeholder={t("For example, Hotel Sawaaed")} autoFocus={!edit} />
        </Field>
        <Field label={t("City")} required>
          <Picker searchable={false} value={d.city} heading={t("City")} placeholder={t("Choose the city")}
            options={Object.entries(REF).map(([v, r]) => ({ value: v, label: v === "makkah" ? "Makkah" : "Madinah", meta: t("Distance measured to {place}", { place: r.label }) }))}
            onPick={(o) => form.setData("city", o.value)}
            extra={ref ? <span className={FA.meta}>{ref.label}</span> : null} />
        </Field>
        <Field label={t("Stars")} required>
          <Picker searchable={false} value={d.stars} heading={t("Stars")} placeholder={t("Choose the stars")}
            options={[5, 4, 3, 2, 1].map((n) => ({ value: n, label: stars(n), meta: "★".repeat(n) }))}
            onPick={(o) => form.setData("stars", o.value)}
            extra={d.stars ? <span className={FA.meta}>{"★".repeat(d.stars)}</span> : null} />
        </Field>
        <Field label={t("Area")}>
          <TextIn value={d.area} onChange={set("area")} placeholder={t("Misfalah, Ajyad…")} list="hotel-areas" />
        </Field>
        <Field label={t("Hotel average")} hint={occ > 0 ? t("35 pilgrims need {n} rooms", { n: Math.ceil(35 / occ) }) : t("People per room, used to estimate rooms")}>
          <TextIn value={d.avg_occupancy} onChange={(v) => form.setData("avg_occupancy", v.replace(/[^\d.]/g, ""))} placeholder="3.4" inputMode="decimal" aria-label={t("Hotel average, people per room")} />
        </Field>
        <Field label={t("Coordinates")} className={FA.wide}
          error={coordsBad ? t("Couldn't read that. Use \"21.41816, 39.82877\" or paste a Google Maps link.") : null}>
          <TextIn value={d.coords} onChange={set("coords")} icon={<PinIcon />} invalid={coordsBad}
            onBlur={() => point && form.setData("coords", coordText(point.lat, point.lng))}
            placeholder={t("Paste coordinates or a Google Maps link")} aria-label={t("Coordinates")} />
          {point ? (
            <span className="flex flex-wrap items-center gap-3 text-[13px] text-muted-foreground">
              {!ref ? <span>{t("Choose the city to see the distance.")}</span>
                : dist > FAR_M
                  ? <span className="font-medium text-warning-text" role="status">{t("{d} from {place}. Check the coordinates or the city.", { d: distLabel(dist), place: ref.label })}</span>
                  : <span><b className="font-semibold text-foreground tabular-nums">{distLabel(dist)}</b> {t("from {place}, straight line", { place: ref.label })}</span>}
              <a className="ml-auto font-semibold text-foreground no-underline hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring" href={`https://www.google.com/maps?q=${point.lat},${point.lng}`} target="_blank" rel="noopener noreferrer">{t("Open in Google Maps")} ↗</a>
            </span>
          ) : !coordsBad ? (
            <span className="text-[12px] text-muted-foreground">{t("In Google Maps, right-click the hotel and click the numbers to copy them. Without coordinates, lists show no distance.")}</span>
          ) : null}
        </Field>
      </div>
      <datalist id="hotel-areas">{AREAS.map((a) => <option key={a} value={a} />)}</datalist>

      <div className="mt-[18px] grid grid-cols-2 gap-x-4 gap-y-3.5 max-[640px]:grid-cols-1">
        <SwitchRow title={t("Allotment contract")} note={t("Holds rooms for us this season")}
          checked={d.has_allotment} aria-label={t("Allotment contract")} onCheckedChange={(v) => form.setData("has_allotment", v)} />
        <SwitchRow title={t("Active")} note={t("Shown when making a CL")}
          checked={d.is_active} aria-label={t("Active")} onCheckedChange={(v) => form.setData("is_active", v)} />
      </div>

      <NoteField label={t("Note")} value={d.note} onChange={set("note")} placeholder={t("Anything worth knowing about this hotel")} />

      <Foot why={why} cancelHref={edit ? `/hotels/${h.id}/` : "/hotels/"} submitLabel={edit ? t("Save hotel") : t("Add hotel")} processing={form.processing} />
    </FormA>
  );
}

export default withStandaloneModal(HotelFormBody, (p) => (p.edit && p.hotel ? `/hotels/${p.hotel.id}/` : "/hotels/"));
