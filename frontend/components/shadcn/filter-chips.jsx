import { Icon } from "../icons.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Active-filter chips (Homlu v2.1 doc 02b): appears under the toolbar only
// when a filter is applied. One chip per value; clicking its × removes just
// that value and reloads immediately, no panel involved. "Clear all" empties
// search, dates and status together.
// `chips`: [{ key, label, onRemove }]
export default function FilterChips({ chips, onClearAll }) {
  const { t } = useI18n();
  if (!chips || !chips.length) return null;
  return (
    <div className="hms-fchips">
      <span className="hms-fchips-label">{t("Active filters")}</span>
      {chips.map((c) => (
        <span key={c.key} className="hms-fchip" onClick={c.onRemove}>
          {c.label}
          <Icon name="close" size={12} strokeWidth={2} />
        </span>
      ))}
      <span className="hms-fchips-clear" onClick={onClearAll}>{t("Clear all")}</span>
    </div>
  );
}
