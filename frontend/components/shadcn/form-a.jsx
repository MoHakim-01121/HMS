import { Fragment, useContext, useMemo, useRef, useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover.jsx";
import { Dialog, DialogCloseButton } from "./ui/dialog.jsx";
import { FormModalContext, ModalContent, ModalHead, ModalTitle, ModalBody, actionsClass } from "./form-modal.jsx";
import FormHeader from "./form-header.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { cn } from "@/lib/utils";
import { Switch } from "./ui/switch.jsx";

// Building blocks of the approved CL and Invoice forms (Record View HMS
// canvas, "CL Form (disetujui)" / "Invoice Form (disetujui)"): a labelled
// field, a picker that opens a searchable list, and one- and two-month
// calendars. Popovers portal out of the dialog so its scroll never clips them.

const FOCUS = "focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-ring";
const HOVER_EDGE = "hover:border-[color:color-mix(in_oklch,var(--foreground)_45%,var(--input))]";
// A bare input inside one of the drawn controls below.
const BARE = "min-h-0 min-w-0 rounded-none border-0 bg-transparent p-0 font-sans leading-[normal] text-foreground shadow-none outline-none";
// On touch screens the small icon buttons get a 44px hit area around them.
const TOUCH = "pointer-coarse:relative pointer-coarse:after:absolute pointer-coarse:after:-inset-2 pointer-coarse:after:content-['']";

// The pieces of the approved form, as classes for the parts a page lays out
// itself (the CL rooms table, the Invoice reservations list). The components
// below use the same strings.
export const FA = {
  fields: "grid grid-cols-2 gap-4 max-[640px]:grid-cols-1",
  wide: "col-span-full",
  // A drawn control: a button that opens a picker, or a span around an input.
  control: cn(
    "box-border flex h-10 w-full cursor-pointer items-center gap-2 rounded-[10px] border-[1.5px] border-field bg-card px-3 text-left font-sans text-[14px] leading-[normal] font-semibold text-foreground",
    "transition-[border-color,box-shadow] duration-[120ms] ease-[ease] aria-expanded:border-foreground aria-expanded:shadow-[0_0_0_3px_color-mix(in_oklch,var(--foreground)_8%,transparent)]",
    "[&>svg]:flex-none [&>svg]:text-muted-foreground [&>svg:last-child:not(:first-child)]:ml-auto",
    HOVER_EDGE, FOCUS,
  ),
  bad: "border-danger hover:border-danger aria-expanded:border-danger",
  // The control hosts a typed input (TextIn, AmountIn).
  hostsInput: "cursor-text focus-within:border-foreground focus-within:shadow-[0_0_0_3px_color-mix(in_oklch,var(--foreground)_8%,transparent)]",
  input: cn(BARE, "h-full flex-1 text-[14px] font-semibold placeholder:font-normal placeholder:text-muted-foreground"),
  readOnly: "cursor-default border-transparent bg-[color:color-mix(in_oklch,var(--foreground)_3%,var(--card))] hover:border-transparent",
  text: "min-w-0 flex-1 truncate",
  placeholder: "font-normal text-muted-foreground",
  meta: "flex-none text-[12px] font-medium text-muted-foreground",
  muted: "font-medium text-muted-foreground",
  num: "tabular-nums",
  unit: "ml-[3px] text-[.7em] font-medium text-muted-foreground",
  ccy: "inline-flex h-[22px] flex-none items-center rounded-[6px] bg-secondary px-2 text-[12px] font-bold tracking-[.03em] text-foreground",
  newTag: "inline-flex h-5 flex-none items-center rounded-full bg-info-tint px-2 text-[12px] font-semibold text-info-text",

  // Section caption over a framed table, and the frame.
  sectionHead: "mt-6 mb-2 flex items-baseline justify-between text-[13px]",
  caption: "text-[12px] font-semibold tracking-[.13em] uppercase text-muted-foreground",
  box: "rounded-[14px] border border-border px-2 pt-2",
  scroll: "-mx-1.5 -mt-1.5 overflow-x-auto px-2 pt-2",
  noteEmpty: "px-3 py-4 text-[13px] text-muted-foreground [&_a]:font-semibold [&_a]:text-foreground",

  // CL rooms table: each row carries data-row so the rule between rows can
  // key off its neighbour.
  row: "grid min-h-14 min-w-[620px] grid-cols-[minmax(0,1fr)_128px_92px_112px_104px_30px] items-center gap-3 px-2 text-[14px] [[data-row]+&]:border-t [[data-row]+&]:border-hairline",
  rowHead: "min-h-[34px] text-[12px] font-medium text-muted-foreground",
  rowTotal: "mx-[-6px] mt-2 min-h-[58px] rounded-b-[13px] border-t border-border bg-card px-4 [[data-row]+&]:border-border [&_b]:font-bold",
  // A compact control in a table cell.
  pill: cn(
    "box-border flex h-[34px] w-full cursor-pointer items-center justify-between gap-2 rounded-[10px] border-[1.5px] border-field bg-card px-3 text-left font-sans text-[13px] leading-[normal] font-semibold text-foreground",
    "transition-[border-color] duration-[120ms] ease-[ease] disabled:cursor-not-allowed disabled:opacity-55 [&_svg]:flex-none [&_svg]:text-muted-foreground",
    HOVER_EDGE, FOCUS,
  ),
  pillInput: cn(BARE, "flex-1 text-[13px] font-semibold"),
  stepper: cn("box-border flex h-[34px] w-full items-center justify-between rounded-[10px] border-[1.5px] border-field bg-card px-[3px] focus-within:border-foreground", HOVER_EDGE),
  stepperButton: "grid size-6 cursor-pointer place-content-center rounded-[6px] border-0 bg-transparent text-muted-foreground hover:bg-secondary hover:text-foreground pointer-coarse:relative pointer-coarse:after:absolute pointer-coarse:after:inset-x-[-4px] pointer-coarse:after:inset-y-[-10px] pointer-coarse:after:content-['']",
  qty: cn(BARE, "h-6 w-[34px] text-center text-[14px] font-semibold tabular-nums"),
  price: cn("box-border flex h-[34px] cursor-text items-center justify-end gap-0.5 rounded-[10px] text-[12px] border-[1.5px] border-field bg-card px-3 transition-[border-color] duration-[120ms] ease-[ease] focus-within:border-foreground", HOVER_EDGE),
  priceInput: cn(BARE, "w-full text-right text-[14px] font-medium tabular-nums"),
  subtotal: "text-right font-semibold tabular-nums",
  totalPerNight: "pr-3 text-right font-semibold tabular-nums",
  trash: cn("grid size-7 cursor-pointer place-content-center rounded-full border-0 bg-transparent text-muted-foreground hover:bg-danger-tint hover:text-danger-text", TOUCH, FOCUS),
  addRow: cn("mt-0.5 flex min-h-[42px] w-full cursor-pointer items-center gap-2 border-0 border-t border-dashed border-border bg-transparent px-3 text-left font-sans text-[13px] leading-[normal] font-medium text-muted-foreground hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60", FOCUS),

  // Invoice: confirmation letters to bill.
  checkRow: "box-border grid min-h-[52px] w-full min-w-[540px] cursor-pointer grid-cols-[30px_96px_minmax(0,1fr)_150px_120px] items-center gap-3 border-0 border-t border-hairline bg-transparent px-2 text-left [font-family:inherit] [font-weight:inherit] [line-height:inherit] text-[14px] text-muted-foreground transition-colors duration-[120ms] ease-[ease] hover:bg-[color:color-mix(in_oklch,var(--foreground)_3%,var(--card))]",
  checkRowOn: "text-foreground",
  checkRowHead: "min-h-9 cursor-default border-t-0 text-[12px] font-medium hover:bg-transparent",
  checkNote: "px-3 py-4 text-[13px] text-muted-foreground",
  // The row's checkbox: `checkBoxOn` ticked, `checkBoxMid` some ticked.
  checkBox: cn("box-border grid size-[18px] flex-none cursor-pointer place-content-center rounded-[5px] border-2 border-input bg-card p-0 text-primary-foreground [&_svg]:invisible", FOCUS),
  checkBoxOn: "border-primary bg-primary [&_svg]:visible",
  checkBoxMid: "border-primary bg-primary [&_svg]:hidden after:h-0.5 after:w-2 after:rounded-[1px] after:bg-primary-foreground after:content-['']",
  checkTotal: "mx-[-6px] mt-2 flex min-h-14 items-center justify-between rounded-b-[13px] border-t border-border bg-card px-4",

  // Note and messages.
  noteWrap: "mt-5 flex flex-col gap-2",
  note: cn(
    "box-border min-h-16 w-full resize-y rounded-[10px] border-[1.5px] border-field bg-card p-3 font-sans text-[14px] leading-[1.5] font-medium text-foreground outline-none transition-[border-color] duration-[120ms] ease-[ease]",
    "focus:border-foreground focus:shadow-[0_0_0_3px_color-mix(in_oklch,var(--foreground)_8%,transparent)]",
    HOVER_EDGE,
  ),
  // A quiet text button under or beside the fields ("Keep current password").
  textBtn: cn("inline-flex cursor-pointer items-center gap-1.5 border-0 bg-transparent p-0 font-sans text-[13px] leading-[normal] font-semibold text-muted-foreground hover:text-foreground", FOCUS),
  alert: "mt-2 text-[12px] text-danger-text",
  alertTop: "mt-0 mb-3 text-[12px] text-danger-text",

  // A row in a picker's list.
  option: cn("box-border flex min-h-[38px] w-full cursor-pointer items-center gap-3 rounded-[8px] border-0 bg-transparent px-3 py-2 text-left font-sans text-[13px] leading-[normal] font-medium text-foreground no-underline hover:bg-secondary [&>svg]:flex-none [&>svg]:text-muted-foreground", FOCUS),
  optionOn: "bg-[color:color-mix(in_oklch,var(--secondary)_80%,var(--card))] hover:bg-[color:color-mix(in_oklch,var(--secondary)_80%,var(--card))]",
  optionText: "flex min-w-0 flex-1 flex-col leading-[1.3] font-medium [&_small]:text-[12px] [&_small]:font-normal [&_small]:text-muted-foreground",
  popover: "surface w-(--radix-popover-trigger-width) min-w-60 max-w-[calc(100vw-32px)] rounded-[14px] border-border bg-popover p-2 text-left font-sans shadow-menu",
  popSep: "mx-0.5 my-1 h-px bg-hairline",
};

// One of the two buttons of the form's action row (and the calendar's).
export const btnClass = (variant = "o", sm) => cn(
  "inline-flex h-9 cursor-pointer items-center justify-center gap-2 rounded-full px-4 font-sans text-[13px] leading-[normal] font-semibold whitespace-nowrap no-underline",
  "[transition:background-color_120ms_ease,border-color_120ms_ease,transform_120ms_ease] active:[transform:scale(.97)]",
  FOCUS,
  variant === "p"
    ? "border-0 bg-primary text-primary-foreground shadow-[0_1px_0_rgba(255,255,255,.12)_inset,0_1px_2px_rgba(10,12,16,.18)] hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-45 aria-disabled:cursor-not-allowed aria-disabled:opacity-45"
    : "border border-input bg-card text-foreground hover:border-foreground",
  sm && "h-[30px] px-3",
);

// A reservation's status as a coloured dot.
const DOT = { DEFINITE: "bg-success text-success", TENTATIVE: "bg-transparent text-warning", CANCELLED: "bg-muted-foreground text-muted-foreground" };
export const StatusDot = ({ status }) => <span className={cn("box-border size-2.5 flex-none rounded-full border-2 border-current", DOT[status])} />;

const Rq = () => <span className="ml-0.5 text-danger-text">*</span>;

// The caps caption over a section ("ROOMS", "NOTE"), with its required or
// optional mark.
export function Caption({ children, required, optional }) {
  const { t } = useI18n();
  return (
    <span className={FA.caption}>
      {children}{required && <Rq />}
      {optional && <span className="ml-2 font-medium tracking-normal normal-case text-muted-foreground">{t(optional === true ? "Optional" : optional)}</span>}
    </span>
  );
}

export const Chevron = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M6 9l6 6 6-6" /></svg>
);
const Tick = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M5 12l5 5 9-10" /></svg>
);
const Plus = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path strokeLinecap="round" d="M12 5v14M5 12h14" /></svg>
);
const SearchIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path strokeLinecap="round" d="M20 20l-3.5-3.5" /></svg>
);

