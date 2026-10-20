import { useEffect, useRef, useState } from "react";
import { Link, router } from "@inertiajs/react";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import "../../styles/list-a.css";

// Building blocks of the approved list pages (Record View HMS canvas, row
// "Halaman list"). Pages compose these; the server owns filtering and paging.

const S = (props) => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props} />;
export const LIcon = {
  search: <S><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></S>,
  filter: <S><path d="M4 5h16l-6 7.5V19l-4 1.5v-8z" /></S>,
  export: <S><path d="M12 4v11m0 0l-4-4m4 4l4-4M5 20h14" /></S>,
  plus: <S strokeWidth="2.2"><path d="M12 5v14M5 12h14" /></S>,
  prev: <S width="16" height="16" strokeWidth="2"><path d="M15 18l-6-6 6-6" /></S>,
  next: <S width="16" height="16" strokeWidth="2"><path d="M9 6l6 6-6 6" /></S>,
  chev: <S strokeWidth="2"><path d="M6 9l6 6 6-6" /></S>,
  sortDown: <S width="13" height="13" strokeWidth="2"><path d="M12 5v14m0 0l-5-5m5 5l5-5" /></S>,
  sortUp: <S width="13" height="13" strokeWidth="2"><path d="M12 19V5m0 0l-5 5m5-5l5 5" /></S>,
  check: <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10" /></svg>,
  dots: <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1.7" fill="currentColor" /><circle cx="12" cy="12" r="1.7" fill="currentColor" /><circle cx="19" cy="12" r="1.7" fill="currentColor" /></svg>,
  up: <svg viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M12 19V5m0 0l-6 6m6-6l6 6" /></svg>,
  down: <svg viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M12 5v14m0 0l-6-6m6 6l6-6" /></svg>,
};

export const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const MON = MONTHS.map((m) => m.slice(0, 3));
export const fmtN = (v) => (v == null || v === "" ? "" : Math.round(Number(v)).toLocaleString("en-US"));
// "2026-10-28" -> "28 Oct"
export const dShort = (iso) => { if (!iso) return ""; const [, m, d] = iso.split("-"); return `${d} ${MON[+m - 1]}`; };
// Stay: "01 to 05 Nov", or "28 Oct to 02 Nov"
export const stay = (a, b, t) => {
  if (!a) return "";
  if (!b) return dShort(a);
  const [, am, ad] = a.split("-"), [, bm, bd] = b.split("-");
  return am === bm ? t("{a} to {b} {m}", { a: ad, b: bd, m: t(MON[+am - 1]) }) : t("{a} to {b}", { a: dShort(a), b: dShort(b) });
};

// Navigate the list to new query params (merged onto `current`); empty
// values drop out. Page resets unless given.
export function useListNav(base, current) {
  const [loading, setLoading] = useState(false);
  const go = (patch) => {
    const next = { ...current, page: undefined, ...patch };
    const params = {};
    for (const [k, v] of Object.entries(next)) {
      if (v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length)) continue;
      params[k] = Array.isArray(v) ? v.join(",") : v;
    }
    router.get(base, params, {
      preserveState: true, preserveScroll: true, replace: true,
      onStart: () => setLoading(true), onFinish: () => setLoading(false),
    });
  };
  return [go, loading];
}

export function ListPage({ title, legend, children, loading }) {
  return (
    <div className="page shadcn-root">
      <div className={"la-main" + (loading ? " la-loading" : "")}>
        <div className="la-head">
          <h1 className="la-h1">{title}</h1>
          {legend}
        </div>
        {children}
      </div>
    </div>
  );
}

export function Legend({ current, previous, note }) {
  return (
    <span className="la-lg">
      <span><i />{current}</span>
      <span><i className="g" />{previous}</span>
      {note && <span>{note}</span>}
    </span>
  );
}

export const Kpis = ({ children }) => <div className="la-kpis">{children}</div>;

