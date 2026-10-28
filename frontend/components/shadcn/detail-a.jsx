import { Fragment, useContext, useState } from "react";
import { Link } from "@inertiajs/react";
import { Popover, PopoverTrigger } from "./ui/popover.jsx";
import { Drawer, DrawerContent, DrawerTitle } from "./ui/drawer.jsx";
import { FormModalContext } from "./form-modal.jsx";
import { LIcon, Menu, MenuItem, MenuSep } from "./list-a.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { cn } from "@/lib/utils";
import Page from "./page.jsx";

// Building blocks of the detail pages on the Record View HMS canvas (row
// "CL, Invoice, Client, Hotel, Payment, Remittance, Client Ledger dan
// Expense"). Every page is the same stack: a back row, an optional status
// strip with its action, the head card (number, status, ⋯ menu, file chips,
// facts), then plain cards of tables. Pages write their own <table
// className={DA.table}> so each keeps its columns.
//
// Defaults for what a page puts inside (links, table cells, rows of a list)
// are written as [:where(&)_x] variants: they weigh no more than the element
// itself, so a utility the page sets on a cell or a link always wins.

const S = (props) => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props} />;
export const DIcon = {
  back: <S width="14" height="14"><path d="M15 6l-6 6 6 6" /></S>,
  edit: <S><path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></S>,
  pdf: <S><path d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></S>,
  trash: <S><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></S>,
  plus: <S><path d="M12 5v14M5 12h14" /></S>,
  wallet: <S><path d="M3 8a2 2 0 012-2h14a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" /><path d="M16 12.5h3M3 10h18" /></S>,
  receipt: <S><path d="M9 14l6-6m-5.5.5h.01m4.99 5h.01M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16l3.5-2 3.5 2 3.5-2 3.5 2z" /></S>,
  clip: <S><path d="M15.17 7l-6.59 6.59a2 2 0 102.83 2.82l6.41-6.58a4 4 0 10-5.66-5.66l-6.41 6.59a6 6 0 108.49 8.48L20.5 13" /></S>,
  file: <S><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><path d="M14 2v6h6M8 13h8M8 17h5" /></S>,
  message: <S><path d="M21 12a8 8 0 01-11.6 7.1L4 20l1-4.6A8 8 0 1121 12z" /></S>,
  close: <S><path d="M6 18L18 6M6 6l12 12" /></S>,
  reverse: <S><path d="M20 16H7m0 0l4-4m-4 4l4 4" /></S>,
  check: <S><path d="M5 12l5 5 9-10" /></S>,
  user: <S><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0116 0" /></S>,
  pay: <S><path d="M12 4v16m6-12H9.5a2.5 2.5 0 000 5h5a2.5 2.5 0 010 5H6" /></S>,
  chev: <S width="15" height="15" strokeWidth="2"><path d="M9 6l6 6-6 6" /></S>,
  calendar: <S width="15" height="15"><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></S>,
  download: <S width="15" height="15"><path d="M12 4v11m0 0l-4-4m4 4l4-4M5 20h14" /></S>,
};

const FOCUS = "focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-ring";
const EDGE_X = "px-6 max-[600px]:px-4";

