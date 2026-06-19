import { useForm } from "@inertiajs/react";
import FormPanel from "../../components/form/FormPanel.jsx";
import FormSection from "../../components/form/FormSection.jsx";
import FormField from "../../components/form/FormField.jsx";
import FormActions from "../../components/form/FormActions.jsx";
import Combobox from "../../components/form/Combobox.jsx";
import PageBack from "../../components/ui/PageBack.jsx";
import { postForm } from "../../utils/inertiaForm.js";
import RoomRows from "./RoomRows.jsx";

const STATUS = [["DEFINITE", "Definite"], ["TENTATIVE", "Tentative"], ["CANCELLED", "Cancelled"]];
const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

function nightsBetween(ci, co) {
  if (!ci || !co) return 1;
  const d = (new Date(co) - new Date(ci)) / 86400000;
  return d > 0 ? d : 1;
}

export default function Form({ cl, edit, errors: serverErrors, suggested_number, default_company, hotels, clients }) {
  const c = cl || {};
  const form = useForm({
    company: c.company || default_company || "konoz",
    client_id: c.client_id || "",
    hotel_name: c.hotel_name || "",
    guest_name: c.guest_name || "",
    guest_phone: c.guest_phone || "",
    check_in: c.check_in || "",
    check_out: c.check_out || "",
    confirmation_number: c.confirmation_number || suggested_number || "",
    reservation_status: c.reservation_status || "DEFINITE",
    note: c.note || "",
    rooms: c.rooms || [],
  });
  const errors = { ...serverErrors, ...form.errors };
  const set = (k) => (v) => form.setData(k, v);

  // Tamu = client. Typing free text keeps it as guest_name (no client link);
  // an exact name match or picking from the list links the client_id.
  const clientList = clients || [];
  const onGuestText = (text) => {
    const match = clientList.find((c) => c.name.toLowerCase() === text.trim().toLowerCase());
    form.setData("guest_name", text);
    form.setData("client_id", match ? String(match.id) : "");
  };
  const onGuestSelect = (c) => {
    form.setData("guest_name", c.name);
    form.setData("client_id", String(c.id));
  };

  const nights = nightsBetween(form.data.check_in, form.data.check_out);
  const total = nights * form.data.rooms.reduce((s, r) => s + (Number(r.quantity) || 0) * (Number(r.price) || 0), 0);

  const submit = (e) => {
    e.preventDefault();
    postForm(form, edit ? `/cl/${c.id}/edit/` : "/cl/new/", { json: ["rooms"] });
  };

  return (
    <div className="form-page">
      <PageBack href={edit ? `/cl/${c.id}/` : "/cl/"} />
      <div className="page-header" style={{ marginBottom: 16 }}>
        <div>
          <div className="page-title">{edit ? "Edit Confirmation Letter" : "New Confirmation Letter"}</div>
          <div className="page-sub">Hotel reservation details</div>
        </div>
      </div>

      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label="Company & Status">
            <div className="fg-2">
              <FormField label="Company" name="company">
                <select name="company" value={form.data.company} onChange={(e) => form.setData("company", e.target.value)}>
                  <option value="konoz">Konoz United</option>
                  <option value="ijabah">Ijabah</option>
                </select>
              </FormField>
              <FormField label="Reservation Status" name="reservation_status">
                <select name="reservation_status" value={form.data.reservation_status} onChange={(e) => form.setData("reservation_status", e.target.value)}>
                  {STATUS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </FormField>
            </div>
          </FormSection>

          <FormSection label="Reservation">
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField label="CL Number" name="confirmation_number" required value={form.data.confirmation_number} onChange={set("confirmation_number")} error={errors.confirmation_number} />
              <FormField label="Hotel" name="hotel_name">
                <input list="cl-hotels" name="hotel_name" value={form.data.hotel_name} onChange={(e) => form.setData("hotel_name", e.target.value)} placeholder="Hotel name" />
                <datalist id="cl-hotels">
                  {(hotels || []).map((h, i) => <option key={i} value={h.name} />)}
                </datalist>
              </FormField>
            </div>
            <div className="fg-2">
              <FormField label="Check-in" name="check_in" type="date" value={form.data.check_in} onChange={set("check_in")} />
              <FormField label="Check-out" name="check_out" type="date" value={form.data.check_out} onChange={set("check_out")} error={errors.check_out} />
            </div>
          </FormSection>

          <FormSection label="Guest">
            <div className="fg-2">
              <FormField label="Guest / Client" name="guest_name" error={errors.guest_name} hint="Pick a registered client or type the guest name">
                <Combobox
                  name="guest_name"
                  value={form.data.guest_name}
                  onTextChange={onGuestText}
                  onSelect={onGuestSelect}
                  options={clientList}
                  getLabel={(o) => o.name}
                  getSub={(o) => (o.company === "ijabah" ? "Ijabah" : "Konoz")}
                  placeholder="Search client or type guest name…"
                  error={errors.guest_name}
                />
              </FormField>
              <FormField label="Phone No." name="guest_phone" value={form.data.guest_phone} onChange={set("guest_phone")} inputMode="tel" />
            </div>
          </FormSection>

          <FormSection label="Rooms">
            <RoomRows rooms={form.data.rooms} onChange={(next) => form.setData("rooms", next)} nights={nights} />
            <div style={{ marginTop: 12, textAlign: "right", fontWeight: 600 }}>
              Total: {fmt(total)} SAR <span style={{ fontWeight: 400, fontSize: 12, color: "var(--text-3)" }}>({nights} nights)</span>
            </div>
          </FormSection>

          <FormSection label="Notes">
            <FormField name="note">
              <textarea name="note" rows={3} value={form.data.note} onChange={(e) => form.setData("note", e.target.value)} placeholder="Internal notes…" />
            </FormField>
          </FormSection>

          <FormActions
            cancelHref={edit ? `/cl/${c.id}/` : "/cl/"}
            submitLabel={edit ? "Save Changes" : "Create CL"}
            processing={form.processing} />
        </FormPanel>
      </form>
    </div>
  );
}