// One KPI. Pressable when `onClick`/`href` (it then filters the table), `on`
// while its filter is the one applied.
export function Kpi({ label, value, unit, delta, foot, tone, onClick, href, on, spark, title }) {
  const body = (
    <>
      <span className="la-kt"><span className="l">{label}</span>{delta && <Delta {...delta} />}</span>
      <span className="la-kr"><span className={"la-v" + (tone ? " " + tone : "")}>{value}{unit && <small>{unit}</small>}</span>{spark}</span>
      {foot && <span className="la-kb">{foot}</span>}
    </>
  );
  const cls = "la-kpi" + (on ? " on" : "");
  if (href) return <Link className={cls} href={href} title={title}>{body}</Link>;
  if (onClick) return <button type="button" className={cls} aria-pressed={!!on} onClick={onClick} title={title}>{body}</button>;
  return <div className={cls} title={title}>{body}</div>;
}

export function Delta({ text, good, title }) {
  if (!text) return null;
  const up = !String(text).startsWith("-");
  return <span className={"la-d " + (good ? "good" : "bad")} title={title}>{up ? LIcon.up : LIcon.down}{text}</span>;
}

// Two cumulative series (this period, the one before) as a tiny line chart.
export function Spark({ cur = [], prev = [], label }) {
  const all = [...cur, ...prev].map(Number);
  const max = Math.max(1, ...all);
  const n = Math.max(cur.length, prev.length, 2);
  const pts = (arr) => arr.map((v, i) => `${(4 + (i * 75) / (n - 1)).toFixed(1)},${(28 - (Number(v) / max) * 24).toFixed(1)}`).join(" ");
  const last = cur.length ? pts(cur).split(" ").pop().split(",") : null;
  return (
    <svg width="84" height="32" viewBox="0 0 84 32" role="img" aria-label={label}>
      <title>{label}</title>
      {prev.length > 1 && <polyline points={pts(prev)} fill="none" className="la-sl ghost" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />}
      {cur.length > 1 && <polyline points={pts(cur)} fill="none" className="la-sl" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />}
      {last && <circle cx={last[0]} cy={last[1]} r="4" fill="var(--foreground)" stroke="var(--card)" strokeWidth="2" />}
    </svg>
  );
}

export function Toolbar({ left, children, spaced }) {
  return (
    <div className={"la-bar" + (spaced ? " spaced" : "")}>
      <div className="la-left">{left}</div>
      <div className="la-right">{children}</div>
    </div>
  );
}

// "October  ‹ ›  2026 ▾" — month = "YYYY-MM", or "" with year set (whole
// year), or both empty for all dates.
export function MonthNav({ month, year, years = [], onChange, prefix }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const y = month ? +month.slice(0, 4) : year ? +year : null;
  const m = month ? +month.slice(5, 7) - 1 : null;
  const shift = (d) => {
    const dt = new Date(y, m + d, 1);
    onChange({ month: `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}`, year: "" });
  };
  const label = m != null ? t(MONTHS[m]) : y ? t("Whole year") : t("All dates");
  return (
    <>
      {prefix && <span className="la-pre">{prefix}</span>}
      <span className="la-month">{label}</span>
      <button type="button" className="la-icon" aria-label={t("Previous month")} disabled={m == null} onClick={() => shift(-1)}>{LIcon.prev}</button>
      <button type="button" className="la-icon" aria-label={t("Next month")} disabled={m == null} onClick={() => shift(1)}>{LIcon.next}</button>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button type="button" className="la-yr" aria-haspopup="menu">{y || t("All")}{LIcon.chev}</button>
        </PopoverTrigger>
        <PopoverContent align="start" sideOffset={6} className="la-menu" style={{ width: 160 }}>
          <div role="menu">
            {years.map((yy) => (
              <button type="button" key={yy} role="menuitem" className={"la-mi" + (yy === y ? " on" : "")}
                onClick={() => { setOpen(false); onChange({ month: `${yy}-${String((m ?? new Date().getMonth()) + 1).padStart(2, "0")}`, year: "" }); }}>{yy}</button>
            ))}
            {y && <button type="button" role="menuitem" className={"la-mi" + (m == null ? " on" : "")} onClick={() => { setOpen(false); onChange({ month: "", year: String(y) }); }}>{t("Whole {year}", { year: y })}</button>}
            <div className="la-sep" />
            <button type="button" role="menuitem" className={"la-mi" + (!y ? " on" : "")} onClick={() => { setOpen(false); onChange({ month: "", year: "all" }); }}>{t("All dates")}</button>
          </div>
        </PopoverContent>
      </Popover>
    </>
  );
}

