import { useContext } from "react";
import { Button } from "./ui/button.jsx";
import { FormModalContext, actionsClass } from "./form-modal.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// shadcn Button-based rebuild of ../form/FormActions.jsx — same props.
//
// Cancel used to be `ghost`, which gave it no edge at all: next to a solid
// primary it read as loose text rather than the other half of a pair. Homlu
// draws its secondary controls as 2px-stroked surfaces, so `outline` is the
// match — and both sit at `lg` (48px) to line up with the fields above them.
//
// Inside a dialog the row sticks to the bottom of the scroll area (see
// actionsClass), so the submit button stays reachable in a long form instead
// of being stranded below the fold.
export default function FormActions({ cancelHref, submitLabel, processing }) {
  const { t } = useI18n();
  const ctx = useContext(FormModalContext);
  return (
    <div className={actionsClass()}>
      {ctx?.inModal ? (
        <Button type="button" variant="outline" size="lg" onClick={ctx.close}>{t("Cancel")}</Button>
      ) : (
        <Button asChild variant="outline" size="lg">
          <a href={cancelHref}>{t("Cancel")}</a>
        </Button>
      )}
      {submitLabel && (
        <Button type="submit" size="lg" disabled={processing}>
          {processing ? t("Saving…") : submitLabel}
        </Button>
      )}
    </div>
  );
}
