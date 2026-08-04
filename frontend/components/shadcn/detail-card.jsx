import KebabMenu from "./kebab-menu.jsx";
import StatusPill from "./status-pill.jsx";

// Detail page shell, adapted from 21st.dev "Project Detail View"
// (@kavikatiyar, demo 8248): one card holding a muted header strip
// (breadcrumb left, actions right), a large plain title with the status pill
// beside it, then the page body (meta grid + line-item sections).
//
// Replaces detail-hero.jsx, whose gold inverted panel and mono-uppercase
// kicker predate the Homlu direction. Props are a superset of that
// component's (`kicker`/`title`/`sub`/`pill`/`menuItems`) plus:
//   crumbs  — extra breadcrumb hops rendered before `kicker`, [{label, href}]
//   actions — nodes placed left of the kebab in the strip
//   children— the card body
export default function DetailCard({ kicker, crumbs = [], title, sub, pill, menuItems, actions, children }) {
  const trail = [...crumbs, kicker ? { label: kicker } : null].filter(Boolean);
  return (
    <div className="hms-dv-card">
      <div className="hms-dv-strip">
        <div className="hms-dv-crumbs">
          {trail.map((c, i) => (
            <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 7, minWidth: 0 }}>
              {i > 0 ? <span aria-hidden="true">/</span> : null}
              {c.href ? <a href={c.href}>{c.label}</a> : <span>{c.label}</span>}
            </span>
          ))}
        </div>
        <div className="hms-dv-strip-actions">
          {actions}
          <KebabMenu items={menuItems || []} />
        </div>
      </div>

      <div className="hms-dv-head">
        <div style={{ minWidth: 0 }}>
          <h1 className="hms-dv-title">{title}</h1>
          {sub ? <div className="hms-dv-sub">{sub}</div> : null}
        </div>
        {pill ? <StatusPill label={pill.label} tone={pill.tone} /> : null}
      </div>

      <div className="hms-dv-body">{children}</div>
    </div>
  );
}
