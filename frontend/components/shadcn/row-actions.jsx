import { Icon } from "../icons.jsx";
import { Button } from "./ui/button.jsx";

// v2.1: row-action icons are muted ink; only a destructive action carries
// colour (red). "green" is accepted but no longer tints — it falls through
// to the default muted ghost so callers don't need touching.
const VARIANT_CLASS = {
  red: "text-destructive",
};

// Reverted from the single kebab-dropdown trigger back to one icon button
// per action, inline in the row — matching the pre-shadcn ../ui/RowActions.jsx
// behavior per user request. Same `actions` prop shape as before.
export default function RowActions({ actions }) {
  const list = actions.filter(Boolean);
  if (!list.length) return null;
  return (
    <div className="flex justify-end gap-0.5" onClick={(e) => e.stopPropagation()}>
      {list.map((a, i) => {
        const className = VARIANT_CLASS[a.variant];
        return a.href ? (
          <Button key={i} asChild variant="ghost" size="icon-sm" title={a.label} className={className}>
            <a href={a.href} aria-label={a.label} {...(a.external ? { target: "_blank", rel: "noreferrer" } : {})}>
              <Icon name={a.icon} size={14} strokeWidth={a.strokeWidth} />
            </a>
          </Button>
        ) : (
          <Button key={i} type="button" variant="ghost" size="icon-sm" title={a.label} aria-label={a.label} onClick={a.onClick} className={className}>
            <Icon name={a.icon} size={14} strokeWidth={a.strokeWidth} />
          </Button>
        );
      })}
    </div>
  );
}
