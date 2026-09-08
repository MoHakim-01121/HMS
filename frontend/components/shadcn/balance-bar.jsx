import { cn } from "../../lib/utils";

const CSS = `
.balance-bar { display:flex; flex-direction:column; gap:8px; min-width:0; }
.balance-bar-track {
  width:100%; height:10px; border-radius:999px;
  background: color-mix(in oklch, var(--muted) 60%, transparent);
  overflow:hidden; position:relative;
}
.balance-bar-alloc {
  height:100%; border-radius:999px;
  background: var(--primary);
  transition: width 180ms ease;
}
.balance-bar-legend { display:flex; gap:18px; flex-wrap:wrap; align-items:center; }
.balance-bar-cell { display:inline-flex; align-items:center; gap:6px; }
.balance-bar-cell .dot { width:8px; height:8px; border-radius:50%; }
.balance-bar-cell .dot-alloc { background: var(--primary); }
.balance-bar-cell .dot-free { background: color-mix(in oklch, var(--muted) 80%, var(--muted-foreground)); }
.balance-bar-cell .lbl { font-size:13px; font-weight:600; color:var(--foreground); font-variant-numeric:tabular-nums; }
.balance-bar-cell .sub { font-size:10px; text-transform:uppercase; letter-spacing:0.4px; color:var(--muted-foreground); }
.balance-bar-total { margin-left:auto; }
`;

/**
 * BalanceBar — horizontal allocation progress bar.
 *
 * Shows how much of a payment/invoice total is allocated vs unallocated.
 * Segments are proportional: gold = allocated, muted = unallocated.
 *
 * Props:
 *  - total:   full amount (SAR)
 *  - allocated: amount currently allocated
 *  - currency: ISO code (default "SAR")
 *  - className: extra classes for the wrapper
 */
export default function BalanceBar({ total, allocated, currency = "SAR", className }) {
  const unallocated = Math.max(0, (total || 0) - (allocated || 0));
  const pctAllocated = total > 0 ? Math.min(100, ((allocated || 0) / total) * 100) : 0;
  const fmt = (n) => (n || 0).toLocaleString();

  return (
    <div
      className={cn("balance-bar", className)}
      role="status"
      aria-label={`Allocated ${fmt(allocated)} of ${fmt(total)} ${currency}`}
    >
      <style>{CSS}</style>
      <div className="balance-bar-track" aria-hidden="true">
        <div
          className="balance-bar-alloc"
          style={{ width: `${pctAllocated}%` }}
        />
      </div>
      <div className="balance-bar-legend">
        <span className="balance-bar-cell">
          <span className="dot dot-alloc" aria-hidden="true" />
          <span className="lbl">{`${fmt(allocated)} ${currency}`}</span>
          <span className="sub">{`Allocated`}</span>
        </span>
        <span className="balance-bar-cell">
          <span className="dot dot-free" aria-hidden="true" />
          <span className="lbl">{`${fmt(unallocated)} ${currency}`}</span>
          <span className="sub">{unallocated > 0 ? `Unallocated` : `—`}</span>
        </span>
        <span className="balance-bar-cell balance-bar-total">
          <span className="lbl">{`${fmt(total)} ${currency}`}</span>
          <span className="sub">Total</span>
        </span>
      </div>
    </div>
  );
}

