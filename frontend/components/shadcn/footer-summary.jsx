// Grand-total strip closing the detail card. Same `left`/`right` slots as
// before; the helper exports below keep the markup for the label / big number
// / caption trio in one place instead of repeating inline styles (and the old
// dv-l / dv-foot-total classes) on every detail page.
export default function FooterSummary({ left, right }) {
  return (
    <div className="hms-dv-foot">
      <div style={{ minWidth: 0 }}>{left}</div>
      {right ? <div className="hms-dv-foot-r">{right}</div> : null}
    </div>
  );
}

// Big closing figure, e.g. Total Price 12,400 SAR.
export function FooterTotal({ label, value, currency }) {
  return (
    <>
      <div className="hms-dv-foot-l">{label}</div>
      <div className="hms-dv-foot-total">
        {value}
        {currency ? <span className="cur">{currency}</span> : null}
      </div>
    </>
  );
}

// Secondary figure on the left, e.g. Paid 10,000 SAR / 3 payments received.
export function FooterFigure({ label, value, tone, sub }) {
  return (
    <>
      <div className="hms-dv-foot-l">{label}</div>
      <div className={["hms-dv-foot-val", tone || ""].filter(Boolean).join(" ")}>{value}</div>
      {sub ? <div className="hms-dv-foot-sub">{sub}</div> : null}
    </>
  );
}
