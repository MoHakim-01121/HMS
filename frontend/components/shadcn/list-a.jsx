import { Children, forwardRef, useEffect, useRef, useState } from "react";
import { Link, router } from "@inertiajs/react";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { cn } from "@/lib/utils";

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

const FOCUS = "focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-ring";

// The page frame of a list page or the dashboard: fills what the sidebar
// leaves, up to 1280px of content, so collapsing the sidebar widens it. The
// topbar follows the same column (shell.css keys off data-slot="list-main").
export function PageFrame({ className, children }) {
  return <div className={cn("page shadcn-root max-w-[1320px]", className)}>{children}</div>;
}

export function PageMain({ loading, className, children }) {
  return (
    <div data-slot="list-main" className={cn(
      "mx-auto flex max-w-[1280px] flex-col gap-4 text-[14px] leading-normal text-foreground",
      loading && "opacity-55 transition-opacity duration-150 ease-[ease]",
      className,
    )}>{children}</div>
  );
}

export function ListPage({ title, legend, children, loading }) {
  return (
    <PageFrame>
      <PageMain loading={loading}>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h1 className="m-0 text-[24px] leading-[1.15] font-semibold tracking-[-0.02em]">{title}</h1>
          {legend}
        </div>
        {children}
      </PageMain>
    </PageFrame>
  );
}

export function Legend({ current, previous, note }) {
  const mark = "mr-1 inline-block h-0.5 w-3 rounded-[1px] align-middle";
  return (
    <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-muted-foreground">
      <span><i className={cn(mark, "bg-foreground")} />{current}</span>
      <span><i className={cn(mark, "bg-muted-foreground opacity-45")} />{previous}</span>
      {note && <span>{note}</span>}
    </span>
  );
}

// Muted supporting text in a toolbar or under a table.
export const Note = ({ className, children }) => (
  <span data-slot="note" className={cn("text-[13px] text-muted-foreground tabular-nums", className)}>{children}</span>
);

// `dense`: five cards or long rupiah figures, values one step smaller.
export const Kpis = ({ children, dense }) => (
  <div data-dense={dense ? "" : undefined} className="group/kpis flex gap-3 max-[900px]:flex-wrap">{children}</div>
);

// The card a KPI sits in. Pressable when it is a button or link.
export const kpiFrame = (pressable, on) => cn(
  "surface box-border flex min-w-0 flex-[1_1_0] flex-col rounded-[20px] border border-border bg-card p-4 text-left text-inherit no-underline [font:inherit]",
  "[transition:border-color_.15s_ease,box-shadow_.15s_ease,transform_.1s_ease] max-[900px]:flex-[1_1_calc(50%-6px)] max-[600px]:flex-[1_1_100%]",
  FOCUS,
  pressable && "cursor-pointer hover:border-input active:[transform:scale(.995)]",
  on && "border-foreground shadow-[inset_0_0_0_1px_var(--foreground)]",
);

export const KpiHead = ({ label, children }) => (
  <span className="flex items-center justify-between gap-2">
    <span className="text-[13px] font-medium text-muted-foreground">{label}</span>
    {children}
  </span>
);

export const KpiRow = ({ children }) => <span className="mt-2 flex items-center justify-between gap-3">{children}</span>;

const TONE = { warn: "text-warning-text", good: "text-success-text", loss: "text-danger-text" };

// The figure. A KPI with nothing to show yet (`tone="none"`) says so in words.
export function KpiValue({ tone, unit, children }) {
  const cls = tone === "none"
    ? "text-[13px] leading-[34px] font-medium tracking-normal text-muted-foreground"
    : cn("text-[28px] leading-[1.1] font-semibold tracking-[-0.02em] tabular-nums max-[600px]:text-[24px] group-data-[dense]/kpis:text-[20px]", TONE[tone]);
  return (
    <span className={cls}>
      {children}
      {unit && <small className="ml-1 text-[13px] font-semibold tracking-normal whitespace-nowrap text-muted-foreground">{unit}</small>}
    </span>
  );
}

export const KpiFoot = ({ children }) => <span className="mt-3 block text-[12px] text-muted-foreground tabular-nums">{children}</span>;

