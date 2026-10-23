import { Link } from "@inertiajs/react";
import { useContext } from "react";
import { FormModalContext } from "./form-modal.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Back link above a list or form page's header. Hidden inside a FormModal,
// which has its own close button.
export default function PageBack({ href = "/", label = "Back" }) {
  const { t } = useI18n();
  if (useContext(FormModalContext)?.inModal) return null;
  return (
    <div className="mb-4 flex items-center justify-between gap-4">
      <Link href={href} className="inline-flex h-[26px] items-center gap-1.5 text-[13px] font-semibold text-foreground no-underline hover:text-muted-foreground">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M15 6l-6 6 6 6" /></svg>
        {t(label)}
      </Link>
    </div>
  );
}
