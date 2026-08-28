import { createPortal } from "react-dom";
import { useI18n } from "../../utils/i18n.jsx";

// Bottom sheet reservation details for touch screens (replaces the hover
// tooltip). Uses the asheet-* pattern from design.css; rs-* classes are
// injected from gridCss in Index.jsx. Portaled to <body> so position:fixed is
// not trapped by a containing block.
//
// Redesigned 2026-08-26: larger touch targets, swipe-to-dismiss via the grab
// handle, and a primary action button styled as a full-width CTA for thumb
// ergonomics.
const SHEET_CSS = `
.rs-head { padding:4px 4px 12px; display:flex; align-items:flex-start; justify-content:space-between; gap:10px; }
.rs-guest { font-size:17px; font-weight:700; color:var(--foreground); line-height:1.3; letter-spacing:-.02em; }
.rs-status { flex-shrink:0; padding:4px 12px; border-radius:9999px; font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:.04em; background:var(--secondary); color:var(--muted-foreground); margin-top:2px; }
.rs-status-dot-green { background:color-mix(in oklch, var(--green) 16%, transparent); color:var(--green); }
.rs-status-dot-yellow { background:color-mix(in oklch, var(--yellow) 18%, transparent); color:var(--yellow); }
.rs-status-dot-red { background:color-mix(in oklch, var(--red) 16%, transparent); color:var(--red); }

.rs-body { padding:0 4px 14px; display:grid; grid-template-columns:80px 1fr; gap:10px 12px; align-items:baseline; }
.rs-label { font-size:12px; color:var(--muted-foreground); font-weight:400; }
.rs-val { font-size:14px; color:var(--foreground); font-weight:500; font-variant-numeric:tabular-nums; }
.rs-inv-section { border-top:1px solid var(--border); padding:12px 4px 14px; display:grid; grid-template-columns:80px 1fr; gap:10px 12px; align-items:baseline; }
.rs-inv-link { font-size:14px; font-weight:600; color:var(--foreground); text-decoration:underline; text-underline-offset:2px; min-height:44px; display:inline-flex; align-items:center; }
.rs-sisa-val { font-size:14px; font-weight:600; font-variant-numeric:tabular-nums; }

/* Primary CTA — full-width, thumb-friendly */
.rs-cta { display:flex; align-items:center; justify-content:center; width:100%; min-height:48px; margin-top:4px; background:var(--primary); color:var(--primary-foreground); border:none; border-radius:12px; font-family:inherit; font-size:14px; font-weight:600; text-decoration:none; cursor:pointer; transition:opacity .12s; -webkit-tap-highlight-color:transparent; }
.rs-cta:active { opacity:.85; }
`;

const STATUS_TONE = { green: "rs-status-dot-green", yellow: "rs-status-dot-yellow", red: "rs-status-dot-red" };

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
      <style dangerouslySetInnerHTML={{ __html: SHEET_CSS }} />
      <div className="asheet" onClick={(e) => e.stopPropagation()}>
        <div className="asheet-grab" aria-hidden="true"></div>
        <div className="rs-head">
          <div className="rs-guest">{res.guest || res.ref || t("No name")}</div>
          <span className={"rs-status " + (STATUS_TONE[res.color] || "")}>{res.status}</span>
        </div>
        <div className="rs-body">
          <span className="rs-label">{t("CL No")}</span><span className="rs-val">{res.ref}</span>
          <span className="rs-label">{t("CI / CO")}</span><span className="rs-val">{res.start} – {res.end}</span>
          <span className="rs-label">{t("Check-in")}</span><span className="rs-val" style={{ color: cd?.color }}>{cdText}</span>
          <span className="rs-label">{t("Nights")}</span><span className="rs-val">{t("{n} nights", { n: res.nights })}</span>
          <span className="rs-label">{t("Total")}</span><span className="rs-val">{res.total}</span>
          {res.inv_number && (<>
            <span className="rs-label">{t("Invoice")}</span>
            <a className="rs-inv-link" href={res.inv_url || "#"}>{res.inv_number}</a>
            <span className="rs-label">{t("Remaining")}</span>
            <span className="rs-sisa-val" style={{ color: res.inv_remaining && res.inv_remaining !== "0 SAR" ? "var(--red)" : "var(--green)" }}>{res.inv_remaining || "—"}</span>
          </>)}
        </div>
        <a className="rs-cta" href={res.url}>{t("Open CL")}</a>
      </div>
    </div>,
    document.body
  );
}
