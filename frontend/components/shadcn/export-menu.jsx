import { useEffect, useId, useRef, useState } from "react";
import { Icon } from "../icons.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// The "Export ▾" split affordance on list pages. Replaces three copies of a
// `<div onClick>` toggle that had no menu semantics, no aria-expanded, and no
// Escape / outside-click close.
//
//   items: [{ href, label, icon, external }]
export default function ExportMenu({ items, label }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const btnRef = useRef(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === "Escape") { setOpen(false); btnRef.current?.focus(); }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className={`export-dropdown${open ? " open" : ""}`} ref={wrapRef}>
      <button
        type="button"
        ref={btnRef}
        className="btn btn-secondary export-btn"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((v) => !v)}
      >
        {label || t("Export")} ▾
      </button>
      {open && (
        <div className="export-menu" id={menuId} role="menu">
          {items.map((it) => (
            <a
              key={it.href}
              href={it.href}
              role="menuitem"
              {...(it.external ? { target: "_blank", rel: "noreferrer" } : {})}
              onClick={() => setOpen(false)}
            >
              {it.icon && <Icon name={it.icon} size={13} />} {it.label}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
