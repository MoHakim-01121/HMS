import { createPortal } from "react-dom";
import { useI18n } from "../../utils/i18n.jsx";

// Bottom sheet reservation details for touch screens (replaces the hover
// tooltip). Uses the asheet-* pattern from design.css; rs-* classes are
// injected from gridCss in Index.jsx. Portaled to <body> so position:fixed is
// not trapped by a containing block.
export default function ReservationSheet({ res, cd, onClose }) {
  const { t } = useI18n();
  if (!res) return null;
  const cdText = cd
    ? (cd.key === "today" ? t("Today")
      : cd.key === "tomorrow" ? t("Tomorrow")
      : cd.key === "in" ? t("in {n} days", { n: cd.n })
      : t("{n} days ago", { n: cd.n }))
    : null;
  return createPortal(
    <div className="asheet-overlay" onClick={onClose}>
      <div className="asheet" onClick={(e) => e.stopPropagation()}>
        <div className="asheet-grab" aria-hidden="true"></div>
        <div className="rs-head">
          <div className="rs-guest">{res.guest}</div>
          <span className={`rs-status rs-status-${res.color}`}>{res.status}</span>
        </div>
        <div className="rs-body">
          <span className="tt-label">{t("CL No")}</span><span className="tt-val">{res.ref}</span>
          <span className="tt-label">{t("CI / CO")}</span><span className="tt-val">{res.start} – {res.end}</span>
          <span className="tt-label">{t("Check-in")}</span><span className="tt-val" style={{ color: cd?.color }}>{cdText}</span>
          <span className="tt-label">{t("Nights")}</span><span className="tt-val">{t("{n} nights", { n: res.nights })}</span>
          <span className="tt-label">{t("Total")}</span><span className="tt-val">{res.total}</span>
          {res.inv_number && (<>
            <span className="tt-label">{t("Invoice")}</span>
            <a className="tt-inv-link" href={res.inv_url || "#"}>{res.inv_number}</a>
            <span className="tt-label">{t("Remaining")}</span>
            <span className="tt-sisa-val" style={{ color: res.inv_remaining && res.inv_remaining !== "0 SAR" ? "var(--red)" : "var(--green)" }}>{res.inv_remaining || "—"}</span>
          </>)}
        </div>
        <a className="rs-cta" href={res.url}>{t("Open CL")}</a>
        <button type="button" className="asheet-cancel" onClick={onClose}>{t("Close")}</button>
      </div>
    </div>,
    document.body
  );
}
