// The dashboard kit: what the four role dashboards (Manager, Admin, Finance,
// Staff/Viewer) are composed of, as components and utility maps — the styles
// that used to live in styles/dashboard.css. Everything here is Tailwind
// utility; the report pages build on the same exports.
//
//   DashKpis   the KPI strip: one accent card beside three or four KPI cards
//   HeroCard   the one accent card (booked value / bank and cash)
//   DashGrid   the card grids (g2 2:1, g2b 1.25:1, g3 equal)
//   DashStack  cards stacked in one column, feet pushed to the bottom
//   GridTable  repeating rows as a grid (to do, check-ins, queues)
//   Count      the count pill inside a grid row
//   RankBars   a ranking with bars (top clients, top hotels)
//   MoneyRow(s) the label/value rows of "money now"-style cards
//   BigFigure  the headline figure above a chart
//   Legend     a chart legend
//   BC / FC    the two bar charts' cells (CL sold per month, money in/out)
//   KV / GAUGE the collected gauge and its key-value rows

import { Link } from "@inertiajs/react";
import { cn } from "@/lib/utils";
import { fmtN } from "./list-a.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// ── Head line, and links in card heads/feet ───────────────────────────────
export const DH = {
  hi: "m-0 text-[24px] font-semibold tracking-[-0.02em] leading-[1.2]",
  sub: "mt-1 text-[13px] text-muted-foreground",
  // Links grow to a 40px tap target on a phone without moving the line.
  link: "text-[12px] font-medium text-muted-foreground no-underline hover:text-foreground phone:-my-3 phone:inline-block phone:py-3",
  footLink: "font-semibold text-foreground no-underline phone:-my-3 phone:inline-block phone:py-3",
};

// ── Card grids ─────────────────────────────────────────────────────────────
// g2: the chart spans, one narrow card beside it. g2b/g3: equal-weight cards
// stretched to the tallest, their feet at the bottom. "-one": a single column,
// "3-two": g3 with two cards.
const GRID_STRETCH =
  "[:where(&)>[data-slot=card]]:flex [:where(&)>[data-slot=card]]:flex-col [:where(&)_[data-slot=card-foot]]:mt-auto [:where(&)_[data-slot=empty]]:my-auto";
const GRIDS = {
  "2": "grid-cols-[minmax(0,2fr)_minmax(0,1fr)]",
  "2-one": "grid-cols-[minmax(0,1fr)]",
  "2b": `grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] ${GRID_STRETCH}`,
  "2b-one": `grid-cols-[minmax(0,1fr)] ${GRID_STRETCH}`,
  "3": `grid-cols-[repeat(3,minmax(0,1fr))] ${GRID_STRETCH}`,
  "3-two": `grid-cols-[repeat(2,minmax(0,1fr))] ${GRID_STRETCH}`,
};

export function DashGrid({ g = "2", className, children }) {
  return <div className={cn("grid items-stretch gap-4 max-[1100px]:grid-cols-1", GRIDS[g], className)}>{children}</div>;
}

export function DashStack({ className, children }) {
  return (
    <div className={cn(
      "flex min-w-0 flex-col gap-4",
      "[:where(&)>[data-slot=card]]:flex [:where(&)>[data-slot=card]]:flex-col [:where(&)_[data-slot=card-foot]]:mt-auto",
      className,
    )}>{children}</div>
  );
}

// ── The KPI strip ─────────────────────────────────────────────────────────
// hero: the accent card node; children: the KPI cards (three or four, with or
// without the hero — the column templates follow). Two across under 1180, one
// under 600.
const KPI_GRIDS = {
  hero3: "grid-cols-[minmax(0,1.35fr)_repeat(3,minmax(0,1fr))]",
  hero4: "grid-cols-[minmax(0,1.35fr)_repeat(4,minmax(0,1fr))]",
  flat3: "grid-cols-[repeat(3,minmax(0,1fr))]",
  flat4: "grid-cols-[repeat(4,minmax(0,1fr))]",
};

