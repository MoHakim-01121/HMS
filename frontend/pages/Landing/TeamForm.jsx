import { useContext, useRef } from "react";
import { useForm } from "@inertiajs/react";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import { FormModalContext, StandaloneFormModal } from "../../components/shadcn/form-modal.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { useI18n } from "../../utils/i18n.jsx";

export default function TeamForm({ team, edit, errors: serverErrors }) {
  const { t } = useI18n();
  const m = team || {};
  const errors = serverErrors || {};
  const formRef = useRef(null);
  const form = useForm({});

  const submit = (e) => {
    e.preventDefault();
    const fd = new FormData(formRef.current);
    const data = {};
    fd.forEach((v, k) => { data[k] = v; });
    form.transform(() => data);
    form.post(edit ? `/manage-landing/team/${m.id}/edit/` : "/manage-landing/team/new/", { forceFormData: true });
  };

  const inModal = useContext(FormModalContext)?.inModal;
  const closeHref = "/manage-landing/";

  const page = (
    <div className="form-page shadcn-root">
      <FormHeader
        kicker={t("Manage Landing")}
        title={edit ? t("Edit Member") : t("New Member")}
        sub={t("Anggota tim yang tampil di section Our Team landing page")}
      />
      <form ref={formRef} method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label={t("Team Member")}>
            <FormField label={t("Name")} name="name" error={errors.name}>
              <Input id="name" name="name" type="text" defaultValue={m.name || ""} placeholder={t("Nama lengkap")} />
            </FormField>
            <FormField label={t("Position")} name="position" error={errors.position}>
              <Input id="position" name="position" type="text" defaultValue={m.position || ""} placeholder={t("Mis. Marketing & Reservasi")} />
            </FormField>
            <FormField label={t("WhatsApp")} name="wa" error={errors.wa} hint={t("Format internasional, mis. 6281234567890")}>
              <Input id="wa" name="wa" type="text" defaultValue={m.wa || ""} placeholder="6281234567890" />
            </FormField>
            <FormField
              label={t("Photo")} name="photo" error={errors.photo}
              hint={edit && m.photo_url ? t("Foto saat ini akan diganti jika memilih foto baru") : t("Opsional — tampil di section Our Team")}
            >
              {edit && m.photo_url && (
                <img src={m.photo_url} alt="" style={{ width: 64, height: 64, borderRadius: "50%", objectFit: "cover", marginBottom: 8, display: "block" }} />
              )}
              <Input id="photo" name="photo" type="file" accept="image/*" />
            </FormField>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <FormField label={t("Order")} name="order" error={errors.order} hint={t("Angka kecil tampil lebih dulu")}>
                <Input id="order" name="order" type="number" min="0" step="1" defaultValue={m.order ?? ""} />
              </FormField>
              <div style={{ display: "flex", alignItems: "flex-end", paddingBottom: 3 }}>
                <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", margin: 0, fontSize: 13, color: "var(--foreground)" }}>
                  <input type="checkbox" name="is_active" defaultChecked={!edit || m.is_active} style={{ width: 16, height: 16, accentColor: "var(--foreground)" }} />
                  <span>{t("Active")}</span>
                </label>
              </div>
            </div>
          </FormSection>

          <FormActions
            cancelHref={closeHref}
            submitLabel={edit ? t("Save Changes") : t("Create Member")}
            processing={form.processing}
          />
        </FormPanel>
      </form>
    </div>
  );

  return inModal ? page : <StandaloneFormModal closeHref={closeHref}>{page}</StandaloneFormModal>;
}
