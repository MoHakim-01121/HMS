import { useContext, useState } from "react";
import { useForm } from "@inertiajs/react";
import { actionsClass, FormModalContext, StandaloneFormModal } from "../../components/shadcn/form-modal.jsx";
import { Field, Picker, CellPicker, DateRangePicker, nightsBetween, todayIso, FormAFrame, Why, FA, Caption, StatusDot, TextIn, btnClass } from "../../components/shadcn/form-a.jsx";
import { usePhone } from "../../components/shadcn/list-a.jsx";
import { Drawer, DrawerContent, DrawerTitle } from "../../components/shadcn/ui/drawer.jsx";
import { cn } from "@/lib/utils";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

const EMPTY_ROOM = { room_type: "", room_type_id: "", meals: "", meal_plan_code: "", quantity: 1, price: "" };

const ICON = {
  client: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="9" cy="8" r="3.2" /><path strokeLinecap="round" d="M3 19c.8-3.2 3.2-5 6-5s5.2 1.8 6 5" /><path strokeLinecap="round" d="M15.5 4.8a3.2 3.2 0 010 6.2M17.5 14.4c1.8.6 3 2.2 3.5 4.6" /></svg>,
  hotel: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M4 20V6l8-3 8 3v14M9 20v-4h6v4" /></svg>,
  number: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path strokeLinecap="round" d="M9 4L7 20M17 4l-2 16M4 9h16M3 15h16" /></svg>,
  person: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="12" cy="8" r="4" /><path strokeLinecap="round" d="M4 20c1.5-4 4.5-6 8-6s6.5 2 8 6" /></svg>,
  minus: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path strokeLinecap="round" d="M5 12h14" /></svg>,
  plus: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path strokeLinecap="round" d="M12 5v14M5 12h14" /></svg>,
  trash: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M4 7h16M10 11v6M14 11v6M5 7l1 12a2 2 0 002 2h8a2 2 0 002-2l1-12M9 7V4h6v3" /></svg>,
};

// One choice among a few, as a grid of buttons (the phone room sheet).
function Options({ value, options, onPick, label, wide }) {
  return (
    <div role="radiogroup" aria-label={label} className={cn("grid gap-1.5", wide ? "grid-cols-2" : "grid-cols-[repeat(auto-fill,minmax(76px,1fr))]")}>
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={o.value === value} onClick={() => onPick(o)}
          className={cn("h-11 cursor-pointer rounded-[12px] border border-field bg-card px-2 font-sans text-[14px] font-medium text-foreground",
            o.value === value && "border-2 border-primary bg-secondary font-semibold")}>{o.label}</button>
      ))}
    </div>
  );
}

