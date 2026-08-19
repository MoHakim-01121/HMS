import { useContext, useState } from "react";
import { useForm } from "@inertiajs/react";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import Combobox from "../../components/shadcn/combobox.jsx";
import { FormModalContext, StandaloneFormModal } from "../../components/shadcn/form-modal.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { postForm } from "../../utils/inertiaForm.js";
import { useI18n } from "../../utils/i18n.jsx";

export default function Form({ visit, edit, errors: serverErrors, clients }) {
  const v = visit || {};
  const { t } = useI18n();
  const clientList = clients || [];
  const initialClient = clientList.find((c) => String(c.id) === String(v.client_id));

  const form = useForm({
    client_id: v.client_id || "",
    scheduled_date: v.scheduled_date || "",
    start_time: v.start_time || "",
    end_time: v.end_time || "",
    purpose: v.purpose || "",
  });
  const errors = { ...serverErrors, ...form.errors };
  const [clientQuery, setClientQuery] = useState(initialClient ? initialClient.name : "");

  const onClientText = (text) => {
    setClientQuery(text);
    const match = clientList.find((c) => c.name.toLowerCase() === text.trim().toLowerCase());
    form.setData("client_id", match ? String(match.id) : "");
  };
  const onClientSelect = (c) => { setClientQuery(c.name); form.setData("client_id", String(c.id)); };

  const submit = (e) => {
    e.preventDefault();
    postForm(form, edit ? `/visits/${v.id}/edit/` : "/visits/new/");
  };

  const inModal = useContext(FormModalContext)?.inModal;
  const closeHref = edit ? `/visits/${v.id}/` : "/visits/";

  const page = (
    <div className="form-page shadcn-root">
      <FormHeader
        kicker={t("Visit")}
        title={edit ? t("Edit Visit") : t("New Visit")}
        sub={t("Schedule a visit to a client")}
      />
      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label={t("Visit")}>
            <FormField label={t("Client")} name="client_id" error={errors.client_id}>
              <Combobox
                name="client_id"
                value={clientQuery}
                onTextChange={onClientText}
                onSelect={onClientSelect}
                options={clientList}
                getLabel={(o) => o.name}
                placeholder={t("Search client…")}
                error={errors.client_id}
              />
            </FormField>
            <FormField label={t("Date")} name="scheduled_date" error={errors.scheduled_date}>
              <Input
                id="scheduled_date" name="scheduled_date" type="date"
                value={form.data.scheduled_date}
                onChange={(e) => form.setData("scheduled_date", e.target.value)}
              />
            </FormField>
            <FormField label={t("Time slot (optional)")} name="start_time" error={errors.start_time}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                <Input
                  id="start_time" name="start_time" type="time"
                  value={form.data.start_time}
                  onChange={(e) => form.setData("start_time", e.target.value)}
                />
                <Input
                  id="end_time" name="end_time" type="time"
                  value={form.data.end_time}
                  onChange={(e) => form.setData("end_time", e.target.value)}
                />
              </div>
              <div style={{ fontSize: 12, color: "var(--muted-foreground)", marginTop: 6 }}>
                {t("Start – end. Slots that overlap another visit are rejected.")}
              </div>
            </FormField>
            <FormField label={t("Purpose")} name="purpose" error={errors.purpose}>
              <Textarea
                name="purpose" rows={3}
                value={form.data.purpose}
                onChange={(e) => form.setData("purpose", e.target.value)}
                placeholder={t("Follow up renewal, presentasi paket baru, dll…")}
              />
            </FormField>
          </FormSection>

          <FormActions
            cancelHref={closeHref}
            submitLabel={edit ? t("Save Changes") : t("Create Visit")}
            processing={form.processing}
          />
        </FormPanel>
      </form>
    </div>
  );

  return inModal ? page : <StandaloneFormModal closeHref={closeHref}>{page}</StandaloneFormModal>;
}
