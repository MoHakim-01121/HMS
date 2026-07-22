import { useEffect, useRef, useState } from "react";

// Dropdown aksi titik-tiga di hero detail (PDF, Edit). Tutup saat klik di luar.
export default function KebabMenu({ items = [] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  if (!items.length) return null;
  return (
    <span className="dv-kebab-wrap" ref={ref}>
      <button type="button" className="dv-kebab" aria-label="Actions" aria-haspopup="true" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <svg viewBox="0 0 24 24"><circle cx="12" cy="5" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="12" cy="19" r="1" /></svg>
      </button>
      {open && (
        <div className="dv-menu">
          {items.map((it) =>
            it.href ? (
              <a key={it.label} href={it.href} target={it.target} rel={it.target === "_blank" ? "noreferrer" : undefined} className={it.danger ? "danger" : undefined} onClick={() => setOpen(false)}>
                {it.label}
              </a>
            ) : (
              <button key={it.label} type="button" className={it.danger ? "danger" : undefined} onClick={() => { setOpen(false); if (it.onClick) it.onClick(); }}>
                {it.label}
              </button>
            )
          )}
        </div>
      )}
    </span>
  );
}
