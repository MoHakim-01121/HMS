import { router } from "@inertiajs/react";

// Shared Inertia navigation for list pages: keeps scroll/state, replaces
// history so filter changes don't pile up back-button entries, and drops
// empty params so URLs stay clean.
export function listVisit(url, params = {}) {
  const clean = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== "" && v !== null && v !== undefined)
  );
  router.get(url, clean, { preserveState: true, preserveScroll: true, replace: true });
}
