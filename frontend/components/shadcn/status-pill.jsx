// Status pill for detail pages — the `pill` shape DetailHero used to take
// ({ label, tone }) is unchanged, so every call site keeps its existing
// heroPill()/riskPill() helpers. Tone maps to the semantic status colors only
// (--green/--yellow/--red); anything else stays monochrome, per the Homlu
// direction where color carries meaning and never brand.
//
// No leading dot: the tint and the label already carry the status, so the dot
// was redundant decoration. The `dot` prop is gone with it.
const TONES = { green: "tone-green", yellow: "tone-yellow", red: "tone-red", gray: "tone-gray" };

export default function StatusPill({ label, tone, small }) {
  if (!label) return null;
  return (
    <span className={["hms-dv-pill", TONES[tone] || "", small ? "sm" : ""].filter(Boolean).join(" ")}>
      {label}
    </span>
  );
}
