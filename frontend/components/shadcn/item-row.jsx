// Simple name / sub / amount row, for line-item groups too small to deserve a
// full DetailTable header. Same props and the same named DvLink export as
// before; restyled to the detail card's type scale (plain labels, tabular
// numbers) and no longer tinting amounts gold.
//
// DvLink is the inline "jump to the related record" affordance (CL, INV,
// Proof). It reads as a small outlined chip rather than a colored link, since
// the Homlu direction keeps color for status only.
export function DvLink({ href, newTab, children }) {
  return (
    <a
      className="hms-dv-act"
      style={{ padding: "1px 7px", fontSize: 11.5, marginLeft: 7, gap: 4, verticalAlign: "middle" }}
      href={href}
      target={newTab ? "_blank" : undefined}
      rel={newTab ? "noreferrer" : undefined}
    >
      {children}
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
        <path d="M15 3h6v6" />
        <path d="M10 14L21 3" />
      </svg>
    </a>
  );
}

const AMOUNT_COLOR = { red: "var(--red)", green: "var(--green)" };

export default function ItemRow({ name, link, sub, amount, amountSub, amountColor, small }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 14, padding: "11px 0", borderBottom: "1px solid var(--border)" }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 500, fontSize: small ? 13 : 13.5 }}>{name}{link}</div>
        {sub ? <div style={{ fontSize: 12, color: "var(--muted-foreground)", marginTop: 3, lineHeight: 1.5 }}>{sub}</div> : null}
      </div>
      {amount != null ? (
        <div
          style={{
            fontWeight: 500, fontSize: small ? 13 : 13.5, textAlign: "right", flexShrink: 0,
            fontVariantNumeric: "tabular-nums",
            color: amountColor ? AMOUNT_COLOR[amountColor] : undefined,
          }}
        >
          {amount}
          {amountSub}
        </div>
      ) : null}
    </div>
  );
}
