import { Icon } from "../icons.jsx";
import { Button } from "./ui/button.jsx";

const VARIANT_COLOR = {
  red: "var(--destructive)",
  green: "var(--green, #15803D)",
};

// Reverted from the single kebab-dropdown trigger back to one icon button
// per action, inline in the row — matching the pre-shadcn ../ui/RowActions.jsx
// behavior per user request. Same `actions` prop shape as before.
export default function RowActions({ actions }) {
  const list = actions.filter(Boolean);
  if (!list.length) return null;
  return (
    <div className="row-actions" onClick={(e) => e.stopPropagation()} style={{ display: "flex", gap: 2, justifyContent: "flex-end" }}>
      {list.map((a, i) => {
        const style = VARIANT_COLOR[a.variant] ? { color: VARIANT_COLOR[a.variant] } : undefined;
        return a.href ? (
          <Button key={i} asChild variant="ghost" size="icon-sm" title={a.label} style={style}>
            <a href={a.href} aria-label={a.label} {...(a.external ? { target: "_blank", rel: "noreferrer" } : {})}>
              <Icon name={a.icon} size={14} strokeWidth={a.strokeWidth} />
            </a>
          </Button>
        ) : (
          <Button key={i} type="button" variant="ghost" size="icon-sm" title={a.label} aria-label={a.label} onClick={a.onClick} style={style}>
            <Icon name={a.icon} size={14} strokeWidth={a.strokeWidth} />
          </Button>
        );
      })}
    </div>
  );
}
