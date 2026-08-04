// Line-item table for detail pages, from 21st.dev "Invoice History Table"
// (@cnippet.dev, demo 22187): muted header row, per-row status badge, and a
// footer that carries the total / outstanding figure.
//
//   columns: [{ header, render(row, i), align: "right", strong, className, width }]
//   footer:  [{ label, value, total, tone: "green"|"red" }] — falsy entries ok
//
// `value` (and `tone`) may be an array to close several numeric columns at
// once, e.g. a Total + Remaining pair. Each entry takes one column from the
// right, so the label always lands immediately left of the first figure.
//
// Mobile collapse (tailwind.css) drops the header row and pairs each cell with
// its own column label, so `header` doubles as the mobile label; pass an empty
// string for columns that should stay unlabelled there.
import { useI18n } from "../../utils/i18n.jsx";

export default function DetailTable({ columns, rows, rowKey, empty, footer }) {
  const { t } = useI18n();
  const cols = columns.filter(Boolean);
  const foot = (footer || []).filter(Boolean);
  const cellClass = (c) =>
    [c.align === "right" ? "num" : "", c.strong ? "strong" : "", c.className || ""].filter(Boolean).join(" ") || undefined;
  const toneColor = (t) => (t === "green" ? "var(--green)" : t === "red" ? "var(--red)" : undefined);

  return (
    <div className="hms-dv-table-wrap">
      <table className="hms-dv-table">
        <thead>
          <tr>
            {cols.map((c, i) => (
              <th key={i} style={{ textAlign: c.align === "right" ? "right" : undefined, width: c.width }}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((row, i) => (
              <tr key={rowKey ? rowKey(row, i) : i}>
                {cols.map((c, ci) => (
                  <td key={ci} data-label={c.header || ""} className={cellClass(c)}>
                    {c.render(row, i)}
                  </td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={cols.length} className="hms-dv-empty hms-dv-empty-cell" style={{ borderBottom: "none" }}>
                {empty || t("No data")}
              </td>
            </tr>
          )}
        </tbody>
        {foot.length ? (
          <tfoot>
            {foot.map((f, i) => {
              const vals = Array.isArray(f.value) ? f.value : [f.value];
              const tones = Array.isArray(f.tone) ? f.tone : [f.tone];
              // The label sits immediately left of its figures — spanning it
              // from column 1 instead left it orphaned across the table's whole
              // width. The spacer keeps the hairline running edge to edge;
              // mobile hides it, since the footer collapses to a flex row.
              const spacer = cols.length - vals.length - 1;
              return (
                <tr key={i} className={[f.total ? "total" : "", vals.length > 1 ? "multi" : ""].filter(Boolean).join(" ") || undefined}>
                  {spacer > 0 ? <td className="pad" colSpan={spacer} /> : null}
                  <td className="lbl">{f.label}</td>
                  {vals.map((v, vi) => (
                    <td
                      key={vi}
                      className="num val"
                      data-label={cols[cols.length - vals.length + vi]?.header || ""}
                      style={{ color: toneColor(tones[vi]) }}
                    >
                      {v}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tfoot>
        ) : null}
      </table>
    </div>
  );
}