export function SearchTool({ value, onSearch, placeholder }) {
  const [q, setQ] = useState(value || "");
  const timer = useRef(null);
  useEffect(() => { setQ(value || ""); }, [value]);
  const change = (v) => {
    setQ(v);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => onSearch(v.trim()), 300);
  };
  return (
    <label className="la-tool la-search">
      {LIcon.search}
      <input value={q} onChange={(e) => change(e.target.value)} placeholder={placeholder} aria-label={placeholder}
        onKeyDown={(e) => { if (e.key === "Enter") { clearTimeout(timer.current); onSearch(q.trim()); } }} />
    </label>
  );
}

// The Filter button and its panel. Children edit a draft; Apply commits it.
export function FilterMenu({ count = 0, onApply, onReset, onOpen, children }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (o && onOpen) onOpen(); }}>
      <PopoverTrigger asChild>
        <button type="button" className="la-tool" aria-haspopup="dialog">
          {t("Filter")}{LIcon.filter}{count > 0 && <span className="badge">{count}</span>}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" sideOffset={8} className="la-menu la-filter" aria-label={t("Filter")}>
        {children}
        <div className="la-ffoot">
          <button type="button" className="la-tool reset" onClick={() => { onReset(); }}>{t("Reset")}</button>
          <button type="button" className="apply" onClick={() => { setOpen(false); onApply(); }}>{t("Apply")}</button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

export const FilterSection = ({ label, children, hint }) => (
  <div className="la-fsec">
    {label && <div className="la-fl">{label}</div>}
    {children}
    {hint && <div className="la-fhint">{hint}</div>}
  </div>
);

export function Check({ on, onClick, label, count, radio }) {
  return (
    <button type="button" className="la-ck" role={radio ? "radio" : "checkbox"} aria-checked={!!on} onClick={onClick}>
      {radio ? <span className={"la-rad" + (on ? " on" : "")} /> : <span className={"la-box" + (on ? " on" : "")}>{LIcon.check}</span>}
      {label}
      {count != null && <span className="c">{count}</span>}
    </button>
  );
}

export function DateRange({ from, to, onFrom, onTo }) {
  const { t } = useI18n();
  return (
    <div className="la-dates">
      <label className="la-date">{t("From")}<input type="date" value={from || ""} onChange={(e) => onFrom(e.target.value)} /></label>
      <label className="la-date">{t("To")}<input type="date" value={to || ""} onChange={(e) => onTo(e.target.value)} /></label>
    </div>
  );
}