// Phones, every role: the accent card on its own row, the KPI cards under it
// swiping sideways like a list page's (canvas "HMS Mobile v2", Home).
export function DashKpis({ hero, className, children }) {
  const n = Array.isArray(children) ? children.length : children ? 1 : 0;
  const cols = KPI_GRIDS[`${hero ? "hero" : "flat"}${n}`] || KPI_GRIDS.flat4;
  return (
    <>
      {hero && <div className="hidden phone:flex phone:flex-col">{hero}</div>}
      <div className={cn(
        "grid gap-3",
        cols,
        "[:where(&)_[data-slot=kpi]]:min-w-0",
        "max-[1180px]:grid-cols-2",
        "phone:grid-cols-1",
        hero && "max-[1180px]:[:where(&)>:first-child]:col-span-full",
        "phone:-mx-4 phone:flex phone:scroll-px-4 phone:snap-x phone:snap-mandatory phone:gap-2.5 phone:overflow-x-auto phone:px-4 phone:[scrollbar-width:none] phone:[&::-webkit-scrollbar]:hidden",
        hero && "phone:[&>:first-child]:hidden",
        className,
      )}>
        {hero}
        {children}
      </div>
    </>
  );
}

// ── The accent card ────────────────────────────────────────────────────────
export const HERO = {
  card: "flex min-w-0 flex-col rounded-[20px] bg-hero p-4 text-white no-underline",
  label: "flex items-center justify-between gap-2 text-[13px] font-medium text-hero-ink",
  chip: "inline-flex h-5 items-center rounded-[6px] bg-hero-chip px-1.5 text-[12px] font-medium whitespace-nowrap text-white",
  chipBad: "bg-hero-chip-bad text-hero-chip-bad-ink",
  value: "mt-2 text-[32px] font-semibold tracking-[-0.02em] leading-[1.1] tabular-nums [overflow-wrap:anywhere]",
  unit: "ml-1 text-[13px] font-semibold tracking-normal text-hero-ink",
  bars: "mt-3 flex h-8 items-end gap-1",
  bar: "min-h-[2px] flex-1 rounded-t-[4px] rounded-b-[2px] bg-hero-bar",
  barOn: "bg-hero-on",
  axis: "mt-1 flex justify-between text-[12px] text-hero-ink",
  foot: "mt-2 text-[12px] text-hero-ink tabular-nums",
  lines: "mt-3 flex flex-col gap-1 text-[13px] tabular-nums",
  line: "flex justify-between gap-3 text-hero-ink",
};

// chip: { text, bad }; bars: { data: [{ h, on }], label }; axis: [from, to];
// lines: [{ k, v }] — the Finance shape, the value's build-up per currency.
export function HeroCard({ href, label, chip, value, unit, bars, axis, foot, lines, className }) {
  return (
    <Link href={href} className={cn(HERO.card, className)}>
      <span className={HERO.label}>
        {label}
        {chip && <span className={cn(HERO.chip, chip.bad && HERO.chipBad)}>{chip.text}</span>}
      </span>
      <span className={HERO.value}>{value}{unit && <small className={HERO.unit}>{unit}</small>}</span>
      {bars && (
        <span className={HERO.bars} role="img" aria-label={bars.label}>
          {bars.data.map((b, i) => (
            <i key={i} className={cn(HERO.bar, b.on && HERO.barOn)} style={{ height: `${Math.max(b.h, 4)}%` }} />
          ))}
        </span>
      )}
      {axis && <span className={HERO.axis}><span>{axis[0]}</span><span>{axis[1]}</span></span>}
      {lines && (
        <span className={HERO.lines}>
          {lines.map((l) => (
            <span key={l.k} className={HERO.line}><span>{l.k}</span><b className="font-semibold text-white">{l.v}</b></span>
          ))}
        </span>
      )}
      {foot && <span className={HERO.foot}>{foot}</span>}
    </Link>
  );
}