// The pieces of a detail page, as classes for what a page lays out itself.
export const DA = {
  main: cn(
    "mx-auto flex max-w-[1040px] flex-col gap-4 text-[14px] leading-normal text-foreground",
    "[:where(&)_a]:font-semibold [:where(&)_a]:text-foreground [:where(&)_a]:no-underline [:where(&)_a:hover]:underline",
    "[:where(&)_:is(a,button):focus-visible]:outline-2 [:where(&)_:is(a,button):focus-visible]:outline-solid [:where(&)_:is(a,button):focus-visible]:outline-offset-2 [:where(&)_:is(a,button):focus-visible]:outline-ring",
  ),
  card: "surface min-w-0 overflow-hidden rounded-[20px] border border-border bg-card max-[600px]:rounded-[16px]",
  cardPad: "px-6 pt-4 pb-6",
  // A card head laid out by the page itself (DCard draws its own).
  cardHead: "flex items-baseline justify-between gap-3 px-6 pt-4 pb-2 max-[600px]:px-4 [:where(&)_h2]:m-0 [:where(&)_h2]:text-[14px] [:where(&)_h2]:font-semibold",
  count: "ml-2 text-[12px] font-medium text-muted-foreground tabular-nums",
  meta: "text-[12px] text-muted-foreground",
  cardFoot: "flex flex-wrap items-center gap-3 border-t border-border px-6 py-4 text-[13px]",
  footLabel: "text-muted-foreground",
  text: "mt-3 mb-0 text-[14px] leading-[1.6] whitespace-pre-line",
  empty: "px-6 pt-5 pb-6 text-[13px] text-muted-foreground",
  panel: cn("pt-2 pb-4", EDGE_X),
  files: cn("pt-3 pb-4", EDGE_X),
  notice: "m-0 border-b border-border px-6 py-3 text-[13px] text-muted-foreground",
  link: "ml-2 cursor-pointer border-0 bg-transparent p-0 font-sans text-[13px] leading-[normal] font-semibold text-foreground underline decoration-input underline-offset-3",
  mono: "font-mono text-[13px] font-semibold",
  // A record linked by its number, as a filled pill; `tagSm` is the small one.
  tag: "inline-flex h-7 items-center gap-2 rounded-full bg-secondary px-3 font-semibold no-underline hover:no-underline",
  tagSm: "h-[22px] px-2 text-[12px]",
  tagSub: "font-medium text-[color:color-mix(in_oklch,var(--muted-foreground)_70%,var(--foreground))]",
  // Lines of label/value in a card.
  rows: cn("pb-3 text-[14px] [:where(&)>div]:flex [:where(&)>div]:gap-4 [:where(&)>div]:border-b [:where(&)>div]:border-hairline [:where(&)>div]:py-3 [:where(&)>div:last-child]:border-b-0", EDGE_X),
  kv: "mt-4 mb-0 grid grid-cols-[120px_minmax(0,1fr)] gap-x-3 gap-y-4 text-[14px] max-[600px]:grid-cols-[104px_minmax(0,1fr)] [:where(&)_dt]:text-muted-foreground [:where(&)_dd]:m-0 [:where(&)_dd]:font-medium [:where(&)_dd]:[overflow-wrap:anywhere]",
  // Two cards side by side, one column on narrow screens.
  pair: "grid grid-cols-2 items-stretch gap-4 max-[820px]:grid-cols-1 [&>section]:flex [&>section]:flex-col",
  map: "relative mx-6 min-h-[200px] flex-1 overflow-hidden rounded-[14px] bg-secondary max-[600px]:mx-4 [&>div]:absolute [&>div]:inset-0",

  // Tables: the table, then classes for whole rows. `scrollWide` is a table
  // that gives way to DLines on a phone.
  scroll: "overflow-x-auto",
  scrollWide: "overflow-x-auto max-[600px]:hidden",
  table: cn(
    "w-full border-collapse text-[13px]",
    "[:where(&)_th]:border-b [:where(&)_th]:border-border [:where(&)_th]:bg-transparent [:where(&)_th]:px-4 [:where(&)_th]:py-3 [:where(&)_th]:text-left [:where(&)_th]:text-[12px] [:where(&)_th]:font-semibold [:where(&)_th]:tracking-normal [:where(&)_th]:whitespace-nowrap [:where(&)_th]:normal-case [:where(&)_th]:text-foreground",
    "[:where(&)_td]:border-b [:where(&)_td]:border-hairline [:where(&)_td]:px-4 [:where(&)_td]:py-3 [:where(&)_td]:align-top [:where(&)_tbody_td]:font-medium [:where(&)_tfoot_td]:text-[14px]",
    "[:where(&)_:is(th,td):first-child]:pl-6 [:where(&)_:is(th,td):last-child]:pr-6 max-[600px]:[:where(&)_:is(th,td):first-child]:pl-4 max-[600px]:[:where(&)_:is(th,td):last-child]:pr-4",
    "[:where(&)_tbody_tr:last-child_td]:border-b-0",
    "[:where(&)_tfoot_td]:border-t [:where(&)_tfoot_td]:border-t-border [:where(&)_tfoot_td]:border-b-0 [:where(&)_tfoot_td]:bg-card [:where(&)_tfoot_td]:font-semibold [:where(&)_tfoot_td]:tabular-nums [:where(&)_tfoot_tr:first-child_td]:border-t [:where(&)_tfoot_tr:first-child_td]:border-t-input",
  ),
  rowLast: "[&>td]:border-b-0",
  rowMid: "[&>td]:align-middle",
  // A group heading row inside a table; `rowGroupRuled` draws a rule above it.
  rowGroup: "[&>:is(th,td)]:border-b-0 [&>:is(th,td)]:bg-[color:oklch(0.975_0.007_75)] [[data-theme=dark]_&>:is(th,td)]:bg-[color:oklch(0.215_0.007_75)] [&>:is(th,td)]:py-2 [&>:is(th,td)]:align-middle [&>:is(th,td)]:text-[13px] [&>:is(th,td)]:tabular-nums [&>th]:font-semibold [&>th]:text-foreground [&>td]:font-medium [&>td]:text-muted-foreground",
  rowGroupRuled: "[&>:is(th,td)]:border-t [&>:is(th,td)]:border-t-border",
  rowVoid: "[&>td]:text-muted-foreground",
  // Totals rows: `rowSoft` a quieter line, `rowAfter` one that follows on.
  rowSoft: "[&>td]:font-normal [&>td]:text-muted-foreground",
  rowAfter: "[&>td]:pt-0",
};