// One KPI. Pressable when `onClick`/`href` (it then filters the table), `on`
// while its filter is the one applied.
export function Kpi({ label, value, unit, delta, foot, tone, onClick, href, on, spark, title }) {
  const body = (
    <>
      <KpiHead label={label}>{delta && <Delta {...delta} />}</KpiHead>
      <KpiRow><KpiValue tone={tone} unit={unit}>{value}</KpiValue>{spark}</KpiRow>
      {foot && <KpiFoot>{foot}</KpiFoot>}
    </>
  );
  if (href) return <Link data-slot="kpi" className={kpiFrame(true, on)} href={href} title={title}>{body}</Link>;
  if (onClick) return <button data-slot="kpi" type="button" className={kpiFrame(true, on)} aria-pressed={!!on} onClick={onClick} title={title}>{body}</button>;
  return <div data-slot="kpi" className={kpiFrame(false, on)} title={title}>{body}</div>;
}

// A KPI that turns over to show its figure by currency: rows = [{ code, amount, sar }].
export function FlipKpi({ label, ariaLabel, delta, flipped, onToggle, front, rows }) {
  const face = "col-start-1 row-start-1 flex flex-col transition-[opacity,translate] duration-[220ms] ease-[cubic-bezier(.2,.7,.2,1)]";
  return (
    <button data-slot="kpi" type="button" className={cn(kpiFrame(true), "group/flip")} aria-expanded={flipped} aria-label={ariaLabel} onClick={onToggle}>
      <KpiHead label={label}>
        <span className="inline-flex items-center gap-2">
          {!flipped && delta}
          <span className={cn("-mr-1 grid size-[22px] place-content-center rounded-full text-muted-foreground transition-[rotate,background-color] duration-[220ms,150ms] ease-[cubic-bezier(.2,.7,.2,1),ease] group-hover/flip:bg-secondary group-hover/flip:text-foreground", flipped && "rotate-180")}>{LIcon.chev}</span>
        </span>
      </KpiHead>
      <span className="grid">
        <span className={cn(face, flipped && "-translate-y-1.5 opacity-0")} aria-hidden={flipped}>{front}</span>
        <span className={cn(face, !flipped && "pointer-events-none translate-y-1.5 opacity-0")} aria-hidden={!flipped}>
          <span className="mt-2 grid grid-cols-[28px_1fr_auto] items-baseline gap-x-2 gap-y-1 text-[13px] tabular-nums">
            {rows.map((c) => (
              <span key={c.code} className="contents">
                <span className="text-[12px] font-semibold tracking-[.02em] text-muted-foreground">{c.code}</span>
                <span className="text-right font-semibold">{fmtN(c.amount)}</span>
                <span className="text-right text-[12px] text-muted-foreground">{fmtN(c.sar)} SAR</span>
              </span>
            ))}
          </span>
        </span>
      </span>
    </button>
  );
}

export function Delta({ text, good, title }) {
  if (!text) return null;
  const up = !String(text).startsWith("-");
  // The arrow carries the direction, so the sign is not repeated.
  return (
    <span title={title} className={cn(
      "inline-flex h-5 items-center gap-1 rounded-full px-2 text-[12px] font-semibold whitespace-nowrap tabular-nums [&_svg]:size-[11px] [&_svg]:fill-none [&_svg]:stroke-current [&_svg]:stroke-[2.6]",
      good ? "bg-success-tint text-success-text" : "bg-warning-tint text-warning-text",
    )}>{up ? LIcon.up : LIcon.down}{String(text).replace(/^[-+−]/, "")}</span>
  );
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
      {prev.length > 1 && <polyline points={pts(prev)} fill="none" className="stroke-muted-foreground opacity-45" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />}
      {cur.length > 1 && <polyline points={pts(cur)} fill="none" className="stroke-foreground" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />}
      {last && <circle cx={last[0]} cy={last[1]} r="4" fill="var(--foreground)" stroke="var(--card)" strokeWidth="2" />}
    </svg>
  );
}

export function Toolbar({ left, children, spaced }) {
  return (
    <div className={cn("flex flex-wrap items-center justify-between gap-3", spaced && "mt-9")}>
      <div className="flex flex-wrap items-center gap-1">{left}</div>
      {Children.toArray(children).length > 0 && <ToolbarRight>{children}</ToolbarRight>}
    </div>
  );
}

export const ToolbarRight = ({ children }) => <div className="flex flex-wrap items-center gap-2 max-[900px]:w-full">{children}</div>;

// The month label of a month navigator.
export const MonthLabel = ({ children }) => <span data-slot="month" className="mr-2 min-w-[76px] text-[14px] font-semibold">{children}</span>;

