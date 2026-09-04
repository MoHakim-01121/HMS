// Single source for payment-status badges. Renders the v2.1 library pill
// (StatusPill) so payment status reads the same as every other status in
// the app — filled, semantic hue.
import { useI18n } from "../../utils/i18n.jsx";
import StatusPill from "../shadcn/status-pill.jsx";

const MAP = {
  paid: { label: "Paid", tone: "green" },
  overpaid: { label: "Overpaid", tone: "green" },
  partial: { label: "Partial", tone: "yellow" },
  unpaid: { label: "Unpaid", tone: "red" },
};

// Derive status the same way the Django views do (from remaining vs total).
export function paymentStatus(total, remaining) {
  if (remaining < 0) return "overpaid";
  if (remaining === 0) return "paid";
  if (remaining < total) return "partial";
  return "unpaid";
}

export default function StatusBadge({ status, small }) {
  const { t } = useI18n();
  const m = MAP[status] || MAP.unpaid;
  return <StatusPill tone={m.tone} label={t(m.label)} small={small} />;
}
