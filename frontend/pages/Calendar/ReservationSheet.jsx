import { createPortal } from "react-dom";

// Bottom sheet detail reservasi untuk layar sentuh (pengganti tooltip hover).
// Memakai pola asheet-* dari design.css; kelas rs-* di-inject dari gridCss
// di Index.jsx. Di-portal ke <body> agar position:fixed tidak terjebak
// containing block.
export default function ReservationSheet({ res, cd, onClose }) {
  if (!res) return null;
  return createPortal(
    <div className="asheet-overlay" onClick={onClose}>
      <div className="asheet" onClick={(e) => e.stopPropagation()}>
        <div className="asheet-grab" aria-hidden="true"></div>
        <div className="rs-head">
          <div className="rs-guest">{res.guest}</div>
          <span className={`rs-status rs-status-${res.color}`}>{res.status}</span>
        </div>
        <div className="rs-body">
          <span className="tt-label">CL No</span><span className="tt-val">{res.ref}</span>
          <span className="tt-label">CI/CO</span><span className="tt-val">{res.start} – {res.end}</span>
          <span className="tt-label">Check-in</span><span className="tt-val" style={{ color: cd?.color }}>{cd?.text}</span>
          <span className="tt-label">Malam</span><span className="tt-val">{res.nights} malam</span>
          <span className="tt-label">Total</span><span className="tt-val">{res.total}</span>
          {res.inv_number && (<>
            <span className="tt-label">Invoice</span>
            <a className="tt-inv-link" href={res.inv_url || "#"}>{res.inv_number}</a>
            <span className="tt-label">Sisa</span>
            <span className="tt-sisa-val" style={{ color: res.inv_remaining && res.inv_remaining !== "0 SAR" ? "var(--red)" : "var(--green)" }}>{res.inv_remaining || "—"}</span>
          </>)}
        </div>
        <a className="rs-cta" href={res.url}>Buka CL</a>
        <button type="button" className="asheet-cancel" onClick={onClose}>Tutup</button>
      </div>
    </div>,
    document.body
  );
}
