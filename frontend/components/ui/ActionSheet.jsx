import { createPortal } from "react-dom";
import { Icon } from "../icons.jsx";

// Bottom sheet untuk aksi baris di mobile. `actions` memakai bentuk yang sama
// dengan RowActions: { icon, label, href?, onClick?, variant?, external? }.
// Di-portal ke <body> agar position:fixed tidak terjebak containing block
// (ancestor dengan transform/backdrop-filter di dalam kartu).
export default function ActionSheet({ open, onClose, title, actions }) {
  if (!open) return null;
  return createPortal(
    <div className="asheet-overlay" onClick={(e) => { e.stopPropagation(); onClose(); }}>
      <div className="asheet" onClick={(e) => e.stopPropagation()}>
        <div className="asheet-grab" aria-hidden="true"></div>
        {title && <div className="asheet-title">{title}</div>}
        {actions.filter(Boolean).map((a, i) => {
          const cls = "asheet-item" + (a.variant ? ` asheet-item-${a.variant}` : "");
          return a.href ? (
            <a key={i} href={a.href} className={cls} onClick={onClose}
              {...(a.external ? { target: "_blank", rel: "noreferrer" } : {})}>
              <Icon name={a.icon} size={16} /> {a.label}
            </a>
          ) : (
            <button key={i} type="button" className={cls}
              onClick={(e) => { onClose(); a.onClick && a.onClick(e); }}>
              <Icon name={a.icon} size={16} /> {a.label}
            </button>
          );
        })}
        <button type="button" className="asheet-cancel" onClick={onClose}>Cancel</button>
      </div>
    </div>,
    document.body
  );
}
