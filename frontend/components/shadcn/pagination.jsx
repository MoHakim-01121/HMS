import { Icon } from "../icons.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Pagination strip for list pages — 21st.dev HeroUI v3 Table direction (the
// same reference the `.hms-table-v2` skin follows). It reads as the closing
// band of the table card: the tinted strip the header uses, a result counter
// on the left, and Prev / page pills / Next on the right.
//
// Replaces four byte-identical copies of this markup (CL, Invoice, Hotel and
// Services list pages) that differed only in how they issued the request —
// hence `onPage`, which each page wires to its own query-building helper.
//
// `count`/`start_index`/`end_index` come from the views' pagination dict; the
// counter is skipped when a caller's payload predates them.
export default function Pagination({ pagination, onPage, unit = "results" }) {
  const { t } = useI18n();
  if (!pagination?.has_other_pages) return null;

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
          onClick={() => onPage(previous_page_number)}
        >
          <span className="hms-pag-chev back"><Icon name="chevron" size={13} /></span>
          {t("Prev")}
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
          onClick={() => onPage(next_page_number)}
        >
          {t("Next")}
          <span className="hms-pag-chev fwd"><Icon name="chevron" size={13} /></span>
        </button>
      </div>
    </nav>
  );
}
