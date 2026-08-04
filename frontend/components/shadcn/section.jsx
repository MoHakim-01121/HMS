import { Icon } from "../icons.jsx";

// Section block inside the detail card. Same props as before (`label`,
// `right`, `action`, `children`) plus optional `icon` and `count`, mirroring
// the reference's "Attachment 2" / "Task List" headings. The label is plain
// 14px semibold now — the mono-uppercase 11px kicker belonged to the retired
// Terminal direction.
export default function Section({ label, icon, count, right, action, children }) {
  return (
    <div className="hms-dv-sec">
      <div className="hms-dv-sech">
        <span className="hms-dv-sec-title">
          {icon ? <Icon name={icon} size={15} strokeWidth={1.8} /> : null}
          {label}
          {count != null ? <span className="hms-dv-count">{count}</span> : null}
        </span>
        {action ? <span className="hms-dv-sec-actions">{action}</span> : right ? <span className="hms-dv-sec-right">{right}</span> : null}
      </div>
      {children}
    </div>
  );
}
