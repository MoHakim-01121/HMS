import { useState } from "react";
import {
  Table as ShadcnTable,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/table.jsx";
import { Checkbox } from "./ui/checkbox.jsx";
import { Button } from "./ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// shadcn Table-primitive rebuild of ../ui/Table.jsx — same props and logic
// (keyboard-accessible rows, data-label mobile collapse, function-or-string
// column className, optional footer). Only the raw <table>/<tr>/<td>
// elements are swapped for their shadcn equivalents.
//
// `bulkActions` is additive and opt-in: pass an array of
// { label, onClick(selectedRows, clearSelection), variant } to turn on the
// checkbox column + a floating bottom bulk-action bar (Workbench direction,
// sourced from 21st's Leads Data Table pattern). Omitting it keeps every
// existing call site byte-for-byte identical to before.
//
// The list-table skin (`.hms-table-v2`, styled in styles/tailwind.css) follows
// 21st.dev's HeroUI v3 Table: a tinted header strip with the body as a lighter
// "sheet" in front of it. It is a pure restyle — the props and markup below are
// unchanged, so every call site keeps working as-is.
//
// `col.hoverReveal: true` on a column opts that cell's content into
// hover-only visibility (desktop pointer devices only — `@media (hover:
// hover)` in tailwind.css keeps it always-visible on touch, since there is
// no hover gesture to reveal it there).
export default function Table({ columns, rows, rowKey, onRowClick, empty, footer, bulkActions }) {
  const { t } = useI18n();
  const [selected, setSelected] = useState(() => new Set());
  const selectable = !!bulkActions?.length;

  const toggleOne = (key) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };
  const toggleAll = () => {
    setSelected((prev) => (prev.size === rows.length ? new Set() : new Set(rows.map((r, i) => rowKey(r, i)))));
  };
  const clearSelection = () => setSelected(new Set());
  const selectedRows = rows.filter((r, i) => selected.has(rowKey(r, i)));

  return (
    <div className="table-wrap hms-table-v2">
      <ShadcnTable>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {selectable && (
              <TableHead className="hms-th-select" style={{ width: 36 }}>
                <Checkbox
                  checked={rows.length > 0 && selected.size === rows.length}
                  onCheckedChange={toggleAll}
                  aria-label={t("Select all rows")}
                />
              </TableHead>
            )}
            {columns.map((col, i) => {
              // Responsive column classes (col-mobile-only, col-m-hide, …)
              // are what decide whether a column exists at a given
              // breakpoint. They must land on the <th> too, or a column
              // hidden on the body shifts every header out of sync with its
              // data — only skip them when className is per-row (a
              // function), since a header has no row to evaluate against.
              const staticColClassName = typeof col.className === "function" ? null : col.className;
              return (
                // Label-less columns (the trailing row-actions one) skip the
                // header's column separator — a rule with nothing beside it
                // reads as a stray mark.
                <TableHead
                  key={i}
                  className={[staticColClassName, col.headerClassName, col.header ? null : "hms-th-blank"].filter(Boolean).join(" ") || undefined}
                  style={col.headerStyle}
                >
                  {col.header}
                </TableHead>
              );
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.length ? rows.map((row, i) => {
            const key = rowKey(row, i);
            return (
              <TableRow
                key={key}
                style={onRowClick ? { cursor: "pointer" } : undefined}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                onKeyDown={onRowClick ? (e) => {
                  if (e.target !== e.currentTarget) return;
                  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRowClick(row); }
                } : undefined}
              >
                {selectable && (
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Checkbox checked={selected.has(key)} onCheckedChange={() => toggleOne(key)} aria-label={t("Select row")} />
                  </TableCell>
                )}
                {columns.map((col, ci) => {
                  const cls = typeof col.className === "function" ? col.className(row) : col.className;
                  const content = col.render(row, i);
                  return (
                    <TableCell key={ci} className={cls} style={col.style} data-label={col.header || undefined}>
                      {col.hoverReveal ? <span className="hms-row-reveal">{content}</span> : content}
                    </TableCell>
                  );
                })}
              </TableRow>
            );
          }) : (
            <TableRow>
              <TableCell colSpan={columns.length + (selectable ? 1 : 0)} style={{ textAlign: "center", color: "var(--muted-foreground)", padding: 20 }}>
                {empty || t("No data")}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
        {footer && <TableFooter>{footer}</TableFooter>}
      </ShadcnTable>

      {selectable && selected.size > 0 && (
        <div className="hms-bulk-bar" role="toolbar">
          <span className="hms-bulk-count">{t("{count} selected", { count: selected.size })}</span>
          <div className="hms-bulk-actions">
            {bulkActions.map((a, i) => (
              <Button key={i} size="sm" variant={a.variant || "outline"} onClick={() => a.onClick(selectedRows, clearSelection)}>
                {a.label}
              </Button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