// ‹ › beside the month.
export const NavButton = (props) => (
  <button type="button" {...props} className={cn(
    "grid size-[30px] cursor-pointer place-content-center rounded-full border-0 bg-transparent text-foreground transition-colors duration-150 ease-[ease] hover:bg-card disabled:cursor-default disabled:opacity-35 max-[600px]:size-11",
    FOCUS, props.className,
  )} />
);

// "2026 ▾": a bare button that opens a menu.
export const MenuButton = forwardRef(({ className, ...props }, ref) => (
  <button ref={ref} type="button" {...props} className={cn(
    "ml-2 inline-flex h-[30px] cursor-pointer items-center gap-1 rounded-[8px] border-0 bg-transparent px-2 font-sans text-[14px] leading-[normal] font-semibold text-foreground tabular-nums transition-colors duration-150 ease-[ease] hover:bg-card aria-expanded:bg-card max-[600px]:h-11",
    FOCUS, className,
  )} />
));
MenuButton.displayName = "MenuButton";

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
      {prefix && <span className="mr-2 text-[14px] font-medium text-muted-foreground">{prefix}</span>}
      <MonthLabel>{label}</MonthLabel>
      <NavButton aria-label={t("Previous month")} disabled={m == null} onClick={() => shift(-1)}>{LIcon.prev}</NavButton>
      <NavButton aria-label={t("Next month")} disabled={m == null} onClick={() => shift(1)}>{LIcon.next}</NavButton>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <MenuButton aria-haspopup="menu">{y || t("All")}{LIcon.chev}</MenuButton>
        </PopoverTrigger>
        <Menu align="start" sideOffset={6} className="w-40">
          {years.map((yy) => (
            <MenuItem key={yy} on={yy === y}
              onClick={() => { setOpen(false); onChange({ month: `${yy}-${String((m ?? new Date().getMonth()) + 1).padStart(2, "0")}`, year: "" }); }}>{yy}</MenuItem>
          ))}
          {y && <MenuItem on={m == null} onClick={() => { setOpen(false); onChange({ month: "", year: String(y) }); }}>{t("Whole {year}", { year: y })}</MenuItem>}
          <MenuSep />
          <MenuItem on={!y} onClick={() => { setOpen(false); onChange({ month: "", year: "all" }); }}>{t("All dates")}</MenuItem>
        </Menu>
      </Popover>
    </>
  );
}

// The toolbar's pill button (Filter, Export, a picker, a link). `as` renders
// it as another element: "a", "label", Link.
export const toolClass = cn(
  "surface box-border inline-flex h-9 cursor-pointer items-center gap-2 rounded-full border border-input bg-card px-4 font-sans text-[13px] leading-[normal] font-medium whitespace-nowrap text-foreground no-underline",
  "transition-[border-color,background-color] duration-150 ease-[ease] hover:border-[color:color-mix(in_oklch,var(--foreground)_45%,var(--input))] aria-expanded:border-[color:color-mix(in_oklch,var(--foreground)_45%,var(--input))] [&_svg]:flex-none [&_svg]:text-muted-foreground",
  FOCUS,
);
export const ToolButton = forwardRef(({ as: As = "button", className, ...props }, ref) => (
  <As ref={ref} {...(As === "button" ? { type: "button" } : {})} {...props} className={cn(toolClass, className)} />
));
ToolButton.displayName = "ToolButton";

// A bare input inside a ToolButton-shaped control (search, "As of" date).
export const toolInput = "h-full min-w-0 rounded-none border-0 bg-transparent p-0 font-sans text-[13px] leading-[normal] font-medium text-foreground shadow-none outline-none placeholder:font-normal placeholder:text-muted-foreground";

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
    <label data-slot="search" className={cn(toolClass, "w-[260px] cursor-text focus-within:border-foreground max-[900px]:w-full max-[900px]:flex-[1_1_100%]")}>
      {LIcon.search}
      <input className={cn(toolInput, "flex-1")} value={q} onChange={(e) => change(e.target.value)} placeholder={placeholder} aria-label={placeholder}
        onKeyDown={(e) => { if (e.key === "Enter") { clearTimeout(timer.current); onSearch(q.trim()); } }} />
    </label>
  );
}

