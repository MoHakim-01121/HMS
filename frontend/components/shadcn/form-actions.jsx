import { useContext } from "react";
import { Button } from "./ui/button.jsx";
import { FormModalContext } from "./form-modal.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// shadcn Button-based rebuild of ../form/FormActions.jsx — same props.
//
// Cancel used to be `ghost`, which gave it no edge at all: next to a solid
// primary it read as loose text rather than the other half of a pair. Homlu
// draws its secondary controls as 2px-stroked surfaces, so `outline` is the
// match — and both sit at `lg` (48px) to line up with the fields above them.
//
// The .hms-form-actions class is what tailwind.css sticks to the bottom of the
// dialog's scroll area, so the submit row stays reachable in a long form
// instead of being stranded below the fold.
export default function FormActions({ cancelHref, submitLabel, processing }) {
  const { t } = useI18n();
  const ctx = useContext(FormModalContext);
  return (
    <div className="hms-form-actions" style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
      {ctx?.inModal ? (
        <Button type="button" variant="outline" size="lg" onClick={ctx.close}>{t("Cancel")}</Button>
      ) : (
        <Button asChild variant="outline" size="lg">
          <a href={cancelHref}>{t("Cancel")}</a>
        </Button>
      )}
      {submitLabel && (
        <Button type="submit" size="lg" disabled={processing}>
          {submitLabel}
        </Button>
      )}
    </div>
  );
}
