import { useForm } from "@inertiajs/react";
import FormPanel from "../../components/form/FormPanel.jsx";
import FormSection from "../../components/form/FormSection.jsx";
import FormField from "../../components/form/FormField.jsx";
import FormActions from "../../components/form/FormActions.jsx";
import PageBack from "../../components/ui/PageBack.jsx";

export default function Form({ client, edit, errors: serverErrors }) {
  const c = client || {};
  const form = useForm({
    name: c.name || "", city: c.city || "", province: c.province || "",
    pic: c.pic || "", wa: c.wa || "", email: c.email || "",
    lat: c.lat ?? "", lng: c.lng ?? "", note: c.note || "",
    is_active: edit ? !!c.is_active : true,
  });
  const errors = { ...serverErrors, ...form.errors };
  const set = (k) => (v) => form.setData(k, v);

  const submit = (e) => {
    e.preventDefault();
    // Django reads checkbox as the string "on".
    form.transform((d) => ({ ...d, is_active: d.is_active ? "on" : "" }));
    const url = edit ? `/clients/${c.id}/edit/` : `/clients/new/`;
    form.post(url, { forceFormData: true });
  };

  return (
    <div className="form-page">
      <PageBack href={edit ? `/clients/${c.id}/` : "/clients/"} />
      <div className="page-header" style={{ marginBottom: 16 }}>
        <div>
          <div className="page-title">{edit ? "Edit Client" : "New Client"}</div>
          <div className="page-sub">Umrah travel agent data</div>
        </div>
      </div>

      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label="Identity">
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField span={2} label="Agent Name" name="name" required
                value={form.data.name} onChange={set("name")} error={errors.name}
                placeholder="PT. Anugerah Wisata" autoFocus />
              <FormField label="City" name="city" value={form.data.city} onChange={set("city")} placeholder="Surabaya" />
              <FormField label="Province" name="province" value={form.data.province} onChange={set("province")} placeholder="Jawa Timur" />
            </div>
            <label className="ff-check">
              <input type="checkbox" checked={form.data.is_active} onChange={(e) => form.setData("is_active", e.target.checked)} />
              <span>Active <span className="check-sub">Client can be selected when creating new documents</span></span>
            </label>
          </FormSection>

          <FormSection label="Contact">
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField label="PIC" name="pic" value={form.data.pic} onChange={set("pic")} placeholder="Person in charge name" />
              <FormField label="WhatsApp" name="wa" value={form.data.wa} onChange={set("wa")} placeholder="628123456789" inputMode="tel" />
            </div>
            <FormField label="Email" name="email" type="email" value={form.data.email} onChange={set("email")} placeholder="email@agency.com" error={errors.email} />
          </FormSection>

          <FormSection label="Location" sub="for map">
            <div className="fg-2">
              <FormField label="Latitude" name="lat" type="number" step="any" value={form.data.lat} onChange={set("lat")} placeholder="-7.2575" />
              <FormField label="Longitude" name="lng" type="number" step="any" value={form.data.lng} onChange={set("lng")} placeholder="112.7521" />
            </div>
            <div className="hint" style={{ marginTop: 8 }}>
              Find city coordinates at <a href="https://www.latlong.net/" target="_blank" rel="noreferrer" style={{ color: "var(--accent)", textDecoration: "none" }}>latlong.net ↗</a>
            </div>
          </FormSection>

          <FormSection label="Internal Notes">
            <FormField name="note">
              <textarea name="note" rows={3} value={form.data.note} onChange={(e) => form.setData("note", e.target.value)} placeholder="Notes about this client…" />
            </FormField>
          </FormSection>

          <FormActions
            cancelHref={edit ? `/clients/${c.id}/` : "/clients/"}
            submitLabel={edit ? "Save Changes" : "Add Client"}
            processing={form.processing} />
        </FormPanel>
      </form>
    </div>
  );
}
