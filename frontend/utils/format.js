// Shared number/date formatters for the frontend.
// English locale is intentional — SAR figures use Arabic numerals.

export const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

export const fmtDec = (n, max = 2) =>
  Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: max });

export const fmtDate = (iso) =>
  iso
    ? new Date(iso).toLocaleDateString("en-US", { day: "2-digit", month: "short" })
    : "-";

export const fmtDist = (m) =>
  m < 1000 ? Math.round(m) + " m" : (m / 1000).toFixed(2) + " km";
