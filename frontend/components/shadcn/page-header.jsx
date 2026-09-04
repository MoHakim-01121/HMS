// Canonical list-page header (Homlu v2.1) — replaces the legacy
// `.page-header` / `.page-title` / `.page-sub` / `.page-actions` block from
// design.css. `title` and `sub` are already-translated nodes/strings.
// See the .hms-ph-* rules in tailwind.css (incl. the mobile treatment:
// 18px title, actions hidden, per doc 02d).
export default function PageHeader({ title, sub, actions }) {
  return (
    <div className="hms-ph">
      <div className="hms-ph-text">
        <div className="hms-ph-title">{title}</div>
        {sub && <div className="hms-ph-sub">{sub}</div>}
      </div>
      {actions && <div className="hms-ph-actions">{actions}</div>}
    </div>
  );
}