// Cell classes, in the order the old stylesheet declared them so a later one
// wins where two disagree (`late` over `sub`).
export const DC = {
  n: "text-right tabular-nums whitespace-nowrap",
  nWide: "w-[110px]",
  nw: "whitespace-nowrap tabular-nums",
  sub: "mt-0.5 block text-[12px] font-normal text-muted-foreground",
  mut: "text-muted-foreground",
  strong: "font-medium",
  bold: "font-semibold",
  late: "font-semibold text-danger-text",
  good: "text-success-text",
  mono: "font-mono text-[13px] font-semibold",
  date: "w-[72px] whitespace-nowrap text-muted-foreground tabular-nums",
  acts: "w-8",
  actsIn: "inline-flex justify-end gap-2",
  empty: "px-6 py-8 text-center text-muted-foreground",
  footLabel: "text-right font-medium text-muted-foreground",
};

// A detail table on a phone (canvas "HMS Mobile v2", details): one line per
// row, the name and a second line on the left, the figure on the right, then
// the total. Shown only on phones, beside a table wrapped in DA.scrollWide.
// `children` is a full-width line under the row (a line's match controls).
export const DLines = ({ children }) => <div className="hidden max-[600px]:block">{children}</div>;
export function DLine({ title, sub, value, valueSub, valueTone, href, mono, children }) {
  const body = (
    <>
      <span className="min-w-0 flex-1">
        <span className={cn("block text-[15px] font-semibold", mono && "font-mono text-[14px] font-bold")}>{title}</span>
        {sub ? <span className="block text-[12.5px] text-muted-foreground">{sub}</span> : null}
      </span>
      <span className="flex-none text-right tabular-nums">
        <b className={cn("block text-[14.5px] font-semibold", valueTone)}>{value}</b>
        {valueSub ? <span className="block text-[12px] text-muted-foreground">{valueSub}</span> : null}
      </span>
      {children ? <span className="basis-full">{children}</span> : null}
    </>
  );
  const cls = cn("flex items-center justify-between gap-3 border-t border-hairline px-4 py-3 text-foreground no-underline first:border-t-0 hover:no-underline", children && "flex-wrap gap-y-2");
  return href ? <a href={href} className={cls}>{body}</a> : <div className={cls}>{body}</div>;
}
export const DLinesTotal = ({ label, children }) => (
  <div className="flex items-baseline justify-between gap-3 border-t border-input px-4 py-3.5 font-semibold tabular-nums">
    <span>{label}</span><span className="text-[16px]">{children}</span>
  </div>
);

