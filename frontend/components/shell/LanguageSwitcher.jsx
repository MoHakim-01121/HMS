import axios from "axios";
import { router } from "@inertiajs/react";
import { useI18n } from "../../utils/i18n.jsx";
import { Icon } from "../icons.jsx";

const LANGUAGES = [
  { code: "en", label: "EN" },
  { code: "id", label: "ID" },
];

export default function LanguageSwitcher({ compact = false }) {
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

  const current = LANGUAGES.find((l) => l.code === locale) || LANGUAGES[0];

  // Desktop: segmented control (shadcn style)
  if (!compact) {
    return (
      <div className="hms-lang-switch" role="group" aria-label={t("Language")}>
        {LANGUAGES.map((lang) => (
          <button
            key={lang.code}
            type="button"
            className={`hms-lang-btn ${locale === lang.code ? "active" : ""}`}
            title={lang.label}
            aria-pressed={locale === lang.code}
            onClick={() => change(lang.code)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                change(lang.code);
              }
            }}
          >
            <span className="hms-lang-code">{lang.label}</span>
          </button>
        ))}
      </div>
    );
  }

  // Mobile/compact: dropdown matching app's co-option pattern
  return (
    <div className="hms-lang-dropdown">
      <button
        type="button"
        className="hms-lang-trigger co-option"
        aria-haspopup="listbox"
        aria-expanded={false}
        aria-label={t("Language")}
        onClick={(e) => {
          e.stopPropagation();
          e.currentTarget.setAttribute("aria-expanded", "true");
        }}
      >
        <span className="hms-lang-name">{current.label}</span>
        <Icon name="chevron" size={12} strokeWidth={2.5} className="hms-lang-chevron" />
      </button>
      <ul
        className="hms-lang-list co-option-list"
        role="listbox"
        aria-label={t("Language")}
      >
        {LANGUAGES.map((lang) => (
          <li key={lang.code} role="option" aria-selected={locale === lang.code}>
            <button
              type="button"
              className={`hms-lang-option ${locale === lang.code ? "active" : ""}`}
              onClick={(e) => {
                e.stopPropagation();
                change(lang.code);
                document.querySelector(".hms-lang-trigger")?.setAttribute("aria-expanded", "false");
              }}
            >
              <span className="hms-lang-name">{lang.label}</span>
              {locale === lang.code && (
                <Icon name="check" size={12} strokeWidth={2.5} className="hms-lang-check" />
              )}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}