// A setting in a bordered box: title and note on the left, its control on
// the right. SwitchRow is the common case, a setting that is on or off.
export function SettingRow({ title, note, className, children }) {
  return (
    <div className={cn("flex items-center justify-between gap-4 rounded-[14px] border border-border px-4 py-3", className)}>
      <span><b className="block text-[14px] font-medium">{title}</b>{note ? <span className="block text-[12px] text-muted-foreground">{note}</span> : null}</span>
      {children}
    </div>
  );
}
export const SwitchRow = ({ title, note, className, ...props }) => (
  <SettingRow title={title} note={note} className={className}><Switch {...props} /></SettingRow>
);

// One choice out of a few, as a grey track with the chosen option lifted:
// options = [[value, label]]. `wide` fills the row, the options sharing it.
export function Segmented({ value, options, onChange, label, wide }) {
  return (
    <div className={cn("inline-flex gap-1 rounded-[12px] bg-secondary p-1", wide && "flex w-full")} role="radiogroup" aria-label={label}>
      {options.map(([v, l]) => (
        <button key={v} type="button" role="radio" aria-checked={value === v} onClick={() => onChange(v)}
          className={cn("h-[34px] cursor-pointer rounded-[9px] border-0 bg-transparent px-4 font-sans text-[13px] leading-[normal] font-medium text-muted-foreground aria-checked:bg-card aria-checked:text-foreground aria-checked:shadow-seg-on", wide && "h-10 flex-1 text-[14px]", FOCUS)}>{l}</button>
      ))}
    </div>
  );
}