// A phone's action bar at the foot of a detail page, in place of the bottom
// nav (the top bar's back link leads out): the page's one primary action and
// a share button for its PDF, which opens Share / Download / Print.
// primary = { label, href | onClick } or null; pdf = { title, sub, href }.
export function DPhoneBar({ primary, pdf }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  if (!primary && !pdf) return null;
  const share = async () => {
    setOpen(false);
    const url = new URL(pdf.href, window.location.href).href;
    try { await navigator.share({ title: pdf.title, url }); } catch { /* cancelled */ }
  };
  const canShare = typeof navigator !== "undefined" && !!navigator.share;
  const row = "flex min-h-[60px] w-full cursor-pointer items-center gap-3 border-0 border-t border-hairline bg-transparent px-3.5 py-2.5 text-left font-sans text-foreground no-underline first:border-t-0 hover:no-underline active:bg-secondary";
  const ico = "grid size-9 flex-none place-content-center rounded-[10px] bg-secondary [&_svg]:size-[18px]";
  const label = (title, sub) => <span className="min-w-0 flex-1"><b className="block text-[14px] font-semibold">{title}</b><span className="text-[12.5px] text-muted-foreground">{sub}</span></span>;
  const pbtn = "inline-flex h-11 flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-full border-0 bg-primary px-[18px] font-sans text-[14px] font-semibold whitespace-nowrap text-primary-foreground no-underline hover:no-underline";
  return (
    <div data-slot="phone-bar" className="fixed inset-x-0 bottom-0 z-(--z-sticky) hidden items-center gap-2.5 border-t border-border bg-card px-4 pt-2.5 pb-[calc(14px+env(safe-area-inset-bottom))] max-[600px]:flex">
      {pdf && (
        <button type="button" aria-label={t("Share or download PDF")} onClick={() => setOpen(true)}
          className="grid size-11 flex-none cursor-pointer place-content-center rounded-full border border-input bg-card text-foreground [&_svg]:size-[19px]">
          <S><path d="M12 15V3m0 0L8 7m4-4l4 4M5 12v8h14v-8" /></S>
        </button>
      )}
      {primary && (primary.href
        ? <Link href={primary.href} className={pbtn}>{primary.label}</Link>
        : <button type="button" onClick={primary.onClick} className={pbtn}>{primary.label}</button>)}
      {pdf && (
        <Drawer open={open} onOpenChange={setOpen} direction="bottom">
          <DrawerContent aria-describedby={undefined} className="rounded-t-[22px] border-0 px-4 pb-[calc(18px+env(safe-area-inset-bottom))]">
            <div className="pt-3 pb-2.5">
              <DrawerTitle className="m-0 text-[17px]">{t("{n} PDF", { n: pdf.title })}</DrawerTitle>
              {pdf.sub && <p className="m-0 text-[13px] text-muted-foreground">{pdf.sub}</p>}
            </div>
            <div className="overflow-hidden rounded-[16px] border border-border">
              {canShare && <button type="button" className={row} onClick={share}><span className={ico}><S><path d="M12 15V3m0 0L8 7m4-4l4 4M5 12v8h14v-8" /></S></span>{label(t("Share PDF"), t("WhatsApp, email or any app on this phone"))}</button>}
              <a className={row} href={pdf.href} download onClick={() => setOpen(false)}><span className={ico}>{LIcon.export}</span>{label(t("Download PDF"), t("Save it to this phone"))}</a>
              <a className={row} href={pdf.href} target="_blank" rel="noreferrer" onClick={() => setOpen(false)}><span className={ico}><S><path d="M7 8V3h10v5M7 17H4v-7h16v7h-3M7 14h10v7H7z" /></S></span>{label(t("Print"), t("Open the PDF to print it"))}</a>
            </div>
          </DrawerContent>
        </Drawer>
      )}
    </div>
  );
}

export function DPage({ children, className }) {
  return (
    <Page>
      <div className={cn(DA.main, className)}>{children}</div>
    </Page>
  );
}

