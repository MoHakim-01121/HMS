// Token-restyled rebuild of ../detail/FooterSummary.jsx — same props.
export default function FooterSummary({ left, right }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, marginTop: 24, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
      <div style={{ flex: 1 }}>{left}</div>
      <div style={{ textAlign: "right" }}>{right}</div>
    </div>
  );
}
