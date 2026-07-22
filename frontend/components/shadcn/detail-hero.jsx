import KebabMenu from "./kebab-menu.jsx";

// Token-restyled rebuild of ../detail/DetailHero.jsx — same props. Uses the
// batch-1 kebab-menu.jsx (DropdownMenu-based) instead of the old KebabMenu.
export default function DetailHero({ kicker, title, sub, pill, menuItems }) {
  return (
    <div style={{ background: "var(--primary)", color: "var(--primary-foreground)", borderRadius: 16, padding: 24, position: "relative" }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <span style={{ fontSize: 12, fontWeight: 600, padding: "2px 10px", borderRadius: 9999, background: "rgba(0,0,0,0.15)" }}>
          {pill ? pill.label : ""}
        </span>
        <KebabMenu items={menuItems} />
      </div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, textTransform: "uppercase", letterSpacing: 1, opacity: 0.8, marginTop: 16 }}>{kicker}</div>
      <div style={{ fontFamily: "var(--font-display)", fontSize: 32, fontWeight: 700, marginTop: 4 }}>{title}</div>
      {sub ? <div style={{ fontSize: 13, opacity: 0.85, marginTop: 4 }}>{sub}</div> : null}
    </div>
  );
}