// "← Back" and, on the right, when the record was made. Hidden when the page
// is shown inside the form modal.
export function DTop({ href, stamp }) {
  const { t } = useI18n();
  if (useContext(FormModalContext)?.inModal) return null;
  return (
    <div className="flex items-center justify-between gap-3 text-[13px] text-muted-foreground">
      <Link href={href} className="inline-flex items-center gap-1 font-medium text-muted-foreground">{DIcon.back}{t("Back")}</Link>
      {stamp ? <span>{stamp}</span> : null}
    </div>
  );
}

const BANNER = { warning: "bg-warning-tint", danger: "bg-danger-tint", success: "bg-success-tint", info: "bg-info-tint", gray: "bg-secondary" };
// The strip above the head card: one sentence and the actions it asks for.
export function DBanner({ tone = "warning", children, actions }) {
  return (
    <div role="status" className={cn("box-border flex min-h-[54px] flex-wrap items-center justify-between gap-4 rounded-[14px] py-3 pr-3 pl-4 tabular-nums", BANNER[tone])}>
      <span className="text-[14px] [&_b]:font-semibold">{children}</span>
      {actions ? <span className="flex flex-wrap gap-2">{actions}</span> : null}
    </div>
  );
}

// A quiet text button; `primary` filled, `soft` on a grey fill.
export const dBtnClass = ({ primary, soft } = {}) => cn(
  "inline-flex h-[34px] cursor-pointer items-center gap-2 rounded-full border-0 bg-transparent px-3 font-sans text-[13px] leading-[normal] font-semibold whitespace-nowrap text-foreground no-underline",
  "transition-colors duration-150 ease-[ease] hover:bg-[color:color-mix(in_oklch,var(--foreground)_6%,transparent)] hover:no-underline disabled:cursor-default disabled:opacity-50",
  FOCUS,
  primary && "bg-primary px-4 text-primary-foreground hover:bg-primary-hover",
  soft && "h-8 bg-secondary hover:bg-input",
);
export function DBtn({ primary, soft, className, children, ...rest }) {
  const cls = cn(dBtnClass({ primary, soft }), className);
  if (rest.href) return <a data-slot="dbtn" className={cls} {...rest}>{children}</a>;
  return <button data-slot="dbtn" type="button" className={cls} {...rest}>{children}</button>;
}

const PILL = { green: "border-success text-success-text", amber: "border-warning text-warning-text", red: "border-danger text-danger-text", info: "border-info text-info-text" };
export const DPill = ({ tone = "gray", sm, children }) => (
  <span className={cn("box-border inline-flex h-6 items-center whitespace-nowrap rounded-full border border-input px-3 text-[12px] font-semibold text-muted-foreground", PILL[tone], sm && "h-[22px] px-2")}>{children}</span>
);

// The ⋯ menu: [{ label, icon, onClick | href, danger, separator, external }];
// falsy entries drop out.
export function DMenu({ items, label, small }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const list = (items || []).filter(Boolean);
  if (!list.length) return null;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" aria-label={label || t("Actions")} aria-haspopup="menu" className={cn(
          "grid size-10 flex-none cursor-pointer place-content-center rounded-full border-0 bg-transparent text-muted-foreground transition-colors duration-[120ms] ease-[ease] hover:bg-secondary hover:text-foreground aria-expanded:bg-secondary aria-expanded:text-foreground",
          FOCUS, small && "size-8",
        )}>{LIcon.dots}</button>
      </PopoverTrigger>
      <Menu align="end" sideOffset={6} className="w-[220px]">
        {list.map((it, i) => {
          const body = <>{it.icon ? DIcon[it.icon] : null}{it.label}</>;
          return (
            <Fragment key={it.label}>
              {it.separator && i > 0 ? <MenuSep /> : null}
              {it.href ? (
                <MenuItem as="a" danger={it.danger} href={it.href} target={it.external ? "_blank" : undefined} rel="noreferrer" onClick={() => setOpen(false)}>{body}</MenuItem>
              ) : (
                <MenuItem danger={it.danger} onClick={(e) => { setOpen(false); it.onClick(e); }}>{body}</MenuItem>
              )}
            </Fragment>
          );
        })}
      </Menu>
    </Popover>
  );
}