// A menu panel (portalled popover) and its rows.
export function Menu({ className, children, role = "menu", ...props }) {
  return (
    <PopoverContent {...props} className={cn("surface w-auto min-w-40 rounded-[12px] border-border bg-popover p-1 text-left font-sans shadow-menu", className)}>
      {role ? <div role={role}>{children}</div> : children}
    </PopoverContent>
  );
}

export const MenuItem = ({ as: As = "button", on, danger, className, ...props }) => (
  <As role="menuitem" {...(As === "button" ? { type: "button" } : {})} {...props} className={cn(
    "box-border flex w-full cursor-pointer items-center gap-2 rounded-[8px] border-0 bg-transparent px-3 py-2 text-left font-sans text-[13px] leading-[normal] font-medium whitespace-nowrap text-foreground no-underline transition-colors duration-[120ms] ease-[ease] hover:bg-secondary [&_svg]:flex-none [&_svg]:text-muted-foreground",
    FOCUS,
    on && "font-semibold",
    danger && "text-danger-text [&_svg]:text-danger-text",
    className,
  )} />
);

// A second line under a menu row's label.
export const MenuHint = ({ children }) => <span className="block text-[12px] font-normal whitespace-normal text-muted-foreground">{children}</span>;

export const MenuSep = () => <div className="my-1 h-px bg-hairline" />;

// The Filter button and its panel. Children edit a draft; Apply commits it.
export function FilterMenu({ count = 0, onApply, onReset, onOpen, children }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (o && onOpen) onOpen(); }}>
      <PopoverTrigger asChild>
        <ToolButton aria-haspopup="dialog">
          {t("Filter")}{LIcon.filter}{count > 0 && <span className="box-border grid h-5 min-w-5 place-content-center rounded-full bg-primary px-1 text-[12px] font-semibold text-primary-foreground">{count}</span>}
        </ToolButton>
      </PopoverTrigger>
      <Menu role={null} align="end" sideOffset={8} className="max-h-(--radix-popover-content-available-height) w-[300px] overflow-y-auto p-4" aria-label={t("Filter")}>
        {children}
        <div className="mt-4 flex justify-between gap-2 border-t border-border pt-4">
          <ToolButton className="border-transparent bg-transparent px-2 hover:border-transparent" onClick={() => { onReset(); }}>{t("Reset")}</ToolButton>
          <button type="button" className="h-9 cursor-pointer rounded-full border-0 bg-primary px-4 font-sans text-[13px] leading-[normal] font-semibold text-primary-foreground hover:bg-primary-hover" onClick={() => { setOpen(false); onApply(); }}>{t("Apply")}</button>
        </div>
      </Menu>
    </Popover>
  );
}

export const FilterSection = ({ label, children, hint }) => (
  <div data-slot="filter-section" className="[[data-slot=filter-section]+&]:mt-4 [[data-slot=filter-section]+&]:border-t [[data-slot=filter-section]+&]:border-hairline [[data-slot=filter-section]+&]:pt-4">
    {label && <div className="mb-2 text-[12px] font-semibold text-muted-foreground">{label}</div>}
    {children}
    {hint && <div className="mt-1.5 text-[12px] text-muted-foreground">{hint}</div>}
  </div>
);

export function Check({ on, onClick, label, count, radio }) {
  return (
    <button type="button" role={radio ? "radio" : "checkbox"} aria-checked={!!on} onClick={onClick} className={cn(
      "box-border flex w-full cursor-pointer items-center gap-2 rounded-[8px] border-0 bg-transparent p-2 text-left font-sans text-[13px] leading-[normal] font-normal text-foreground hover:bg-secondary",
      FOCUS,
    )}>
      {radio
        ? <span className={cn("box-border size-4 flex-none rounded-full border-[1.5px] border-field transition-[border-width,border-color] duration-[120ms] ease-[ease]", on && "border-[5px] border-primary")} />
        : <span className={cn("box-border grid size-4 flex-none place-content-center rounded-[4px] border-[1.5px] border-field text-primary-foreground transition-[background-color,border-color] duration-[120ms] ease-[ease] [&_svg]:invisible", on && "border-primary bg-primary [&_svg]:visible")}>{LIcon.check}</span>}
      {label}
      {count != null && <span className="ml-auto text-muted-foreground tabular-nums">{count}</span>}
    </button>
  );
}

