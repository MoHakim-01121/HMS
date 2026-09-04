// Status pill for detail pages — the `pill` shape DetailHero used to take
// ({ label, tone }) is unchanged, so every call site keeps its existing
// heroPill()/riskPill() helpers. Tone maps to the semantic status colors only
// (--green/--yellow/--red); anything else stays monochrome, per the Homlu
// direction where color carries meaning and never brand.
//
// No leading dot: the tint and the label already carry the status, so the dot
// was redundant decoration. The `dot` prop is gone with it.
const TONES = { green: "tone-green", yellow: "tone-yellow", red: "tone-red", blue: "tone-blue", purple: "tone-purple", gray: "tone-gray" };

// Homlu v2.1 badge. Filled by default (document-cycle status); pass
// `outline` for derived tags (currency code, role) and `gray` tone for
// neutral states (Locked, Inactive).
export default function StatusPill({ label, tone, small, outline }) {
  if (!label) return null;
  return (
    <span className={["hms-dv-pill", TONES[tone] || "", outline ? "outline" : "", small ? "sm" : ""].filter(Boolean).join(" ")}>
      {label}
    </span>
  );
}
