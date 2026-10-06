import { useEffect, useRef } from "react";

// Close a hand-rolled popup (filter panel, sort menu) on a pointer press
// outside `ref` or on Escape, so opening any other menu on the page closes it
// instead of stacking on top of it. Radix menus already behave this way.
//
// Presses inside a portaled Radix surface (a select/combobox list opened from
// within the popup) are ignored: they render under <body>, outside `ref`, but
// belong to the popup.
export default function useDismiss(open, onClose) {
  const ref = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      if (ref.current?.contains(e.target)) return;
      if (e.target.closest?.("[data-radix-popper-content-wrapper]")) return;
      closeRef.current();
    };
    const onKey = (e) => { if (e.key === "Escape") closeRef.current(); };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return ref;
}