// Export menu: [{ label, hint, href }]
export function ExportMenu({ items }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  if (!items.length) return null;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className="la-tool" aria-haspopup="menu">{t("Export")}{LIcon.export}</button>
      </PopoverTrigger>
      <PopoverContent align="end" sideOffset={8} className="la-menu" style={{ width: 280 }}>
        <div role="menu">
          {items.map((it) => (
            <a key={it.label} className="la-mi" role="menuitem" href={it.href} target={it.external ? "_blank" : undefined} rel="noreferrer" onClick={() => setOpen(false)}>
              <span>{it.label}{it.hint && <span className="h">{it.hint}</span>}</span>
            </a>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

export function Primary({ label, onClick, onPrefetch, href }) {
  if (href) return <Link className="la-primary" href={href}>{LIcon.plus}{label}</Link>;
  return <button type="button" className="la-primary" onClick={onClick} onPointerEnter={onPrefetch} onFocus={onPrefetch}>{LIcon.plus}{label}</button>;
}

// The row's ⋯ menu: [{ label, onClick | href, danger, external }]; falsy items drop.
export function RowMenu({ items, label }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const list = items.filter(Boolean);
  if (!list.length) return null;
  return (
    <span onClick={(e) => e.stopPropagation()} style={{ display: "inline-block" }}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button type="button" className="la-dots" aria-label={label || t("Actions")} aria-haspopup="menu">{LIcon.dots}</button>
        </PopoverTrigger>
        <PopoverContent align="end" sideOffset={4} className="la-menu" style={{ width: 200 }}>
          <div role="menu">
            {list.map((it) => it.href ? (
              <a key={it.label} role="menuitem" className={"la-mi" + (it.danger ? " danger" : "")} href={it.href}
                target={it.external ? "_blank" : undefined} rel="noreferrer" onClick={() => setOpen(false)}>{it.label}</a>
            ) : (
              <button type="button" key={it.label} role="menuitem" className={"la-mi" + (it.danger ? " danger" : "")}
                onClick={(e) => { setOpen(false); it.onClick(e); }}>{it.label}</button>
            ))}
          </div>
        </PopoverContent>
      </Popover>
    </span>
  );
}

export const Pill = ({ tone = "gray", sm, children }) => <span className={"la-pill " + tone + (sm ? " sm" : "")}>{children}</span>;

export function Amt({ code, value }) {
  return <span className="amt"><span className="code">{code}</span><b>{fmtN(value)}</b></span>;
}

// The table card. `cols` = widths (px or null); children = <thead>/<tbody>/<tfoot>.
export function TableCard({ cols, children, empty }) {
  return (
    <section className="la-card">
      <div className="la-scroll">
        <table className="la-t">
          {cols && <colgroup>{cols.map((w, i) => <col key={i} style={w ? { width: w } : undefined} />)}</colgroup>}
          {children}
        </table>
      </div>
      {empty}
    </section>
  );
}

export function Empty({ title, sub }) {
  return <div className="la-empty"><b>{title}</b>{sub}</div>;
}

// "Show 10 per page" and the page buttons. `p` is pagination_props from the server.
export function Pager({ p, perPage, onPage, onPerPage, summary }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  if (!p) return null;
  const page = p.number || p.page || 1;
  const pages = p.num_pages || p.pages || 1;
  const nums = [1, page - 1, page, page + 1, pages].filter((n, i, a) => n >= 1 && n <= pages && a.indexOf(n) === i).sort((a, b) => a - b);
  return (
    <div className="la-foot">
      {summary ? <span>{summary}</span> : (
        <span className="la-show">{t("Show")}
          <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild><button type="button" className="la-tool" aria-haspopup="menu">{perPage}{LIcon.chev}</button></PopoverTrigger>
            <PopoverContent side="top" align="start" sideOffset={6} className="la-menu" style={{ width: 90, minWidth: 0 }}>
              <div role="menu">{[10, 25, 50].map((n) => (
                <button type="button" key={n} role="menuitem" className={"la-mi" + (n === perPage ? " on" : "")} onClick={() => { setOpen(false); onPerPage(n); }}>{n}</button>
              ))}</div>
            </PopoverContent>
          </Popover>
          {t("per page")}
        </span>
      )}
      <span className="la-pages">
        <button type="button" className="la-pg plain" aria-label={t("Previous page")} disabled={page <= 1} onClick={() => onPage(page - 1)}>{LIcon.prev}</button>
        {nums.map((n, i) => (
          <span key={n} style={{ display: "contents" }}>
            {i > 0 && n - nums[i - 1] > 1 && <span className="la-gap" aria-hidden="true">…</span>}
            <button type="button" className={"la-pg" + (n === page ? " on" : "")} aria-current={n === page ? "page" : undefined} onClick={() => n !== page && onPage(n)}>{n}</button>
          </span>
        ))}
        <button type="button" className="la-pg plain" aria-label={t("Next page")} disabled={page >= pages} onClick={() => onPage(page + 1)}>{LIcon.next}</button>
      </span>
    </div>
  );
}
