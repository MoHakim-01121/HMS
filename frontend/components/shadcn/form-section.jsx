export default function FormSection({ label, sub, children }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {label && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, textTransform: "uppercase", letterSpacing: 1, color: "var(--muted-foreground)" }}>
          {label}
          {sub && <span style={{ textTransform: "none", letterSpacing: 0, marginLeft: 6, fontWeight: 400 }}>{sub}</span>}
        </div>
      )}
      {children}
    </div>
  );
}
