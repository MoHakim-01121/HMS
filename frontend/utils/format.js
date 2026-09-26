// Shared number/date formatters for the frontend.
// English locale is intentional — SAR figures use Arabic numerals.

export const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

export const fmtDec = (n, max = 2) =>
  Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: max });

// Same rounding as Hotel.distance_label on the server ("850 m", "1.2 km"),
// so client-computed distances read the same as server-sent labels.
export const fmtDist = (m) =>
  m < 1000 ? Math.round(m) + " m" : (m / 1000).toFixed(1) + " km";

// Attachment sizes: "820 B", "340 KB", "2.4 MB".
export const fmtSize = (n) => {
  if (!n) return "";
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  if (n >= 1024) return `${Math.round(n / 1024)} KB`;
  return `${n} B`;
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const pad = (n) => String(n).padStart(2, "0");

// Accepts a Date, 'YYYY-MM-DD', 'DD/MM/YYYY' (what most views send) or a full
// ISO timestamp. Date-only strings become local calendar dates — new Date()
// would read them as UTC midnight and shift the day west of Greenwich.
export function toDate(v) {
  if (!v) return null;
  if (v instanceof Date) return Number.isNaN(+v) ? null : v;
  let m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v);
  if (m) return new Date(+m[1], +m[2] - 1, +m[3]);
  m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(v);
  if (m) return new Date(+m[3], +m[2] - 1, +m[1]);
  const d = new Date(v);
  return Number.isNaN(+d) ? null : d;
}

const dayMonth = (d) => `${pad(d.getDate())} ${MONTHS[d.getMonth()]}`;

// App-wide display dates: "02 Sep 2026", or "02 Sep" where the year is
// obvious from context. Empty input gives ""; unparsable input passes through.
export const fmtDate = (v) => {
  const d = toDate(v);
  return d ? `${dayMonth(d)} ${d.getFullYear()}` : v || "";
};

export const fmtDateShort = (v) => {
  const d = toDate(v);
  return d ? dayMonth(d) : v || "";
};

// "02 Oct – 18 Oct 2026"; the year is written once when both ends share it.
export function fmtStay(a, b) {
  const da = toDate(a);
  const db = toDate(b);
  if (!da || !db) return fmtDate(a || b);
  const left = da.getFullYear() === db.getFullYear() ? dayMonth(da) : fmtDate(da);
  return `${left} – ${fmtDate(db)}`;
}

// ISO 'YYYY-MM-DD' → 'DD/MM/YYYY', the compact format the server already
// sends for table columns (CL/Invoice/Remittance). Anything else passes through.
export const fmtDMY = (iso) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
};
