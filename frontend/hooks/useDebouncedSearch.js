import { useEffect, useRef, useState } from "react";

/**
 * Debounced search box state for list pages.
 *
 * Consolidates the copy-pasted pattern every list page had:
 *   - `query` state seeded from the server prop
 *   - a `first` ref so the initial render never fires a navigation
 *   - a 350ms debounce timer that calls `onSearch(query)` on change
 *
 * The callback is held in a ref, so pages may pass an inline closure that
 * captures the latest server props without re-arming the timer every render.
 *
 * @param {string} initial - server-supplied `q` prop
 * @param {(q: string) => void} onSearch - fired with the queued query
 * @param {number} delay - debounce delay in ms (default 350)
 * @returns {{ query, setQuery, clear }}
 */
export default function useDebouncedSearch(initial = "", onSearch, delay = 350) {
  const [query, setQuery] = useState(initial || "");
  const timer = useRef(null);
  const first = useRef(true);
  const cbRef = useRef(onSearch);
  cbRef.current = onSearch;

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    clearTimeout(timer.current);
    timer.current = setTimeout(() => cbRef.current(query), delay);
    return () => clearTimeout(timer.current);
  }, [query, delay]);

  const clear = () => setQuery("");

  return { query, setQuery, clear };
}