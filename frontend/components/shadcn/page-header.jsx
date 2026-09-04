import { useI18n } from "../../utils/i18n.jsx";

// Canonical list-page header (Homlu direction) — replaces the legacy
// `.page-header` / `.page-title` / `.page-sub` / `.page-actions` block from
// design.css. Token-driven (--foreground/--muted-foreground, cssvar radius),
// so it reads as the same system as the shadcn Table/KPI row it sits above.
// `title` and `sub` are already-translated nodes/strings (callers own the
// `useI18n` call so interpolations like "{count}" resolve correctly).
// Rollout target: every list page (Invoice, Client, Remittance, ...).
export default function PageHeader({ title, sub, actions }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        gap: 16,
        marginBottom: 24,
        flexWrap: "wrap",
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 21, fontWeight: 600, letterSpacing: "-.02em", lineHeight: 1.15, color: "var(--foreground)" }}>
          {title}
        </div>
        {sub && (
          <div style={{ fontSize: 12.5, color: "var(--muted-foreground)", marginTop: 4, lineHeight: 1.5 }}>
            {sub}
          </div>
        )}
      </div>
      {actions && (
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          {actions}
        </div>
      )}
    </div>
  );
}