import {
  Table as ShadcnTable,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/table.jsx";

// shadcn Table-primitive rebuild of ../ui/Table.jsx — same props and logic
// (keyboard-accessible rows, data-label mobile collapse, function-or-string
// column className, optional footer). Only the raw <table>/<tr>/<td>
// elements are swapped for their shadcn equivalents.
export default function Table({ columns, rows, rowKey, onRowClick, empty, footer }) {
  return (
    <div className="table-wrap">
      <ShadcnTable>
        <TableHeader>
          <TableRow>
            {columns.map((col, i) => (
              <TableHead key={i} className={col.headerClassName} style={col.headerStyle}>{col.header}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.length ? rows.map((row, i) => (
            <TableRow
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
                  <TableCell key={ci} className={cls} style={col.style} data-label={col.header || undefined}>{col.render(row, i)}</TableCell>
                );
              })}
            </TableRow>
          )) : (
            <TableRow>
              <TableCell colSpan={columns.length} style={{ textAlign: "center", color: "var(--muted-foreground)", padding: 20 }}>
                {empty || "No data"}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
        {footer && <TableFooter>{footer}</TableFooter>}
      </ShadcnTable>
    </div>
  );
}
