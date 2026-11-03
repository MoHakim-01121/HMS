import { Children, createContext, forwardRef, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, router } from "@inertiajs/react";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover.jsx";
import { Drawer, DrawerContent, DrawerTitle } from "./ui/drawer.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { cn } from "@/lib/utils";
import Page from "./page.jsx";

// Building blocks of the approved list pages (Record View HMS canvas, row
// "Halaman list"). Pages compose these; the server owns filtering and paging.

const S = (props) => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props} />;
export const LIcon = {
  search: <S><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></S>,
  filter: <S><path d="M4 5h16l-6 7.5V19l-4 1.5v-8z" /></S>,
  sliders: <S><path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2" /><circle cx="10" cy="17" r="2" /></S>,
  export: <S><path d="M12 4v11m0 0l-4-4m4 4l4-4M5 20h14" /></S>,
  plus: <S strokeWidth="2.2"><path d="M12 5v14M5 12h14" /></S>,
  prev: <S width="16" height="16" strokeWidth="2"><path d="M15 18l-6-6 6-6" /></S>,
  next: <S width="16" height="16" strokeWidth="2"><path d="M9 6l6 6-6 6" /></S>,
  chev: <S strokeWidth="2"><path d="M6 9l6 6 6-6" /></S>,
  sortDown: <S width="13" height="13" strokeWidth="2"><path d="M12 5v14m0 0l-5-5m5 5l5-5" /></S>,
  sortUp: <S width="13" height="13" strokeWidth="2"><path d="M12 19V5m0 0l-5 5m5-5l5 5" /></S>,
  x: <S width="12" height="12" strokeWidth="2.2"><path d="M6 6l12 12M18 6L6 18" /></S>,
  spin: <S className="animate-spin" strokeWidth="2"><path d="M12 3a9 9 0 1 0 9 9" /></S>,
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

// Phones (600px and below, or a phone turned sideways: the `phone` variant in
// tailwind.css) rearrange a few parts rather than restyle them: the filter
// becomes a bottom sheet, the table a list of rows.
const PHONE = "(max-width: 600px), (max-height: 500px) and (pointer: coarse)";
export function usePhone() {
  const [on, setOn] = useState(() => typeof window !== "undefined" && window.matchMedia(PHONE).matches);
  useEffect(() => {
    const mq = window.matchMedia(PHONE);
    const fn = (e) => setOn(e.matches);
    mq.addEventListener("change", fn);
    setOn(mq.matches);
    return () => mq.removeEventListener("change", fn);
  }, []);
  return on;
}

// What a toolbar's tools leave to the filter sheet on a phone: Export and the
// one-pick menus (salesperson, season) move into it. Kept in a ref, read when
// the sheet opens, so the tools re-render without re-rendering the toolbar.
const ToolCtx = createContext(null);
function useSheetEntry(key, entry) {
  const ctx = useContext(ToolCtx);
  useLayoutEffect(() => { if (ctx) ctx.entries.current[key] = entry; });
  useEffect(() => () => { if (ctx) delete ctx.entries.current[key]; }, [ctx, key]);
  return ctx;
}

// The page frame of a list page or the dashboard: fills what the sidebar
// leaves, up to 1280px of content, so collapsing the sidebar widens it. The
// topbar follows the same column (it keys off data-slot="list-main").
export function PageFrame({ className, children }) {
  return <Page className={cn("max-w-[1320px]", className)}>{children}</Page>;
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
          <h1 className="m-0 text-[24px] leading-[1.15] font-semibold tracking-[-0.02em] phone:text-[26px] phone:leading-[1.2]">{title}</h1>
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
// On a phone the cards swipe sideways instead of stacking.
export const Kpis = ({ children, dense }) => (
  <div data-dense={dense ? "" : undefined} className={cn(
    "group/kpis flex gap-3 max-[900px]:flex-wrap",
    "phone:-mx-4 phone:snap-x phone:snap-mandatory phone:flex-nowrap phone:gap-2.5 phone:overflow-x-auto phone:px-4 phone:[scrollbar-width:none] phone:[&::-webkit-scrollbar]:hidden",
  )}>{children}</div>
);

// The card a KPI sits in (pick B of the "HMS KPI Cards" canvas). Pressable
// when it is a button or link.
export const kpiFrame = (pressable, on) => cn(
  "box-border flex min-w-0 flex-[1_1_0] flex-col rounded-card border border-border bg-card px-[18px] pt-4 pb-3 text-left text-inherit no-underline [font:inherit]",
  "transition-[border-color,box-shadow,scale] duration-150 ease-out-quint max-[900px]:flex-[1_1_calc(50%-6px)] phone:flex-[0_0_80%] phone:snap-start",
  FOCUS,
  pressable && "cursor-pointer hover:border-input active:scale-[.995]",
  on && "border-foreground ring-1 ring-inset ring-foreground",
);

// Label on the left, the card's one badge (a delta or a status) on the right.
// When the title and its badge do not fit on one line the badge wraps under
// the title, so the title is never cut to "L…".
export const KpiHead = ({ label, children }) => (
  <span className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
    <span className="max-w-full truncate text-[13px] text-muted-foreground">{label}</span>
    {children}
  </span>
);

export const KpiRow = ({ children }) => <span className="mt-2 flex items-center justify-between gap-3">{children}</span>;

const BADGE = {
  good: "bg-success-tint text-success-text",
  bad: "bg-danger-tint text-danger-text",
  warn: "bg-warning-tint text-warning-text",
  neutral: "bg-secondary text-muted-foreground",
};

export const KpiBadge = ({ tone = "neutral", title, children }) => (
  <span title={title} className={cn("inline-flex h-5 flex-none items-center rounded-[6px] px-1.5 text-[12px] font-medium whitespace-nowrap tabular-nums", BADGE[tone])}>{children}</span>
);

// The figure, always in ink: the badge carries the state. A KPI with nothing
// to show yet (`tone="none"`) says so in words.
export function KpiValue({ tone, unit, children }) {
  const cls = tone === "none"
    ? "text-[13px] leading-[29px] font-medium text-muted-foreground"
    : "text-[24px] leading-[1.2] font-semibold tracking-[-0.01em] whitespace-nowrap tabular-nums group-data-[dense]/kpis:text-[20px]";
  return (
    <span className={cls}>
      {children}
      {unit && <small className="ml-1 text-[13px] font-medium tracking-normal whitespace-nowrap text-muted-foreground">{unit}</small>}
    </span>
  );
}

export const KpiFoot = ({ children }) => <span className="mt-1 block text-[12px] text-muted-foreground tabular-nums">{children}</span>;

// The foot of every card: a rule, and what pressing the card does when it
// can be pressed. Cards that cannot keep the rule so a row reads as one.
export const KpiAction = ({ children }) => (
  <span className="mt-auto block w-full self-stretch pt-3.5">
    <span className="box-border flex h-[29px] w-full items-center justify-end gap-0.5 border-t border-border pt-2.5 text-[12px] font-medium text-foreground [&_svg]:size-[13px]">{children}{children && LIcon.next}</span>
  </span>
);

// A status badge for a card that has no delta, from its tone.
const TONE_BADGE = { warn: ["warn", "Needs attention"], loss: ["bad", "Loss"] };

// One KPI. Pressable when `onClick`/`href` (it then filters the table), `on`
// while its filter is the one applied. `status` = { text, tone } names the
// badge when the tone's default words do not fit.
export function Kpi({ label, value, unit, delta, status, foot, tone, onClick, href, on, title }) {
  const { t } = useI18n();
  const fromTone = TONE_BADGE[tone];
  const badge = delta?.text ? <Delta {...delta} />
    : status ? <KpiBadge tone={status.tone}>{status.text}</KpiBadge>
    : fromTone ? <KpiBadge tone={fromTone[0]}>{t(fromTone[1])}</KpiBadge> : null;
  const action = href ? t("View details") : onClick ? (on ? t("Clear filter") : t("Show in table")) : null;
  const body = (
    <>
      <KpiHead label={label}>{badge}</KpiHead>
      <KpiRow><KpiValue tone={tone} unit={unit}>{value}</KpiValue></KpiRow>
      {foot && <KpiFoot>{foot}</KpiFoot>}
      <KpiAction>{action}</KpiAction>
    </>
  );
  if (href) return <Link data-slot="kpi" className={kpiFrame(true, on)} href={href} title={title}>{body}</Link>;
  if (onClick) return <button data-slot="kpi" type="button" className={kpiFrame(true, on)} aria-pressed={!!on} onClick={onClick} title={title}>{body}</button>;
  return <div data-slot="kpi" className={kpiFrame(false, on)} title={title}>{body}</div>;
}

// A KPI that turns over to show its figure by currency: rows = [{ code, amount, sar }].
export function FlipKpi({ label, ariaLabel, delta, flipped, onToggle, front, rows }) {
  const { t } = useI18n();
  const face = "col-start-1 row-start-1 flex flex-col transition-[opacity,translate] duration-[180ms] ease-out-quint";
  return (
    <button data-slot="kpi" type="button" className={kpiFrame(true)} aria-expanded={flipped} aria-label={ariaLabel} onClick={onToggle}>
      <KpiHead label={label}>{!flipped && delta}</KpiHead>
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
      <KpiAction>{flipped ? t("Show total") : t("Show by currency")}</KpiAction>
    </button>
  );
}

// A change against the previous period, signed, coloured by whether it is
// good news (`good`), not by its direction.
export function Delta({ text, good, title }) {
  if (!text) return null;
  const s = String(text);
  return <KpiBadge tone={good ? "good" : "bad"} title={title}>{/^[-−+]/.test(s) ? s.replace(/^-/, "−") : `+${s}`}</KpiBadge>;
}


export function Toolbar({ left, children, spaced }) {
  const entries = useRef({});
  const [hasFilter, setHasFilter] = useState(false);
  const ctx = useMemo(() => ({ entries, hasFilter, setHasFilter }), [hasFilter]);
  return (
    <ToolCtx.Provider value={ctx}>
      <div className={cn("flex flex-wrap items-center justify-between gap-3", spaced && "mt-9 phone:mt-2")}>
        <div className="flex flex-wrap items-center gap-1 phone:w-full">{left}</div>
        {Children.toArray(children).length > 0 && <ToolbarRight>{children}</ToolbarRight>}
      </div>
    </ToolCtx.Provider>
  );
}

// ml-auto keeps it on the right when a wide month nav wraps it onto its own line.
export const ToolbarRight = ({ children }) => <div className="ml-auto flex flex-wrap items-center gap-2 max-[900px]:w-full phone:flex-nowrap">{children}</div>;

// The month label of a month navigator.
export const MonthLabel = ({ className, children }) => (
  <span data-slot="month" className={cn("mr-2 min-w-[76px] text-[14px] font-semibold phone:mr-auto phone:text-[15px]", className)}>{children}</span>
);

// ‹ › beside the month.
export const NavButton = (props) => (
  <button type="button" {...props} className={cn(
    "grid size-[30px] cursor-pointer place-content-center rounded-full border-0 bg-transparent text-foreground transition-colors duration-150 ease-[ease] hover:bg-card disabled:cursor-default disabled:opacity-35 phone:size-11",
    FOCUS, props.className,
  )} />
);

// "2026 ▾": a bare button that opens a menu.
export const MenuButton = forwardRef(({ className, ...props }, ref) => (
  <button ref={ref} type="button" {...props} className={cn(
    "ml-2 inline-flex h-[30px] cursor-pointer items-center gap-1 rounded-[8px] border-0 bg-transparent px-2 font-sans text-[14px] leading-[normal] font-semibold text-foreground tabular-nums transition-colors duration-150 ease-[ease] hover:bg-card aria-expanded:bg-card phone:h-11",
    FOCUS, className,
  )} />
));
MenuButton.displayName = "MenuButton";

// "October  ‹ ›  2026 ▾" — month = "YYYY-MM", or "" with year set (whole
// year), or both empty for all dates.
// With `seasons` (newest first) the picker lists umrah seasons, each read
// whole, in place of calendar years.
export function MonthNav({ month, year, season, years = [], seasons = [], onChange, prefix }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const y = month ? +month.slice(0, 4) : year && year !== "all" ? +year : null;
  const m = month ? +month.slice(5, 7) - 1 : null;
  const bySeason = seasons.length > 0;
  const cur = bySeason && (season ? seasons.find((s) => s.name === season)
    : month ? seasons.find((s) => s.from.slice(0, 7) <= month && month <= s.to.slice(0, 7)) : null);
  const shift = (d) => {
    const dt = new Date(y, m + d, 1);
    onChange({ month: `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}`, year: "", season: "" });
  };
  const label = m != null ? t(MONTHS[m]) : season && cur ? t("Whole season") : y ? t("Whole year") : t("All dates");
  const pick = (patch) => { setOpen(false); onChange({ month: "", year: "", season: "", ...patch }); };
  return (
    <>
      {prefix && <span className="mr-2 text-[14px] font-medium text-muted-foreground">{prefix}</span>}
      <MonthLabel>{label}</MonthLabel>
      <NavButton aria-label={t("Previous month")} disabled={m == null} onClick={() => shift(-1)}>{LIcon.prev}</NavButton>
      <NavButton aria-label={t("Next month")} disabled={m == null} onClick={() => shift(1)}>{LIcon.next}</NavButton>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <MenuButton aria-haspopup="menu">{bySeason ? (cur ? cur.name : y || t("All")) : (y || t("All"))}{LIcon.chev}</MenuButton>
        </PopoverTrigger>
        <Menu align="start" sideOffset={6} className={bySeason ? "w-48" : "w-40"}>
          {bySeason ? seasons.map((s) => (
            <MenuItem key={s.name} on={!!season && s.name === season} onClick={() => pick({ season: s.name })}>{t("Whole {season}", { season: s.name })}</MenuItem>
          )) : (
            <>
              {years.map((yy) => (
                <MenuItem key={yy} on={yy === y}
                  onClick={() => pick({ month: `${yy}-${String((m ?? new Date().getMonth()) + 1).padStart(2, "0")}` })}>{yy}</MenuItem>
              ))}
              {y && <MenuItem on={m == null} onClick={() => pick({ year: String(y) })}>{t("Whole {year}", { year: y })}</MenuItem>}
            </>
          )}
          <MenuSep />
          <MenuItem on={year === "all"} onClick={() => pick({ year: "all" })}>{t("All dates")}</MenuItem>
        </Menu>
      </Popover>
    </>
  );
}

// The toolbar's pill button (Filter, Export, a picker, a link). `as` renders
// it as another element: "a", "label", Link.
export const toolClass = cn(
  "surface box-border inline-flex h-9 cursor-pointer items-center gap-2 phone:h-11 rounded-full border border-input bg-card px-4 font-sans text-[13px] leading-[normal] font-medium normal-nums whitespace-nowrap text-foreground no-underline",
  "transition-[border-color,background-color] duration-150 ease-[ease] hover:border-[color:color-mix(in_oklch,var(--foreground)_45%,var(--input))] aria-expanded:border-[color:color-mix(in_oklch,var(--foreground)_45%,var(--input))] [&_svg]:flex-none [&_svg]:text-muted-foreground",
  FOCUS,
);
export const ToolButton = forwardRef(({ as: As = "button", className, ...props }, ref) => (
  <As ref={ref} {...(As === "button" ? { type: "button" } : {})} {...props} className={cn(toolClass, className)} />
));
ToolButton.displayName = "ToolButton";

// A bare input inside a ToolButton-shaped control (search, "As of" date).
export const toolInput = "h-full w-full min-w-0 rounded-none border-0 bg-transparent p-0 font-sans text-[13px] leading-[normal] font-medium text-foreground shadow-none outline-none placeholder:font-normal placeholder:text-muted-foreground";

// Searches on Enter (not while typing); the icon turns into a spinner until
// the list comes back.
export function SearchTool({ value, onSearch, placeholder }) {
  const { t } = useI18n();
  const [q, setQ] = useState(value || "");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setQ(value || ""); }, [value]);
  const submit = (v) => {
    setBusy(true);
    const off = router.on("finish", () => { setBusy(false); off(); });
    onSearch(v);
  };
  return (
    <label data-slot="search" aria-busy={busy || undefined} className={cn(toolClass, "w-[260px] cursor-text focus-within:border-foreground max-[900px]:w-full max-[900px]:flex-[1_1_100%] phone:h-11 phone:w-auto phone:flex-[1_1_0%] phone:text-[14px]")}>
      {busy ? LIcon.spin : LIcon.search}
      <input className={cn(toolInput, "flex-1")} value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} aria-label={placeholder}
        enterKeyHint="search" onKeyDown={(e) => { if (e.key === "Enter") submit(q.trim()); }} />
      {q && (
        <button type="button" aria-label={t("Clear search")} title={t("Clear search")}
          onClick={() => { setQ(""); if (value) submit(""); }}
          className={cn("-mr-2 grid size-6 flex-none cursor-pointer place-content-center rounded-full border-0 bg-transparent p-0 transition-colors duration-150 ease-[ease] hover:bg-secondary [&_svg]:hover:text-foreground phone:size-8", FOCUS)}>
          {LIcon.x}
        </button>
      )}
    </label>
  );
}

