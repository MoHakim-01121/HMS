const nf = new Intl.NumberFormat("en-US");

// Mirrors the Django `{{ value|floatformat:0|intcomma }} SAR` formatting.
export default function Money({ value, currency = "SAR", className }) {
  return (
    <span className={className}>
      {nf.format(Math.round(value || 0))} {currency}
    </span>
  );
}