export function DateRange({ from, to, onFrom, onTo }) {
  const { t } = useI18n();
  const field = "flex min-w-0 flex-1 flex-col gap-1 text-[12px] text-muted-foreground";
  const input = "box-border h-9 w-full rounded-[10px] border border-input bg-card px-3 font-sans text-[13px] leading-[normal] font-medium text-foreground";
  return (
    <div className="flex gap-2">
      <label className={field}>{t("From")}<input className={input} type="date" value={from || ""} onChange={(e) => onFrom(e.target.value)} /></label>
      <label className={field}>{t("To")}<input className={input} type="date" value={to || ""} onChange={(e) => onTo(e.target.value)} /></label>
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
        <ToolButton aria-haspopup="menu">{t("Export")}{LIcon.export}</ToolButton>
      </PopoverTrigger>
      <Menu align="end" sideOffset={8} className="w-[280px]">
        {items.map((it) => (
          <MenuItem as="a" key={it.label} href={it.href} target={it.external ? "_blank" : undefined} rel="noreferrer" onClick={() => setOpen(false)}>
            <span>{it.label}{it.hint && <MenuHint>{it.hint}</MenuHint>}</span>
          </MenuItem>
        ))}
      </Menu>
    </Popover>
  );
}

// A toolbar button that opens a one-pick menu (branch, season):
// options = [{ value, label, hint }]; `label` shows when nothing is picked.
export function PickMenu({ value, options, onPick, label, width = 220 }) {
  const [open, setOpen] = useState(false);
  const cur = options.find((o) => o.value === value);
  if (!options.length) return null;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <ToolButton aria-haspopup="menu">{cur ? cur.label : label}{LIcon.chev}</ToolButton>
      </PopoverTrigger>
      <Menu align="end" sideOffset={8} style={{ width }}>
        {options.map((o) => (
          <MenuItem key={o.value} on={o.value === value} onClick={() => { setOpen(false); onPick(o.value); }}>
            <span>{o.label}{o.hint && <MenuHint>{o.hint}</MenuHint>}</span>
          </MenuItem>
        ))}
      </Menu>
    </Popover>
  );
}

// A heading between the cards of a page with more than one table.
export function Section({ title, sub, children }) {
  return (
    <div className="mt-4 flex items-end justify-between gap-3">
      <div><h2 className="m-0 text-[16px] font-semibold">{title}</h2>{sub && <span className="mt-1 block text-[13px] text-muted-foreground">{sub}</span>}</div>
      {children}
    </div>
  );
}

// "2026-10-21" -> "21 Oct 2026"
export const dLong = (iso) => (iso ? `${dShort(iso)} ${iso.slice(0, 4)}` : "");

export const primaryClass = cn(
  "inline-flex h-9 cursor-pointer items-center gap-2 rounded-full border-0 bg-primary px-4 font-sans text-[13px] leading-[normal] font-semibold whitespace-nowrap text-primary-foreground no-underline [transition:background-color_.15s_ease,transform_.1s_ease] hover:bg-primary-hover active:[transform:scale(.97)]",
  FOCUS,
);
export function Primary({ label, onClick, onPrefetch, href }) {
  if (href) return <Link className={primaryClass} href={href}>{LIcon.plus}{label}</Link>;
  return <button type="button" className={primaryClass} onClick={onClick} onPointerEnter={onPrefetch} onFocus={onPrefetch}>{LIcon.plus}{label}</button>;
}

// The row's ⋯ menu: [{ label, onClick | href, danger, external }]; falsy items drop.
export function RowMenu({ items, label }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const list = items.filter(Boolean);
  if (!list.length) return null;
  return (
    <span className="inline-block" onClick={(e) => e.stopPropagation()}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button type="button" aria-label={label || t("Actions")} aria-haspopup="menu" className={cn(
            "grid size-8 cursor-pointer place-content-center rounded-full border-0 bg-transparent text-muted-foreground transition-colors duration-[120ms] ease-[ease] hover:bg-secondary hover:text-foreground aria-expanded:bg-secondary aria-expanded:text-foreground max-[600px]:size-11",
            FOCUS,
          )}>{LIcon.dots}</button>
        </PopoverTrigger>
        <Menu align="end" sideOffset={4} className="w-[200px]">
          {list.map((it) => it.href ? (
            <MenuItem as="a" key={it.label} danger={it.danger} href={it.href}
              target={it.external ? "_blank" : undefined} rel="noreferrer" onClick={() => setOpen(false)}>{it.label}</MenuItem>
          ) : (
            <MenuItem key={it.label} danger={it.danger} onClick={(e) => { setOpen(false); it.onClick(e); }}>{it.label}</MenuItem>
          ))}
        </Menu>
      </Popover>
    </span>
  );
}

