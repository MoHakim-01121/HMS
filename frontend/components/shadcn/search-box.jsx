import { Icon } from "../icons.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Search input used inside every list page's `.filter-bar`. Consolidates the
// byte-identical `.search-wrap` block (icon + debounced input + clear button)
// that used to be copy-pasted across Client/Hotel/Cl/Invoice/
// Remittance list pages — only the placeholder differed.
export default function SearchBox({ value, onChange, placeholder }) {
  const { t } = useI18n();
  return (
    <div className="search-wrap">
      <Icon name="search" size={13} />
      <input
        type="text"
        value={value}
        placeholder={t(placeholder)}
        onChange={(e) => onChange(e.target.value)}
      />
      {value && (
        <button type="button" className="sw-clear" title={t("Clear search")} onClick={() => onChange("")}>
          <Icon name="close" size={11} strokeWidth={2.5} />
        </button>
      )}
    </div>
  );
}