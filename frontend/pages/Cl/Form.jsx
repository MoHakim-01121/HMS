import { useContext } from "react";
import { useForm } from "@inertiajs/react";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import Combobox from "../../components/shadcn/combobox.jsx";
import { FormModalContext, StandaloneFormModal } from "../../components/shadcn/form-modal.jsx";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/shadcn/ui/select.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { postForm } from "../../utils/inertiaForm.js";
import RoomRows from "./RoomRows.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

const STATUS = [["DEFINITE", "Definite"], ["TENTATIVE", "Tentative"], ["CANCELLED", "Cancelled"]];

function nightsBetween(ci, co) {
  if (!ci || !co) return 1;
  const d = (new Date(co) - new Date(ci)) / 86400000;
  return d > 0 ? d : 1;
}

export default function Form({ cl, edit, errors: serverErrors, suggested_number, hotels, clients }) {
  const c = cl || {};
  const { t } = useI18n();
  const form = useForm({
    // Company is set server-side from the active company; not a form field.
    client_id: c.client_id || "",
    hotel_name: c.hotel_name || "",
    guest_name: c.guest_name || "",
    guest_phone: c.guest_phone || "",
    check_in: c.check_in || "",
    check_out: c.check_out || "",
    confirmation_number: c.confirmation_number || suggested_number || "",
    reservation_status: c.reservation_status || "DEFINITE",
    note: c.note || "",
    rooms: (c.rooms && c.rooms.length) ? c.rooms : [{ room_type: "", meals: "", quantity: 1, price: "" }],
  });
  const errors = { ...serverErrors, ...form.errors };
  const set = (k) => (v) => form.setData(k, v);

  // Guest = client. Typing free text keeps it as guest_name (no client link);
  // an exact name match or picking from the list links the client_id.
  const clientList = clients || [];
  const onGuestText = (text) => {
    const t = text.trim().toLowerCase();
    const match = clientList.find((c) => (c.brand || c.name).toLowerCase() === t || c.name.toLowerCase() === t);
    form.setData("guest_name", text);
    form.setData("client_id", match ? String(match.id) : "");
  };
  const onGuestSelect = (c) => {
    form.setData("guest_name", c.brand || c.name);
    form.setData("client_id", String(c.id));
  };

  const nights = nightsBetween(form.data.check_in, form.data.check_out);
  const total = nights * form.data.rooms.reduce((s, r) => s + (Number(r.quantity) || 0) * (Number(r.price) || 0), 0);

  // Mirrors the server's _validate_cl check so a bad range is caught before the
  // round trip. The check-out field also carries min=check_in, so the native
  // date picker never offers a date before check-in in the first place.
  const setDate = (k, v) => {
    form.setData(k, v);
    if (form.errors.check_out) form.clearErrors("check_out");
  };

  const submit = (e) => {
    e.preventDefault();
    const { check_in: ci, check_out: co } = form.data;
    if (ci && co && co < ci) {
      form.setError("check_out", t("Check-out cannot be before check-in."));
      return;
    }
    postForm(form, edit ? `/cl/${c.id}/edit/` : "/cl/new/", { json: ["rooms"] });
  };

  // Every route into this form ends up in the dialog: opened from the list or
  // the detail page it is already inside the provider's one, and reached any
  // other way (direct URL, validation re-render) StandaloneFormModal supplies
  // the identical frame below. There is no page-shaped second copy of the form
  // any more, so no back link / kicker / big title here either — the dialog
  // header owns those, published by FormHeader.
  const inModal = useContext(FormModalContext)?.inModal;
  const closeHref = edit ? `/cl/${c.id}/` : "/cl/";

  const page = (
    <div className="form-page cl-form shadcn-root">
      <style>{CSS}</style>
      <FormHeader
        kicker={t("Confirmation Letter")}
        title={edit ? t("Edit Confirmation Letter") : t("New Confirmation Letter")}
        sub={t("Hotel reservation details")}
      />

      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label={t("Status")}>
            <FormField label={t("Reservation Status")} name="reservation_status">
              <Select name="reservation_status" value={form.data.reservation_status} onValueChange={(v) => form.setData("reservation_status", v)}>
                <SelectTrigger id="reservation_status" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUS.map(([v, l]) => <SelectItem key={v} value={v}>{t(l)}</SelectItem>)}
                </SelectContent>
              </Select>
            </FormField>
          </FormSection>

          <FormSection label={t("Reservation")}>
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField label={t("CL Number")} name="confirmation_number" required value={form.data.confirmation_number} onChange={set("confirmation_number")} error={errors.confirmation_number} />
              <FormField label={t("Hotel")} name="hotel_name" error={errors.hotel_name}>
                <Combobox
                  name="hotel_name"
                  value={form.data.hotel_name}
                  onTextChange={(text) => form.setData("hotel_name", text)}
                  onSelect={(h) => form.setData("hotel_name", h.name)}
                  options={hotels || []}
                  getLabel={(o) => o.name}
                  getSub={(o) => o.city || ""}
                  placeholder={t("Search hotel or type name…")}
                  emptyLabel={t("New hotel — typed manually")}
                  error={errors.hotel_name}
                />
              </FormField>
            </div>
            <div className="fg-2">
              <FormField label={t("Check-in")} name="check_in" error={errors.check_in}>
                <Input
                  id="check_in" name="check_in" type="date"
                  value={form.data.check_in}
                  onChange={(e) => setDate("check_in", e.target.value)}
                />
              </FormField>
              <FormField label={t("Check-out")} name="check_out" error={errors.check_out}>
                <Input
                  id="check_out" name="check_out" type="date"
                  min={form.data.check_in || undefined}
                  value={form.data.check_out}
                  onChange={(e) => setDate("check_out", e.target.value)}
                />
              </FormField>
            </div>
          </FormSection>

          <FormSection label={t("Guest")}>
            <div className="fg-2">
              <FormField label={t("Guest / Client")} name="guest_name" error={errors.guest_name} hint={t("Pick a registered client or type the guest name")}>
                <Combobox
                  name="guest_name"
                  value={form.data.guest_name}
                  onTextChange={onGuestText}
                  onSelect={onGuestSelect}
                  options={clientList}
                  getLabel={(o) => o.brand || o.name}
                  placeholder={t("Search client or type guest name…")}
                  error={errors.guest_name}
                />
              </FormField>
              <FormField label={t("Phone No.")} name="guest_phone" value={form.data.guest_phone} onChange={set("guest_phone")} inputMode="tel" />
            </div>
          </FormSection>

          <FormSection label={t("Rooms")}>
            <RoomRows rooms={form.data.rooms} onChange={(next) => form.setData("rooms", next)} nights={nights} />
            <div className="cl-rooms-total-desktop" style={{ marginTop: 32, textAlign: "right", fontWeight: 600 }}>
              {t("Total")}: {fmt(total)} SAR <span style={{ fontWeight: 400, fontSize: 12, color: "var(--muted-foreground)" }}>({nights} {t(nights === 1 ? "night" : "nights")})</span>
            </div>
            <div className="cl-rooms-total-mobile dv-foot">
              <div>
                <span className="dv-l">{t("Rooms")}</span>
                <div className="cl-rooms-total-nights">{nights} {t(nights === 1 ? "night" : "nights")} · {form.data.rooms.length} {t(form.data.rooms.length === 1 ? "room" : "rooms")}</div>
              </div>
              <div style={{ textAlign: "right" }}>
                <span className="dv-l">{t("Total Price")}</span>
                <div className="dv-foot-total">{fmt(total)}<span className="cur"> SAR</span></div>
              </div>
            </div>
          </FormSection>

          <FormSection label={t("Notes")}>
            <FormField name="note">
              <Textarea name="note" rows={3} value={form.data.note} onChange={(e) => form.setData("note", e.target.value)} placeholder={t("Internal notes…")} />
            </FormField>
          </FormSection>

          <div className="cl-desktop-actions">
            <FormActions
              cancelHref={closeHref}
              submitLabel={edit ? t("Save Changes") : t("Create CL")}
              processing={form.processing} />
          </div>

          <div className="cl-mobile-save-wrap">
            <button type="submit" className="dv-cta" disabled={form.processing}>
              {edit ? t("Save Changes") : t("Create CL")}
            </button>
          </div>
        </FormPanel>
      </form>
    </div>
  );

  return inModal ? page : <StandaloneFormModal closeHref={closeHref}>{page}</StandaloneFormModal>;
}