const PILL = {
  green: "bg-success-tint text-success-text",
  amber: "bg-warning-tint text-warning-text",
  "amber-o": "border border-warning text-warning-text",
  red: "bg-danger-tint text-danger-text",
  gray: "bg-secondary text-[color:color-mix(in_oklch,var(--muted-foreground)_70%,var(--foreground))]",
  outline: "border border-input text-foreground",
  "info-o": "border border-info text-info-text",
  dark: "bg-primary text-primary-foreground",
};
export const Pill = ({ tone = "gray", sm, className, children }) => (
  <span className={cn("box-border inline-flex h-6 items-center rounded-full px-3 text-[12px] font-semibold whitespace-nowrap", PILL[tone], sm && "h-[22px] px-2", className)}>{children}</span>
);

export function Amt({ code, value }) {
  return (
    <span className="flex items-baseline justify-between gap-2">
      <span className="text-[12px] font-semibold tracking-[.02em] text-muted-foreground">{code}</span>
      <b className="font-semibold">{fmtN(value)}</b>
    </span>
  );
}

// Props for a row that opens `href`: a plain click visits it, Ctrl/⌘-click and
// middle-click open it in a new tab the way a link would. Spread onto the <Tr>.
export const rowNav = (href) => ({
  onClick: (e) => (e.metaKey || e.ctrlKey ? window.open(href, "_blank") : router.visit(href)),
  onAuxClick: (e) => { if (e.button === 1) window.open(href, "_blank"); },
});

// Table cells and rows of a TableCard. Page classes merge over the base, so a
// cell is right-aligned with `className="text-right"`. Edge cells get the
// card's 20px inset; the action column at the end is tight.
const EDGE = "first:pl-5 last:px-2";
export const Th = ({ className, ...props }) => (
  <th {...props} className={cn("border-b border-border bg-card px-4 py-3 text-left text-[12px] font-semibold tracking-normal whitespace-nowrap normal-case text-foreground", EDGE, className)} />
);
export const Td = ({ label, className, ...props }) => (
  <td {...props} className={cn(
    "border-b border-hairline px-4 py-3 align-middle whitespace-nowrap text-foreground tabular-nums", EDGE,
    // In the totals row: no rule under, a firmer one over, bold figures.
    "in-[tfoot]:cursor-default in-[tfoot]:border-t in-[tfoot]:border-b-0 in-[tfoot]:border-t-input in-[tfoot]:bg-card in-[tfoot]:py-3 in-[tfoot]:font-semibold",
    label && "in-[tfoot]:font-normal text-muted-foreground",
    className,
  )} />
);
// A sortable header's label and arrow.
export const SortLabel = ({ children }) => <span className="inline-flex items-center gap-1 font-semibold text-foreground">{children}</span>;

// `row`: "static" (not openable), "band" (a group heading), "on" (selected),
// "dim" (greyed out). Body rows open on click; Tab reaches them.
export const Tr = ({ row, className, ...props }) => (
  <tr data-row={row} {...props} className={cn(
    "[tbody>&]:cursor-pointer [tbody>&]:transition-colors [tbody>&]:duration-[120ms] [tbody>&]:ease-[ease]",
    "[tbody>&:hover>td]:bg-[color:color-mix(in_oklch,var(--foreground)_3%,var(--card))]",
    "[tbody>&:focus-visible]:outline-2 [tbody>&:focus-visible]:-outline-offset-2 [tbody>&:focus-visible]:outline-ring [tbody>&:focus-visible]:outline-solid",
    "[tbody>&:last-child>td]:border-b-0",
    row === "static" && "[tbody>&]:cursor-default [tbody>&:hover>td]:bg-transparent",
    row === "band" && "[tbody>&]:cursor-default [&>td]:bg-[color:oklch(0.975_0.007_75)] [&>td]:py-2 [&>td]:font-semibold [tbody>&:hover>td]:bg-[color:oklch(0.975_0.007_75)] [[data-theme=dark]_&>td]:bg-[color:oklch(0.215_0.007_75)] [[data-theme=dark]_tbody>&:hover>td]:bg-[color:oklch(0.215_0.007_75)]",
    row === "on" && "[tbody>&>td]:bg-[color:color-mix(in_oklch,var(--foreground)_5%,var(--card))] [tbody>&:hover>td]:bg-[color:color-mix(in_oklch,var(--foreground)_5%,var(--card))]",
    row === "dim" && "[&>td]:text-muted-foreground",
    className,
  )} />
);

