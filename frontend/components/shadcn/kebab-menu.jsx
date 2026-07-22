import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu.jsx";

// shadcn/Radix rebuild of ../detail/KebabMenu.jsx — same `items` prop shape.
// Radix's DropdownMenuTrigger sets aria-haspopup/aria-expanded on the real
// button automatically, so those attributes no longer need to be added by hand.
export default function KebabMenu({ items = [] }) {
  if (!items.length) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className="dv-kebab" aria-label="Actions">
          <svg viewBox="0 0 24 24"><circle cx="12" cy="5" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="12" cy="19" r="1" /></svg>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {items.map((it) =>
          it.href ? (
            <DropdownMenuItem key={it.label} asChild variant={it.danger ? "destructive" : "default"}>
              <a href={it.href} target={it.target} rel={it.target === "_blank" ? "noreferrer" : undefined}>
                {it.label}
              </a>
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem key={it.label} onClick={it.onClick} variant={it.danger ? "destructive" : "default"}>
              {it.label}
            </DropdownMenuItem>
          )
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
