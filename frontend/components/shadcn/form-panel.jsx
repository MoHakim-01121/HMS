export default function FormPanel({ children }) {
  return (
    <div style={{ background: "var(--secondary)", border: "1px solid var(--border)", borderRadius: 16, padding: 24, display: "flex", flexDirection: "column", gap: 24 }}>
      {children}
    </div>
  );
}
