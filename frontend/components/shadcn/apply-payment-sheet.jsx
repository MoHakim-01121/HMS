import { Fragment, useEffect, useMemo, useState } from "react";
import { router } from "@inertiajs/react";
import {
  Dialog, DialogCloseButton,
} from "./ui/dialog.jsx";
import { Button } from "./ui/button.jsx";
import { Input } from "./ui/input.jsx";
import { showToast } from "./toast.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";
import { fmt } from "../../utils/format.js";
import { ModalContent, ModalHead, ModalTitle, ModalBody } from "./form-modal.jsx";
import { cn } from "../../lib/utils.js";

/* Chorded onto the shared form-modal chrome (ModalContent, ModalHead,
   ModalBody in form-modal.jsx), so padding, scrolling and
   the always-visible footer come for free. Only the inner layout is new.

   Summary reads like a Progress … Allocated / Remaining pair; the reservations
   list reuses the remittance table's visual grammar (mono ref, muted sub,
   tabular money, 14px bordered cells, red "Max {n}" overflow hint). The
   progress fill turns red while an allocation overshoots the payment, the same
   cue the MoneyField used historically, so the error reads at a glance. */
const NOTE = {
  warn: "border-border bg-[color:color-mix(in_oklch,var(--muted)_55%,var(--card))] text-foreground",
  err: "border-[color:color-mix(in_oklch,var(--red)_30%,var(--border))] bg-[color:color-mix(in_oklch,var(--red)_8%,var(--card))] text-red",
  muted: "border-border bg-card text-muted-foreground",
};
const Note = ({ tone, className, ...props }) => (
  <p className={cn("m-0 rounded-[10px] border px-[11px] py-[9px] text-[12px] leading-[1.5]", NOTE[tone], className)} {...props} />
);
const Fig = ({ label, value, big, zero }) => (
  <div className="min-w-0 flex-1">
    <dt className="text-[12px] font-semibold tracking-[.07em] text-muted-foreground uppercase">{label}</dt>
    <dd className={cn("mt-1 text-[18px] font-semibold tracking-[-.02em] whitespace-nowrap text-foreground tabular-nums", big && "text-[21px]", zero && "text-muted-foreground")}>
      {value}<span className="ml-[5px] text-[11px] font-semibold tracking-normal text-muted-foreground">SAR</span>
    </dd>
  </div>
);
const toolClass = cn(
  "h-[30px] cursor-pointer rounded-full border border-input bg-card px-3 font-[family-name:inherit] text-[12px] leading-[inherit] font-semibold text-foreground",
  "transition-[border-color,background-color] duration-[120ms] hover:border-foreground disabled:cursor-default disabled:border-input disabled:opacity-45",
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid max-[600px]:h-8",
);
const GROUP = "bg-[color:color-mix(in_oklch,var(--muted)_45%,var(--card))] px-[14px] py-2 text-[12px] font-semibold tracking-[.08em] text-muted-foreground uppercase";
const ROW = "flex items-center gap-[14px] px-[14px] py-[11px] max-[600px]:gap-2.5 max-[600px]:px-3 max-[600px]:py-2.5";
const ROW_META = "flex min-w-0 flex-1 flex-col gap-0.5";
const ROW_NO = "font-mono text-[12px] font-bold text-foreground";
const ROW_SUB = "truncate text-[12px] text-muted-foreground";

/**
 * ApplyPaymentSheet — split a payment across reservations.
 *
 * Opens as a compact dialog with a live progress summary (allocated vs
 * remaining of the payment) and one amount field per reservation. Auto-fill
 * distributes the whole payment across the reservations in list order, each
 * capped at its own outstanding balance; Clear resets the fields. No per-row
 * fill buttons — typing the amount and watching the summary is the whole
 * interaction, and the apply action lives in the pinned footer.
 *
 * Props:
 *  - open / onOpenChange
 *  - payment: { id, amount_sar, payment_number, invoice_id }
 *  - reservations: [{ id, number, hotel, remaining_int, max_sar, invoice_id,
 *    invoice_number }] — hotel lines across the client's invoices (the
 *    payment's own first, see payment_views._allocatable_reservations).
 *    `max_sar` is this payment's cap on the line: what is still owed plus
 *    what this payment already put there, so a reservation amended down
 *    (15,000 → 13,000) can still keep 13,000 and send the rest elsewhere.
 *    `remaining_int` < 0 is an overpayment.
 *  - unbilled: [{ id, number, hotel, check_in, check_out }] — the client's
 *    bookings not on any invoice yet; shown greyed with the reason, since an
 *    allocation always lands on an invoice line.
 *  - initialAllocations: [{ reservation_id, amount_sar }] to prefill when
 *    re-applying an already-allocated payment
 *  - onApplied: callback after a successful apply
 */
