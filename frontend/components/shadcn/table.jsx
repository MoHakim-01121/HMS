import { useState, useEffect, Fragment } from "react";
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
import { cn } from "@/lib/utils";
import { useI18n } from "../../utils/i18n.jsx";

function useIsMobile(bp = 600) {
  const [m, setM] = useState(() => typeof window !== "undefined" && window.innerWidth <= bp);
  useEffect(() => {
    const mq = window.matchMedia(`(max-width:${bp}px)`);
    const fn = (e) => setM(e.matches);
    mq.addEventListener("change", fn);
    setM(mq.matches);
    return () => mq.removeEventListener("change", fn);
  }, [bp]);
  return m;
}

// Where a column goes in the mobile card: `mobile` on the column is one of
// primary | badge | secondary | meta | amount | actions | hide (default meta).
// Actions are dropped on mobile: the whole card is the tap target.
const ROLES = new Set(["primary", "badge", "secondary", "meta", "amount", "actions", "hide"]);
const roleOf = (col) => (ROLES.has(col.mobile) ? col.mobile : "meta");

// Roles whose content is "label ... value" within a single column (Total,
// or Hotel+dates) spread that column's own children apart too.
const SPREAD_ROLES = new Set(["meta", "amount"]);

// Uppercase band that opens a group (the `section` prop), in both layouts.
const BAND = "text-[11px] font-semibold tracking-[.08em] uppercase text-muted-foreground";

