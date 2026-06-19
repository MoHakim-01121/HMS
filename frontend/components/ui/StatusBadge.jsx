// Single source for payment-status badges. Matches design.css badge classes
// and the labels used across the Django templates.
const MAP = {
  paid: { label: "Paid", cls: "badge badge-green" },
  partial: { label: "Partial", cls: "badge badge-yellow" },
  unpaid: { label: "Unpaid", cls: "badge badge-red" },
};

// Derive status the same way the Django views do (from remaining vs total).
export function paymentStatus(total, remaining) {
  if (remaining <= 0) return "paid";
  if (remaining < total) return "partial";
  return "unpaid";
}

export default function StatusBadge({ status }) {
  const m = MAP[status] || MAP.unpaid;
  return <span className={m.cls}>{m.label}</span>;
}
