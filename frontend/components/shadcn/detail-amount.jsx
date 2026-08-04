// Headline figure tile beside the meta grid — replaces the .dv-amtbox markup
// each detail page used to hand-roll (gold-tinted panel, 9px mono-uppercase
// label, 800-weight number). tone: "green" when settled, "red" when
// outstanding, omitted for neutral figures like a hotel's distance.
export default function DetailAmount({ label, value, currency, tone, note, noteTone }) {
  return (
    <div className={["hms-dv-amt", tone ? `tone-${tone}` : ""].filter(Boolean).join(" ")}>
      <div className="hms-dv-amt-l">{label}</div>
      <div className="hms-dv-amt-num">
        {value}
        {currency ? <span className="cur">{currency}</span> : null}
      </div>
      {note ? <div className={["hms-dv-amt-note", noteTone || ""].filter(Boolean).join(" ")}>{note}</div> : null}
    </div>
  );
}