/* ── Rooms table ──────────────────────────────────────────────────────────
   Same editable-table treatment as the Invoice form's Reservations and
   Payments tables (see Invoice/Form.jsx's CSS block): a real <table> inside
   one bordered frame, a muted header row that labels each column once, and
   chromeless controls in the cells so a room reads as a line of data rather
   than a rack of inputs — with Add row sitting inside the frame, where the
   new row will appear.

   It replaces forms.css's .cl-rooms grid, which was still painted from the
   retired token set (--bg-2 / --border-2 / --text-3 / --r) and boxed the
   subtotal in a dashed pseudo-field. Renaming the classes is what takes those
   legacy rules out of play; the mobile card layout below 600px is untouched
   and still keyed off .cl-rooms-cards.

   Scoped .cl-form .cl-tbl .c-in — three classes, so it outranks design.css's
   unlayered `input:not([type=checkbox]):not([type=radio]), select, textarea`
   reset at (0,2,1) without !important. */
const CSS = `
.cl-form .cl-tbl-wrap {
  border: 1px solid var(--border);
  border-radius: var(--radius-control, 16px);
  background: var(--card);
  overflow: hidden;
}
.cl-form .cl-tbl-scroll { overflow-x: auto; }
.cl-form .cl-tbl { width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 0; min-width: 560px; }

.cl-form .cl-tbl thead th {
  padding: 0 10px; height: 38px;
  font-size: 12px; font-weight: 500; line-height: 38px;
  color: var(--muted-foreground); text-align: left; white-space: nowrap;
  background: var(--muted); border-bottom: 1px solid var(--border);
  text-transform: none; letter-spacing: normal;
}
.cl-form .cl-tbl thead th.r { text-align: right; }
.cl-form .cl-tbl thead th + th { border-left: 1px solid var(--border); }

/* design.css staggers every tbody row in with a fade+slide — right for a
   read-only list, wrong for rows that are edited in place and re-keyed on
   every add/remove. */
.cl-form .cl-tbl tbody tr { animation: none; }
.cl-form .cl-tbl tbody td {
  padding: 0; height: 40px;
  border-bottom: 1px solid var(--border);
  background: transparent; vertical-align: middle;
  transition: background .1s;
}
.cl-form .cl-tbl tbody td + td { border-left: 1px solid var(--border); }
.cl-form .cl-tbl tbody tr:hover td { background: color-mix(in oklch, var(--muted) 45%, transparent); }
.cl-form .cl-tbl tbody tr:hover td:first-child,
.cl-form .cl-tbl tbody tr:hover td:last-child { border-radius: 0; }

.cl-form .cl-tbl .c-in {
  width: 100%; height: 100%; min-height: 40px;
  padding: 0 10px; margin: 0;
  background: transparent; border: none; border-radius: 0; box-shadow: none;
  font-family: inherit; font-size: 13px; font-weight: 400; color: var(--foreground);
  -webkit-appearance: none; appearance: none;
}
.cl-form .cl-tbl .c-in:focus {
  outline: none; border-color: transparent;
  box-shadow: inset 0 0 0 2px var(--ring);
  background: var(--card);
}
.cl-form .cl-tbl .c-in::placeholder { color: var(--muted-foreground); opacity: .75; }
.cl-form .cl-tbl .c-in.c-num { text-align: right; font-variant-numeric: tabular-nums; }
.cl-form .cl-tbl .c-in.c-strong { font-weight: 600; }
/* Spinners steal ~16px from already-tight numeric cells, and these values are
   typed, not stepped. */
.cl-form .cl-tbl .c-in[type="number"]::-webkit-outer-spin-button,
.cl-form .cl-tbl .c-in[type="number"]::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.cl-form .cl-tbl .c-in[type="number"] { -moz-appearance: textfield; }

.cl-form .cl-tbl .c-sel { position: relative; display: block; height: 100%; }
.cl-form .cl-tbl .c-sel select.c-in { padding-right: 24px; cursor: pointer; }
.cl-form .cl-tbl .c-sel::after {
  content: ''; position: absolute; right: 11px; top: 50%;
  width: 5px; height: 5px; pointer-events: none;
  border-right: 1.5px solid var(--muted-foreground);
  border-bottom: 1.5px solid var(--muted-foreground);
  transform: translateY(-70%) rotate(45deg);
}

/* Computed, not editable: right-aligned like the money column it belongs to,
   and muted so the row's one read-only cell is legible as such without a
   dashed box around it. */
.cl-form .cl-tbl .c-calc {
  padding: 0 10px; text-align: right;
  font-family: var(--font-mono); font-size: 13px; font-variant-numeric: tabular-nums;
  color: var(--muted-foreground); white-space: nowrap;
}
.cl-form .cl-tbl .c-act { text-align: center; }

.cl-form .cl-row-del {
  display: inline-flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; border-radius: 8px; border: none; padding: 0;
  background: transparent; color: var(--muted-foreground);
  cursor: pointer; opacity: .45; transition: opacity .12s, background .12s, color .12s;
}
.cl-form .cl-tbl tbody tr:hover .cl-row-del { opacity: 1; }
.cl-form .cl-row-del:hover { background: var(--destructive); color: var(--destructive-foreground); opacity: 1; }
.cl-form .cl-row-del:focus-visible { opacity: 1; outline: 2px solid var(--ring); outline-offset: 1px; }

.cl-form .cl-tbl-add {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  width: 100%; height: 38px; padding: 0;
  background: transparent; border: none;
  font-family: inherit; font-size: 12.5px; font-weight: 500;
  color: var(--muted-foreground); cursor: pointer; transition: background .12s, color .12s;
}
.cl-form .cl-tbl-add:hover { background: var(--muted); color: var(--foreground); }

/* Phones keep the card list forms.css already draws (.cl-rooms-cards). */
.cl-form .cl-rooms-desktop { display: block; }
.cl-form .cl-mobile-save-wrap { display: none; }
@media (max-width: 600px) {
  .cl-form .cl-rooms-desktop { display: none; }
  .cl-form .cl-desktop-actions { display: none; }
  .cl-form .cl-mobile-save-wrap { display: block; margin-top: 20px; }
}
`;
