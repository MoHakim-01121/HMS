import { useState } from "react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import { useForm } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { suggestRoomTypeName } from "./roomTypeName.js";

// Native <select>, styled like shadcn's Input — same reason as Hotel/Form.jsx:
// view is optional, and a Radix Select cannot carry the empty "— Optional —"
// value that clears it.
const SELECT_CLASS = "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-base shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 md:text-sm";

// Occupancy is not asked for: the server derives it from capacity. The name
// follows view + capacity ("Quad Kaaba View") until the user types their own.
function RoomTypeFormBody({ hotel, room_type, occupancy_labels = {}, view_choices = [], edit, action, errors: serverErrors }) {
  const { t } = useI18n();
  const rt = room_type || {};
  const suggest = (capacity, view) => suggestRoomTypeName(capacity, view, occupancy_labels, view_choices);
  const startCapacity = rt.capacity ?? 2;
  const startView = rt.view || "";
  // An existing name that still reads as the generated one keeps following
  // edits; a hand-picked name ("Deluxe Suite Tower B") is never overwritten.
  const [auto, setAuto] = useState(() => !rt.name || rt.name === suggest(startCapacity, startView));
  const form = useForm({
    name: rt.name || suggest(startCapacity, startView),
    capacity: startCapacity,
    view: startView,
  });
  const errors = { ...serverErrors, ...form.errors };
  const back = `/hotels/${hotel.id}/`;
  const suggestion = suggest(form.data.capacity, form.data.view);

  const setDimension = (key) => (value) => {
    const next = { ...form.data, [key]: value };
    form.setData(auto ? { ...next, name: suggest(next.capacity, next.view) } : next);
  };
  const setName = (value) => {
    // Clearing the field hands it back to the suggestion on the next change.
    setAuto(value.trim() === "");
    form.setData("name", value);
  };
  const applySuggestion = () => {
    setAuto(true);
    form.setData("name", suggestion);
  };

  const submit = (e) => {
    e.preventDefault();
    form.post(action, { forceFormData: true });
  };

  const nameHint = auto
    ? t("Filled in from Room View and Capacity — type to use your own name.")
    : suggestion && suggestion !== form.data.name
      ? (
        <button
          type="button" onClick={applySuggestion}
          style={{ padding: 0, border: 0, background: "none", font: "inherit", color: "var(--primary)", textDecoration: "underline", textUnderlineOffset: 3, cursor: "pointer" }}
        >
          {t("Use “{name}”", { name: suggestion })}
        </button>
      )
      : null;

  return (
    <div className="form-page shadcn-root">
      <PageBack href={back} />
      <FormHeader kicker={hotel.name} title={edit ? t("Edit Room Type") : t("New Room Type")} />
      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label={t("Details")}>
            <FormField label={t("Room Type Name")} name="name" required error={errors.name} hint={nameHint}>
              <Input
                id="name" name="name" autoFocus
                value={form.data.name}
                onChange={(e) => setName(e.target.value)}
                // While the name is generated, focusing selects it so typing
                // replaces it outright instead of appending to "Double".
                onFocus={(e) => { if (auto) e.target.select(); }}
                aria-invalid={errors.name ? "true" : undefined}
              />
            </FormField>
            <div className="fg-2" style={{ marginTop: 12 }}>
              <FormField label={t("Room View")} name="view">
                <select id="view" name="view" className={SELECT_CLASS} value={form.data.view} onChange={(e) => setDimension("view")(e.target.value)}>
                  <option value="">{t("— Optional —")}</option>
                  {view_choices.map((c) => <option key={c.value} value={c.value}>{t(c.label)}</option>)}
                </select>
              </FormField>
              <FormField
                label={t("Capacity (guests)")} name="capacity" type="number" inputMode="numeric" required
                value={form.data.capacity} onChange={setDimension("capacity")} error={errors.capacity}
              />
            </div>
          </FormSection>

          <FormActions cancelHref={back} submitLabel={edit ? t("Save Changes") : t("Add Room Type")} processing={form.processing} />
        </FormPanel>
      </form>
    </div>
  );
}

export default withStandaloneModal(RoomTypeFormBody, (p) => `/hotels/${p.hotel.id}/`);