// ── Grid rows: a table drawn as a grid ─────────────────────────────────────
export const DGT = {
  table: "text-[13px]",
  head: "grid min-h-10 items-center gap-3 border-b border-border px-6 text-[12px] font-semibold text-foreground phone:px-4",
  row: "grid min-h-14 items-center gap-3 border-b border-hairline px-6 text-inherit no-underline transition-colors duration-[120ms] ease-[ease] last:border-b-0 hover:bg-[color-mix(in_oklch,var(--foreground)_3%,var(--card))] phone:px-4",
  n: "text-right tabular-nums whitespace-nowrap",
  d: "text-muted-foreground tabular-nums whitespace-nowrap",
  strong: "block font-medium",
  sub: "mt-0.5 block text-[12px] text-muted-foreground",
  ell: "overflow-hidden text-ellipsis whitespace-nowrap",
  bold: "font-semibold",
  mut: "ml-1 text-[12px] font-medium text-muted-foreground",
  go: "text-muted-foreground justify-self-end",
  late: "font-semibold text-danger-text",
};

// Column templates per grid table. They ride the row containers (role=row),
// so one class on the table lays out header and rows alike; on a phone the
// third column is dropped where the template says so.
const HIDE_COL_3 = "phone:[:where(&)_[role=row]>*:nth-child(3)]:hidden";
export const DGT_COLS = {
  todo: "[:where(&)_[role=row]]:grid-cols-[minmax(0,1fr)_56px_140px_16px] " + HIDE_COL_3 +
    " phone:[:where(&)_[role=row]]:grid-cols-[minmax(0,1fr)_48px_auto]",
  ci: "[:where(&)_[role=row]]:grid-cols-[64px_minmax(0,1fr)_48px_104px] " + HIDE_COL_3 +
    " phone:[:where(&)_[role=row]]:grid-cols-[48px_minmax(0,1fr)_auto]",
  pay: "[:where(&)_[role=row]]:grid-cols-[minmax(0,1fr)_140px_16px]",
  pd: "[:where(&)_[role=row]]:grid-cols-[minmax(0,1fr)_48px_80px_80px] " + HIDE_COL_3 +
    " phone:[:where(&)_[role=row]]:grid-cols-[minmax(0,1fr)_48px_auto]",
  mypay: "[:where(&)_[role=row]]:grid-cols-[minmax(0,1fr)_128px_152px] " + HIDE_COL_3 +
    " phone:[:where(&)_[role=row]]:grid-cols-[minmax(0,1fr)_auto]",
};

export function GridTable({ cols, label, head, className, children }) {
  return (
    <div role="table" aria-label={label} className={cn(DGT.table, DGT_COLS[cols], className)}>
      <div role="row" className={DGT.head}>{head}</div>
      {children}
    </div>
  );
}

export function GridRow({ href, className, children, ...rest }) {
  return <Link role="row" className={cn(DGT.row, className)} href={href} {...rest}>{children}</Link>;
}

// The count pill inside a grid row: neutral, red when it is the locked/
// over-a-month-late count calling out.
export function Count({ red, children }) {
  return (
    <span className={cn(
      "inline-grid h-6 min-w-6 place-content-center rounded-full bg-secondary px-2 font-semibold tabular-nums",
      red && "bg-danger-tint text-danger-text",
    )}>{children}</span>
  );
}

// The check badge of an empty to do.
export const OK_BADGE = "mx-auto mb-2 grid size-10 place-content-center rounded-[12px] bg-success-tint text-success-text";

