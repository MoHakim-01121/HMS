// Token-restyled rebuild of ../detail/ItemRow.jsx — same props and the same
// named DvLink export. amountColor "red"/"green" now map to --destructive/
// --primary (gold) — no new colors outside the approved black/gold/red palette.
export function DvLink({ href, newTab, children }) {
  return (
    <a
      style={{ color: "var(--primary)", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, marginLeft: 6 }}
      href={href} target={newTab ? "_blank" : undefined} rel={newTab ? "noreferrer" : undefined}
    >
      {children}
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
        <path d="M15 3h6v6" />
        <path d="M10 14L21 3" />
      </svg>
    </a>
  );
}

const AMOUNT_COLOR = { red: "var(--destructive)", green: "var(--primary)" };

export default function ItemRow({ name, link, sub, amount, amountSub, amountColor, small }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: small ? 13 : 14 }}>{name}{link}</div>
        {sub ? <div style={{ fontSize: 12, color: "var(--muted-foreground)", marginTop: 2 }}>{sub}</div> : null}
      </div>
      {amount != null ? (
        <div style={{ fontWeight: 600, fontSize: small ? 13 : 14, textAlign: "right", flexShrink: 0, color: amountColor ? (AMOUNT_COLOR[amountColor] || "var(--foreground)") : undefined }}>
          {amount}
          {amountSub}
        </div>
      ) : null}
    </div>
  );
}