// A group caption inside the field grid, on phones only, where the one
// column of fields runs long (canvas "HMS Mobile v2", forms).
export const PhoneCaption = ({ children }) => (
  <div className={cn(FA.caption, FA.wide, "mt-2 -mb-1 hidden max-[600px]:block")}>{children}</div>
);

export function Field({ label, required, optional, error, hint, className = "", children, htmlFor }) {
  const { t } = useI18n();
  const Tag = htmlFor ? "label" : "div";
  return (
    <Tag className={cn("flex min-w-0 flex-col gap-2", className)} htmlFor={htmlFor}>
      <span className="text-[13px] font-medium text-muted-foreground">{label}{required && <Rq />}{optional && <span className="ml-2 font-normal">{t("optional")}</span>}</span>
      {children}
      {error ? <span className="text-[12px] text-danger-text" role="alert">{error}</span> : hint ? <span className="text-[12px] text-muted-foreground">{hint}</span> : null}
    </Tag>
  );
}

// A row of a picker's list.
function Option({ on, lead, label, meta, ...props }) {
  return (
    <button type="button" role="option" aria-selected={on} {...props} className={cn(FA.option, on && FA.optionOn)}>
      {lead}
      <span className={FA.optionText}>{label}{meta ? <small>{meta}</small> : null}</span>
      <span className={cn("grid w-3.5 text-foreground", !on && "invisible")}><Tick /></span>
    </button>
  );
}