// ── Ranking with bars ──────────────────────────────────────────────────────
// rows: [{ id, href, name, sub, v, chg, new }]; the first row's bar carries
// the full accent, the rest a quiet tint. hasPrev: "New" only means something
// against an earlier season.
export function RankBars({ rows, hasPrev }) {
  const { t } = useI18n();
  const max = Math.max(1, ...rows.map((r) => r.v));
  return (
    <div className="px-6 pb-4 pt-1">
      {rows.map((r, i) => {
        const [c, tone] = r.new
          ? (hasPrev ? [t("New"), "nw"] : ["", ""])
          : r.chg == null ? ["", ""]
            : [`${r.chg >= 0 ? "+" : "−"}${Math.abs(r.chg)}%`, r.chg >= 0 ? "up" : "dn"];
        return (
          <Link key={r.id} href={r.href} className="group/rk grid grid-cols-[16px_minmax(0,1fr)_auto_auto] items-center gap-x-3 gap-y-1 border-t border-hairline py-2 text-[13px] text-inherit no-underline first:border-t-0">
            <span className="text-[12px] font-semibold text-muted-foreground tabular-nums">{i + 1}</span>
            <span className="min-w-0 truncate font-medium group-hover/rk:underline group-hover/rk:underline-offset-[3px]">
              {r.name}<small className="ml-2 text-[12px] font-normal text-muted-foreground">{r.sub}</small>
            </span>
            <span className={cn(
              "min-w-10 text-right text-[12px] font-semibold tabular-nums",
              tone === "up" && "text-success-text",
              tone === "dn" && "text-warning-text",
              tone === "nw" && "text-info-text",
            )}>{c}</span>
            <b className="font-semibold tabular-nums">{fmtN(r.v)}</b>
            <span className="h-1.5 overflow-hidden rounded-full bg-secondary [grid-column:2/-1]">
              <i className={cn("block h-full rounded-full bg-[color-mix(in_srgb,var(--data)_40%,var(--card))]", i === 0 && "bg-data")} style={{ width: `${(r.v / max) * 100}%` }} />
            </span>
          </Link>
        );
      })}
    </div>
  );
}

// ── Money rows ─────────────────────────────────────────────────────────────
// MoneyRow: label (and a sub line) on the left, the value on the right; a
// link row tints on hover, a plain one does not. tone: "warn" (money to act
// on), "zero" (nothing there — quiet figure).
export function MoneyRows({ className, children }) {
  return <div className={cn("px-6 pb-4 pt-1", className)}>{children}</div>;
}

export function MoneyRow({ href, label, sub, ell, value, className, children }) {
  const row = cn(
    "-mx-2 flex items-baseline justify-between gap-2 rounded-[8px] border-t border-hairline px-2 py-3 text-[13px] no-underline first:border-t-0",
    href && "text-inherit transition-colors duration-[120ms] ease-[ease] hover:bg-secondary",
    className,
  );
  const body = children ?? (
    <>
      <span className={cn("min-w-0 text-muted-foreground", ell && "overflow-hidden text-ellipsis whitespace-nowrap")}>
        {label}{sub && <small className="block text-[12px]">{sub}</small>}
      </span>
      {value}
    </>
  );
  return href ? <Link href={href} className={row}>{body}</Link> : <div className={row}>{body}</div>;
}

export function MoneyValue({ tone, children }) {
  // tone: warn (money to act on), zero (nothing there — a quiet figure).
  const TONE = { warn: "text-warning-text", zero: "font-medium text-muted-foreground" };
  return (
    <b className={cn("text-[16px] font-semibold tracking-[-0.01em] tabular-nums whitespace-nowrap", TONE[tone])}>{children}</b>
  );
}
export const MONEY_UNIT = "ml-1 text-[12px] font-medium text-muted-foreground";

// ── Figures and legends above a chart ─────────────────────────────────────
export function BigFigure({ value, note }) {
  return (
    <div className="mt-3 flex flex-wrap items-baseline gap-2">
      <b className="text-[24px] font-semibold tracking-[-0.02em] tabular-nums">{value}</b>
      <span className="text-[13px] text-muted-foreground">{note}</span>
    </div>
  );
}

// items: [{ label, bg: utility (bg-data, bg-chart-bar, …), dashed: last-year }]
export function Legend({ items }) {
  return (
    <span className="flex flex-wrap gap-3 text-[12px] text-muted-foreground">
      {items.map((it) => (
        <span key={it.label} className="inline-flex items-center gap-1">
          <i className={it.dashed
            ? "inline-block h-0 w-3 border-0 border-t-2 border-dashed border-muted-foreground"
            : cn("inline-block size-2 rounded-[2px]", it.bg)} />
          {it.label}
        </span>
      ))}
    </span>
  );
}

