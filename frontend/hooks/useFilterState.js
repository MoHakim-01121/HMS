import { useState } from "react";
import { router } from "@inertiajs/react";

/**
 * Hook untuk filter state + navigasi server-side.
 *
 * @param {Object} initialFilters - nilai awal dari server props
 * @param {string} basePath - URL path (mis. "/finance/journal/")
 * @returns {{ vals, setVal, apply, gotoPage }}
 */
export default function useFilterState(initialFilters = {}, basePath) {
  const [vals, setVals] = useState({ ...initialFilters });

  const setVal = (key, value) => setVals((prev) => ({ ...prev, [key]: value }));

  const apply = (page) => {
    const clean = Object.fromEntries(
      Object.entries(page !== undefined ? { ...vals, page } : vals).filter(
        ([, v]) => v !== "" && v !== undefined && v !== null,
      ),
    );
    router.get(basePath, clean);
  };

  return { vals, setVal, apply };
}
