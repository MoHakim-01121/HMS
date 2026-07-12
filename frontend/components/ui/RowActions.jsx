import { Icon } from "../icons.jsx";

export default function RowActions({ actions }) {
  return (
    <div className="row-actions" onClick={(e) => e.stopPropagation()}>
      {actions.filter(Boolean).map((a, i) => {
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
    </div>
  );
}
