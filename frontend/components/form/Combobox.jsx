import { useState, useRef, useEffect } from "react";

// Searchable dropdown that also allows free text.
// - value / onTextChange: the displayed text (free-typed or chosen label)
// - onSelect(option): fired when an option is picked from the list
// - options: [{ id, ... }]; getLabel/getSub derive the shown text
export default function Combobox({
  name, value, onTextChange, onSelect, options = [],
  getLabel = (o) => o.name, getSub, placeholder, error,
}) {
  const [open, setOpen] = useState(false);
  const [focused, setFocused] = useState(-1);
  const wrapRef = useRef(null);

  const q = (value || "").trim().toLowerCase();
  const filtered = q ? options.filter((o) => getLabel(o).toLowerCase().includes(q)) : options;

  useEffect(() => {
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const choose = (o) => {
    onSelect(o);
    setOpen(false);
    setFocused(-1);
  };

  const onKeyDown = (e) => {
    if (!open && (e.key === "ArrowDown" || e.key === "ArrowUp")) { setOpen(true); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); setFocused((i) => Math.min(i + 1, filtered.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setFocused((i) => Math.max(i - 1, 0)); }
    else if (e.key === "Enter" && open && focused >= 0 && filtered[focused]) { e.preventDefault(); choose(filtered[focused]); }
    else if (e.key === "Escape") { setOpen(false); }
  };

  return (
    <div ref={wrapRef} style={{ position: "relative" }}>
      <input
        id={name} name={name} autoComplete="off"
        value={value ?? ""}
        onChange={(e) => { onTextChange(e.target.value); setOpen(true); setFocused(-1); }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        aria-invalid={error ? "true" : undefined}
        className={error ? "is-invalid" : undefined}
      />
      {open && (
        <div style={{
          position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 50,
          background: "var(--surface-2)", border: "1px solid var(--border-2)",
          borderRadius: "var(--r-lg)", maxHeight: 240, overflowY: "auto",
          boxShadow: "0 12px 32px rgba(0,0,0,.5)",
        }}>
          {filtered.length === 0 ? (
            <div className="ac-empty">No client — used as guest name</div>
          ) : filtered.map((o, i) => (
            <div
              key={o.id}
              className={"ac-item" + (i === focused ? " focused" : "")}
              onMouseDown={(e) => { e.preventDefault(); choose(o); }}
              onMouseEnter={() => setFocused(i)}
            >
              <span>{getLabel(o)}</span>
              {getSub && getSub(o) && <span className="ac-item-sub">{getSub(o)}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
