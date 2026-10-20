import { Link } from "@inertiajs/react";
import { useContext } from "react";
import { FormModalContext } from "./form-modal.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// "Record view" — the detail-page layout modeled on the Claude Design mockup
// "03 Detail Pages v2" (project "Konoz United HMS Redesign"). Its rules:
//   - One answer per page: a single hero card states the one thing the reader
//     opened this page to know, everything else is supporting evidence.
//   - One number: a value lives in exactly one place (the hero figure OR a
//     table's total row, never both).
//   - A status badge is always paired with one sentence explaining what it
//     means now and what's blocking the next step (the "note" banner).
//   - One primary (filled) action; the rest are text-height links. Destructive
//     actions are red-outline and always confirm with written consequences.
//   - The right rail (320px) is for things read once in a while — party,
//     dates, attachments, history — as a bordered key/value list, not cards.
//   - Tables carry no decoration: no chips, no per-row icons, no colored
//     rows — right-aligned tabular numbers, a hairline before the sum row.
//   - Exactly one "back" link (no breadcrumb trail); the document number sits
//     above the title as dim mono text, not repeated in a kicker+breadcrumb.

export function RvBack({ href, label, stamp }) {
  const { t } = useI18n();
  if (useContext(FormModalContext)?.inModal) return null;
  return (
    <div className="hms-rv-top">
      <Link href={href} className="hms-rv-backlink">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M15 6l-6 6 6 6" /></svg>
        {t(label)}
      </Link>
      {stamp ? <span className="hms-rv-stamp">{stamp}</span> : null}
    </div>
  );
}

export function RvHero({ kicker, badge, title, facts, mainExtra, side, note, actions, cardStyle }) {
  return (
    <div className="hms-rv-hero" style={cardStyle}>
      <div className="hms-rv-hero-top">
        <div style={{ minWidth: 0 }}>
          <div className="hms-rv-hero-kicker">
            {kicker ? <span className="hms-rv-kicker">{kicker}</span> : null}
            {badge ? <span className={`hms-dv-pill hms-rv-badge tone-${badge.tone || "gray"}`}>{badge.label}</span> : null}
          </div>
          <h1 className="hms-rv-h1">{title}</h1>
          {facts && facts.length ? (
            <div className="hms-rv-facts">
              {facts.map((f, i) => (
                <div key={i}>
                  <div className="hms-rv-lbl">{f.k}</div>
                  <div className="hms-rv-factv">{f.v}</div>
                </div>
              ))}
            </div>
          ) : null}
          {mainExtra}
        </div>
        {side ? <div className="hms-rv-side">{side}</div> : null}
      </div>

      {note ? (
        <div className="hms-rv-notebar">
          <div className="hms-rv-note-l">
            {note.icon ? (
              <span className="hms-rv-note-ico" style={{ background: note.iconBg }}>{note.icon}</span>
            ) : null}
            <div>
              <div className="hms-rv-note-title">{note.title}</div>
              {note.text ? <div className="hms-rv-note-text">{note.text}</div> : null}
            </div>
          </div>
          {actions ? <div className="hms-rv-note-r">{actions}</div> : null}
        </div>
      ) : actions ? (
        <div className="hms-rv-notebar" style={{ justifyContent: "flex-end" }}>
          <div className="hms-rv-note-r">{actions}</div>
        </div>
      ) : null}
    </div>
  );
}

export function RvFigure({ label, value, unit, color, note, bar }) {
  return (
    <div className="hms-rv-figure">
      <div className="hms-rv-lbl">{label}</div>
      <div className="hms-rv-figv" style={color ? { color } : undefined}>
        {value}
        {unit ? <span className="u">{unit}</span> : null}
      </div>
      {bar ? (
        <div className="hms-rv-bar">
          <span style={{ width: bar.pct, background: bar.color || "var(--green)" }} />
        </div>
      ) : null}
      {note ? <div className="hms-rv-fignote">{note}</div> : null}
    </div>
  );
}

export function RvSteps({ steps }) {
  return (
    <div className="hms-rv-steps">
      {steps.map((s, i) => (
        <div key={i} className={`hms-rv-step ${s.state}`}>
          <div className="hms-rv-step-top">
            <span className="hms-rv-step-dot">
              {s.state === "done" ? "✓" : s.state === "halted" ? "✕" : i + 1}
            </span>
            {i < steps.length - 1 ? <span className="hms-rv-step-line" /> : null}
          </div>
          <span className="hms-rv-step-label">{s.label}</span>
        </div>
      ))}
    </div>
  );
}

export function RvPairs({ pairs }) {
  return (
    <div className="hms-rv-pairs">
      {pairs.map((p, i) => (
        <div key={i}>
          <span>{p.k}</span>
          <span className="v" style={p.color ? { color: p.color } : undefined}>{p.v}</span>
        </div>
      ))}
    </div>
  );
}

export function RvCard({ children, style }) {
  return <div className="hms-rv-card" style={style}>{children}</div>;
}

export function RvSection({ title, meta, children, first }) {
  return (
    <div className={first ? "hms-rv-sec first" : "hms-rv-sec"}>
      {(title || meta) && (
        <div className="hms-rv-sech">
          <span className="hms-rv-sec-title">{title}</span>
          {meta ? <span className="hms-rv-sec-meta">{meta}</span> : null}
        </div>
      )}
      {children}
    </div>
  );
}

export function RvRail({ rows, children }) {
  return (
    <div className="hms-rv-railcard">
      {rows && rows.length ? (
        <div className="hms-rv-raillist">
          {rows.map((r, i) => (
            <div key={i} className="hms-rv-railrow">
              <span className="k">{r.k}</span>
              <span className="v" style={r.c ? { color: r.c } : undefined}>
                {r.v}
                {r.s ? <span className="s">{r.s}</span> : null}
              </span>
            </div>
          ))}
        </div>
      ) : null}
      {children}
    </div>
  );
}

export function RvRailBlock({ label, action, children, pin }) {
  return (
    <div className={pin ? "hms-rv-railblock pin" : "hms-rv-railblock"}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <span className="hms-rv-lbl">{label}</span>
        {action}
      </div>
      <div style={{ marginTop: 8 }}>{children}</div>
    </div>
  );
}

export function initials(name) {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "—";
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}
