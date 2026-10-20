import { useEffect, useState } from "react";

// Keep a popover mounted for `ms` after `open` turns false, so it can play its
// closing animation instead of vanishing. Returns [mounted, closing].
export function usePresence(open, ms = 150) {
  const [mounted, setMounted] = useState(open);
  useEffect(() => {
    if (open) { setMounted(true); return undefined; }
    if (!mounted) return undefined;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const id = setTimeout(() => setMounted(false), reduce ? 0 : ms);
    return () => clearTimeout(id);
  }, [open, ms, mounted]);
  return [mounted || open, mounted && !open];
}
