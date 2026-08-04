import { useContext } from "react";
import { Link } from "@inertiajs/react";
import { FormModalContext } from "./form-modal.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Token-restyled rebuild of ../ui/PageBack.jsx — same props.
export default function PageBack({ href = "/", label = "Back" }) {
  const { t } = useI18n();
  // Rendered inside a FormModal dialog: the Dialog already has its own
  // close (X), and a Link here would navigate the whole app away instead
  // of closing the modal — so it's redundant, drop it.
  if (useContext(FormModalContext)?.inModal) return null;
  return (
    <Link href={href} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--muted-foreground)", textDecoration: "none", marginBottom: 16 }}>
      <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M19 12H5m7-7l-7 7 7 7" />
      </svg>
      {t(label)}
    </Link>
  );
}