// ── Bar charts ─────────────────────────────────────────────────────────────
// BC — CL sold per month: grey bars, the picked one in green, last season
// dashed. Every bar carries its value, so there is no y axis, only a baseline.
export const BC = {
  chart: "relative mt-6 grid h-52 grid-cols-[repeat(12,minmax(0,1fr))] items-end gap-2 phone:gap-1",
  gl: "absolute inset-x-0 border-t border-hairline pointer-events-none",
  pre: "absolute bottom-0 left-0 flex h-full items-center justify-center border-0 border-b border-dashed border-hairline text-[12px] text-muted-foreground pointer-events-none",
  col: "group/col relative flex h-full items-end justify-center",
  bar: "relative w-full max-w-8 rounded-t-[8px] rounded-b-[2px] bg-chart-bar transition-colors duration-[120ms] ease-[ease] group-hover/col:bg-[color-mix(in_oklch,var(--foreground)_18%,var(--chart-bar))]",
  on: "bg-data group-hover/col:brightness-105",
  onDown: "bg-warning group-hover/col:brightness-105",
  val: "absolute inset-x-0 -top-5 text-center text-[12px] font-semibold tabular-nums",
  ly: "absolute left-1/2 w-8 -translate-x-1/2 border-0 border-t-2 border-dashed border-muted-foreground opacity-55 pointer-events-none",
  tip: "pointer-events-none absolute bottom-full left-1/2 z-4 min-w-[168px] -translate-x-1/2 -translate-y-2 rounded-[12px] border border-border bg-popover px-3 py-2 text-[13px] whitespace-nowrap shadow-menu",
  tipL: "left-0 translate-x-0",
  tipR: "left-auto right-0 translate-x-0",
  tipH: "mb-1 block font-semibold",
  tipRow: "flex justify-between gap-4 text-muted-foreground",
  tipVal: "font-semibold text-foreground tabular-nums",
  x: "mt-2 grid grid-cols-[repeat(12,minmax(0,1fr))] gap-2 text-center text-[12px] text-muted-foreground phone:gap-1",
  xOn: "font-semibold text-foreground",
  xPre: "opacity-50",
};

// FC — money in and out: received in green, paid out in ink, the current
// month on. Bars carry no values here, so this chart keeps its y axis.
export const FC = {
  chart: "relative ml-8 mt-6 grid h-52 grid-cols-[repeat(6,minmax(0,1fr))] items-end gap-4 phone:gap-2",
  gl: "absolute inset-x-0 border-t border-hairline pointer-events-none",
  glNum: "absolute -top-2 -left-8 w-6 text-right text-[12px] text-muted-foreground tabular-nums",
  col: "group/col relative flex h-full items-end justify-center gap-1",
  in: "block w-full max-w-6 min-h-[2px] rounded-t-[6px] rounded-b-[2px] bg-[color-mix(in_srgb,var(--data)_35%,var(--card))] group-hover/col:bg-data",
  out: "block w-full max-w-6 min-h-[2px] rounded-t-[6px] rounded-b-[2px] bg-chart-bar group-hover/col:bg-foreground",
  onIn: "bg-data",
  onOut: "bg-foreground",
  tip: BC.tip,
  tipR: BC.tipR,
  tipH: BC.tipH,
  tipRow: BC.tipRow,
  tipVal: BC.tipVal,
  x: "ml-8 mt-2 grid grid-cols-[repeat(6,minmax(0,1fr))] gap-4 text-center text-[12px] text-muted-foreground phone:gap-2",
  xOn: "font-semibold text-foreground",
};

// ── The collected gauge and its rows ───────────────────────────────────────
export const GAUGE = {
  wrap: "relative mt-4 flex justify-center",
  pct: "absolute inset-x-0 top-16 text-center text-[24px] font-semibold tracking-[-0.02em] leading-none tabular-nums",
  label: "absolute inset-x-0 top-24 text-center text-[12px] text-muted-foreground",
};

// Row of label / dot / value; `tot` is the billed line: the sum of the rows
// above it, drawn on the stronger rule.
export const KV = {
  row: "flex items-center justify-between border-t border-hairline py-2 text-[13px] first:border-t-0",
  key: "inline-flex items-center gap-2 text-muted-foreground",
  dot: "inline-block size-2 rounded-[2px]",
  val: "font-semibold tabular-nums",
  tot: "mt-1 flex items-center justify-between border-t border-border py-2 text-[13px] [:where(&)_span]:font-medium [:where(&)_span]:text-foreground",
};
