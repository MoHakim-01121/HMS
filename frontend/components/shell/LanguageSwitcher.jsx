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

  // Mobile/compact: one row, matching app's co-option pattern. No dropdown —
  // tapping it switches straight to the other language; the badge on the
  // right just labels what the tap does.
  const other = LANGUAGES.find((l) => l.code !== locale) || LANGUAGES[1];
  return (
    <button
      type="button"
      className="hms-lang-trigger co-option"
      aria-label={t("Switch language to {lang}", { lang: other.label })}
      onClick={(e) => {
        e.stopPropagation();
        change(other.code);
      }}
    >
      <span className="hms-lang-trigger-label">
        <Icon name="globe" size={13} />
        <span className="hms-lang-name">{current.label}</span>
      </span>
      <span className="hms-lang-switch-badge">
        {t("Switch")}
        <Icon name="swap" size={11} strokeWidth={2.2} />
      </span>
    </button>
  );
}