// The rooms on a phone (canvas "HMS Mobile v2", New CL, picked option C): a
// line per room with its quantity stepper; tapping a room opens one sheet for
// its type, meal plan and price, in that order.
function PhoneRooms({ hotel, roomTypes, mealPlans, rooms, nights, setRoom, addRoom, removeRoom, roomCount, total, t }) {
  const [open, setOpen] = useState(-1);
  const r = rooms[open];
  const mealName = (code) => t(mealPlans.find((mp) => mp.code === code)?.name || code);
  const add = () => { addRoom(); setOpen(rooms.length); };
  return (
    <div className="overflow-hidden rounded-[16px] border border-border">
      {!hotel && <div className={FA.noteEmpty}>{t("Choose the hotel first; its room types fill this list.")}</div>}
      {hotel && roomTypes.length === 0 && (
        <div className={FA.noteEmpty}>{t("This hotel has no room types yet.")} <a href={`/hotels/${hotel.id}/edit/`} target="_blank" rel="noreferrer">{t("Add them on the hotel's page")}</a></div>
      )}
      {hotel && roomTypes.length > 0 && rooms.map((room, i) => {
        const meal = room.meal_plan_code || room.meals;
        return (
          <div key={i} className="flex flex-col gap-2 border-b border-hairline px-3.5 py-3">
            <div className="flex items-center justify-between gap-2.5">
              <button type="button" onClick={() => setOpen(i)} className="inline-flex min-h-8 min-w-0 cursor-pointer items-center gap-1 border-0 bg-transparent p-0 text-left font-sans text-[15px] text-foreground">
                <b className="font-semibold">{room.room_type || t("Choose a room type")}</b>
                {meal && <span className="truncate text-muted-foreground">· {mealName(meal)}</span>}
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true" className="flex-none text-muted-foreground"><path d="M6 9l6 6 6-6" /></svg>
              </button>
              <b className="text-[15px] font-semibold tabular-nums">{fmt((Number(room.quantity) || 0) * (Number(room.price) || 0) * nights)}</b>
            </div>
            <div className="flex items-center justify-between gap-2.5">
              <button type="button" onClick={() => setOpen(i)} className="inline-flex min-h-8 cursor-pointer items-center gap-1.5 border-0 bg-transparent p-0 font-sans text-[13px] text-muted-foreground">
                {room.price ? t("{p} / night", { p: fmt(room.price) }) : t("Set the price")}
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16zM14 6l4 4" /></svg>
              </button>
              <span className="inline-flex h-9 items-center rounded-full border border-input">
                <button type="button" className="grid size-9 cursor-pointer place-content-center border-0 bg-transparent text-foreground" aria-label={t("Fewer")} onClick={() => setRoom(i, { quantity: Math.max(1, (Number(room.quantity) || 1) - 1) })}>{ICON.minus}</button>
                <b className="min-w-7 text-center font-semibold tabular-nums">{room.quantity}</b>
                <button type="button" className="grid size-9 cursor-pointer place-content-center border-0 bg-transparent text-foreground" aria-label={t("More")} onClick={() => setRoom(i, { quantity: (Number(room.quantity) || 0) + 1 })}>{ICON.plus}</button>
              </span>
            </div>
          </div>
        );
      })}
      {hotel && roomTypes.length > 0 && (
        <button type="button" onClick={add} className="flex h-12 w-full cursor-pointer items-center gap-2 border-0 border-b border-border bg-transparent px-3.5 font-sans text-[14px] font-semibold text-foreground">{ICON.plus}{t("Add room type")}</button>
      )}
      <div className="flex items-center justify-between gap-3 bg-muted px-3.5 py-3">
        <span><b className="font-semibold">{t("Total")}</b> <span className="text-[13px] text-muted-foreground">· {roomCount === 1 ? t("1 room") : t("{n} rooms", { n: roomCount })}{nights > 0 ? ` · ${nights === 1 ? t("1 night") : t("{n} nights", { n: nights })}` : ""}</span></span>
        <b className="text-[15px] font-semibold tabular-nums">{fmt(total)} <span className={FA.unit}>SAR</span></b>
      </div>

      <Drawer open={!!r} onOpenChange={(o) => { if (!o) setOpen(-1); }} direction="bottom">
        <DrawerContent aria-describedby={undefined} className="rounded-t-[22px] border-0 px-4 pb-[calc(18px+env(safe-area-inset-bottom))]">
          <DrawerTitle className="m-0 pt-3 text-[17px]">{t("Room, meal and price")}</DrawerTitle>
          {r && (
            <div className="flex flex-col gap-3.5 overflow-y-auto py-3.5">
              <Field label={t("Room type")}>
                <Options label={t("Room type")} value={String(r.room_type_id)} onPick={(o) => setRoom(open, { room_type_id: o.value, room_type: o.label })}
                  options={roomTypes.map((rt) => ({ value: String(rt.id), label: rt.name }))} />
              </Field>
              <Field label={t("Meal plan")}>
                {mealPlans.length > 0 ? (
                  <Options wide label={t("Meal plan")} value={r.meal_plan_code || r.meals} onPick={(o) => setRoom(open, { meal_plan_code: o.value, meals: o.value })}
                    options={mealPlans.map((mp) => ({ value: mp.code, label: t(mp.name) }))} />
                ) : (
                  <TextIn aria-label={t("Meal plan")} placeholder="BB, HB…" value={r.meals} onChange={(v) => setRoom(open, { meals: v })} />
                )}
              </Field>
              <Field label={t("Price per night")} hint={t("× {n} rooms × {m} nights = {v} SAR", { n: r.quantity || 0, m: nights, v: fmt((Number(r.quantity) || 0) * (Number(r.price) || 0) * nights) })}>
                <TextIn aria-label={t("Price per night")} inputMode="decimal" placeholder="0" suffix="SAR" value={r.price}
                  onChange={(v) => setRoom(open, { price: v.replace(/[^\d.]/g, "") })} />
              </Field>
              <div className="flex items-center gap-2.5 pt-1">
                <button type="button" onClick={() => { removeRoom(open); setOpen(-1); }}
                  className="h-11 cursor-pointer rounded-full border-0 bg-transparent px-3 font-sans text-[14px] font-semibold text-danger-text">{t("Remove room")}</button>
                <button type="button" onClick={() => setOpen(-1)}
                  className="h-11 flex-1 cursor-pointer rounded-full border-0 bg-primary font-sans text-[14px] font-semibold text-primary-foreground">{t("Done")}</button>
              </div>
            </div>
          )}
        </DrawerContent>
      </Drawer>
    </div>
  );
}

