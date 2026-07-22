export default function Table({ columns, rows, rowKey, onRowClick, empty, footer }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((col, i) => (
              <th key={i} className={col.headerClassName} style={col.headerStyle}>{col.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length ? rows.map((row, i) => (
            <tr
              key={rowKey(row, i)}
              style={onRowClick ? { cursor: "pointer" } : undefined}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              tabIndex={onRowClick ? 0 : undefined}
              onKeyDown={onRowClick ? (e) => {
                if (e.target !== e.currentTarget) return;
                if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRowClick(row); }
              } : undefined}
            >
              {columns.map((col, ci) => {
                const cls = typeof col.className === "function" ? col.className(row) : col.className;
                return (
                  <td key={ci} className={cls} style={col.style} data-label={col.header || undefined}>{col.render(row, i)}</td>
                );
              })}
            </tr>
          )) : (
            <tr>
              <td colSpan={columns.length} style={{ textAlign: "center", color: "var(--text-3)", padding: 20 }}>
                {empty || "No data"}
              </td>
            </tr>
          )}
        </tbody>
        {footer && <tfoot>{footer}</tfoot>}
      </table>
    </div>
  );
}
