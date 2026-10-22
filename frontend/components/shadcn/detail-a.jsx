import { Fragment, useContext, useState } from "react";
import { Link } from "@inertiajs/react";
import { Popover, PopoverTrigger } from "./ui/popover.jsx";
import { FormModalContext } from "./form-modal.jsx";
import { LIcon, Menu, MenuItem, MenuSep } from "./list-a.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import "../../styles/detail-a.css";

// Building blocks of the detail pages on the Record View HMS canvas (row
// "CL, Invoice, Client, Hotel, Payment, Remittance, Client Ledger dan
// Expense"). Every page is the same stack: a back row, an optional status
// strip with its action, the head card (number, status, ⋯ menu, file chips,
// facts), then plain cards of tables. Pages write their own <table
// className="da-t"> so each keeps its columns.

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

export function DPage({ children, className }) {
  return (
    <div className="page shadcn-root">
      <div className={"da-main" + (className ? " " + className : "")}>{children}</div>
    </div>
  );
}

// "← Back" and, on the right, when the record was made. Hidden when the page
// is shown inside the form modal.
export function DTop({ href, stamp }) {
  const { t } = useI18n();
  if (useContext(FormModalContext)?.inModal) return null;
  return (
    <div className="da-top">
      <Link href={href} className="da-back">{DIcon.back}{t("Back")}</Link>
      {stamp ? <span>{stamp}</span> : null}
    </div>
  );
}

// The strip above the head card: one sentence and the actions it asks for.
export function DBanner({ tone = "warning", children, actions }) {
  return (
    <div role="status" className={"da-banner " + tone}>
      <span className="da-banner-t">{children}</span>
      {actions ? <span className="da-banner-a">{actions}</span> : null}
    </div>
  );
}

export function DBtn({ primary, children, ...rest }) {
  const cls = "da-btn" + (primary ? " primary" : "");
  if (rest.href) return <a className={cls} {...rest}>{children}</a>;
  return <button type="button" className={cls} {...rest}>{children}</button>;
}

export const DPill = ({ tone = "gray", sm, children }) => <span className={"da-pill " + tone + (sm ? " sm" : "")}>{children}</span>;

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
        <button type="button" className={"da-dots" + (small ? " sm" : "")} aria-label={label || t("Actions")} aria-haspopup="menu">{LIcon.dots}</button>
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
    <a className={"da-chip" + (small ? " sm" : "")} href={href} target="_blank" rel="noreferrer" aria-label={label}>
      {DIcon[icon]}{children}
    </a>
  );
}

// facts: [{ k, v, tone: "danger"|"warning"|"success", strong }]; falsy drop.
// cols: a fixed column count (the design uses 3 or 4), else auto-fit.
export function DFacts({ facts, cols }) {
  const list = (facts || []).filter(Boolean);
  if (!list.length) return null;
  return (
    <dl className={"da-facts" + (cols ? " c" + cols : "")}>
      {list.map((f) => (
        <div key={f.k}>
          <dt>{f.k}</dt>
          <dd className={[f.tone, f.strong ? "strong" : ""].filter(Boolean).join(" ") || undefined}>{f.v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function DHead({ title, badge, menu, chips, facts, cols, note, children }) {
  const { t } = useI18n();
  return (
    <section className="da-card da-head">
      <div className="da-head-top">
        <div className="da-head-id">
          <h1>{title}</h1>
          {badge ? <DPill tone={badge.tone}>{badge.label}</DPill> : null}
        </div>
        {menu ? <DMenu items={menu} /> : null}
      </div>
      {chips && chips.filter(Boolean).length ? <div className="da-chips">{chips}</div> : null}
      <DFacts facts={facts} cols={cols} />
      {children}
      {note ? (
        <div className="da-note">
          <div className="k">{note.label || t("Note")}</div>
          <p>{note.text}</p>
        </div>
      ) : null}
    </section>
  );
}

export function DCard({ title, count, meta, sub, actions, children, className, pad }) {
  return (
    <section className={"da-card" + (pad ? " pad" : "") + (className ? " " + className : "")}>
      {title || meta || actions ? (
        <div className="da-card-h">
          <h2>{title}{count != null ? <span className="c">{count}</span> : null}</h2>
          {meta ? <span className="meta">{meta}</span> : null}
          {actions ? <span className="acts">{actions}</span> : null}
        </div>
      ) : null}
      {sub ? <p className="da-card-sub">{sub}</p> : null}
      {children}
    </section>
  );
}

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
    <div className={"da-tabbar" + (tall ? " tall" : "")}>
      <div role="tablist" aria-label={label} className="da-tabs" onKeyDown={onKey}>
        {tabs.map((x) => (
          <button key={x.key} type="button" role="tab" aria-selected={x.key === value} tabIndex={x.key === value ? 0 : -1}
            className={"da-tab" + (x.key === value ? " on" : "")} onClick={() => onChange(x.key)}>
            {x.label}{x.count ? <span className="c">{x.count}</span> : null}
          </button>
        ))}
      </div>
      {tools ? <div className="da-tools">{tools}</div> : null}
    </div>
  );
}

// Activity rows: [{ key, when, body, by }].
export function DLog({ rows, wide, empty }) {
  if (!rows.length) return <div className="da-empty">{empty}</div>;
  return (
    <div className={"da-log" + (wide ? " wide" : "")}>
      {rows.map((r) => (
        <div key={r.key} className="da-log-r">
          <span className="w">{r.when}</span>
          <span>{r.body}{r.by ? <span className="by"> · {r.by}</span> : null}</span>
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
