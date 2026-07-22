import { useState } from "react";
import { Icon } from "../icons.jsx";
import ActionSheet from "./ActionSheet.jsx";

export default function RowActions({ actions }) {
  const [open, setOpen] = useState(false);
  const list = actions.filter(Boolean);
  return (
    <div className="row-actions" onClick={(e) => e.stopPropagation()}>
      <span className="ra-inline">
        {list.map((a, i) => {
          const cls = ["btn", "btn-ghost", "btn-icon", a.variant && `btn-icon-${a.variant}`].filter(Boolean).join(" ");
          return a.href ? (
            <a
              key={i}
              href={a.href}
              className={cls}
              title={a.label}
              {...(a.external ? { target: "_blank", rel: "noreferrer" } : {})}
            >
              <Icon name={a.icon} size={14} strokeWidth={a.strokeWidth} />
            </a>
          ) : (
            <button key={i} type="button" className={cls} title={a.label} onClick={a.onClick}>
              <Icon name={a.icon} size={14} strokeWidth={a.strokeWidth} />
            </button>
          );
        })}
      </span>
      <button type="button" className="btn btn-ghost btn-icon ra-kebab" aria-label="Actions" aria-haspopup="true" aria-expanded={open} onClick={() => setOpen(true)}>
        <Icon name="dots" size={17} />
      </button>
      <ActionSheet open={open} onClose={() => setOpen(false)} actions={list} />
    </div>
  );
}
