import axios from "axios";
import { router } from "@inertiajs/react";
import { useI18n } from "../../utils/i18n.jsx";

// Homlu v2.1 (doc 1e): one component, two shapes.
//  - default  → segmented control for a wide topbar / settings row
//  - "mini"   → the same segmented control, tightened for the account menu row
// Language codes shown as value chips, no flags. HMS ships id + en locales
// (AR has no translation catalogue yet, so it is omitted rather than shown dead).
const LANGUAGES = [
  { code: "id", label: "ID" },
  { code: "en", label: "EN" },
];

export default function LanguageSwitcher({ variant = "default" }) {
  const { locale, t } = useI18n();

  const change = async (value) => {
    if (value === locale) return;
    try {
      await axios.post("/account/language/", new URLSearchParams({ language: value }));
      router.reload();
    } catch {
      /* keep current language on failure */
    }
  };

  return (
    <div className={"hms-seg" + (variant === "mini" ? " hms-seg--mini" : "")} role="group" aria-label={t("Language")}>
      {LANGUAGES.map((lang) => (
        <button
          key={lang.code}
          type="button"
          className={"hms-seg-opt" + (locale === lang.code ? " active" : "")}
          aria-pressed={locale === lang.code}
          onClick={(e) => { e.stopPropagation(); change(lang.code); }}
        >
          {lang.label}
        </button>
      ))}
    </div>
  );
}
