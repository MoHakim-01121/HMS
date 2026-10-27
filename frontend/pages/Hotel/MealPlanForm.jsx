import { useForm } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import { Checkbox } from "../../components/shadcn/ui/checkbox.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import Page from "../../components/shadcn/page.jsx";

// Picks from the global MealPlan master rather than creating anything — the
// codes are fixed (RO/BB/HB/FB), so this is one checkbox set saved at once,
// not the add/edit/remove rows the room-type catalog gets.
function MealPlanFormBody({ hotel, available = [], selected = [] }) {
  const { t } = useI18n();
  const form = useForm({ meal_plans: selected });
  const back = `/hotels/${hotel.id}/`;
  const chosen = new Set(form.data.meal_plans);

  const toggle = (code, on) => {
    const next = new Set(chosen);
    if (on) next.add(code); else next.delete(code);
    // Keep master order, so the saved set never depends on click order.
    form.setData("meal_plans", available.map((mp) => mp.code).filter((c) => next.has(c)));
  };

  const submit = (e) => {
    e.preventDefault();
    // Same JSON-string convention the hotel form used for its room rows:
    // forceFormData would otherwise flatten the array into meal_plans[0]… keys.
    form.transform((data) => ({ meal_plans: JSON.stringify(data.meal_plans) }));
    form.post(`/hotels/${hotel.id}/meal-plans/`, { forceFormData: true });
  };

  return (
    <Page size="form">
      <PageBack href={back} />
      <FormHeader kicker={hotel.name} title={t("Manage Meal Plans")} sub={t("Board types this hotel offers. Only these appear in the CL form's Meals column.")} />
      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label={t("Meal Plans")}>
            <div className="flex flex-col gap-2.5">
              {available.map((mp) => (
                <label key={mp.code} className="flex cursor-pointer items-center gap-2.5 text-[13px] font-medium text-muted-foreground">
                  <Checkbox checked={chosen.has(mp.code)} onCheckedChange={(v) => toggle(mp.code, !!v)} />
                  <span className="min-w-7 font-semibold tabular-nums">{mp.code}</span>
                  <span className="text-muted-foreground">{t(mp.name)}</span>
                </label>
              ))}
            </div>
          </FormSection>

          <FormActions cancelHref={back} submitLabel={t("Save")} processing={form.processing} />
        </FormPanel>
      </form>
    </Page>
  );
}

export default withStandaloneModal(MealPlanFormBody, (p) => `/hotels/${p.hotel.id}/`);
