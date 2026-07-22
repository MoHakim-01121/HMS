export default function FormHeader({ kicker, title, sub }) {
  return (
    <div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, textTransform: "uppercase", letterSpacing: 1, color: "var(--muted-foreground)" }}>{kicker}</div>
      <div style={{ fontFamily: "var(--font-display)", fontSize: 24, fontWeight: 600, marginTop: 3 }}>{title}</div>
      {sub && <div style={{ fontSize: 13, color: "var(--muted-foreground)", marginTop: 4 }}>{sub}</div>}
    </div>
  );
}
