import { useForm } from "@inertiajs/react";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { Checkbox } from "../../components/shadcn/ui/checkbox.jsx";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/shadcn/ui/select.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { useI18n } from "../../utils/i18n.jsx";

export default function Form({ client, edit, errors: serverErrors }) {
  const { t } = useI18n();
  const c = client || {};
  const form = useForm({
    name: c.name || "", city: c.city || "", province: c.province || "",
    pic: c.pic || "", wa: c.wa || "", wa_group: c.wa_group || "",
    reminder_target: c.reminder_target || "GROUP",
    email: c.email || "",
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
    <div className="form-page shadcn-root">
      <PageBack href={edit ? `/clients/${c.id}/` : "/clients/"} label={t("Back")} />
      <FormHeader
        kicker={t("Client")}
        title={edit ? t("Edit Client") : t("New Client")}
        sub={t("Umrah travel agent data")}
      />

      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label={t("Identity")}>
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField span={2} label={t("Agent Name")} name="name" required
                value={form.data.name} onChange={set("name")} error={errors.name}
                placeholder="PT. Anugerah Wisata" autoFocus />
              <FormField label={t("City")} name="city" value={form.data.city} onChange={set("city")} placeholder="Surabaya" />
              <FormField label={t("Province")} name="province" value={form.data.province} onChange={set("province")} placeholder="Jawa Timur" />
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
              <Checkbox checked={form.data.is_active} onCheckedChange={(v) => form.setData("is_active", !!v)} />
              <span>{t("Active")} <span style={{ color: "var(--muted-foreground)" }}>— {t("Client can be selected when creating new documents")}</span></span>
            </label>
          </FormSection>

          <FormSection label={t("Contact")}>
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField label={t("PIC")} name="pic" value={form.data.pic} onChange={set("pic")} placeholder={t("Person in charge name")} />
              <FormField label={t("WhatsApp PIC")} name="wa" value={form.data.wa} onChange={set("wa")} placeholder="628123456789" inputMode="tel" />
            </div>
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField label={t("WhatsApp Group")} name="wa_group" value={form.data.wa_group} onChange={set("wa_group")} placeholder={t("120363xxxxx@g.us or Fonnte group ID")} />
              <FormField label={t("Send Reminder To")} name="reminder_target">
                <Select name="reminder_target" value={form.data.reminder_target} onValueChange={(v) => form.setData("reminder_target", v)}>
                  <SelectTrigger id="reminder_target" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="PIC">{t("PIC")}</SelectItem>
                    <SelectItem value="GROUP">{t("WhatsApp Group")}</SelectItem>
                    <SelectItem value="BOTH">{t("PIC & Group")}</SelectItem>
                  </SelectContent>
                </Select>
              </FormField>
            </div>
            <FormField label={t("Email")} name="email" type="email" value={form.data.email} onChange={set("email")} placeholder="email@agency.com" error={errors.email} />
          </FormSection>

          <FormSection label={t("Location")} sub={t("for map")}>
            <div className="fg-2">
              <FormField label={t("Latitude")} name="lat" type="number" step="any" value={form.data.lat} onChange={set("lat")} placeholder="-7.2575" />
              <FormField label={t("Longitude")} name="lng" type="number" step="any" value={form.data.lng} onChange={set("lng")} placeholder="112.7521" />
            </div>
            <div className="hint" style={{ marginTop: 8 }}>
              {t("Find city coordinates at")} <a href="https://www.latlong.net/" target="_blank" rel="noreferrer" style={{ color: "var(--foreground)", textDecoration: "underline" }}>latlong.net ↗</a>
            </div>
          </FormSection>

          <FormSection label={t("Internal Notes")}>
            <FormField name="note">
              <Textarea name="note" rows={3} value={form.data.note} onChange={(e) => form.setData("note", e.target.value)} placeholder={t("Notes about this client…")} />
            </FormField>
          </FormSection>

          <FormActions
            cancelHref={edit ? `/clients/${c.id}/` : "/clients/"}
            submitLabel={edit ? t("Save Changes") : t("Add Client")}
            processing={form.processing} />
        </FormPanel>
      </form>
    </div>
  );
}
