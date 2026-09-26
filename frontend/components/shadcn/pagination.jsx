import { Icon } from "../icons.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Pagination strip for list pages — 21st.dev HeroUI v3 Table direction (the
// same reference the `.hms-table-v2` skin follows). It reads as the closing
// band of the table card: the tinted strip the header uses, a result counter
// on the left, and Prev / page pills / Next on the right.
//
// Merges the two pagination contracts the pages used to swap between:
//   - `pagination` dict (number / range / has_previous / start_index / …)
//     from views that build page-aware ranges;
//   - raw `page` / `numPages` / `total` primitives from views that return
//     only the current page and its count (previously <ListPager>).
//
// The counter is skipped when a caller's payload predates `start_index`.
export default function Pagination({ pagination, onPage, unit = "results", page, numPages, total }) {
  const { t } = useI18n();

  if (pagination) {
    if (!pagination.has_other_pages) return null;
    const {
      number, range, has_previous, has_next,
      previous_page_number, next_page_number,
      start_index, end_index, count,
    } = pagination;
    return (
      <nav className="hms-pag" aria-label={t("Pagination")}>
        <div className="hms-pag-count">
          {count != null && t("{start} to {end} of {count} {unit}", { start: start_index, end: end_index, count, unit: t(unit) })}
        </div>
        <div className="hms-pag-nav">
          <button
            type="button"
            className="hms-pag-step"
            disabled={!has_previous}
            aria-label={t("Previous page")}
            onClick={() => onPage(previous_page_number)}
          >
            <span className="hms-pag-chev back"><Icon name="chevron" size={14} /></span>
          </button>
          {range.map((p, i) =>
            p === null ? (
              <span key={i} className="hms-pag-gap" aria-hidden="true">…</span>
            ) : p === number ? (
              <span key={i} className="hms-pag-num is-active" aria-current="page">{p}</span>
            ) : (
              <button key={i} type="button" className="hms-pag-num" onClick={() => onPage(p)}>
                {p}
              </button>
            )
          )}
          <button
            type="button"
            className="hms-pag-step"
            disabled={!has_next}
            aria-label={t("Next page")}
            onClick={() => onPage(next_page_number)}
          >
            <span className="hms-pag-chev fwd"><Icon name="chevron" size={14} /></span>
          </button>
        </div>
      </nav>
    );
  }

  // Primitive contract: only a page-aware nav (numPages > 1) or a total count
  // render anything at all.
  const hasNav = numPages > 1 && typeof onPage === "function";
  if (total == null && !hasNav) return null;

  return (
    <nav className="hms-pag" aria-label={t("Pagination")}>
      <div className="hms-pag-count">
        {total != null && `${total.toLocaleString("en-US")} ${t(unit)}`}
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