import { createContext, useCallback, useContext, useMemo } from "react";
import { usePage } from "@inertiajs/react";
import { en } from "../locales/en.js";
import { id } from "../locales/id.js";

const LocaleContext = createContext({ locale: "en", t: (str) => str });

const DICTS = { en, id };

export function LocaleProvider({ children }) {
  const { props } = usePage();
  const locale = props?.locale === "id" ? "id" : "en";
  const dict = DICTS[locale] || en;

  // t("Send recap to {name}?", { name: client }) → interpolates {name}.
  // Depend on `dict`, not `locale`: the callback reads `dict`, and the two
  // change together anyway (DICTS[locale]).
  const t = useCallback(
    (str, vars) => {
      let out = (dict && dict[str]) || str;
      if (vars) {
        for (const [k, v] of Object.entries(vars)) {
          out = out.split(`{${k}}`).join(String(v ?? ""));
        }
      }
      return out;
    },
    [dict],
  );

  const value = useMemo(() => ({ locale, t }), [locale, t]);
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useI18n() {
  return useContext(LocaleContext);
}