// A button showing the chosen value; pressing it opens `options` with a search
// box (when `searchable`). Each option: { value, label, meta }.
export function Picker({ icon, value, options, onPick, placeholder, searchable = true, heading, addNew, emptyText, invalid, extra, popClass = "" }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const cur = options.find((o) => String(o.value) === String(value));
  const list = useMemo(() => {
    const s = q.trim().toLowerCase();
    const hits = options.filter((o) => !s || o.label.toLowerCase().includes(s) || String(o.meta || "").toLowerCase().includes(s));
    // The chosen one first, as on the canvas.
    if (hits.some((o) => o.group)) return hits;
    return cur ? [...hits.filter((o) => o === cur), ...hits.filter((o) => o !== cur)] : hits;
  }, [options, q, cur]);
  const groupHead = "px-3 pt-2 pb-1 text-[12px] font-semibold tracking-[.08em] uppercase text-muted-foreground";

  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (!o) setQ(""); }}>
      <PopoverTrigger asChild>
        <button type="button" className={cn(FA.control, invalid && FA.bad)} aria-haspopup="listbox" aria-expanded={open}>
          {icon}
          {cur ? <span className={FA.text}>{cur.label}</span> : <span className={cn(FA.text, FA.placeholder)}>{placeholder}</span>}
          {extra}
          <Chevron />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={6} className={cn(FA.popover, popClass)} onOpenAutoFocus={(e) => { if (!searchable) e.preventDefault(); }}>
        <div role="listbox">
          {searchable && (
            <label className="-mx-1.5 -mt-1.5 mb-1 flex h-10 items-center gap-2 border-b border-hairline px-4 text-muted-foreground">
              <SearchIcon />
              <input className={cn(BARE, "h-full flex-1 text-[13px] font-medium")} aria-label={t("Search")} placeholder={t("Search")} value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
            </label>
          )}
          <div className="max-h-[300px] overflow-y-auto">
            {heading && <div className={groupHead}>{heading}</div>}
            {list.map((o, i) => {
              const head = o.group && (i === 0 || list[i - 1].group !== o.group);
              return (
                <Fragment key={o.value}>
                  {head && <div className={groupHead}>{o.group}</div>}
                  <Option on={cur === o} lead={o.lead} label={o.label} meta={o.meta} onClick={() => { onPick(o); setOpen(false); setQ(""); }} />
                </Fragment>
              );
            })}
            {!list.length && <div className="p-3 text-[13px] text-muted-foreground">{emptyText || t("No match for this search.")}</div>}
          </div>
          {addNew && (
            <>
              <div className={FA.popSep} />
              <a className={FA.option} href={addNew.href} target="_blank" rel="noreferrer" onClick={() => setOpen(false)}>
                <Plus /><span className={FA.optionText}>{addNew.label}<small>{addNew.meta}</small></span>
              </a>
            </>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

// A compact select for table cells (room type, meal plan).
export function CellPicker({ value, options, onPick, placeholder, disabled, label }) {
  const [open, setOpen] = useState(false);
  const cur = options.find((o) => String(o.value) === String(value));
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className={FA.pill} disabled={disabled} aria-label={label} aria-haspopup="listbox" aria-expanded={open}>
          <span className={cn(FA.text, !cur && FA.placeholder)}>{cur ? cur.label : placeholder}</span><Chevron />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={6} className={cn(FA.popover, "min-w-[220px]")}>
        <div role="listbox">
          {options.map((o) => (
            <Option key={o.value} on={cur === o} label={o.label} meta={o.meta} onClick={() => { onPick(o); setOpen(false); }} />
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

// ── Dates (ISO yyyy-mm-dd strings, local calendar) ──────────────────────────
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const MON = MONTHS.map((m) => m.slice(0, 3));
const WD = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
const pad = (n) => String(n).padStart(2, "0");
export const isoOf = (y, m, d) => `${y}-${pad(m + 1)}-${pad(d)}`;
export const todayIso = () => { const d = new Date(); return isoOf(d.getFullYear(), d.getMonth(), d.getDate()); };
const parse = (iso) => { const [y, m, d] = iso.split("-").map(Number); return { y, m: m - 1, d }; };
export const dateLabel = (iso, withYear = true) => {
  if (!iso) return "";
  const { y, m, d } = parse(iso);
  return `${pad(d)} ${MON[m]}${withYear ? " " + y : ""}`;
};
export const addDaysIso = (iso, n) => {
  const { y, m, d } = parse(iso);
  const x = new Date(y, m, d + n);
  return isoOf(x.getFullYear(), x.getMonth(), x.getDate());
};
export const nightsBetween = (a, b) => {
  if (!a || !b) return 0;
  const A = parse(a), B = parse(b);
  return Math.round((Date.UTC(B.y, B.m, B.d) - Date.UTC(A.y, A.m, A.d)) / 86400000);
};

function monthCells(y, m) {
  const lead = (new Date(y, m, 1).getDay() + 6) % 7;
  const len = new Date(y, m + 1, 0).getDate();
  return { lead, days: Array.from({ length: len }, (_, i) => isoOf(y, m, i + 1)) };
}

// A day of the calendar grid. `f` = { past, today, s (stay start), e (stay
// end), in (inside the stay), pv (inside the hovered preview), pe (preview
// end), pk (picked) }.
const DAY = cn(
  "grid h-[34px] cursor-pointer place-items-center border-0 bg-transparent p-0 font-sans text-[13px] leading-[normal] font-medium text-foreground tabular-nums",
  "[&>span]:grid [&>span]:size-8 [&>span]:place-content-center [&>span]:rounded-full [&>span]:transition-colors [&>span]:duration-[120ms] [&>span]:ease-[ease]",
  FOCUS,
);
const dayClass = (f) => {
  const end = f.s || f.e || f.pk;
  return cn(
    DAY,
    f.past && "cursor-not-allowed text-muted-foreground opacity-45",
    f.today && "[&>span]:shadow-[inset_0_0_0_1px_var(--input)]",
    f.in && "bg-secondary",
    f.pv && "bg-[color:color-mix(in_oklch,var(--secondary)_55%,transparent)]",
    f.s && "rounded-l-full bg-secondary",
    f.e && "rounded-r-full bg-secondary",
    f.s && f.e && "rounded-full bg-transparent",
    end && "[&>span]:bg-primary [&>span]:font-semibold [&>span]:text-primary-foreground",
    f.pe && "[&>span]:shadow-[inset_0_0_0_2px_var(--foreground)]",
    !end && !f.past && "hover:[&>span]:bg-card hover:[&>span]:shadow-[inset_0_0_0_1px_var(--foreground)]",
  );
};
const Blank = () => <span className="invisible h-[34px] cursor-default" />;
const Weekdays = () => {
  const { t } = useI18n();
  return WD.map((w) => <span key={w} className="grid h-6 place-content-center text-[12px] font-medium text-muted-foreground">{t(w)}</span>);
};
const MONTH_HEAD = "mb-2 flex h-7 items-center justify-center text-[13px] font-semibold";
const GRID = "grid grid-cols-7 gap-y-0.5";

function Month({ y, m, cellFlags, onPick, onHover }) {
  const { t } = useI18n();
  const { lead, days } = monthCells(y, m);
  return (
    <div>
      <div className={MONTH_HEAD}>{t(MONTHS[m])} {y}</div>
      <div className={GRID}>
        <Weekdays />
        {Array.from({ length: lead }, (_, i) => <Blank key={"b" + i} />)}
        {days.map((iso, i) => {
          const f = cellFlags(iso);
          return (
            <button type="button" key={iso} className={dayClass(f)} disabled={f.past} aria-pressed={!!(f.s || f.e)}
              aria-label={`${i + 1} ${t(MONTHS[m])} ${y}`} onClick={() => onPick(iso)} onMouseEnter={() => onHover && onHover(iso)}>
              <span>{i + 1}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

const NavBtn = ({ dir, onClick, label }) => (
  <button type="button" className={cn("grid size-7 flex-none cursor-pointer place-content-center rounded-full border-0 bg-transparent text-muted-foreground hover:bg-secondary hover:text-foreground", TOUCH, FOCUS)} aria-label={label} onClick={onClick}>
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d={dir < 0 ? "M15 18l-6-6 6-6" : "M9 6l6 6-6 6"} /></svg>
  </button>
);

const CalIcon = ({ size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="4" y="5" width="16" height="15" rx="2" /><path strokeLinecap="round" d="M4 10h16M9 3v4M15 3v4" /></svg>
);

// Check-in to check-out over two months. `minDate` greys out earlier days.
export function DateRangePicker({ start, end, onChange, minDate, invalid }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const base = parse(start || todayIso());
  const [view, setView] = useState({ y: base.y, m: base.m });
  const [phase, setPhase] = useState("start");
  const [hover, setHover] = useState(null);
  const shift = (n) => setView((v) => { const d = new Date(v.y, v.m + n, 1); return { y: d.getFullYear(), m: d.getMonth() }; });
  const next = new Date(view.y, view.m + 1, 1);
  const today = todayIso();
  const previewEnd = phase === "end" && hover && start && hover > start ? hover : null;

  const cellFlags = (iso) => {
    const st = iso === start, en = !!end && iso === end;
    return {
      past: !!minDate && iso < minDate,
      today: iso === today,
      s: st,
      e: en || (st && !end && !previewEnd),
      in: !!(end && start && iso > start && iso < end),
      pv: !!(previewEnd && iso > start && iso <= previewEnd),
      pe: !!(previewEnd && iso === previewEnd),
    };
  };
  const pick = (iso) => {
    if (phase === "start" || !start || iso <= start) { onChange(iso, ""); setPhase("end"); }
    else { onChange(start, iso); setPhase("start"); }
    setHover(null);
  };
  const n = nightsBetween(start, end);

  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (o) { const b = parse(start || todayIso()); setView({ y: b.y, m: b.m }); setPhase(start && !end ? "end" : "start"); } setHover(null); }}>
      <PopoverTrigger asChild>
        <button type="button" className={cn(FA.control, invalid && FA.bad)} aria-haspopup="dialog" aria-expanded={open}>
          <CalIcon />
          <span className={cn(FA.text, FA.num)}>
            {start ? dateLabel(start) : <span className={FA.placeholder}>{t("Check-in")}</span>}
            {" "}<span className={FA.muted}>{t("to")}</span>{" "}
            {end ? dateLabel(end) : <span className={FA.placeholder}>{t("Check-out")}</span>}
          </span>
          {n > 0 && <span className={FA.meta}>{n === 1 ? t("1 night") : t("{n} nights", { n })}</span>}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={6} className={cn(FA.popover, "relative w-[560px] px-4 pt-4 pb-3 max-[640px]:w-[300px]")} onMouseLeave={() => setHover(null)} aria-label={t("Choose stay dates")}>
        <div className="pointer-events-none absolute top-2.5 right-2.5 left-2.5 flex justify-between [&_button]:pointer-events-auto">
          <NavBtn dir={-1} label={t("Previous month")} onClick={() => shift(-1)} /><NavBtn dir={1} label={t("Next month")} onClick={() => shift(1)} />
        </div>
        <div className="grid grid-cols-2 gap-6 max-[640px]:grid-cols-1 max-[640px]:[&>div+div]:hidden">
          <Month y={view.y} m={view.m} cellFlags={cellFlags} onPick={pick} onHover={(iso) => phase === "end" && setHover(iso)} />
          <Month y={next.getFullYear()} m={next.getMonth()} cellFlags={cellFlags} onPick={pick} onHover={(iso) => phase === "end" && setHover(iso)} />
        </div>
        <div className="mt-3 flex justify-end gap-2 border-t border-hairline pt-3">
          <button type="button" className={btnClass("o", true)} onClick={() => { onChange(start, ""); setPhase("end"); }}>{t("Clear")}</button>
          <button type="button" className={btnClass("p", true)} onClick={() => setOpen(false)}>{t("Done")}</button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

export function DatePicker({ value, onChange, label }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const base = parse(value || todayIso());
  const [view, setView] = useState({ y: base.y, m: base.m });
  const shift = (n) => setView((v) => { const d = new Date(v.y, v.m + n, 1); return { y: d.getFullYear(), m: d.getMonth() }; });
  const today = todayIso();
  const { lead, days } = monthCells(view.y, view.m);
  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (o) { const b = parse(value || todayIso()); setView({ y: b.y, m: b.m }); } }}>
      <PopoverTrigger asChild>
        <button type="button" className={FA.control} aria-haspopup="dialog" aria-expanded={open}>
          <CalIcon size={15} />
          <span className={cn(FA.text, FA.num)}>{value ? dateLabel(value) : <span className={FA.placeholder}>{t("Pick a date")}</span>}</span>
          <Chevron />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={6} className={cn(FA.popover, "w-[300px] min-w-0 px-4 py-3")} aria-label={label}>
        <div className={cn(MONTH_HEAD, "justify-between")}>
          <NavBtn dir={-1} label={t("Previous month")} onClick={() => shift(-1)} />
          <span>{t(MONTHS[view.m])} {view.y}</span>
          <NavBtn dir={1} label={t("Next month")} onClick={() => shift(1)} />
        </div>
        <div className={GRID}>
          <Weekdays />
          {Array.from({ length: lead }, (_, i) => <Blank key={"b" + i} />)}
          {days.map((iso, i) => (
            <button type="button" key={iso} className={dayClass({ pk: iso === value, today: iso === today })}
              aria-label={`${i + 1} ${t(MONTHS[view.m])} ${view.y}`} aria-pressed={iso === value}
              onClick={() => { onChange(iso); setOpen(false); }}>
              <span>{i + 1}</span>
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

// ── Plain inputs ────────────────────────────────────────────────────────────
// Thousands separators while typing; the value handed back is digits only.
export const groupDigits = (v) => {
  const d = String(v ?? "").replace(/[^\d]/g, "");
  return d ? Number(d).toLocaleString("en-US") : "";
};
export const digitsOf = (v) => String(v ?? "").replace(/[^\d]/g, "");

export function TextIn({ value, onChange, placeholder, icon, suffix, id, type = "text", inputMode, autoFocus, invalid, className, ...rest }) {
  return (
    <span className={cn(FA.control, FA.hostsInput, invalid && FA.bad)}>
      {icon}
      <input id={id} type={type} inputMode={inputMode} value={value ?? ""} placeholder={placeholder} autoFocus={autoFocus}
        className={cn(FA.input, className)} onChange={(e) => onChange(e.target.value)} {...rest} />
      {suffix}
    </span>
  );
}

// An amount: the currency as a chip, the number grouped as it is typed, and
// an optional note on the right (its SAR value, the rate).
export function AmountIn({ ccy, value, onChange, hint, id, invalid, decimals = false, autoFocus }) {
  const shown = decimals ? value : groupDigits(value);
  return (
    <span className={cn(FA.control, FA.hostsInput, invalid && FA.bad)}>
      {ccy ? <span className={FA.ccy}>{ccy}</span> : null}
      <input id={id} className={cn(FA.input, "text-[16px]")} inputMode={decimals ? "decimal" : "numeric"} placeholder="0" value={shown ?? ""} autoFocus={autoFocus}
        onChange={(e) => onChange(decimals ? e.target.value.replace(/[^\d.]/g, "") : digitsOf(e.target.value))} />
      {hint ? <span className={FA.meta}>{hint}</span> : null}
    </span>
  );
}

// A field that needs no input in this case, saying why.
export const ReadOnly = ({ children }) => <div className={cn(FA.control, FA.readOnly)}><span className={cn(FA.text, FA.placeholder)}>{children}</span></div>;

const MB = 1024 * 1024;
export const fileSize = (n) => (n >= MB ? `${(n / MB).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

// The proof upload: a dashed drop area until a file is chosen, then the file
// with a remove button. `maxBytes` refuses a file the server would refuse.
export function FileDrop({ file, onFile, title, sub, accept = "image/*,.pdf", maxBytes = 3 * MB, onTooBig }) {
  const { t } = useI18n();
  const ref = useRef(null);
  const pick = (f) => {
    if (!f) return;
    if (f.size > maxBytes) { onTooBig ? onTooBig(f) : null; return; }
    onFile(f);
  };
  const tile = "grid flex-none place-content-center bg-secondary text-foreground";
  return (
    <>
      <input ref={ref} type="file" accept={accept} hidden onChange={(e) => { pick(e.target.files[0]); e.target.value = ""; }} />
      {file ? (
        <div className="flex items-center gap-3 rounded-[12px] border-[1.5px] border-input p-3">
          <span className={cn(tile, "size-9 rounded-[8px]")}><DocIcon /></span>
          <span className="min-w-0 flex-1"><b className="block truncate text-[14px] font-semibold">{file.name}</b><span className="text-[12px] text-muted-foreground">{fileSize(file.size)}</span></span>
          <button type="button" className={FA.trash} aria-label={t("Remove file")} onClick={() => onFile(null)}><TrashIcon /></button>
        </div>
      ) : (
        <button type="button" className={cn("surface box-border flex w-full cursor-pointer items-center gap-4 rounded-[12px] border-[1.5px] border-dashed border-input bg-card p-4 text-left [font:inherit] text-inherit transition-[border-color,background-color] duration-[120ms] ease-[ease] hover:border-foreground hover:bg-[color:color-mix(in_oklch,var(--foreground)_3%,var(--card))]", FOCUS)}
          onClick={() => ref.current?.click()}
          onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files[0]); }}>
          <span className={cn(tile, "size-10 rounded-[10px]")}><UploadIcon /></span>
          <span><b className="block text-[14px] font-semibold">{title}</b><span className="text-[12px] text-muted-foreground">{sub || t("Image or PDF, up to 3 MB")}</span></span>
        </button>
      )}
    </>
  );
}

export function NoteField({ label, value, onChange, placeholder, required, optional, children }) {
  return (
    <div className={FA.noteWrap}>
      <Caption required={required} optional={optional}>{label}</Caption>
      {children || <textarea className={FA.note} value={value ?? ""} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />}
    </div>
  );
}

// Why the primary button is not ready yet, at the start of the action row.
// Before / after figures under a money form (deposit held, after approval):
// muted rows; the `result` row is ruled off, in ink, its figure in bold 16px.
export const Effect = ({ children }) => <div className="rounded-[14px] border border-border px-3.5 py-1.5 text-[13px]">{children}</div>;
export const EffectRow = ({ result, children }) => (
  <div className={cn("flex min-h-[30px] items-center justify-between gap-3 text-muted-foreground", result && "mt-1 border-t border-border pt-1.5 font-medium text-foreground [&_b]:text-[16px] [&_b]:font-bold")}>{children}</div>
);

export const Why = ({ children }) => <span className="mr-auto text-[13px] text-muted-foreground max-[640px]:basis-full max-[600px]:min-w-0 max-[600px]:flex-1 max-[600px]:basis-auto max-[600px]:text-[12px] max-[600px]:leading-[1.35]" role="status">{children}</span>;

// The footer: why the primary button is not ready yet (or, when it is, an
// optional `note`), Cancel, and the primary action. In a modal Cancel closes it; on its own it goes back.
export function Foot({ why, note, cancelHref, onCancel, submitLabel, processing, extra }) {
  const { t } = useI18n();
  const ctx = useContext(FormModalContext);
  return (
    <div className={actionsClass("a")}>
      {why || note ? <Why>{why || note}</Why> : null}
      {/* Phones close the form from its header (✕), so the row keeps the reason and the primary only. */}
      {onCancel ? <button type="button" className={cn(btnClass("o"), "max-[600px]:hidden")} onClick={onCancel}>{t("Cancel")}</button>
        : ctx?.inModal ? <button type="button" className={cn(btnClass("o"), "max-[600px]:hidden")} onClick={ctx.close}>{t("Cancel")}</button>
          : <a className={cn(btnClass("o"), "max-[600px]:hidden")} href={cancelHref}>{t("Cancel")}</a>}
      {extra}
      <button type="submit" className={btnClass("p")} aria-disabled={!!why || processing} disabled={processing}>{processing ? t("Saving…") : submitLabel}</button>
    </div>
  );
}

// The approved form layout's frame: hands the title (and the layout, which
// the dialog frames a little differently) up to the modal header.
export function FormAFrame({ title, children }) {
  return (
    <div data-slot="form-a" className="text-[14px] leading-normal text-foreground">
      <FormHeader title={title} layout="a" />
      {children}
    </div>
  );
}

// A whole form in the approved layout: the title in the modal header, a
// two-column field grid, then whatever the form adds below it.
export function FormA({ title, onSubmit, error, children }) {
  return (
    <FormAFrame title={title}>
      <form method="post" onSubmit={onSubmit} noValidate>
        {error ? <div className={FA.alertTop} role="alert">{error}</div> : null}
        {children}
      </form>
    </FormAFrame>
  );
}

const DocIcon = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M7 3h7l5 5v13H7zM14 3v5h5" /></svg>;
const UploadIcon = () => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M12 16V4m0 0l-4 4m4-4l4 4M5 20h14" /></svg>;
const TrashIcon = () => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>;

// A form opened over a list page (not through the form modal): the same
// 760px dialog, title in the header, the form in the scrolling body.
export function FaDialog({ title, onClose, children }) {
  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <ModalContent className="sm:max-w-3xl" layout="a">
        <ModalHead layout="a">
          <div className="min-w-0"><ModalTitle>{title}</ModalTitle></div>
          <DialogCloseButton />
        </ModalHead>
        <ModalBody layout="a"><div data-slot="form-a" className="text-[14px] leading-normal text-foreground">{children}</div></ModalBody>
      </ModalContent>
    </Dialog>
  );
}
