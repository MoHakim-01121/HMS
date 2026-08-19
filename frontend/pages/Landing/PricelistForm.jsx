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

export default function PricelistForm({ pricelist, edit, errors: serverErrors }) {
  const { t } = useI18n();
  const p = pricelist || {};
  const errors = serverErrors || {};
  const formRef = useRef(null);
  const form = useForm({});

  const submit = (e) => {
    e.preventDefault();
    const fd = new FormData(formRef.current);
    const data = {};
    fd.forEach((v, k) => { data[k] = v; });
    form.transform(() => data);
    form.post(edit ? `/manage-landing/pricelist/${p.id}/edit/` : "/manage-landing/pricelist/new/", { forceFormData: true });
  };

  const inModal = useContext(FormModalContext)?.inModal;
  const closeHref = "/manage-landing/";

  const page = (
    <div className="form-page shadcn-root">
      <FormHeader
        kicker={t("Manage Landing")}
        title={edit ? t("Edit Pricelist") : t("Upload Pricelist")}
        sub={t("File harga hotel yang bisa diunduh agen dari landing page")}
      />
      <form ref={formRef} method="post" onSubmit={submit} encType="multipart/form-data">
        <FormPanel>
          <FormSection label={t("Pricelist")}>
            <FormField label={t("Title")} name="title" error={errors.title}>
              <Input id="title" name="title" type="text" defaultValue={p.title || ""} placeholder={t("Mis. Pricelist Hotel Makkah – Januari")} />
            </FormField>
            <FormField
              label={t("File")} name="file" error={errors.file}
              hint={edit && p.filename
                ? t("File saat ini: {name} — pilih file baru untuk mengganti", { name: p.filename })
                : t("Hanya satu pricelist aktif — upload ini akan menggantikan pricelist sebelumnya")}
            >
              <Input id="file" name="file" type="file" accept=".pdf,.xls,.xlsx,.doc,.docx" />
            </FormField>
            <div style={{ display: "flex", alignItems: "flex-end", paddingBottom: 3 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", margin: 0, fontSize: 13, color: "var(--foreground)" }}>
                <input type="checkbox" name="is_active" defaultChecked={!edit || p.is_active} style={{ width: 16, height: 16, accentColor: "var(--foreground)" }} />
                <span>{t("Active")}</span>
              </label>
            </div>
          </FormSection>

          <FormActions
            cancelHref={closeHref}
            submitLabel={edit ? t("Save Changes") : t("Upload Pricelist")}
            processing={form.processing}
          />
        </FormPanel>
      </form>
    </div>
  );

  return inModal ? page : <StandaloneFormModal closeHref={closeHref}>{page}</StandaloneFormModal>;
}