// A file or document as a rounded chip under the title.
export function DChip({ href, icon = "clip", children, label, small }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" aria-label={label} className={cn(
      "box-border inline-flex h-8 max-w-full items-center gap-2 whitespace-nowrap rounded-full border border-border bg-card px-3 text-[13px] font-medium text-foreground no-underline hover:bg-secondary hover:no-underline [&_svg]:size-3.5 [&_svg]:flex-none [&_svg]:text-muted-foreground",
      small && "h-7 text-[12px] [&_svg]:size-[13px]",
    )}>
      {DIcon[icon]}{children}
    </a>
  );
}

const FACT = { danger: "font-semibold text-danger-text", warning: "text-warning-text", success: "font-semibold text-success-text" };
const COLS = { 3: "grid-cols-3 max-[820px]:grid-cols-2", 4: "grid-cols-4 max-[820px]:grid-cols-2" };
// facts: [{ k, v, tone: "danger"|"warning"|"success", strong }]; falsy drop.
// cols: a fixed column count (the design uses 3 or 4), else auto-fit.
export function DFacts({ facts, cols }) {
  const list = (facts || []).filter(Boolean);
  if (!list.length) return null;
  return (
    <dl className={cn("mt-6 mb-0 grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-x-6 gap-y-5 border-t border-border pt-5 max-[600px]:mt-4 max-[600px]:grid-cols-2 max-[600px]:gap-x-5 max-[600px]:gap-y-4 max-[600px]:pt-4", COLS[cols])}>
      {list.map((f) => (
        <div key={f.k} className="min-w-0">
          <dt className="text-[12px] text-muted-foreground">{f.k}</dt>
          <dd className={cn("mt-1 mb-0 ml-0 text-[14px] font-medium tabular-nums [overflow-wrap:anywhere]", f.strong && "font-semibold", FACT[f.tone])}>{f.v}</dd>
        </div>
      ))}
    </dl>
  );
}

// A quieter part of a fact's value ("· 3 nights").
export const DDim = ({ children }) => <span className="font-normal text-muted-foreground">{children}</span>;

export function DHead({ title, badge, menu, chips, facts, cols, note, children }) {
  const { t } = useI18n();
  return (
    <section className={cn(DA.card, "p-6 max-[600px]:p-4")}>
      <div className="flex items-center justify-between gap-4">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <h1 className="m-0 text-[24px] leading-[1.15] font-semibold tracking-[-0.02em] tabular-nums">{title}</h1>
          {badge ? <DPill tone={badge.tone}>{badge.label}</DPill> : null}
        </div>
        {menu ? <DMenu items={menu} /> : null}
      </div>
      {chips && chips.filter(Boolean).length ? <div className="mt-4 flex flex-wrap gap-2">{chips}</div> : null}
      <DFacts facts={facts} cols={cols} />
      {children}
      {note ? (
        <div className="mt-5 border-t border-border pt-4">
          <div className="text-[12px] text-muted-foreground">{note.label || t("Note")}</div>
          <p className="mt-1 mb-0 text-[14px] leading-[1.6] whitespace-pre-line">{note.text}</p>
        </div>
      ) : null}
    </section>
  );
}

// Plain links and buttons among a card's header actions.
const ACTS = cn(
  "flex gap-4 text-[13px]",
  "[&_:is(a,button):not([data-slot=dbtn])]:cursor-pointer [&_:is(a,button):not([data-slot=dbtn])]:border-0 [&_:is(a,button):not([data-slot=dbtn])]:bg-transparent [&_:is(a,button):not([data-slot=dbtn])]:p-0 [&_:is(a,button):not([data-slot=dbtn])]:font-sans [&_:is(a,button):not([data-slot=dbtn])]:text-[13px] [&_:is(a,button):not([data-slot=dbtn])]:leading-[normal] [&_:is(a,button):not([data-slot=dbtn])]:font-semibold [&_:is(a,button):not([data-slot=dbtn])]:text-muted-foreground [&_button:not([data-slot=dbtn]):hover]:text-foreground",
);

