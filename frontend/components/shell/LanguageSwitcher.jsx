import axios from "axios";
import { router } from "@inertiajs/react";
import { cn } from "@/lib/utils";
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
  const mini = variant === "mini";

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
    <div className={cn("inline-flex items-center gap-0.5 rounded-full bg-secondary p-[3px]", mini && "p-0.5")} role="group" aria-label={t("Language")}>
      {LANGUAGES.map((lang) => (
        <button
          key={lang.code}
          type="button"
          className={cn(
            "inline-flex h-[30px] cursor-pointer appearance-none items-center rounded-full border border-transparent bg-transparent px-4 font-[family-name:inherit] text-[12px] font-semibold whitespace-nowrap text-muted-foreground",
            "transition-[color,background-color] duration-[120ms] hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid",
            mini && "h-6 px-3",
            locale === lang.code && "border-border bg-card text-foreground",
          )}
          aria-pressed={locale === lang.code}
          onClick={(e) => { e.stopPropagation(); change(lang.code); }}
        >
          {lang.label}
        </button>
      ))}
    </div>
  );
}