// `framed`: draw the white card surface around the table (list pages that
// have no card of their own).
//
// `section`: optional row => label. When the label changes between rows a
// grouping band opens the new section — a full-width muted row above the
// table (a card-list header on mobile) — for lists grouped by a key such as
// the Trial Balance's account type. The label may be a string or a node.
export default function Table({ columns, rows, rowKey, onRowClick, empty, footer, bulkActions, section, framed }) {
  const { t } = useI18n();
  const isMobile = useIsMobile();
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

  const frame = (node) => (framed ? <div className="overflow-hidden rounded-card border border-border bg-card">{node}</div> : node);

  /* ── Mobile card list ─────────────────────────────────────────────────── */
  if (isMobile) {
    let lastSection;
    return frame(
      <div className="flex flex-col overflow-hidden rounded-card border border-border bg-card">
        {rows.length ? rows.map((row, i) => {
          const key = rowKey(row, i);
          const primary = [];
          const badges = [];
          const secondary = [];
          const meta = [];
          const amount = [];

          columns.forEach((col, ci) => {
            const role = roleOf(col);
            if (role === "hide" || role === "actions") return;
            const content = col.render(row, i);
            if (role === "badge") { badges.push(<span key={ci}>{content}</span>); return; }
            const item = SPREAD_ROLES.has(role)
              ? <span key={ci} className="flex min-w-0 flex-auto items-center justify-between gap-2">{content}</span>
              : <span key={ci}>{content}</span>;
            if (role === "primary") primary.push(item);
            else if (role === "secondary") secondary.push(item);
            else if (role === "amount") amount.push(item);
            else meta.push(item);
          });

          const sec = section ? section(row, i) : null;
          const showSection = sec != null && sec !== lastSection;
          lastSection = sec;

          return (
            <Fragment key={key}>
              {showSection && <div className={cn("border-b border-hairline px-[15px] pt-[14px] pb-[6px]", BAND)}>{sec}</div>}
              <div
                className="flex cursor-pointer flex-col overflow-hidden border-b border-hairline last:border-b-0 active:bg-secondary"
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                role={onRowClick ? "button" : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                onKeyDown={onRowClick ? (e) => {
                  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRowClick(row); }
                } : undefined}
              >
                <div className="flex min-w-0 flex-col gap-2 px-[15px] py-[13px]">
                  <div className="flex min-h-[22px] items-center justify-between gap-[10px]">
                    <div className="min-w-0 flex-[1_1_0%] truncate text-[13.5px] leading-[1.3] font-semibold tracking-[-0.01em] text-foreground">{primary}</div>
                    {badges.length > 0 && <div className="flex flex-none items-center gap-1">{badges}</div>}
                  </div>
                  {secondary.length > 0 && <div className="truncate text-[13px] leading-[1.4] font-medium text-foreground">{secondary}</div>}
                  {meta.length > 0 && <div className="flex items-center justify-between gap-2 text-[11.5px] leading-[1.4] text-muted-foreground">{meta}</div>}
                  {amount.length > 0 && (
                    <div className="mt-px flex items-end justify-between gap-3 border-t border-hairline pt-[9px] text-[15px] font-semibold text-foreground tabular-nums">{amount}</div>
                  )}
                </div>
              </div>
            </Fragment>
          );
        }) : (
          <div className="px-4 py-8 text-center text-[13px] text-muted-foreground">{empty || t("No data")}</div>
        )}
      </div>
    );
  }

  /* ── Desktop table ────────────────────────────────────────────────────── */
  // The "ledger" skin: one hairline under the header, hairlines between body
  // rows (on the <td>s — a <tr> draws no border in the separate-borders
  // model), a firmer --input rule over group bands and the total row.
  const head = "px-3 [&:has([role=checkbox])]:pr-3 py-[10px] text-[11.5px] font-semibold text-foreground bg-transparent border-b border-b-hairline";
  const cell = "p-3 [&:has([role=checkbox])]:pr-3 text-[13px] font-normal bg-card border-t border-t-hairline border-b border-b-border";
  const rowHover = "[&:hover>td]:bg-accent [&:hover>td:first-child]:rounded-l-[6px] [&:hover>td:last-child]:rounded-r-[6px]";
  let lastSection;
  return frame(
    <div className="overflow-x-auto">
      <ShadcnTable className="border-separate border-spacing-0">
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {selectable && (
              <TableHead className={cn(head, "w-9")}>
                <Checkbox
                  checked={rows.length > 0 && selected.size === rows.length}
                  onCheckedChange={toggleAll}
                  aria-label={t("Select all rows")}
                />
              </TableHead>
            )}
            {columns.map((col, i) => {
              const staticColClassName = typeof col.className === "function" ? null : col.className;
              return (
                <TableHead
                  key={i}
                  className={cn(head, staticColClassName, col.headerClassName)}
                  // A column that aligns its cells (style.textAlign) aligns its
                  // header the same way unless it says otherwise.
                  style={col.headerStyle ?? (col.style?.textAlign ? { textAlign: col.style.textAlign } : undefined)}
                >
                  {col.header}
                </TableHead>
              );
            })}
          </TableRow>
        </TableHeader>
        <TableBody className="[&>tr:first-child>td]:border-t-0 [&>tr:last-child>td]:border-b-0">
          {rows.length ? rows.map((row, i) => {
            const key = rowKey(row, i);
            const sec = section ? section(row, i) : null;
            const showSection = sec != null && sec !== lastSection;
            lastSection = sec;
            return (
              <Fragment key={key}>
                {showSection && (
                  <TableRow>
                    <TableCell colSpan={columns.length + (selectable ? 1 : 0)} className={cn(cell, "border-t-input pt-[15px] pb-[5px]", BAND)}>{sec}</TableCell>
                  </TableRow>
                )}
                <TableRow
                  className={cn(rowHover, onRowClick && "cursor-pointer")}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  tabIndex={onRowClick ? 0 : undefined}
                  onKeyDown={onRowClick ? (e) => {
                    if (e.target !== e.currentTarget) return;
                    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRowClick(row); }
                  } : undefined}
                >
                  {selectable && (
                    <TableCell className={cell} onClick={(e) => e.stopPropagation()}>
                      <Checkbox checked={selected.has(key)} onCheckedChange={() => toggleOne(key)} aria-label={t("Select row")} />
                    </TableCell>
                  )}
                  {columns.map((col, ci) => {
                    const cls = typeof col.className === "function" ? col.className(row) : col.className;
                    return (
                      <TableCell key={ci} className={cn(cell, cls)} style={col.style} data-label={col.header || undefined}>
                        {col.render(row, i)}
                      </TableCell>
                    );
                  })}
                </TableRow>
              </Fragment>
            );
          }) : (
            <TableRow className={rowHover}>
              <TableCell colSpan={columns.length + (selectable ? 1 : 0)} className={cn(cell, "p-5 text-center text-muted-foreground")}>
                {empty || t("No data")}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
        {footer && <TableFooter className="[&_td]:border-t [&_td]:border-t-input [&_td]:bg-card [&_td]:p-3 [&_td]:text-[14px] [&_td]:font-semibold">{footer}</TableFooter>}
      </ShadcnTable>

      {selectable && selected.size > 0 && (
        <div
          role="toolbar"
          className="fixed bottom-6 left-1/2 z-[300] flex -translate-x-1/2 animate-rise-in items-center gap-[14px] rounded-2xl border border-border bg-popover px-4 py-[10px] shadow-menu max-[600px]:bottom-[calc(72px+env(safe-area-inset-bottom))]"
        >
          <span className="font-mono text-[12px] whitespace-nowrap text-muted-foreground">{t("{count} selected", { count: selected.size })}</span>
          <div className="flex gap-2">
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
