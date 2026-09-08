import { Icon } from "../icons.jsx";
import { Button } from "./ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// The list pages' filter dropdown: one trigger `.fbar-btn` (with the active
// count badge) that toggles the `.filter-panel` popup. All panels share the
// same shell — header, labelled sections with per-section Reset, and the
// Reset all / Apply footer — only the section bodies vary, so the sections
// are passed as children.
//
//   count      number of active filter groups (0 → badge hidden)
//   open       whether the popup is expanded
//   onToggle   toggles `open`
//   dirty      true → apply button reads "Apply changes" instead of "Apply"
//   onApply    commit the draft filters (the page also closes the popup)
//   onResetAll clear search + filters in one action
//   children   `.fp-section` blocks (label + reset + control)
export default function FilterPanel({ count = 0, open, onToggle, dirty, onApply, onResetAll, children }) {
  const { t } = useI18n();
  return (
    <div className="filter-panel-wrap" onClick={(e) => e.stopPropagation()}>
      <button type="button" className="fbar-btn" onClick={onToggle}>
        <Icon name="filter" size={13} /> {t("Filter")}
        {count > 0 && <span className="fbar-count">{count}</span>}
      </button>
      {open && (
        <div className="filter-panel open">
          <div className="fp-head"><span className="fp-title">{t("Filter")}</span></div>
          {children}
          <div className="fp-footer">
            <Button type="button" variant="ghost" size="sm" onClick={onResetAll}>{t("Reset all")}</Button>
            <Button type="button" size="sm" onClick={onApply}>{dirty ? t("Apply changes") : t("Apply")}</Button>
          </div>
        </div>
      )}
    </div>
  );
}

// One `.fp-section`: an optional labelled header with its own Reset, then the
// control body. Pass `label` + `onReset` when the section is a plain option
// group; for rich bodies (date ranges, multi-select status) callers use the
// raw `.fp-section` markup instead and `FilterPanel` accepts it as children.
export function FilterSection({ label, onReset, children }) {
  const { t } = useI18n();
  return (
    <div className="fp-section">
      <div className="fp-section-head">
        <span className="fp-section-label">{t(label)}</span>
        {onReset && (
          <button type="button" className="fp-reset" onClick={onReset}>{t("Reset")}</button>
        )}
      </div>
      {children}
    </div>
  );
}