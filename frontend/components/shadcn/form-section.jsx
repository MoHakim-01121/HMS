export default function FormSection({ label, sub, action, children }) {
  return (
    <div data-slot="form-section" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {(label || action) && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          {label && (
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--foreground)" }}>
              {label}
              {sub && <span style={{ marginLeft: 6, fontWeight: 400, color: "var(--muted-foreground)" }}>{sub}</span>}
            </div>
          )}
          {action}
        </div>
      )}
      {children}
    </div>
  );
}
