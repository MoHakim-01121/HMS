import { Fragment } from "react";
import { Icon } from "../icons.jsx";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// shadcn/Radix rebuild of ../detail/KebabMenu.jsx — same `items` prop shape.
// Radix's DropdownMenuTrigger sets aria-haspopup/aria-expanded on the real
// button automatically, so those attributes no longer need to be added by hand.
// Optional per item: `icon` (Icon name) and `separator: true` (draws a rule
// above the item, e.g. to fence a destructive action off from the rest).
export default function KebabMenu({ items = [] }) {
  const { t } = useI18n();
  // Callers gate entries with `perms.can(...) && {...}`, so drop the falsy
  // holes before rendering — same contract as row-actions.jsx.
  items = items.filter(Boolean);
  if (!items.length) return null;
  return (
    // modal=false: see row-actions.jsx — Radix's default modal scroll-lock
    // fights this app's `body { padding-left: var(--sidebar-w) }` shell
    // layout and shifts the whole page while the menu is open.
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <button type="button" className="dv-kebab" aria-label={t("Actions")}>
          <Icon name="dots" size={14} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {items.map((it, i) => {
          const body = (
            <>
              {it.icon ? <Icon name={it.icon} size={14} /> : null}
              {it.label}
            </>
          );
          const item = it.href ? (
            <DropdownMenuItem asChild variant={it.danger ? "destructive" : "default"}>
              <a href={it.href} target={it.target} rel={it.target === "_blank" ? "noreferrer" : undefined}>
                {body}
              </a>
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem onClick={it.onClick} variant={it.danger ? "destructive" : "default"}>
              {body}
            </DropdownMenuItem>
          );
          return (
            <Fragment key={it.label}>
              {it.separator && i > 0 ? <DropdownMenuSeparator /> : null}
              {item}
            </Fragment>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
