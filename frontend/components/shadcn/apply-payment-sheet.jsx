import { useState, useMemo } from "react";
import { router } from "@inertiajs/react";
import BalanceBar from "./balance-bar.jsx";
import ReservationSlot from "./reservation-slot.jsx";
import {
  Dialog, DialogCloseButton, DialogContent, DialogFooter, DialogTitle,
} from "./ui/dialog.jsx";
import { Button } from "./ui/button.jsx";
import { showToast } from "./toast.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";

const CSS = `
.apply-sheet { min-width: 0; }
.apply-head { display:flex; flex-direction:column; gap:2px; min-width:0; }
.apply-summary { display:flex; flex-direction:column; gap:10px; margin-bottom:4px; }
.apply-slotlist { display:flex; flex-direction:column; gap:10px; margin-top:12px; }

.rsv-slot {
  display:flex; align-items:center; gap:10px;
  border:1px solid var(--border); border-radius:14px;
  background:var(--card); padding:10px 12px;
}
.rsv-slot-meta { flex:1; min-width:0; display:flex; flex-direction:column; gap:1px; }
.rsv-slot-num { font-size:13px; font-weight:600; color:var(--foreground); }
.rsv-slot-hotel { font-size:12px; color:var(--muted-foreground); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.rsv-slot-rem { display:flex; gap:6px; align-items:center; margin-top:2px; }
.rsv-slot-rem-lbl { font-size:10px; text-transform:uppercase; letter-spacing:0.4px; color:var(--muted-foreground); }
.rsv-slot-rem-num { font-size:11px; font-weight:600; color:var(--foreground); font-variant-numeric:tabular-nums; }
.rsv-slot-input { width:110px; flex-shrink:0; }
.rsv-slot-fill { flex-shrink:0; }

.apply-warn { font-size:12px; color:var(--yellow); }
.apply-err { font-size:12px; color:var(--red); }
.apply-hint { font-size:12px; color:var(--muted-foreground); margin-top:2px; }
`;

/**
 * ApplyPaymentSheet — split a payment across reservations.
 *
 * Opens as a dialog (sm:max-w-2xl) with a live BalanceBar, one ReservationSlot
 * per reservation, and an "Apply remainder" action.
 *
 * Props:
 *  - open / onOpenChange
 *  - payment: { id, amount_sar, payment_number, invoice_id }
 *  - reservations: [{ id, number, hotel, remaining_int }]
 *  - initialAllocations: [{ reservation_id, amount_sar }] to prefill when
 *    re-applying an already-allocated payment
 *  - onApplied: callback after a successful apply
 */
export default function ApplyPaymentSheet({ open, onOpenChange, payment, reservations, initialAllocations = [], onApplied }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canEdit = perms.can("payments", "edit");

  // value per reservation id (string for controlled inputs)
  const [amounts, setAmounts] = useState({});
  const [busy, setBusy] = useState(false);

  const total = payment?.amount_sar ?? 0;

  // Seed allocations when the sheet opens.
  const [seeded, setSeeded] = useState(false);
  if (open && !seeded) {
    const init = {};
    const hasInitial = (initialAllocations || []).length > 0;
    if (hasInitial) {
      (initialAllocations || []).forEach((a) => {
        if (a.reservation_id) init[a.reservation_id] = String(a.amount_sar);
      });
    } else if (reservations.length === 1) {
      // Auto-apply: single reservation → fill the full payment.
      const only = reservations[0];
      init[only.id] = String(Math.min(total, only.remaining_int ?? total));
    }
    setAmounts(init);
    setSeeded(true);
  }
  if (!open && seeded) {
    setSeeded(false);
  }

  const allocated = useMemo(
    () => Object.values(amounts).reduce((s, v) => s + (parseFloat(v) || 0), 0),
    [amounts]
  );
  const remainder = total - allocated;
  const err = allocated > total ? t("Allocation exceeds payment amount") : null;

  const parse = (v) => {
    if (v == null || v === "") return 0;
    return parseFloat(String(v).replace(/,/g, "")) || 0;
  };

  const fillSlot = (res) => {
    // Only fill the unallocated remainder.
    setAmounts((prev) => {
      const otherAlloc = Object.entries(prev)
        .filter(([id]) => String(id) !== String(res.id))
        .reduce((s, [, v]) => s + parse(v), 0);
      const room = Math.max(0, total - otherAlloc);
      return { ...prev, [res.id]: String(Math.min(room, res.remaining_int ?? room)) };
    });
  };

  const fillAllRemainder = () => {
    if (!reservations.length) return;
    const last = reservations[reservations.length - 1];
    fillSlot(last);
  };

  const submit = () => {
    if (err || busy) return;
    if (!payment?.id) return;

    const allocs = Object.entries(amounts)
      .map(([id, v]) => ({ reservation_id: parseInt(id, 10), amount: parse(v) }))
      .filter((a) => a.amount > 0);

    if (allocs.length === 0) {
      showToast(t("Enter at least one allocation."), "error");
      return;
    }

    setBusy(true);
    router.post(
      `/finance/payments/${payment.id}/apply/`,
      { allocations: JSON.stringify(allocs) },
      {
        onSuccess: () => {
          setBusy(false);
          onOpenChange(false);
          setAmounts({});
          if (onApplied) onApplied();
        },
        onError: () => {
          setBusy(false);
          showToast(t("Could not apply allocation."), "error");
        },
      }
    );
  };

  const reset = () => {
    setAmounts({});
    setBusy(false);
  };

  return (
    <>
      <style>{CSS}</style>
      <Dialog
        open={open}
        onOpenChange={(v) => {
          if (!v) { reset(); onOpenChange(false); }
        }}
      >
        <DialogContent className="sm:max-w-2xl apply-sheet">
          <div className="hms-modal-head">
            <div className="apply-head">
              <DialogTitle className="hms-modal-title">{t("Apply to reservations")}</DialogTitle>
              <span className="apply-hint">
                {payment?.payment_number} · {total.toLocaleString()} SAR
              </span>
            </div>
            <DialogCloseButton />
          </div>

          <div className="hms-modal-body">
            <div className="apply-summary">
              <BalanceBar total={total} allocated={allocated} currency="SAR" />
              {err ? (
                <div className="apply-err">{err}</div>
              ) : (
                allocated > 0 && allocated !== total && (
                  <div className="apply-warn">
                    {t("{n} SAR unallocated", { n: remainder.toLocaleString() })}
                  </div>
                )
              )}

              {reservations.length > 0 ? (
                <div className="apply-slotlist">
                  {reservations.map((res) => (
                    <ReservationSlot
                      key={res.id}
                      reservation={res}
                      value={amounts[res.id] ?? ""}
                      onChange={(v) => setAmounts((prev) => ({ ...prev, [res.id]: v }))}
                      onFill={() => !busy && fillSlot(res)}
                      disabled={busy}
                    />
                  ))}
                </div>
              ) : (
                <div className="apply-hint">{t("This payment has no reservations to allocate to.")}</div>
              )}
            </div>
          </div>

          <DialogFooter className="pay-footer">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              {t("Cancel")}
            </Button>
            {reservations.length > 0 && !err && (
              <Button variant="outline" onClick={fillAllRemainder} disabled={busy}>
                {t("Apply remainder")}
              </Button>
            )}
            <Button onClick={submit} disabled={busy || !!err || !canEdit || reservations.length === 0}>
              {busy ? t("Saving...") : t("Apply")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
