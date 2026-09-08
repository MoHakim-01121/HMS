import { ArrowRight } from "lucide-react";
import { Input } from "./ui/input.jsx";
import { Button } from "./ui/button.jsx";

/**
 * ReservationSlot — one row inside ApplyPaymentSheet.
 *
 * Shows a reservation's number, hotel, remaining balance, an amount input,
 * and a "fill remainder" button (fills unallocated into this row).
 *
 * Props:
 *  - reservation: { id, number, hotel, remaining_int }
 *  - value: current allocated amount (string, may be "")
 *  - onChange(value): update parent
 *  - onFill(): set this slot to its max (remaining - other allocations)
 *  - disabled: hide/disable fill
 */
export default function ReservationSlot({ reservation, value, onChange, onFill, disabled }) {
  const remaining = reservation?.remaining_int ?? 0;
  const canFill = remaining > 0 && !disabled;

  return (
    <div className="rsv-slot">
      <div className="rsv-slot-meta">
        <div className="rsv-slot-num">{reservation?.number || "—"}</div>
        <div className="rsv-slot-hotel">{reservation?.hotel || ""}</div>
        <div className="rsv-slot-rem">
          <span className="rsv-slot-rem-lbl">Remaining</span>
          <span className="rsv-slot-rem-num">{remaining.toLocaleString()} SAR</span>
        </div>
      </div>
      <div className="rsv-slot-input">
        <Input
          type="number"
          min="0"
          max={remaining}
          step="1"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="0"
          aria-label={`Allocate to reservation ${reservation?.number || ""}`}
        />
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="rsv-slot-fill"
        onClick={onFill}
        disabled={!canFill}
        title="Fill remainder"
        aria-label={`Fill remainder to reservation ${reservation?.number || ""}`}
      >
        <ArrowRight />
      </Button>
    </div>
  );
}
