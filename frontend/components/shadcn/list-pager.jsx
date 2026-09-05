import { Icon } from "../icons.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Closing band for list pages whose backend view returns raw page primitives
// (page / numPages / total) rather than the pagination dict that <Pagination>
// consumes. Same `.hms-pag` skin as <Pagination> so the two read identically.
export default function ListPager({ page = 1, numPages = 1, total, unit = "results", onPage }) {
  const { t } = useI18n();
  const hasNav = numPages > 1 && typeof onPage === "function";
  if (total == null && !hasNav) return null;

  return (
    <nav className="hms-pag" aria-label={t("Pagination")}>
      <div className="hms-pag-count">
        {total != null && `${total.toLocaleString()} ${t(unit)}`}
      </div>

      {hasNav && (
        <div className="hms-pag-nav">
          <button
            type="button"
            className="hms-pag-step"
            disabled={page <= 1}
            aria-label={t("Previous page")}
            onClick={() => onPage(page - 1)}
          >
            <span className="hms-pag-chev back"><Icon name="chevron" size={14} /></span>
          </button>
          <span className="hms-pag-count-current" aria-current="page">{t("{page} of {total}", { page, total: numPages })}</span>
          <button
            type="button"
            className="hms-pag-step"
            disabled={page >= numPages}
            aria-label={t("Next page")}
            onClick={() => onPage(page + 1)}
          >
            <span className="hms-pag-chev fwd"><Icon name="chevron" size={14} /></span>
          </button>
        </div>
      )}
    </nav>
  );
}
