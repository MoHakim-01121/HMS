import { useState, useEffect, isValidElement } from "react";
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

function classify(col, row) {
  const cls = typeof col.className === "function" ? col.className(row) : col.className;
  if (!cls) return "meta";
  if (cls.includes("col-m-primary")) return "primary";
  if (cls.includes("col-m-badge")) return "badge";
  if (cls.includes("col-m-secondary")) return "secondary";
  if (cls.includes("col-m-meta")) return "meta";
  if (cls.includes("col-m-amount")) return "amount";
  if (cls.includes("col-m-actions")) return "actions";
  if (cls.includes("col-m-hide")) return "hide";
  return "meta";
}

// Mobile cards can render one badge as a colored ticket-stub instead of an
// inline pill (opt-in via the `mobileStub` prop) — read its semantic color
// straight off the element so existing badge markup (<span className="badge
// badge-green">, <StatusPill tone="green" label=.../>) works without
// changes. Anything unrecognized (a count, a currency code, 2+ badges)
// falls back to showing inline.
// Roles whose content is "label ... value" within a single column (Total,
// or Hotel+dates) need justify-content:space-between at the per-column
// level too, not just across columns. Give that inner span a bare spread
// helper instead of the full role class — reusing the role class on both
// the outer row and the inner span double-applies its margin/border/padding,
// which is what made the amount row's dashed divider render twice.
const SPREAD_ROLES = new Set(["meta", "amount"]);

function extractStub(node) {
  if (!isValidElement(node)) return null;
  const { tone, label, className, children } = node.props || {};
  if (tone && typeof label === "string") return { tone, label };
  if (typeof className === "string" && typeof children === "string") {
    const m = /badge-(green|red|yellow|blue|gray)\b/.exec(className);
    if (m) return { tone: m[1], label: children };
  }
  return null;
}

// `mobileStub`: opt-in ticket-stub treatment for the mobile card list (a
// colored strip carries the row's status, read off its badge column). Off
// by default — every list gets the plain rounded card; CL passes this prop
// explicitly since it's the one page this was designed for.
export default function Table({ columns, rows, rowKey, onRowClick, empty, footer, bulkActions, mobileStub }) {
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

  /* ── Mobile card list ─────────────────────────────────────────────────── */
  if (isMobile) {
    return (
      <div className="m-card-list">
        {rows.length ? rows.map((row, i) => {
          const key = rowKey(row, i);
          const primary = [];
          const badgeRaw = [];
          const secondary = [];
          const meta = [];
          const amount = [];
          let actions = null;

          columns.forEach((col, ci) => {
            const role = classify(col, row);
            const content = col.render(row, i);
            if (role === "hide") return;
            if (role === "actions") { actions = content; return; }
            if (role === "badge") { badgeRaw.push(content); return; }
            const item = SPREAD_ROLES.has(role)
              ? <span key={ci} className="m-card-row">{content}</span>
              : <span key={ci}>{content}</span>;
            if (role === "primary") primary.push(item);
            else if (role === "secondary") secondary.push(item);
            else if (role === "amount") amount.push(item);
            else meta.push(item);
          });

          const stub = mobileStub && badgeRaw.length === 1 ? extractStub(badgeRaw[0]) : null;
          const inlineBadges = stub ? [] : badgeRaw;

          return (
            <div
              key={key}
              className={"m-card" + (stub ? "" : " m-card--no-stub")}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              role={onRowClick ? "button" : undefined}
              tabIndex={onRowClick ? 0 : undefined}
              onKeyDown={onRowClick ? (e) => {
                if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRowClick(row); }
              } : undefined}
            >
              {stub && (
                <div className={`m-card-stub st-${stub.tone}`}>
                  <span className="m-card-stub-label">{stub.label}</span>
                </div>
              )}
              <div className="m-card-main">
                <div className="m-card-head">
                  <div className="m-card-primary">{primary}</div>
                  {inlineBadges.length > 0 && <div className="m-card-badge">{inlineBadges.map((b, bi) => <span key={bi}>{b}</span>)}</div>}
                  {actions && <div className="m-card-actions" onClick={(e) => e.stopPropagation()}>{actions}</div>}
                </div>
                {secondary.length > 0 && <div className="m-card-secondary">{secondary}</div>}
                {meta.length > 0 && <div className="m-card-meta">{meta}</div>}
                {amount.length > 0 && <div className="m-card-amount">{amount}</div>}
              </div>
            </div>
          );
        }) : (
          <div className="m-card-empty">{empty || t("No data")}</div>
        )}
      </div>
    );
  }

  /* ── Desktop table ────────────────────────────────────────────────────── */
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
              const staticColClassName = typeof col.className === "function" ? null : col.className;
              return (
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
