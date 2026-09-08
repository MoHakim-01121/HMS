import { useContext } from "react";
import { useForm } from "@inertiajs/react";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import Combobox from "../../components/shadcn/combobox.jsx";
import { Icon } from "../../components/icons.jsx";
import { FormModalContext, StandaloneFormModal } from "../../components/shadcn/form-modal.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { postForm } from "../../utils/inertiaForm.js";
import RoomRows from "./RoomRows.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

const STATUS = [
  ["DEFINITE", "Definite", "var(--green)"],
  ["TENTATIVE", "Tentative", "var(--yellow)"],
  ["CANCELLED", "Cancelled", "var(--red)"],
];

function nightsBetween(ci, co) {
  if (!ci || !co) return 1;
  const d = (new Date(co) - new Date(ci)) / 86400000;
  return d > 0 ? d : 1;
}

const CAPACITY = { Double: 2, Triple: 3, Quad: 4, Quint: 5 };
const fmtRange = (ci, co) => {
  const f = (s) => { const d = new Date(s); return Number.isNaN(+d) ? s : d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" }); };
  return ci && co ? `${f(ci)} → ${f(co)}` : "—";
};

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
    const q = text.trim().toLowerCase();
    const match = clientList.find((cl) => (cl.brand || cl.name).toLowerCase() === q || cl.name.toLowerCase() === q);
    form.setData("guest_name", text);
    form.setData("client_id", match ? String(match.id) : "");
  };
  const onGuestSelect = (cl) => {
    form.setData("guest_name", cl.brand || cl.name);
    form.setData("client_id", String(cl.id));
  };

  const nights = nightsBetween(form.data.check_in, form.data.check_out);
  const rooms = form.data.rooms;
  const total = nights * rooms.reduce((s, r) => s + (Number(r.quantity) || 0) * (Number(r.price) || 0), 0);
  const totalRooms = rooms.reduce((s, r) => s + (Number(r.quantity) || 0), 0);
  const capacity = rooms.reduce((s, r) => s + (CAPACITY[r.room_type] || 1) * (Number(r.quantity) || 0), 0);

  // Room-type mix for the summary rail — one bar segment + one legend line per
  // distinct room type that carries a subtotal.
  const mix = [];
  for (const r of rooms) {
    const sub = nights * (Number(r.quantity) || 0) * (Number(r.price) || 0);
    if (!r.room_type || sub <= 0) continue;
    const hit = mix.find((m) => m.type === r.room_type);
    if (hit) { hit.qty += Number(r.quantity) || 0; hit.sub += sub; }
    else mix.push({ type: r.room_type, qty: Number(r.quantity) || 0, sub });
  }

  const datesValid = form.data.check_in && form.data.check_out && form.data.check_out > form.data.check_in;
  const checklist = [
    { ok: !!form.data.guest_name.trim(), label: t("Group / client name filled") },
    { ok: !!form.data.hotel_name.trim(), label: t("Hotel selected") },
    { ok: !!datesValid, label: t("Check-in / check-out valid") },
    { ok: total > 0, label: t("At least one priced room") },
  ];

  // Mirrors the server's _validate_cl check so a bad range is caught before the
  // round trip. The check-out field also carries min=check_in.
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

  const inModal = useContext(FormModalContext)?.inModal;
  const closeHref = edit ? `/cl/${c.id}/` : "/cl/";
  const submitLabel = edit ? t("Save Changes") : t("Create CL");

  const page = (
    <div className="form-page cl-form shadcn-root">
      <style>{CSS}</style>
      <FormHeader
        kicker={t("Confirmation Letter")}
        title={edit ? t("Edit Confirmation Letter") : t("New Confirmation Letter")}
        sub={t("Hotel reservation details")}
      />

      <form method="post" onSubmit={submit}>
       <div className="rd-card">
        <div className="rd-body">
          <div className="rd-main">

            {/* ── Group & client ── */}
            <section className="rd-sec">
              <div className="rd-sec-h">
                <span className="rd-sec-title">{t("Group & client")}</span>
                <span className="rd-sec-desc">{t("The group name shows on every document and message to the client.")}</span>
              </div>
              <div className="rd-sec-b">
                <FormField label={t("Group / client name")} name="guest_name" error={errors.guest_name} required>
                  <Combobox
                    name="guest_name"
                    value={form.data.guest_name}
                    onTextChange={onGuestText}
                    onSelect={onGuestSelect}
                    options={clientList}
                    getLabel={(o) => o.brand || o.name}
                    placeholder={t("Search client or type a group name…")}
                    error={errors.guest_name}
                  />
                </FormField>
                <div className="rd-row2">
                  <FormField label={t("Phone (PIC)")} name="guest_phone" value={form.data.guest_phone} onChange={set("guest_phone")} inputMode="tel" placeholder="+62…" />
                  <FormField label={t("CL number")} name="confirmation_number" required value={form.data.confirmation_number} onChange={set("confirmation_number")} error={errors.confirmation_number} />
                </div>
                <FormField label={t("Status")} name="reservation_status">
                  <div className="rd-seg" role="radiogroup" aria-label={t("Status")}>
                    {STATUS.map(([v, l, dot]) => (
                      <button
                        type="button" key={v} role="radio"
                        aria-checked={form.data.reservation_status === v}
                        className={"rd-seg-opt" + (form.data.reservation_status === v ? " is-on" : "")}
                        onClick={() => form.setData("reservation_status", v)}
                      >
                        <span className="rd-seg-dot" style={{ background: dot }} />{t(l)}
                      </button>
                    ))}
                  </div>
                </FormField>
              </div>
            </section>

            {/* ── Hotel & stay ── */}
            <section className="rd-sec">
              <div className="rd-sec-h">
                <span className="rd-sec-title">{t("Hotel & stay")}</span>
                <span className="rd-sec-desc">{t("Nights are computed automatically from the dates.")}</span>
              </div>
              <div className="rd-sec-b">
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
                <div className="rd-row3">
                  <FormField label={t("Check-in")} name="check_in" error={errors.check_in}>
                    <Input id="check_in" name="check_in" type="date" value={form.data.check_in} onChange={(e) => setDate("check_in", e.target.value)} />
                  </FormField>
                  <FormField label={t("Check-out")} name="check_out" error={errors.check_out}>
                    <Input id="check_out" name="check_out" type="date" min={form.data.check_in || undefined} value={form.data.check_out} onChange={(e) => setDate("check_out", e.target.value)} />
                  </FormField>
                  <FormField label={t("Nights")} name="nights">
                    <div className="rd-static">{nights}</div>
                  </FormField>
                </div>
              </div>
            </section>

            {/* ── Rooms & pricing ── */}
            <section className="rd-sec">
              <div className="rd-sec-h">
                <span className="rd-sec-title">{t("Rooms & pricing")}</span>
                <span className="rd-sec-desc">{t("Subtotal = qty × rate × nights, filled automatically.")}</span>
              </div>
              <div className="rd-sec-b">
                <RoomRows rooms={rooms} onChange={(next) => form.setData("rooms", next)} nights={nights} />
                <div className="rd-rooms-foot">
                  <span>{totalRooms} {t(totalRooms === 1 ? "room" : "rooms")} · {t("capacity")} {capacity} {t("pax")}</span>
                  <span className="rd-rooms-foot-total">{t("Total")} {fmt(total)} <span className="cur">SAR</span></span>
                </div>
              </div>
            </section>

            {/* ── Notes ── */}
            <section className="rd-sec rd-sec-last">
              <div className="rd-sec-h">
                <span className="rd-sec-title">{t("Notes")}</span>
                <span className="rd-sec-desc">{t("Shown on the PDF sent to the hotel.")}</span>
              </div>
              <div className="rd-sec-b">
                <FormField name="note">
                  <Textarea name="note" rows={3} value={form.data.note} onChange={(e) => form.setData("note", e.target.value)} placeholder={t("Internal notes…")} />
                </FormField>
              </div>
            </section>
          </div>

          {/* ── Summary rail ── */}
          <aside className="rd-rail">
            <div className="rd-summary">
              <div className="rd-rail-block">
                <span className="rd-rail-lbl">{t("Total price")}</span>
                <div className="rd-rail-total"><span>{fmt(total)}</span><span className="rd-rail-cur">SAR</span></div>
                <span className="rd-rail-meta">{fmtRange(form.data.check_in, form.data.check_out)} · {nights} {t(nights === 1 ? "night" : "nights")}</span>
              </div>

              {mix.length > 0 && (
                <div className="rd-rail-block">
                  <div className="rd-bar">
                    {mix.map((m, i) => (
                      <span key={m.type} style={{ flex: m.sub, background: `color-mix(in oklch, var(--primary) ${100 - i * 32}%, var(--card))` }} />
                    ))}
                  </div>
                  <div className="rd-mix">
                    {mix.map((m, i) => (
                      <div className="rd-mix-row" key={m.type}>
                        <span><span className="rd-mix-dot" style={{ background: `color-mix(in oklch, var(--primary) ${100 - i * 32}%, var(--card))` }} />{m.type} · {m.qty}</span>
                        <span className="rd-num">{fmt(m.sub)}</span>
                      </div>
                    ))}
                    {capacity > 0 && (
                      <div className="rd-mix-row rd-mix-total">
                        <span>{t("Capacity")}</span><span className="rd-num">{capacity} {t("pax")}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              <div className="rd-rail-sep" />

              <div className="rd-rail-block">
                <span className="rd-rail-lbl">{t("Before confirming")}</span>
                {checklist.map((it) => (
                  <div className={"rd-check" + (it.ok ? " is-ok" : "")} key={it.label}>
                    <Icon name={it.ok ? "check" : "clock"} size={15} />{it.label}
                  </div>
                ))}
              </div>
            </div>

            <div className="rd-rail-spacer" />
            <button type="submit" className="rd-cta" disabled={form.processing}>
              <Icon name="check" size={15} />{form.processing ? t("Saving…") : submitLabel}
            </button>
          </aside>
        </div>
       </div>
      </form>
    </div>
  );

  return inModal ? page : <StandaloneFormModal closeHref={closeHref}>{page}</StandaloneFormModal>;
}

/* ── Layout ───────────────────────────────────────────────────────────────
   Two-pane redesign (Claude Design "HOMLU HMS Redesign" §5a/5b): a main
   column of label-left / field-right sections and a 300px summary rail that
   carries the running total, room mix, a readiness checklist and the submit
   CTA. Above 1100px viewport the form-modal widens to fit both panes (see the
   :has() rule below); under that the rail drops beneath the main column and
   every section collapses to a single stack.

   The editable Rooms table keeps the treatment from RoomRows.jsx — a real
   <table> in one bordered frame, muted header, chromeless cells. */
const CSS = `
/* Widen the form-modal to fit both panes once the viewport can spare it. */
@media (min-width: 1100px) {
  .form-modal-content:has(.cl-form) { max-width: 1180px; }
}

.cl-form form { margin-top: 22px; }
.hms-modal-body .cl-form form { margin-top: 0; }

.cl-form .rd-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-card, 22px);
  background: var(--card);
  overflow: visible;
  box-shadow: 0 1px 2px rgba(0,0,0,.04), 0 12px 40px -12px color-mix(in oklch, var(--primary) 16%, transparent);
}
.hms-modal-body .cl-form .rd-card {
  border: none; border-radius: 0; box-shadow: none;
  margin: -24px -20px;
}
@media (max-width: 600px) {
  .hms-modal-body .cl-form .rd-card { margin: -20px -16px; }
}

.cl-form .rd-body { display: flex; align-items: stretch; }
.cl-form .rd-main { flex: 1; min-width: 0; }
.cl-form .rd-rail {
  width: 300px; flex: none;
  border-left: 1px solid var(--border);
  background: color-mix(in oklch, var(--muted) 38%, var(--card));
  display: flex; flex-direction: column;
}
.cl-form .rd-summary {
  position: sticky; top: 0;
  display: flex; flex-direction: column; gap: 22px;
  padding: 28px 24px;
}

.cl-form .rd-sec {
  display: grid; grid-template-columns: 168px minmax(0, 1fr); gap: 28px;
  padding: 26px 30px;
  border-bottom: 1px solid var(--border);
}
.cl-form .rd-sec-last { border-bottom: none; }
.cl-form .rd-sec-h { display: flex; flex-direction: column; gap: 5px; }
.cl-form .rd-sec-title { font-size: 13px; font-weight: 600; color: var(--foreground); }
.cl-form .rd-sec-desc { font-size: 11.5px; line-height: 1.5; color: var(--muted-foreground); }
.cl-form .rd-sec-b { display: flex; flex-direction: column; gap: 14px; min-width: 0; }

.cl-form .rd-row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.cl-form .rd-row3 { display: grid; grid-template-columns: 1fr 1fr 96px; gap: 12px; }

/* Field labels: the small uppercase caption from the design, replacing
   FormField's default sentence-case Label. */
.cl-form .rd-sec-b [data-slot="form-field"] label {
  font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
  color: var(--muted-foreground);
}

.cl-form .rd-static {
  height: 40px; display: flex; align-items: center; justify-content: center;
  border: 2px solid var(--border); border-radius: var(--radius-control);
  background: color-mix(in oklch, var(--muted) 50%, transparent);
  font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums;
  color: var(--muted-foreground);
}

/* Segmented status control */
.cl-form .rd-seg {
  display: inline-flex; gap: 3px; padding: 3px; width: fit-content;
  border: 1px solid var(--border); border-radius: 999px;
  background: color-mix(in oklch, var(--muted) 50%, transparent);
}
.cl-form .rd-seg-opt {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 14px; border: none; border-radius: 999px; background: transparent;
  font: inherit; font-size: 12px; font-weight: 500; color: var(--muted-foreground);
  cursor: pointer; transition: background .12s, color .12s;
}
.cl-form .rd-seg-opt.is-on {
  background: var(--card); color: var(--foreground); font-weight: 600;
  box-shadow: 0 1px 2px rgba(0,0,0,.06);
}
.cl-form .rd-seg-dot { width: 6px; height: 6px; border-radius: 999px; flex: none; }

.cl-form .rd-rooms-foot {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  font-size: 11.5px; color: var(--muted-foreground); font-variant-numeric: tabular-nums;
}
.cl-form .rd-rooms-foot-total { font-weight: 600; color: var(--foreground); }
.cl-form .rd-rooms-foot .cur { font-weight: 400; color: var(--muted-foreground); }

/* ── Rail internals ── */
.cl-form .rd-rail-block { display: flex; flex-direction: column; gap: 10px; }
.cl-form .rd-rail-lbl {
  font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
  color: var(--muted-foreground);
}
.cl-form .rd-rail-total {
  display: flex; align-items: baseline; gap: 8px;
  font-size: 34px; font-weight: 600; letter-spacing: -.025em;
  font-variant-numeric: tabular-nums; color: var(--foreground);
}
.cl-form .rd-rail-cur { font-size: 13px; font-weight: 500; color: var(--muted-foreground); }
.cl-form .rd-rail-meta { font-size: 11.5px; color: var(--muted-foreground); font-variant-numeric: tabular-nums; }

.cl-form .rd-bar { display: flex; gap: 3px; height: 8px; }
.cl-form .rd-bar > span { border-radius: 999px; min-width: 4px; }

.cl-form .rd-mix { display: flex; flex-direction: column; gap: 8px; font-size: 12.5px; }
.cl-form .rd-mix-row { display: flex; align-items: center; justify-content: space-between; color: var(--muted-foreground); }
.cl-form .rd-mix-row > span:first-child { display: inline-flex; align-items: center; gap: 7px; }
.cl-form .rd-mix-dot { width: 8px; height: 8px; border-radius: 3px; flex: none; }
.cl-form .rd-num { font-weight: 500; color: var(--foreground); font-variant-numeric: tabular-nums; }
.cl-form .rd-mix-total {
  padding-top: 9px; border-top: 1px solid var(--border);
  font-weight: 500; color: var(--foreground);
}

.cl-form .rd-rail-sep { height: 1px; background: var(--border); }
.cl-form .rd-rail-spacer { flex: 1; min-height: 8px; }

.cl-form .rd-check {
  display: flex; align-items: center; gap: 9px;
  font-size: 12.5px; color: var(--muted-foreground);
}
.cl-form .rd-check svg { flex: none; color: var(--muted-foreground); }
.cl-form .rd-check.is-ok { color: var(--foreground); }
.cl-form .rd-check.is-ok svg { color: var(--green); }

.cl-form .rd-cta {
  display: flex; align-items: center; justify-content: center; gap: 7px;
  width: auto; margin: 0 24px 24px; height: 42px; border: none; border-radius: 12px;
  background: var(--primary); color: var(--primary-foreground);
  font: inherit; font-size: 13px; font-weight: 600; cursor: pointer;
  transition: background .12s;
  position: sticky; bottom: 0;
}
.cl-form .rd-cta:hover { background: var(--primary-hover); }
.cl-form .rd-cta:disabled { opacity: .6; cursor: default; }

/* ── Narrow: rail below, sections stacked ── */
@media (max-width: 1099px) {
  .cl-form .rd-body { flex-direction: column; }
  .cl-form .rd-main { width: 100%; }
  .cl-form .rd-sec { grid-template-columns: 1fr; gap: 12px; padding: 22px 22px; }
  .cl-form .rd-rail {
    width: auto; border-left: none; border-top: 1px solid var(--border);
    background: color-mix(in oklch, var(--muted) 38%, var(--card));
  }
  .cl-form .rd-summary { position: static; padding: 22px; }
  .cl-form .rd-rail-spacer { display: none; }
  .cl-form .rd-cta { position: static; margin: 0 22px 22px; width: auto; }
}
@media (max-width: 600px) {
  .cl-form .rd-row2, .cl-form .rd-row3 { grid-template-columns: 1fr; }
}

/* Rooms table frame — shared with the Invoice form. */
.cl-form .cl-tbl-wrap {
  border: 1px solid var(--border); border-radius: var(--radius-control, 16px);
  background: var(--card); overflow: hidden;
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
.cl-form .cl-tbl tbody tr { animation: none; }
.cl-form .cl-tbl tbody td {
  padding: 0; height: 40px;
  border-bottom: 1px solid var(--border);
  background: transparent; vertical-align: middle;
  transition: background .1s;
}
.cl-form .cl-tbl tbody td + td { border-left: 1px solid var(--border); }
.cl-form .cl-tbl tbody tr:hover td { background: color-mix(in oklch, var(--muted) 45%, transparent); }

.cl-form .cl-tbl .c-in {
  width: 100%; height: 100%; min-height: 40px;
  padding: 0 10px; margin: 0;
  background: transparent; border: none; border-radius: 0; box-shadow: none;
  font-family: inherit; font-size: 13px; font-weight: 400; color: var(--foreground);
  -webkit-appearance: none; appearance: none;
}
.cl-form .cl-tbl .c-in:focus {
  outline: none; border-color: transparent;
  box-shadow: inset 0 0 0 2px var(--ring); background: var(--card);
}
.cl-form .cl-tbl .c-in::placeholder { color: var(--muted-foreground); opacity: .75; }
.cl-form .cl-tbl .c-in.c-num { text-align: right; font-variant-numeric: tabular-nums; }
.cl-form .cl-tbl .c-in.c-strong { font-weight: 600; }
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
@media (max-width: 600px) {
  .cl-form .cl-rooms-desktop { display: none; }
}
`;