export default function ApplyPaymentSheet({
  open, onOpenChange, payment, reservations = [], unbilled = [], initialAllocations = [], onApplied,
}) {
  const { t } = useI18n();
  const perms = usePerms();
  const canEdit = perms.can("payments", "edit");

  const [amounts, setAmounts] = useState({});
  const [busy, setBusy] = useState(false);

  const total = payment?.amount_sar ?? 0;
  const resRows = reservations || [];
  const capOf = (res) => res.max_sar ?? res.remaining_int;

  // Seed allocations each time the sheet opens.
  useEffect(() => {
    if (!open) return;
    const init = {};
    const hasInitial = (initialAllocations || []).length > 0;
    if (hasInitial) {
      (initialAllocations || []).forEach((a) => {
        if (a.reservation_id) init[a.reservation_id] = String(a.amount_sar);
      });
    } else if (resRows.length === 1) {
      // Auto-apply: single reservation → fill the full payment.
      const only = resRows[0];
      init[only.id] = String(Math.min(total, capOf(only) ?? total));
    }
    setAmounts(init);
    setBusy(false);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const parse = (v) => {
    if (v == null || v === "") return 0;
    return parseFloat(String(v).replace(/,/g, "")) || 0;
  };

  const allocated = useMemo(
    () => Object.values(amounts).reduce((s, v) => s + parse(v), 0),
    [amounts]
  );
  const remainder = total - allocated;
  const pct = total > 0 ? Math.min(100, Math.round((allocated / total) * 100)) : 0;

  const rowOver = (res) => {
    const v = parse(amounts[res.id]);
    const max = capOf(res);
    return max != null && v > max ? max : null;
  };
  const err = allocated > total ? t("Allocation exceeds payment amount") : null;
  const anyRowOver = resRows.some((r) => rowOver(r) != null);

  const autoFill = () => {
    let left = total;
    const next = {};
    for (const res of resRows) {
      if (left <= 0) break;
      const take = Math.min(capOf(res) ?? 0, left);
      if (take > 0) next[res.id] = String(take);
      left -= take;
    }
    setAmounts(next);
  };

  const clear = () => setAmounts({});

  const submit = () => {
    if (err || anyRowOver || busy) return;
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
      <Dialog
        open={open}
        onOpenChange={(v) => {
          if (!v) { reset(); onOpenChange(false); }
        }}
      >
        <ModalContent className="min-w-0 sm:max-w-xl">
          <ModalHead>
            <div className="flex min-w-0 flex-col gap-0.5">
              <ModalTitle>{t("Apply to reservations")}</ModalTitle>
              <span className="text-[13px] text-muted-foreground">
                {payment?.payment_number ?? ""} · <strong className="font-semibold text-foreground tabular-nums">{fmt(total)} SAR</strong>
              </span>
            </div>
            <DialogCloseButton />
          </ModalHead>

          <ModalBody>
            <div className="flex flex-col gap-[13px]">
              <div className="h-2 overflow-hidden rounded-full bg-muted/70" aria-hidden="true">
                <div className={cn("h-full rounded-full bg-primary transition-[width] duration-200 ease-out-quint", err && "bg-red")} style={{ width: `${pct}%` }} />
              </div>

              <dl className="flex gap-2">
                <Fig label={t("Allocated")} value={fmt(allocated)} />
                <Fig label={t("Remaining")} value={fmt(Math.max(0, remainder))} big zero={remainder <= 0} />
              </dl>

              {err ? (
                <Note tone="err" role="alert">{err}</Note>
              ) : allocated > 0 && allocated < total ? (
                <Note tone="warn">
                  {t("{n} SAR unallocated", { n: fmt(remainder) })}
                </Note>
              ) : null}
            </div>

            {resRows.length > 0 ? (
              <section className="mt-[22px] flex flex-col gap-2.5" aria-labelledby="apply-res-title">
                <div className="flex items-center justify-between gap-2.5">
                  <h3 id="apply-res-title" className="m-0 text-[11px] font-semibold tracking-[.1em] text-muted-foreground uppercase">
                    {t("Reservations")} <span className="text-foreground tabular-nums">{resRows.length}</span>
                  </h3>
                  <div className="flex gap-1.5">
                    <button type="button" className={toolClass} onClick={autoFill} disabled={busy || !canEdit}>
                      {t("Auto-fill")}
                    </button>
                    <button type="button" className={toolClass} onClick={clear} disabled={busy || !canEdit}>
                      {t("Clear")}
                    </button>
                  </div>
                </div>

                <div className="overflow-hidden rounded-[14px] border border-border bg-card [&>*+*]:border-t [&>*+*]:border-border">
                  {resRows.map((res, i) => {
                    const over = rowOver(res);
                    const overpaid = (res.remaining_int ?? 0) < 0;
                    const newGroup = res.invoice_number && res.invoice_number !== resRows[i - 1]?.invoice_number;
                    return (
                      <Fragment key={res.id}>
                        {newGroup && <div className={GROUP}>{res.invoice_number}</div>}
                      <div className={ROW}>
                        <div className={ROW_META}>
                          <span className={ROW_NO}>{res.number}</span>
                          <span className={ROW_SUB}>{res.hotel}</span>
                          <span className="text-[12px] text-muted-foreground tabular-nums">
                            {overpaid
                              ? <>{t("Overpaid")}: <strong className="font-semibold text-red">{fmt(-res.remaining_int)} SAR</strong></>
                              : <>{t("Remaining")}: <strong className="font-semibold text-foreground">{fmt(res.remaining_int ?? 0)} SAR</strong></>}
                          </span>
                        </div>
                        <div className="flex flex-col items-end gap-[3px]">
                          <Input
                            className="w-[118px] text-right max-[600px]:w-[112px]"
                            type="number"
                            min="0"
                            max={capOf(res) ?? undefined}
                            step="1"
                            inputMode="numeric"
                            value={amounts[res.id] ?? ""}
                            onChange={(e) => setAmounts((prev) => ({ ...prev, [res.id]: e.target.value }))}
                            placeholder="0"
                            disabled={busy || !canEdit}
                            aria-invalid={!!over || undefined}
                            aria-label={`${res.number} — ${t("Amount (SAR)")}`}
                          />
                          {over != null && (
                            <span className="text-[12px] whitespace-nowrap text-red">{t("Max {n}", { n: fmt(over) })}</span>
                          )}
                        </div>
                      </div>
                      </Fragment>
                    );
                  })}
                  {unbilled.length > 0 && <div className={GROUP}>{t("Not invoiced yet")}</div>}
                  {unbilled.map((cl) => (
                    <div className={cn(ROW, "opacity-55")} key={`cl-${cl.id}`}>
                      <div className={ROW_META}>
                        <span className={ROW_NO}>{cl.number}</span>
                        <span className={ROW_SUB}>{cl.hotel}</span>
                      </div>
                      <span className="max-w-[150px] text-right text-[12px] text-muted-foreground">{t("Create its invoice first")}</span>
                    </div>
                  ))}
                </div>
                <p className="mx-0.5 mt-2.5 mb-0 text-[12px] leading-[1.5] text-muted-foreground">{t("Fully paid reservations are not listed: they cannot take more money.")}</p>
              </section>
            ) : (
              <Note tone="muted" className="mt-[22px]">
                {t("This payment has no reservations to allocate to.")}
              </Note>
            )}
          </ModalBody>

          <div className="flex shrink-0 justify-end gap-2.5 border-t border-border bg-card px-5 py-4 max-[600px]:px-4 max-[600px]:py-3.5">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              {t("Cancel")}
            </Button>
            <Button onClick={submit} disabled={busy || !!err || anyRowOver || !canEdit || resRows.length === 0}>
              {busy ? t("Saving…") : t("Apply")}
            </Button>
          </div>
        </ModalContent>
      </Dialog>
    </>
  );
}