import { Fragment, useContext, useMemo, useRef, useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover.jsx";
import { Dialog, DialogCloseButton, DialogContent, DialogTitle } from "./ui/dialog.jsx";
import { FormModalContext } from "./form-modal.jsx";
import FormHeader from "./form-header.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import "../../styles/form-a.css";

// Building blocks of the approved CL and Invoice forms (Record View HMS
// canvas, "CL Form (disetujui)" / "Invoice Form (disetujui)"): a labelled
// field, a picker that opens a searchable list, and one- and two-month
// calendars. Popovers portal out of the dialog so its scroll never clips them.

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

export function Field({ label, required, optional, error, hint, className = "", children, htmlFor }) {
  const { t } = useI18n();
  const Tag = htmlFor ? "label" : "div";
  return (
    <Tag className={"fa-of " + className} htmlFor={htmlFor}>
      <span className="fa-ol">{label}{required && <span className="fa-rq">*</span>}{optional && <span className="fa-oo">{t("optional")}</span>}</span>
      {children}
      {error ? <span className="fa-oerr" role="alert">{error}</span> : hint ? <span className="fa-ohint">{hint}</span> : null}
    </Tag>
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

  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (!o) setQ(""); }}>
      <PopoverTrigger asChild>
        <button type="button" className={"fa-oi" + (invalid ? " bad" : "")} aria-haspopup="listbox" aria-expanded={open}>
          {icon}
          {cur ? <span className="fa-ot">{cur.label}</span> : <span className="fa-ot fa-ph">{placeholder}</span>}
          {extra}
          <Chevron />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={6} className={"fa-pop " + popClass} onOpenAutoFocus={(e) => { if (!searchable) e.preventDefault(); }}>
        <div role="listbox">
          {searchable && (
            <label className="fa-psearch"><SearchIcon /><input aria-label={t("Search")} placeholder={t("Search")} value={q} onChange={(e) => setQ(e.target.value)} autoFocus /></label>
          )}
          <div className="fa-plist">
            {heading && <div className="fa-phead">{heading}</div>}
            {list.map((o, i) => {
              const on = cur === o;
              const head = o.group && (i === 0 || list[i - 1].group !== o.group);
              return (
                <Fragment key={o.value}>
                  {head && <div className="fa-phead">{o.group}</div>}
                  <button type="button" className={"fa-opt" + (on ? " on" : "")} role="option" aria-selected={on}
                    onClick={() => { onPick(o); setOpen(false); setQ(""); }}>
                    {o.lead}
                    <span className="t">{o.label}{o.meta ? <small>{o.meta}</small> : null}</span>
                    <span className="ck"><Tick /></span>
                  </button>
                </Fragment>
              );
            })}
            {!list.length && <div className="fa-empty">{emptyText || t("No match for this search.")}</div>}
          </div>
          {addNew && (
            <>
              <div className="fa-psep" />
              <a className="fa-opt addnew" href={addNew.href} target="_blank" rel="noreferrer" onClick={() => setOpen(false)}>
                <Plus /><span className="t">{addNew.label}<small>{addNew.meta}</small></span>
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
        <button type="button" className="fa-pill" disabled={disabled} aria-label={label} aria-haspopup="listbox" aria-expanded={open}>
          <span className={"fa-ot" + (cur ? "" : " fa-ph")}>{cur ? cur.label : placeholder}</span><Chevron />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={6} className="fa-pop fa-pop-cell">
        <div role="listbox">
          {options.map((o) => {
            const on = cur === o;
            return (
              <button type="button" key={o.value} className={"fa-opt" + (on ? " on" : "")} role="option" aria-selected={on}
                onClick={() => { onPick(o); setOpen(false); }}>
                <span className="t">{o.label}{o.meta ? <small>{o.meta}</small> : null}</span>
                <span className="ck"><Tick /></span>
              </button>
            );
          })}
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

function Month({ y, m, cellClass, onPick, onHover }) {
  const { t } = useI18n();
  const { lead, days } = monthCells(y, m);
  return (
    <div>
      <div className="fa-calh">{t(MONTHS[m])} {y}</div>
      <div className="fa-calg">
        {WD.map((w) => <span key={w} className="fa-wd">{t(w)}</span>)}
        {Array.from({ length: lead }, (_, i) => <span key={"b" + i} className="fa-cd blank" />)}
        {days.map((iso, i) => {
          const c = cellClass(iso);
          return (
            <button type="button" key={iso} className={"fa-cd " + c.cls} disabled={c.disabled} aria-pressed={c.sel}
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
  <button type="button" className="fa-iconbtn" aria-label={label} onClick={onClick}>
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d={dir < 0 ? "M15 18l-6-6 6-6" : "M9 6l6 6-6 6"} /></svg>
  </button>
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

  const cellClass = (iso) => {
    const past = minDate && iso < minDate;
    const st = iso === start, en = end && iso === end;
    let cls = "";
    if (past) cls += " past";
    if (iso === today) cls += " today";
    if (st) cls += " s" + (end || previewEnd ? "" : " e");
    if (en) cls += " e";
    if (end && start && iso > start && iso < end) cls += " in";
    if (previewEnd && iso > start && iso < previewEnd) cls += " pv";
    if (previewEnd && iso === previewEnd) cls += " pv pe";
    return { cls, disabled: !!past, sel: !!(st || en) };
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
        <button type="button" className={"fa-oi" + (invalid ? " bad" : "")} aria-haspopup="dialog" aria-expanded={open}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="4" y="5" width="16" height="15" rx="2" /><path strokeLinecap="round" d="M4 10h16M9 3v4M15 3v4" /></svg>
          <span className="fa-ot fa-num">
            {start ? dateLabel(start) : <span className="fa-ph">{t("Check-in")}</span>}
            {" "}<span className="fa-mut">{t("to")}</span>{" "}
            {end ? dateLabel(end) : <span className="fa-ph">{t("Check-out")}</span>}
          </span>
          {n > 0 && <span className="fa-om">{n === 1 ? t("1 night") : t("{n} nights", { n })}</span>}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={6} className="fa-pop fa-cal" onMouseLeave={() => setHover(null)} aria-label={t("Choose stay dates")}>
        <div className="fa-calnav"><NavBtn dir={-1} label={t("Previous month")} onClick={() => shift(-1)} /><NavBtn dir={1} label={t("Next month")} onClick={() => shift(1)} /></div>
        <div className="fa-months">
          <Month y={view.y} m={view.m} cellClass={cellClass} onPick={pick} onHover={(iso) => phase === "end" && setHover(iso)} />
          <Month y={next.getFullYear()} m={next.getMonth()} cellClass={cellClass} onPick={pick} onHover={(iso) => phase === "end" && setHover(iso)} />
        </div>
        <div className="fa-calf">
          <button type="button" className="fa-btn o sm" onClick={() => { onChange(start, ""); setPhase("end"); }}>{t("Clear")}</button>
          <button type="button" className="fa-btn p sm" onClick={() => setOpen(false)}>{t("Done")}</button>
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
  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (o) { const b = parse(value || todayIso()); setView({ y: b.y, m: b.m }); } }}>
      <PopoverTrigger asChild>
        <button type="button" className="fa-oi" aria-haspopup="dialog" aria-expanded={open}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="4" y="5" width="16" height="15" rx="2" /><path strokeLinecap="round" d="M4 10h16M9 3v4M15 3v4" /></svg>
          <span className="fa-ot fa-num">{value ? dateLabel(value) : <span className="fa-ph">{t("Pick a date")}</span>}</span>
          <Chevron />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={6} className="fa-pop fa-cal1" aria-label={label}>
        <div className="fa-calh fa-calh-nav">
          <NavBtn dir={-1} label={t("Previous month")} onClick={() => shift(-1)} />
          <span>{t(MONTHS[view.m])} {view.y}</span>
          <NavBtn dir={1} label={t("Next month")} onClick={() => shift(1)} />
        </div>
        <div className="fa-calg">
          {WD.map((w) => <span key={w} className="fa-wd">{t(w)}</span>)}
          {(() => {
            const { lead, days } = monthCells(view.y, view.m);
            return [
              ...Array.from({ length: lead }, (_, i) => <span key={"b" + i} className="fa-cd blank" />),
              ...days.map((iso, i) => (
                <button type="button" key={iso} className={"fa-cd" + (iso === value ? " pk" : "") + (iso === today ? " today" : "")}
                  aria-label={`${i + 1} ${t(MONTHS[view.m])} ${view.y}`} aria-pressed={iso === value}
                  onClick={() => { onChange(iso); setOpen(false); }}>
                  <span>{i + 1}</span>
                </button>
              )),
            ];
          })()}
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

export function TextIn({ value, onChange, placeholder, icon, suffix, id, type = "text", inputMode, autoFocus, invalid, ...rest }) {
  return (
    <span className={"fa-oi fa-oin" + (invalid ? " bad" : "")}>
      {icon}
      <input id={id} type={type} inputMode={inputMode} value={value ?? ""} placeholder={placeholder} autoFocus={autoFocus}
        onChange={(e) => onChange(e.target.value)} {...rest} />
      {suffix}
    </span>
  );
}

// An amount: the currency as a chip, the number grouped as it is typed, and
// an optional note on the right (its SAR value, the rate).
export function AmountIn({ ccy, value, onChange, hint, id, invalid, decimals = false, autoFocus }) {
  const shown = decimals ? value : groupDigits(value);
  return (
    <span className={"fa-oi fa-oin fa-amt" + (invalid ? " bad" : "")}>
      {ccy ? <span className="fa-ccy">{ccy}</span> : null}
      <input id={id} className="fa-num" inputMode={decimals ? "decimal" : "numeric"} placeholder="0" value={shown ?? ""} autoFocus={autoFocus}
        onChange={(e) => onChange(decimals ? e.target.value.replace(/[^\d.]/g, "") : digitsOf(e.target.value))} />
      {hint ? <span className="fa-om">{hint}</span> : null}
    </span>
  );
}

// A field that needs no input in this case, saying why.
export const ReadOnly = ({ children }) => <div className="fa-oi fa-ro"><span className="fa-ot fa-ph">{children}</span></div>;

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
  return (
    <>
      <input ref={ref} type="file" accept={accept} hidden onChange={(e) => { pick(e.target.files[0]); e.target.value = ""; }} />
      {file ? (
        <div className="fa-file">
          <span className="ic"><DocIcon /></span>
          <span className="fa-file-t"><b>{file.name}</b><span>{fileSize(file.size)}</span></span>
          <button type="button" className="fa-trash" aria-label={t("Remove file")} onClick={() => onFile(null)}><TrashIcon /></button>
        </div>
      ) : (
        <button type="button" className="fa-drop" onClick={() => ref.current?.click()}
          onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files[0]); }}>
          <span className="ic"><UploadIcon /></span>
          <span><b>{title}</b><span>{sub || t("Image or PDF, up to 3 MB")}</span></span>
        </button>
      )}
    </>
  );
}

export function NoteField({ label, value, onChange, placeholder, required, optional, children }) {
  const { t } = useI18n();
  return (
    <div className="fa-notewrap">
      <span className="fa-cap">{label}{required && <span className="fa-rq">*</span>}{optional && <span className="fa-oo">{t("Optional")}</span>}</span>
      {children || <textarea className="fa-note" value={value ?? ""} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />}
    </div>
  );
}

// The footer: why the primary button is not ready yet (or, when it is, an
// optional `note`), Cancel, and the primary action. In a modal Cancel closes it; on its own it goes back.
export function Foot({ why, note, cancelHref, onCancel, submitLabel, processing, extra }) {
  const { t } = useI18n();
  const ctx = useContext(FormModalContext);
  return (
    <div className="hms-form-actions fa-foot">
      {why || note ? <span className="fa-why" role="status">{why || note}</span> : null}
      {onCancel ? <button type="button" className="fa-btn o" onClick={onCancel}>{t("Cancel")}</button>
        : ctx?.inModal ? <button type="button" className="fa-btn o" onClick={ctx.close}>{t("Cancel")}</button>
          : <a className="fa-btn o" href={cancelHref}>{t("Cancel")}</a>}
      {extra}
      <button type="submit" className="fa-btn p" aria-disabled={!!why || processing} disabled={processing}>{processing ? t("Saving…") : submitLabel}</button>
    </div>
  );
}

// A whole form in the approved layout: the title in the modal header, a
// two-column field grid, then whatever the form adds below it.
export function FormA({ title, onSubmit, error, children }) {
  return (
    <div className="fa-form">
      <FormHeader title={title} />
      <form method="post" onSubmit={onSubmit} noValidate>
        {error ? <div className="fa-alert fa-alert-top" role="alert">{error}</div> : null}
        {children}
      </form>
    </div>
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
      <DialogContent className="sm:max-w-3xl form-modal-content" showCloseButton={false}>
        <div className="hms-modal-head">
          <div style={{ minWidth: 0 }}><DialogTitle className="hms-modal-title">{title}</DialogTitle></div>
          <DialogCloseButton />
        </div>
        <div className="hms-modal-body"><div className="fa-form">{children}</div></div>
      </DialogContent>
    </Dialog>
  );
}
