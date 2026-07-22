import { useState } from "react";
import { Popover, PopoverAnchor, PopoverContent } from "./ui/popover.jsx";
import { Command, CommandGroup, CommandItem, CommandList } from "./ui/command.jsx";

// shadcn Popover+Command rebuild of ../form/Combobox.jsx — same props.
// PopoverAnchor wraps a real <input> (not shadcn's Input component, which
// isn't ref-forwarding) so free-text entry keeps working: `open` is driven
// by focus/typing, not by a click-to-toggle trigger, and onOpenAutoFocus is
// prevented so opening the popover never steals focus away from the input.
// Arrow-key highlight/Enter-to-select now come from cmdk instead of the old
// manual `focused` state + onKeyDown.
export default function Combobox({
  name, value, onTextChange, onSelect, options = [],
  getLabel = (o) => o.name, getSub, placeholder, error,
  emptyLabel = "No client — used as guest name",
  "aria-describedby": describedBy,
}) {
  const [open, setOpen] = useState(false);

  const q = (value || "").trim().toLowerCase();
  const filtered = q ? options.filter((o) => getLabel(o).toLowerCase().includes(q)) : options;

  const choose = (o) => {
    onSelect(o);
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverAnchor asChild>
        <input
          id={name} name={name} autoComplete="off"
          value={value ?? ""}
          onChange={(e) => { onTextChange(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}
          placeholder={placeholder}
          aria-invalid={error ? "true" : undefined}
          aria-describedby={describedBy}
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-base shadow-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 md:text-sm"
        />
      </PopoverAnchor>
      <PopoverContent
        align="start"
        className="p-0"
        style={{ width: "var(--radix-popover-trigger-width)" }}
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        <Command shouldFilter={false}>
          <CommandList>
            {filtered.length === 0 ? (
              <div style={{ padding: 12, fontSize: 13, color: "var(--muted-foreground)" }}>{emptyLabel}</div>
            ) : (
              <CommandGroup>
                {filtered.map((o, i) => (
                  <CommandItem key={o.id ?? i} value={String(o.id ?? i)} onSelect={() => choose(o)}>
                    <div style={{ display: "flex", flexDirection: "column" }}>
                      <span>{getLabel(o)}</span>
                      {getSub && getSub(o) && <span style={{ fontSize: 11, color: "var(--muted-foreground)" }}>{getSub(o)}</span>}
                    </div>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
