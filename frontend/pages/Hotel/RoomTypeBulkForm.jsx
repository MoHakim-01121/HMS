import { useForm } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import { Checkbox } from "../../components/shadcn/ui/checkbox.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { suggestRoomTypeName } from "./roomTypeName.js";
import { Pill } from "../../components/shadcn/list-a.jsx";
import Page from "../../components/shadcn/page.jsx";

// Hotels in Makkah/Madinah mostly sell the same grid — Double…Quint across a
// few views — so this builds it in one go. The preview mirrors what the
// server will do: names already in the catalog are skipped, not overwritten.
function RoomTypeBulkFormBody({ hotel, capacity_choices = [], view_choices = [], existing_names = [], existing_pairs = [], errors: serverErrors }) {
  const { t } = useI18n();
  // What the hotel already sells, as capacity/view pairs — pre-checked so the
  // ticket state mirrors the catalog and duplicate names are never offered.
  const combos = existing_pairs.filter((c) => c.capacity != null);
  const initialCapacities = [...new Set(combos.map((c) => c.capacity))];
  const initialViews = [...new Set(combos.map((c) => c.view).filter(Boolean))];
  const form = useForm({ capacities: initialCapacities, views: initialViews });
  const errors = { ...serverErrors, ...form.errors };
  const back = `/hotels/${hotel.id}/`;

  const occupancyLabels = Object.fromEntries(capacity_choices.map((c) => [String(c.value), c.label]));
  const existing = new Set(existing_names);
  const comboKeys = new Set(combos.map((c) => `${c.capacity}|${c.view || ""}`));
  // Server order: views outer, capacities inner, both in master order.
  const views = form.data.views.length ? form.data.views : [""];
  const preview = views.flatMap((view) => form.data.capacities.map((capacity) => {
    const name = suggestRoomTypeName(capacity, view, occupancyLabels, view_choices);
    const exists = existing.has(name) || comboKeys.has(`${capacity}|${view || ""}`);
    return { name, exists };
  }));
  const toCreate = preview.filter((p) => !p.exists).length;

  const toggle = (key, master, value, on) => {
    const picked = new Set(form.data[key]);
    if (on) picked.add(value); else picked.delete(value);
    form.setData(key, master.map((c) => c.value).filter((v) => picked.has(v)));
  };

  const submit = (e) => {
    e.preventDefault();
    // JSON strings, same convention as MealPlanForm: forceFormData would
    // otherwise flatten the arrays into capacities[0]… keys.
    form.transform((data) => ({ capacities: JSON.stringify(data.capacities), views: JSON.stringify(data.views) }));
    form.post(`/hotels/${hotel.id}/room-types/bulk/`, { forceFormData: true });
  };

  // A plain render helper, not a component: a component declared in here
  // would remount every render and drop keyboard focus off the checkbox.
  const choices = (name, master, translate) => (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "10px 20px" }}>
      {master.map((c) => (
        <label key={c.value} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
          <Checkbox checked={form.data[name].includes(c.value)} onCheckedChange={(v) => toggle(name, master, c.value, !!v)} />
          <span>{translate ? t(c.label) : c.label}</span>
        </label>
      ))}
    </div>
  );

  return (
    <Page size="form">
      <PageBack href={back} />
      <FormHeader
        kicker={hotel.name}
        title={t("Bulk Add Room Types")}
        sub={t("Tick the capacities and views this hotel sells — one room type is created for each combination.")}
      />
      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label={t("Capacity")}>
            {choices("capacities", capacity_choices, false)}
            {errors.capacities && <div role="alert" style={{ marginTop: 8, fontSize: 12, color: "var(--destructive)" }}>{errors.capacities}</div>}
          </FormSection>

          <FormSection label={t("Room View")}>
            {choices("views", view_choices, true)}
            <div style={{ marginTop: 8, fontSize: 12, color: "var(--muted-foreground)" }}>
              {t("Optional — leave all unticked for names without a view.")}
            </div>
          </FormSection>

          <FormSection label={t("Preview")}>
            {preview.length ? (
              <div className="flex flex-wrap gap-1.5">
                {preview.map((p) => (
                  <Pill
                    key={p.name}
                    tone={p.exists ? "gray" : "green"}
                    className={p.exists ? "line-through" : undefined}
                    title={p.exists ? t("Already in this hotel — will be skipped") : undefined}
                  >
                    {p.exists ? "✓ " : ""}{p.name}
                  </Pill>
                ))}
              </div>
            ) : (
              <div className="py-3 text-[13px] text-muted-foreground">{t("Tick at least one capacity to see the room types.")}</div>
            )}
          </FormSection>

          <FormActions
            cancelHref={back}
            submitLabel={t(toCreate === 1 ? "Create 1 room type" : "Create {n} room types", { n: toCreate })}
            processing={form.processing || toCreate === 0}
          />
        </FormPanel>
      </form>
    </Page>
  );
}

export default withStandaloneModal(RoomTypeBulkFormBody, (p) => `/hotels/${p.hotel.id}/`);
