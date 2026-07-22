// Token-restyled rebuild of ../detail/FloatCard.jsx — same props.
export default function FloatCard({ children, right }) {
  return (
    <div style={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 16, padding: 20, marginTop: -32, position: "relative", display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
      <div style={{ flex: 1, minWidth: 200 }}>{children}</div>
      {right}
    </div>
  );
}
