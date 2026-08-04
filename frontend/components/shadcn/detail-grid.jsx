import { Icon } from "../icons.jsx";

// Meta grid of the detail card — the icon / label / value cluster from
// 21st.dev "Project Detail View" (@kavikatiyar, demo 8248).
//
// Same `rows` contract as before (falsy entries allowed so call sites keep
// their `condition && {...}` shape, `span2` still spans the full width) plus
// an optional `icon` per row, taking any name from components/icons.jsx.
// The old `wide` flag is gone: the grid is a fixed two columns now, so a value
// that used to need two of four tracks already has the room.
// Labels are plain sentence case now — the mono-uppercase 10px label was a
// leftover of the retired Terminal direction.
export default function DetailGrid({ rows, right }) {
  const items = rows.filter(Boolean);
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 20, flexWrap: "wrap" }}>
      <div className="hms-dv-meta" style={{ flex: 1, minWidth: 240 }}>
        {items.map((r, i) => (
          <div key={i} className={"hms-dv-meta-item" + (r.span2 ? " span2" : "")}>
            {r.icon ? (
              <span className="hms-dv-mico" aria-hidden="true"><Icon name={r.icon} size={14} strokeWidth={1.8} /></span>
            ) : null}
            <div style={{ minWidth: 0 }}>
              <div className="hms-dv-mlabel">{r.label}</div>
              <div
                className="hms-dv-mval"
                style={{ color: r.color || undefined, whiteSpace: r.pre ? "pre-wrap" : undefined }}
              >
                {r.value}
              </div>
            </div>
          </div>
        ))}
      </div>
      {right ? <div style={{ paddingTop: 22 }}>{right}</div> : null}
    </div>
  );
}