// Under the toolbar while a search looks past the month nav; the search
// box's clear button brings the month back.
export function SearchScope() {
  const { t } = useI18n();
  return <Note>{t("Search results from all dates; the cards above stay on the month.")}</Note>;
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
// On a phone: a round button beside the search, the panel a bottom sheet that
// also holds the toolbar's one-pick menus and Export.
export function FilterMenu({ count = 0, onApply, onReset, onOpen, children }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const phone = usePhone();
  const ctx = useContext(ToolCtx);
  const setHasFilter = ctx?.setHasFilter;
  useEffect(() => {
    if (!setHasFilter) return undefined;
    setHasFilter(true);
    return () => setHasFilter(false);
  }, [setHasFilter]);
  if (phone) {
    const extra = Object.values(ctx?.entries.current || {});
    const picks = extra.filter((e) => e.kind === "pick");
    const exports = extra.find((e) => e.kind === "export")?.items || [];
    return (
      <>
        <button type="button" aria-label={t("Filter and sort")} aria-haspopup="dialog" onClick={() => { setOpen(true); onOpen?.(); }}
          className={cn(toolClass, "relative size-11 flex-none justify-center p-0 [&_svg]:size-[18px] [&_svg]:text-foreground")}>
          {LIcon.sliders}
          {count > 0 && <span className="absolute -top-0.5 -right-0.5 box-border grid h-[18px] min-w-[18px] place-content-center rounded-full border-2 border-background bg-primary px-1 text-[10.5px] font-bold text-primary-foreground">{count}</span>}
        </button>
        <Drawer open={open} onOpenChange={setOpen} direction="bottom">
          <DrawerContent aria-describedby={undefined} className="rounded-t-[22px] border-0 px-4 pb-[calc(18px+env(safe-area-inset-bottom))]">
            <div className="flex items-center justify-between pt-3">
              <DrawerTitle className="m-0 text-[17px]">{t("Filter and sort")}</DrawerTitle>
              <button type="button" onClick={() => onReset()} className="h-9 cursor-pointer border-0 bg-transparent px-1 font-sans text-[13px] font-medium text-muted-foreground">{t("Reset")}</button>
            </div>
            <div className="-mx-4 min-h-0 overflow-y-auto overscroll-contain px-4 py-3">
              {picks.map((p) => (
                <FilterSection key={p.label} label={p.label}>
                  {p.options.map((o) => (
                    <Check key={o.value} radio on={o.value === p.value} label={o.label} onClick={() => { setOpen(false); p.onPick(o.value); }} />
                  ))}
                </FilterSection>
              ))}
              {picks.length > 0 && <div className="mt-4 border-t border-hairline pt-4" />}
              {children}
            </div>
            <div className="flex gap-2.5 pt-2">
              {exports.length > 0 && (
                <Popover>
                  <PopoverTrigger asChild>
                    <ToolButton className="h-11 px-[18px] text-[14px]" aria-haspopup="menu">{LIcon.export}{t("Export")}</ToolButton>
                  </PopoverTrigger>
                  <Menu side="top" align="start" sideOffset={8} className="w-[260px]">
                    {exports.map((it) => (
                      <MenuItem as="a" key={it.label} href={it.href} target={it.external ? "_blank" : undefined} rel="noreferrer">
                        <span>{it.label}{it.hint && <MenuHint>{it.hint}</MenuHint>}</span>
                      </MenuItem>
                    ))}
                  </Menu>
                </Popover>
              )}
              <button type="button" onClick={() => { setOpen(false); onApply(); }}
                className="h-11 flex-1 cursor-pointer rounded-full border-0 bg-primary px-4 font-sans text-[14px] font-semibold text-primary-foreground">{t("Apply")}</button>
            </div>
          </DrawerContent>
        </Drawer>
      </>
    );
  }
  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (o && onOpen) onOpen(); }}>
      <PopoverTrigger asChild>
        <ToolButton aria-haspopup="dialog">
          {t("Filter")}{LIcon.filter}{count > 0 && <span className="box-border grid h-5 min-w-5 place-content-center rounded-full bg-primary px-1 text-[12px] font-semibold text-primary-foreground">{count}</span>}
        </ToolButton>
      </PopoverTrigger>
      <Menu role={null} align="end" sideOffset={8} className="max-h-(--radix-popover-content-available-height) w-[300px] overflow-y-auto overscroll-contain p-4" aria-label={t("Filter")}>
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
      "box-border flex w-full cursor-pointer items-center gap-2 rounded-[8px] border-0 bg-transparent p-2 text-left font-sans text-[13px] leading-[normal] font-normal text-foreground hover:bg-secondary phone:min-h-11 phone:text-[14px]",
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
  const field = "flex min-w-0 flex-1 flex-col gap-1 text-[12px] font-medium text-muted-foreground";
  const input = "box-border h-9 w-full rounded-[10px] border border-input bg-card px-3 font-sans text-[13px] leading-[normal] font-medium text-foreground";
  return (
    <div className="flex gap-2">
      <label className={field}>{t("From")}<input className={input} type="date" value={from || ""} onChange={(e) => onFrom(e.target.value)} /></label>
      <label className={field}>{t("To")}<input className={input} type="date" value={to || ""} onChange={(e) => onTo(e.target.value)} /></label>
    </div>
  );
}