export function DCard({ title, count, meta, sub, actions, children, className, headClassName, pad }) {
  return (
    <section data-slot="card" className={cn(DA.card, pad && DA.cardPad, className)}>
      {title || meta || actions ? (
        <div data-slot="card-head" className={cn("flex items-baseline justify-between gap-3", pad ? "p-0" : "px-6 pt-4 pb-2 max-[600px]:px-4", headClassName)}>
          <h2 className="m-0 text-[14px] font-semibold">{title}{count != null ? <span className="ml-2 text-[12px] font-medium text-muted-foreground tabular-nums">{count}</span> : null}</h2>
          {meta ? <span className="text-[12px] text-muted-foreground">{meta}</span> : null}
          {actions ? <span className={cn(ACTS, !meta && "ml-auto")}>{actions}</span> : null}
        </div>
      ) : null}
      {sub ? <p className={cn("text-[12px] leading-normal text-muted-foreground", pad ? "m-0 mt-1" : "mx-6 -mt-1 mb-2")}>{sub}</p> : null}
      {children}
    </section>
  );
}

export const DCardFoot = ({ className, children }) => <div data-slot="card-foot" className={cn(DA.cardFoot, className)}>{children}</div>;

// Tabs on a card's top edge, with tools (search, period, PDF) on the right.
export function DTabs({ tabs, value, onChange, tools, label, tall }) {
  const onKey = (e) => {
    const i = tabs.findIndex((x) => x.key === value);
    const n = e.key === "ArrowRight" ? (i + 1) % tabs.length : e.key === "ArrowLeft" ? (i - 1 + tabs.length) % tabs.length : null;
    if (n == null) return;
    e.preventDefault();
    onChange(tabs[n].key);
  };
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pr-4 pl-6 max-[820px]:pr-3 max-[820px]:pl-4">
      <div role="tablist" aria-label={label} className="flex gap-6" onKeyDown={onKey}>
        {tabs.map((x) => (
          <button key={x.key} type="button" role="tab" aria-selected={x.key === value} tabIndex={x.key === value ? 0 : -1}
            className={cn(
              "-mb-px h-12 cursor-pointer border-0 border-b-2 border-transparent bg-transparent p-0 font-sans text-[13px] leading-[normal] font-medium whitespace-nowrap text-muted-foreground hover:text-foreground",
              tall && "h-[52px]",
              x.key === value && "border-b-foreground font-semibold text-foreground",
            )} onClick={() => onChange(x.key)}>
            {x.label}{x.count ? <span className="ml-1 tabular-nums">{x.count}</span> : null}
          </button>
        ))}
      </div>
      {tools ? <div className="flex flex-wrap items-center gap-2 py-2 max-[820px]:w-full [&_[data-slot=search]]:w-[220px] max-[820px]:[&_[data-slot=search]]:w-auto max-[820px]:[&_[data-slot=search]]:flex-1">{tools}</div> : null}
    </div>
  );
}

// Activity rows: [{ key, when, body, by }].
export function DLog({ rows, wide, empty }) {
  if (!rows.length) return <div className={DA.empty}>{empty}</div>;
  return (
    <div className={cn("pt-2 pb-4 text-[14px]", EDGE_X)}>
      {rows.map((r) => (
        <div key={r.key} className="flex gap-4 border-b border-hairline py-3 last:border-b-0 [&_b]:font-semibold [&_s]:text-muted-foreground">
          <span className={cn("w-16 flex-none text-muted-foreground tabular-nums", wide && "w-24")}>{r.when}</span>
          <span>{r.body}{r.by ? <span className="text-muted-foreground"> · {r.by}</span> : null}</span>
        </div>
      ))}
    </div>
  );
}

// "06 Oct 2026" -> "06 Oct"; ISO "2026-10-06T..." -> "06 Oct"
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function dayMonth(v) {
  if (!v) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(v);
  if (m) return `${m[3]} ${MON[+m[2] - 1]}`;
  const d = /^(\d{1,2})[/ ](\w{3}|\d{2})/.exec(v);
  if (d) return `${d[1].padStart(2, "0")} ${/^\d+$/.test(d[2]) ? MON[+d[2] - 1] : d[2]}`;
  return v;
}