// The table card. `cols` = widths (px or null); children = <thead>/<tbody>/<tfoot>
// built from Tr/Th/Td. Rows open on click; Tab reaches each one and Enter or
// Space opens it too (static and band rows are not openable and stay out of
// the tab order).
export function TableCard({ cols, children, empty }) {
  const ref = useRef(null);
  useEffect(() => {
    ref.current?.querySelectorAll("tbody tr").forEach((tr) => {
      if (tr.matches('[data-row="static"], [data-row="band"]')) tr.removeAttribute("tabindex");
      else tr.tabIndex = 0;
    });
  });
  const onKey = (e) => {
    const tr = e.target;
    if ((e.key === "Enter" || e.key === " ") && tr.tagName === "TR" && tr.parentElement?.tagName === "TBODY") {
      e.preventDefault();
      tr.click();
    }
  };
  return (
    <section className="surface overflow-hidden rounded-[20px] border border-border bg-card">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] table-fixed border-collapse text-[13px]" ref={ref} onKeyDown={onKey}>
          {cols && <colgroup>{cols.map((w, i) => <col key={i} style={w ? { width: w } : undefined} />)}</colgroup>}
          {children}
        </table>
      </div>
      {empty}
    </section>
  );
}

export function Empty({ title, sub, lead, className }) {
  return (
    <div data-slot="empty" className={cn("px-6 py-12 text-center text-[13px] text-muted-foreground", className)}>
      {lead}
      <b className="mb-1 block text-[14px] text-foreground">{title}</b>{sub}
    </div>
  );
}

// "Show 10 per page" and the page buttons. `p` is pagination_props from the server.
export function Pager({ p, perPage, onPage, onPerPage, summary }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  if (!p) return null;
  const page = p.number || p.page || 1;
  const pages = p.num_pages || p.pages || 1;
  const nums = [1, page - 1, page, page + 1, pages].filter((n, i, a) => n >= 1 && n <= pages && a.indexOf(n) === i).sort((a, b) => a - b);
  const pg = cn(
    "surface box-border grid size-8 cursor-pointer place-content-center rounded-full border border-border bg-card font-sans text-[13px] leading-[normal] font-medium text-foreground tabular-nums transition-[background-color,border-color] duration-[120ms] ease-[ease] hover:border-input disabled:cursor-default disabled:opacity-35 max-[600px]:size-11",
    FOCUS,
  );
  const plain = "border-transparent bg-transparent hover:border-transparent";
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 text-[13px] text-muted-foreground tabular-nums">
      {summary ? <span>{summary}</span> : (
        <span className="flex items-center gap-2">{t("Show")}
          <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild><ToolButton className="h-8 gap-1 px-3" aria-haspopup="menu">{perPage}{LIcon.chev}</ToolButton></PopoverTrigger>
            <Menu side="top" align="start" sideOffset={6} className="w-[90px] min-w-0">
              {[10, 25, 50].map((n) => (
                <MenuItem key={n} on={n === perPage} onClick={() => { setOpen(false); onPerPage(n); }}>{n}</MenuItem>
              ))}
            </Menu>
          </Popover>
          {t("per page")}
        </span>
      )}
      <span className="flex items-center gap-2">
        <button type="button" className={cn(pg, plain)} aria-label={t("Previous page")} disabled={page <= 1} onClick={() => onPage(page - 1)}>{LIcon.prev}</button>
        {nums.map((n, i) => (
          <span key={n} className="contents">
            {i > 0 && n - nums[i - 1] > 1 && <span className="w-6 text-center" aria-hidden="true">…</span>}
            <button type="button" className={cn(pg, n === page && "border-primary bg-primary font-semibold text-primary-foreground hover:border-primary")} aria-current={n === page ? "page" : undefined} onClick={() => n !== page && onPage(n)}>{n}</button>
          </span>
        ))}
        <button type="button" className={cn(pg, plain)} aria-label={t("Next page")} disabled={page >= pages} onClick={() => onPage(page + 1)}>{LIcon.next}</button>
      </span>
    </div>
  );
}