// Export menu: [{ label, hint, href }]. On a phone it moves into the filter
// sheet when the toolbar has one, else it shrinks to a round icon button.
export function ExportMenu({ items }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const phone = usePhone();
  const ctx = useSheetEntry("export", { kind: "export", items });
  if (!items.length) return null;
  if (phone && ctx?.hasFilter) return null;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        {phone
          ? <ToolButton aria-haspopup="menu" aria-label={t("Export")} className="size-11 flex-none justify-center p-0 [&_svg]:size-[18px] [&_svg]:text-foreground">{LIcon.export}</ToolButton>
          : <ToolButton aria-haspopup="menu">{t("Export")}{LIcon.export}</ToolButton>}
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
  const phone = usePhone();
  const ctx = useSheetEntry(`pick:${label}`, { kind: "pick", label, options, value, onPick });
  const cur = options.find((o) => o.value === value);
  if (!options.length) return null;
  if (phone && ctx?.hasFilter) return null;
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

// Wraps a page's own one-pick menu (the CL salesperson): on a phone with a
// filter sheet the menu leaves the toolbar and its options join the sheet.
export function SheetPick({ label, value, options, onPick, children }) {
  const phone = usePhone();
  const ctx = useSheetEntry(`pick:${label}`, { kind: "pick", label, options, value, onPick });
  return phone && ctx?.hasFilter ? null : children;
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
// On a phone the "new" button floats as a round + above the bottom nav.
const FAB = "phone:fixed phone:right-[max(16px,env(safe-area-inset-right))] phone:bottom-[calc(90px+env(safe-area-inset-bottom))] [@media(max-height:500px)]:bottom-[calc(76px+env(safe-area-inset-bottom))] phone:z-(--z-sticky) phone:size-14 phone:justify-center phone:p-0 phone:shadow-fab phone:[&_svg]:size-6";
export function Primary({ label, onClick, onPrefetch, href }) {
  const text = <span className="phone:sr-only">{label}</span>;
  if (href) return <Link className={cn(primaryClass, FAB)} href={href} aria-label={label}>{LIcon.plus}{text}</Link>;
  return <button type="button" className={cn(primaryClass, FAB)} aria-label={label} onClick={onClick} onPointerEnter={onPrefetch} onFocus={onPrefetch}>{LIcon.plus}{text}</button>;
}

// The row's ⋯ menu: [{ label, onClick | href, danger, external }]; falsy items drop.
export function RowMenu({ items, label }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const list = items.filter(Boolean);
  if (!list.length) return null;
  return (
    // No stopPropagation here: Radix closes an open menu only when the click
    // reaches the document, so stopping it left two menus open. The row
    // ignores clicks from controls and menus itself (Tr).
    <span className="inline-block">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button type="button" aria-label={label || t("Actions")} aria-haspopup="menu" className={cn(
            "grid size-8 cursor-pointer place-content-center rounded-full border-0 bg-transparent text-muted-foreground transition-colors duration-[120ms] ease-[ease] hover:bg-secondary hover:text-foreground aria-expanded:bg-secondary aria-expanded:text-foreground phone:size-11",
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
export const Pill = ({ tone = "gray", sm, className, children, ...rest }) => (
  <span className={cn("box-border inline-flex h-6 items-center rounded-full px-3 text-[12px] font-semibold whitespace-nowrap", PILL[tone], sm && "h-[22px] px-2", className)} {...rest}>{children}</span>
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
    "border-b border-hairline px-4 py-3 align-middle font-medium whitespace-nowrap text-foreground tabular-nums", EDGE,
    // In the totals row: no rule under, a firmer one over, bold figures.
    "in-[tfoot]:cursor-default in-[tfoot]:border-t in-[tfoot]:border-b-0 in-[tfoot]:border-t-input in-[tfoot]:bg-card in-[tfoot]:py-3 in-[tfoot]:text-[14px] in-[tfoot]:font-semibold",
    label && "in-[tfoot]:font-normal text-muted-foreground",
    className,
  )} />
);
// A sortable header's label and arrow.

// `row`: "static" (not openable), "band" (a group heading), "on" (selected),
// "dim" (greyed out). Body rows open on click; Tab reaches them.
// A click on a control in the row, or in a menu or dialog opened from it (a
// portal, but still the row's child in React), is not a click on the row.
const ROW_CONTROL = 'button, a, input, select, textarea, label, [role="menu"], [role="menuitem"], [role="dialog"], [role="alertdialog"]';
// A control that wraps the row itself (a table inside a dialog) does not count.
const fromControl = (e) => {
  const control = e.target instanceof Element ? e.target.closest(ROW_CONTROL) : null;
  return !!control && !control.contains(e.currentTarget);
};

export const Tr = ({ row, className, onClick, onAuxClick, ...props }) => (
  <tr data-row={row} {...props}
    onClick={onClick && ((e) => { if (!fromControl(e)) onClick(e); })}
    onAuxClick={onAuxClick && ((e) => { if (!fromControl(e)) onAuxClick(e); })}
    className={cn(
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
// `phone`: the same rows as PRow lines, shown instead of the table on a phone
// (any value hides the table there, so an empty list leaves just `empty`).
export function TableCard({ cols, children, empty, phone }) {
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
      <div className={cn("overflow-x-auto", phone !== undefined && "phone:hidden")}>
        <table className="w-full min-w-[860px] table-fixed border-collapse text-[13px]" ref={ref} onKeyDown={onKey}>
          {cols && <colgroup>{cols.map((w, i) => <col key={i} style={w ? { width: w } : undefined} />)}</colgroup>}
          {children}
        </table>
      </div>
      {phone && <div className="hidden phone:block">{phone}</div>}
      {empty}
    </section>
  );
}

// One table row on a phone, three lines (canvas "HMS Mobile v2", lists):
// number and status / name and amount / the rest and a note at the end.
// `tag` is a Pill; `end` replaces it with a figure (a balance). Rows with
// `href` open on tap; `onClick` rows act in place. `lead` sits left of the
// lines (a checkbox); `menu` sits at the right end (the desktop row's
// RowMenu); `children` opens under the row (a row's history).
const ROW_LINE = "flex w-full min-w-0 items-center justify-between gap-2.5 [&>:first-child]:min-w-0 [&>:first-child]:truncate [&>:last-child]:flex-none";
export function PRow({ href, onClick, no, mono, tag, end, title, amount, unit, amountTone, meta, note, noteTone, dim, lead, on, menu, children }) {
  const body = (
    <>
      <span className={ROW_LINE}>
        <span className={cn(mono ? "font-mono text-[14px] font-bold tracking-[-0.01em]" : "text-[15px] font-semibold", dim && "line-through decoration-muted-foreground")}>{no}</span>
        {end != null ? <b className={cn("text-[15px] font-semibold tabular-nums", amountTone)}>{end}</b> : tag}
      </span>
      {(title || amount != null) && (
        <span className={ROW_LINE}>
          <span className="text-[15px] font-medium">{title}</span>
          {amount != null && <b className={cn("text-[15px] font-semibold tabular-nums", amountTone)}>{amount}{unit && <small className="ml-[3px] text-[13px] font-medium text-muted-foreground">{unit}</small>}</b>}
        </span>
      )}
      {(meta || note) && (
        <span className={cn(ROW_LINE, "text-[13px] text-muted-foreground")}>
          <span>{meta}</span>
          {note && <span className={noteTone}>{note}</span>}
        </span>
      )}
    </>
  );
  const cls = cn(
    "flex flex-col gap-[3px] border-t border-hairline px-4 py-[13px] text-left text-foreground no-underline tabular-nums first:border-t-0 active:bg-secondary",
    FOCUS,
  );
  if (lead || children || menu) {
    const inner = cn("flex min-w-0 flex-1 flex-col gap-[3px] py-[13px] text-left text-foreground no-underline tabular-nums", menu ? "pr-0" : "pr-4");
    return (
      <div className={cn("border-t border-hairline first:border-t-0", on && "bg-[color:color-mix(in_oklch,var(--foreground)_5%,var(--card))]")}>
        <div className={cn("flex items-center gap-3", !lead && "pl-4")}>
          {lead && <span className="flex flex-none self-stretch items-center pl-4">{lead}</span>}
          {href ? <Link href={href} className={cn(inner, FOCUS)}>{body}</Link>
            : onClick ? <button type="button" onClick={onClick} className={cn(inner, "cursor-pointer border-0 bg-transparent font-sans", FOCUS)}>{body}</button>
            : <div className={inner}>{body}</div>}
          {menu && <span className="flex flex-none items-center pr-1.5">{menu}</span>}
        </div>
        {children}
      </div>
    );
  }
  if (href) return <Link href={href} className={cls}>{body}</Link>;
  if (onClick) return <button type="button" onClick={onClick} className={cn(cls, "w-full cursor-pointer border-x-0 border-b-0 bg-transparent font-sans")}>{body}</button>;
  return <div className={cls}>{body}</div>;
}

// A group heading between phone rows, as the table's band row: an optional
// checkbox, the label and its count, a figure at the end.
export const PBand = ({ lead, label, count, end }) => (
  <div className="flex items-center gap-3 border-t border-hairline bg-[color:oklch(0.975_0.007_75)] px-4 py-2 text-[13px] font-semibold tabular-nums first:border-t-0 [[data-theme=dark]_&]:bg-[color:oklch(0.215_0.007_75)]">
    {lead}
    <span className="min-w-0 flex-1 truncate">{label}{count != null && <span className="ml-1.5 font-normal text-muted-foreground">{count}</span>}</span>
    {end != null && <span className="flex-none">{end}</span>}
  </div>
);

// The totals line under a phone row list.
export const PTotal = ({ label, children }) => (
  <div className="flex items-baseline justify-between gap-3 border-t border-input px-4 py-[13px] text-[15px] font-semibold tabular-nums">
    <span>{label}</span><span>{children}</span>
  </div>
);

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
    "surface box-border grid size-8 cursor-pointer place-content-center rounded-full border border-border bg-card font-sans text-[13px] leading-[normal] font-medium text-foreground tabular-nums transition-[background-color,border-color] duration-[120ms] ease-[ease] hover:border-input disabled:cursor-default disabled:opacity-35 phone:size-11",
    FOCUS,
  );
  const plain = "border-transparent bg-transparent hover:border-transparent";
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 text-[13px] text-muted-foreground tabular-nums">
      {summary ? <span>{summary}</span> : (
        <span className="flex items-center gap-2 phone:hidden">{t("Show")}
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
      {!summary && <span className="hidden phone:inline">{t("Page {n} of {m}", { n: page, m: pages })}</span>}
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
