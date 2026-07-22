// Token-restyled rebuild of ../detail/Section.jsx — same props.
export default function Section({ label, right, action, children }) {
  const labelStyle = { fontFamily: "var(--font-mono)", fontSize: 11, textTransform: "uppercase", letterSpacing: 1, color: "var(--muted-foreground)" };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 24 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={labelStyle}>{label}</span>
        {action || (right ? <span style={labelStyle}>{right}</span> : null)}
      </div>
      {children}
    </div>
  );
}