// Confirmation Letter form, as approved on the Record View HMS canvas:
// six fields in two columns, the rooms in one framed table with its total,
// a note for the hotel, and a footer that says what is still missing.
export default function Form({ cl, edit, errors: serverErrors, suggested_number, hotels, clients, salespeople = [] }) {
  const c = cl || {};
  const { t } = useI18n();
  const form = useForm({
    client_id: c.client_id ? String(c.client_id) : "",
    hotel_name: c.hotel_name || "",
    hotel_id: c.hotel_id ? String(c.hotel_id) : "",
    guest_name: c.guest_name || "",
    // No input for it any more, but it still has to round-trip: the edit view
    // overwrites guest_phone from POST, so dropping it would wipe old CLs' PIC.
    guest_phone: c.guest_phone || "",
    check_in: c.check_in || "",
    check_out: c.check_out || "",
    confirmation_number: c.confirmation_number || suggested_number || "",
    reservation_status: c.reservation_status || "TENTATIVE",
    salesperson_id: c.salesperson_id ? String(c.salesperson_id) : "",
    note: c.note || "",
    rooms: (c.rooms && c.rooms.length) ? c.rooms : [{ ...EMPTY_ROOM }],
  });
  const errors = { ...serverErrors, ...form.errors };
  const d = form.data;
  const hotelList = hotels || [];
  const clientList = clients || [];
  const hotel = hotelList.find((h) => String(h.id) === String(d.hotel_id));
  const roomTypes = hotel ? hotel.room_types : [];
  const mealPlans = hotel ? hotel.meal_plans : [];

  // Switching hotels clears room types (they belong to one hotel). A meal the
  // new hotel also sells is kept; free text survives when it sells none.
  const pickHotel = (h) => {
    if (String(h.id) !== String(d.hotel_id)) {
      const sold = new Set((h.meal_plans || []).map((mp) => mp.code));
      form.setData((prev) => ({
        ...prev, hotel_id: String(h.id), hotel_name: h.name,
        rooms: prev.rooms.map((r) => {
          const code = (r.meal_plan_code || r.meals || "").trim();
          const meal = sold.has(code) ? { meal_plan_code: code, meals: code }
            : sold.size === 0 ? { meal_plan_code: "", meals: r.meals }
            : { meal_plan_code: "", meals: "" };
          return { ...r, room_type_id: "", room_type: "", ...meal };
        }),
      }));
    }
  };
  const pickClient = (o) => form.setData((prev) => ({ ...prev, client_id: String(o.value), guest_name: o.label }));

  const setRoom = (i, patch) => form.setData("rooms", d.rooms.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const addRoom = () => form.setData("rooms", [...d.rooms, { ...EMPTY_ROOM }]);
  const removeRoom = (i) => form.setData("rooms", d.rooms.filter((_, k) => k !== i));

  const nights = Math.max(0, nightsBetween(d.check_in, d.check_out));
  const rooms = d.rooms;
  const capacity = (r) => roomTypes.find((rt) => String(rt.id) === String(r.room_type_id))?.capacity || 0;
  const roomCount = rooms.reduce((s, r) => s + (r.room_type_id ? Number(r.quantity) || 0 : 0), 0);
  const pax = rooms.reduce((s, r) => s + capacity(r) * (Number(r.quantity) || 0), 0);
  const perNight = rooms.reduce((s, r) => s + (Number(r.quantity) || 0) * (Number(r.price) || 0), 0);
  const total = perNight * nights;

  const statusOpts = [
    { value: "TENTATIVE", label: t("Tentative"), meta: t("Rooms held, not confirmed yet"), lead: <StatusDot status="TENTATIVE" /> },
    { value: "DEFINITE", label: t("Definite"), meta: t("Confirmed by the hotel"), lead: <StatusDot status="DEFINITE" /> },
    // Cancelling is a change to an existing CL: a new one starts held or confirmed.
    ...(edit ? [{ value: "CANCELLED", label: t("Cancelled"), meta: t("Released, no longer held"), lead: <StatusDot status="CANCELLED" /> }] : []),
  ];

  const filledRooms = rooms.filter((r) => r.room_type_id);
  const why = !d.client_id ? t("Choose the client to continue.")
    : !d.hotel_id ? t("Choose the hotel to continue.")
    : !d.check_in ? t("Pick the stay dates to continue.")
    : !d.check_out ? t("Pick a check-out date to continue.")
    : !filledRooms.length ? t("Add at least one room to continue.")
    : !d.confirmation_number.trim() ? t("Enter the confirmation number to continue.")
    : (!edit || c.salesperson_id) && !d.salesperson_id ? t("Choose the salesperson to continue.")
    : "";

  const submit = (e) => {
    e.preventDefault();
    if (why) return;
    // Multipart, rooms as one JSON field (Django reads request.POST). Rows
    // without a room type are blanks the user never filled.
    form.transform((data) => ({ ...data, rooms: JSON.stringify(data.rooms.filter((r) => r.room_type_id)) }));
    form.post(edit ? `/cl/${c.id}/edit/` : "/cl/new/", { forceFormData: true });
  };

  const phone = usePhone();
  const inModal = useContext(FormModalContext)?.inModal;
  const closeHref = edit ? `/cl/${c.id}/` : "/cl/";
  const ctx = useContext(FormModalContext);
  const nightsLabel = (n) => (n === 1 ? t("1 night") : t("{n} nights", { n }));

  const page = (
    <FormAFrame title={edit ? t("Edit Confirmation Letter") : t("New Confirmation Letter")}>
      <form method="post" onSubmit={submit} noValidate>
        <div className={FA.fields}>
          <Field label={t("Client")} required error={errors.guest_name && t(errors.guest_name)}>
            <Picker icon={ICON.client} value={d.client_id} placeholder={t("Select a client")} heading={t("Clients")}
              options={clientList.map((o) => ({ value: String(o.id), label: o.brand || o.name, meta: o.city || (o.brand ? o.name : "") }))}
              onPick={pickClient} invalid={!!errors.guest_name}
              addNew={{ label: t("New client"), meta: t("Opens the client form in a new tab"), href: "/clients/new/" }} />
          </Field>
          <Field label={t("Hotel")} required error={errors.hotel_name && t(errors.hotel_name)}>
            <Picker icon={ICON.hotel} value={d.hotel_id} placeholder={t("Select a hotel")} heading={t("Hotels")}
              options={hotelList.map((h) => ({ value: String(h.id), label: h.name, meta: h.city ? h.city[0].toUpperCase() + h.city.slice(1) : "", raw: h }))}
              onPick={(o) => pickHotel(o.raw)} invalid={!!errors.hotel_name}
              addNew={{ label: t("New hotel"), meta: t("Opens the hotel form in a new tab"), href: "/hotels/new/" }} />
          </Field>
          <Field label={t("Stay")} required error={(errors.check_out || errors.check_in) && t(errors.check_out || errors.check_in)}>
            <DateRangePicker start={d.check_in} end={d.check_out} minDate={edit ? undefined : todayIso()}
              invalid={!!(errors.check_out || errors.check_in)}
              onChange={(ci, co) => { form.setData((prev) => ({ ...prev, check_in: ci, check_out: co })); form.clearErrors("check_out", "check_in"); }} />
          </Field>
          <Field label={t("Confirmation no.")} required error={errors.confirmation_number && t(errors.confirmation_number)}>
            <TextIn icon={ICON.number} invalid={!!errors.confirmation_number} aria-label={t("Confirmation no.")} placeholder={t("From HQ")} required
              value={d.confirmation_number} onChange={(v) => form.setData("confirmation_number", v)} />
          </Field>
          <Field label={t("Status")} required error={errors.reservation_status && t(errors.reservation_status)}>
            <Picker searchable={false} value={d.reservation_status} options={statusOpts}
              icon={<StatusDot status={d.reservation_status} />}
              onPick={(o) => form.setData("reservation_status", o.value)} />
          </Field>
          <Field label={t("Salesperson")} required={!edit || !!c.salesperson_id} error={errors.salesperson_id && t(errors.salesperson_id)}>
            <Picker icon={ICON.person} value={d.salesperson_id} placeholder={t("Select a salesperson")} heading={t("Salespeople")}
              options={salespeople.map((s) => ({ value: String(s.id), label: s.name, meta: s.active ? "" : t("Inactive") }))}
              onPick={(o) => form.setData("salesperson_id", o.value)} invalid={!!errors.salesperson_id} />
          </Field>
        </div>

        <div className={FA.sectionHead}>
          <Caption>{t("Rooms")}</Caption>
          <span className={FA.muted}>{roomCount === 1 ? t("1 room") : t("{n} rooms", { n: roomCount })}, {pax} Pax</span>
        </div>
        {phone ? (
          <PhoneRooms t={t} hotel={hotel} roomTypes={roomTypes} mealPlans={mealPlans} rooms={rooms} nights={nights}
            setRoom={setRoom} addRoom={addRoom} removeRoom={removeRoom} roomCount={roomCount} total={total} />
        ) : (
        <div className={FA.box}>
          <div className={FA.scroll}>
            <div data-row className={cn(FA.row, FA.rowHead)} aria-hidden="true">
              <span>{t("Room type")}</span><span>{t("Meal plan")}</span><span>{t("Qty")}</span>
              <span className="text-right">{t("Price per night")}</span><span className="text-right">{t("Subtotal")}</span><span />
            </div>
            {!hotel && <div className={FA.noteEmpty}>{t("Choose the hotel first; its room types fill this list.")}</div>}
            {hotel && roomTypes.length === 0 && (
              <div className={FA.noteEmpty}>{t("This hotel has no room types yet.")} <a href={`/hotels/${hotel.id}/edit/`} target="_blank" rel="noreferrer">{t("Add them on the hotel's page")}</a></div>
            )}
            {hotel && roomTypes.length > 0 && rooms.length === 0 && <div className={FA.noteEmpty}>{t("No rooms yet. Add the first room type.")}</div>}
            {hotel && roomTypes.length > 0 && rooms.map((r, i) => {
              const sub = (Number(r.quantity) || 0) * (Number(r.price) || 0) * nights;
              const mealValue = r.meal_plan_code || r.meals;
              return (
                <div data-row className={FA.row} key={i}>
                  <CellPicker value={r.room_type_id} placeholder={t("Room type")} label={t("Room type")}
                    options={roomTypes.map((rt) => ({ value: String(rt.id), label: rt.name, meta: t("{n} guests", { n: rt.capacity }) }))}
                    onPick={(o) => setRoom(i, { room_type_id: o.value, room_type: o.label })} />
                  {mealPlans.length > 0 ? (
                    <CellPicker value={mealValue} placeholder={t("Meal plan")} label={t("Meal plan")}
                      options={[
                        ...mealPlans.map((mp) => ({ value: mp.code, label: mp.code, meta: t(mp.name) })),
                        // Text from before the meal list that matches no code: kept as is.
                        ...(mealValue && !mealPlans.some((mp) => mp.code === mealValue) ? [{ value: mealValue, label: mealValue, meta: t("old entry") }] : []),
                      ]}
                      onPick={(o) => setRoom(i, { meal_plan_code: mealPlans.some((mp) => mp.code === o.value) ? o.value : "", meals: o.value })} />
                  ) : (
                    <label className={cn(FA.pill, "cursor-text px-3")}><input className={FA.pillInput} aria-label={t("Meal plan")} placeholder="BB, HB…" value={r.meals} onChange={(e) => setRoom(i, { meals: e.target.value })} /></label>
                  )}
                  <span className={FA.stepper}>
                    <button type="button" className={FA.stepperButton} aria-label={t("Fewer")} onClick={() => setRoom(i, { quantity: Math.max(1, (Number(r.quantity) || 1) - 1) })}>{ICON.minus}</button>
                    <input className={FA.qty} aria-label={t("Quantity")} inputMode="numeric" value={r.quantity}
                      onChange={(e) => { const n = parseInt(e.target.value, 10); setRoom(i, { quantity: Number.isNaN(n) ? "" : Math.max(1, Math.min(999, n)) }); }} />
                    <button type="button" className={FA.stepperButton} aria-label={t("More")} onClick={() => setRoom(i, { quantity: (Number(r.quantity) || 0) + 1 })}>{ICON.plus}</button>
                  </span>
                  <label className={FA.price}><input className={FA.priceInput} aria-label={t("Price per night")} inputMode="decimal" value={r.price} placeholder="0"
                    onChange={(e) => setRoom(i, { price: e.target.value.replace(/[^\d.]/g, "") })} /><span className={FA.unit}>SAR</span></label>
                  <span className={FA.subtotal}><b>{fmt(sub)}</b><span className={FA.unit}>SAR</span></span>
                  <button type="button" className={FA.trash} aria-label={t("Remove room")} onClick={() => removeRoom(i)}>{ICON.trash}</button>
                </div>
              );
            })}
            {hotel && roomTypes.length > 0 && (
              <button type="button" className={FA.addRow} onClick={addRoom}>{ICON.plus}{t("Add room")}</button>
            )}
            <div data-row className={cn(FA.row, FA.rowTotal)}>
              <span className="col-span-2"><b>{t("Total")}</b>{nights > 0 && <span className={cn(FA.muted, "ml-2 text-[12px]")}>{nightsLabel(nights)}</span>}</span>
              <span className={FA.num}>{roomCount === 1 ? t("1 room") : t("{n} rooms", { n: roomCount })}</span>
              <span className={FA.totalPerNight}>{fmt(perNight)}<span className={FA.unit}>SAR</span></span>
              <span className={FA.subtotal}><b className="text-[16px] tracking-[-0.01em]">{fmt(total)}</b><span className={FA.unit}>SAR</span></span>
              <span />
            </div>
          </div>
        </div>
        )}
        {errors.rooms && <div className={FA.alert} role="alert">{t(errors.rooms)}</div>}

        <div className={FA.noteWrap}>
          <Caption>{t("Note")}</Caption>
          <textarea className={FA.note} aria-label={t("Note for the hotel")} placeholder={t("Add a note for the hotel")}
            value={d.note} onChange={(e) => form.setData("note", e.target.value)} />
        </div>

        <div className={actionsClass("a")}>
          {why && <Why>{why}</Why>}
          {inModal ? (
            <button type="button" className={cn(btnClass("o"), "phone:hidden")} onClick={ctx.close}>{t("Cancel")}</button>
          ) : (
            <a className={cn(btnClass("o"), "phone:hidden")} href={closeHref}>{t("Cancel")}</a>
          )}
          <button type="submit" className={btnClass("p")} aria-disabled={!!why || form.processing} disabled={form.processing}>
            {edit ? t("Save changes") : t("Create CL")}
          </button>
        </div>
      </form>
    </FormAFrame>
  );

  return inModal ? page : <StandaloneFormModal closeHref={closeHref}>{page}</StandaloneFormModal>;
}
