import { Fragment, useEffect, useMemo, useState } from "react";
import { router } from "@inertiajs/react";
import {
  Dialog, DialogCloseButton, DialogContent, DialogTitle,
} from "./ui/dialog.jsx";
import { Button } from "./ui/button.jsx";
import { Input } from "./ui/input.jsx";
import { showToast } from "./toast.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";
import { fmt } from "../../utils/format.js";
import { cn } from "../../lib/utils.js";

/* Chorded onto the shared form-modal chrome (.form-modal-content +
   .hms-modal-head + .hms-modal-body, tailwind.css), so padding, scrolling and
   the always-visible footer come for free. Only the inner layout is new.

   Summary reads like a Progress … Allocated / Remaining pair; the reservations
   list reuses the remittance table's visual grammar (mono ref, muted sub,
   tabular money, 14px bordered cells, red "Max {n}" overflow hint). The
   progress fill turns red while an allocation overshoots the payment, the same
   cue the MoneyField used historically, so the error reads at a glance. */
const CSS = `
.apply-sheet { min-width: 0; }
.apply-head { display:flex; flex-direction:column; gap:2px; min-width:0; }
.apply-head-sub { font-size: 12.5px; color: var(--muted-foreground); }
.apply-head-sub strong { color: var(--foreground); font-weight: 600; font-variant-numeric: tabular-nums; }

.apply-summary { display:flex; flex-direction:column; gap:13px; }


.apply-track { height:8px; border-radius:999px; background:color-mix(in oklch, var(--muted) 70%, transparent); overflow:hidden; }
.apply-track-fill { height:100%; border-radius:999px; background:var(--primary); transition:width 200ms ease; }
.apply-track-fill.is-err { background:var(--red); }

.apply-figs { display:flex; gap:8px; }
.apply-fig { flex:1; min-width:0; }
.apply-fig dt { font-size:10.5px; font-weight:600; letter-spacing:.07em; text-transform:uppercase; color:var(--muted-foreground); }
.apply-fig dd { margin-top:4px; font-size:18px; font-weight:600; letter-spacing:-.02em; font-variant-numeric:tabular-nums; color:var(--foreground); white-space:nowrap; }
.apply-fig dd span { margin-left:5px; font-size:11px; font-weight:600; color:var(--muted-foreground); letter-spacing:0; }
.apply-fig.is-key { min-width:0; }
.apply-fig.is-key dd { font-size:21px; }
.apply-fig.is-zero dd { color:var(--muted-foreground); }

.apply-note { margin:0; font-size:12px; line-height:1.5; padding:9px 11px; border-radius:10px; }
.apply-note.is-warn { color:var(--foreground); background:color-mix(in oklch, var(--muted) 55%, var(--card)); border:1px solid var(--border); }
.apply-note.is-err { color:var(--red); background:color-mix(in oklch, var(--red) 8%, var(--card)); border:1px solid color-mix(in oklch, var(--red) 30%, var(--border)); }
.apply-note.is-muted { color:var(--muted-foreground); background:var(--card); border:1px solid var(--border); }

.apply-res { display:flex; flex-direction:column; gap:10px; margin-top:22px; }
.apply-res-h { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.apply-res-title { margin:0; font-size:11px; font-weight:600; letter-spacing:.1em; text-transform:uppercase; color:var(--muted-foreground); }
.apply-res-title span { color:var(--foreground); font-variant-numeric:tabular-nums; }
.apply-tools { display:flex; gap:6px; }
.apply-tool {
  height:30px; padding:0 12px; border-radius:999px;
  border:1px solid var(--input); background:var(--card);
  font:inherit; font-size:12px; font-weight:600; color:var(--foreground);
  cursor:pointer; transition:border-color .12s, background .12s;
}
.apply-tool:hover { border-color:var(--foreground); }
.apply-tool:disabled { opacity:.45; cursor:default; border-color:var(--input); }
.apply-tool:focus-visible { outline:2px solid var(--ring); outline-offset:2px; }

.apply-list { border:1px solid var(--border); border-radius:14px; background:var(--card); overflow:hidden; }
.apply-row { display:flex; align-items:center; gap:14px; padding:11px 14px; }
.apply-row + .apply-row, .apply-group + .apply-row { border-top:1px solid var(--border); }
.apply-group {
  padding:8px 14px; font-size:10.5px; font-weight:600; letter-spacing:.08em; text-transform:uppercase;
  color:var(--muted-foreground); background:color-mix(in oklch, var(--muted) 45%, var(--card));
}
.apply-row + .apply-group { border-top:1px solid var(--border); }
.apply-row-rem.is-over strong { color:var(--red); }
.apply-row.is-blocked { opacity:.55; }
.apply-row-why { font-size:11.5px; color:var(--muted-foreground); text-align:right; max-width:150px; }
.apply-foot-note { margin:10px 2px 0; font-size:11.5px; line-height:1.5; color:var(--muted-foreground); }
.apply-row-meta { flex:1; min-width:0; display:flex; flex-direction:column; gap:2px; }
.apply-row-no { font-family:var(--font-mono); font-size:12px; font-weight:700; color:var(--foreground); }
.apply-row-sub { font-size:11.5px; color:var(--muted-foreground); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.apply-row-rem { font-size:11.5px; color:var(--muted-foreground); font-variant-numeric:tabular-nums; }
.apply-row-rem strong { color:var(--foreground); font-weight:600; }
.apply-row-in { display:flex; flex-direction:column; align-items:flex-end; gap:3px; }
.apply-row-in .aps-input { width:118px; text-align:right; }
.apply-row-max { font-size:10.5px; color:var(--red); white-space:nowrap; }

.apply-footer {
  display:flex; justify-content:flex-end; gap:10px;
  padding:16px 20px; border-top:1px solid var(--border);
  background:var(--card); flex-shrink:0;
}

@media (max-width: 600px) {
  .apply-row { padding:10px 12px; gap:10px; }
  .apply-row-in .aps-input { width:112px; }
  .apply-tool { height:32px; }
  .apply-footer { padding:14px 16px; }
}
`;

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
      <style>{CSS}</style>
      <Dialog
        open={open}
        onOpenChange={(v) => {
          if (!v) { reset(); onOpenChange(false); }
        }}
      >
        <DialogContent className="sm:max-w-xl form-modal-content apply-sheet" showCloseButton={false}>
          <div className="hms-modal-head">
            <div className="apply-head">
              <DialogTitle className="hms-modal-title">{t("Apply to reservations")}</DialogTitle>
              <span className="apply-head-sub">
                {payment?.payment_number ?? ""} · <strong>{fmt(total)} SAR</strong>
              </span>
            </div>
            <DialogCloseButton />
          </div>

          <div className="hms-modal-body">
            <div className="apply-summary">
              <div className="apply-track" aria-hidden="true">
                <div className={cn("apply-track-fill", err && "is-err")} style={{ width: `${pct}%` }} />
              </div>

              <dl className="apply-figs">
                <div className="apply-fig">
                  <dt>{t("Allocated")}</dt>
                  <dd>{fmt(allocated)}<span>SAR</span></dd>
                </div>
                <div className={cn("apply-fig", "is-key", remainder <= 0 && "is-zero")}>
                  <dt>{t("Remaining")}</dt>
                  <dd>{fmt(Math.max(0, remainder))}<span>SAR</span></dd>
                </div>
              </dl>

              {err ? (
                <p className="apply-note is-err" role="alert">{err}</p>
              ) : allocated > 0 && allocated < total ? (
                <p className="apply-note is-warn">
                  {t("{n} SAR unallocated", { n: fmt(remainder) })}
                </p>
              ) : null}
            </div>

            {resRows.length > 0 ? (
              <section className="apply-res" aria-labelledby="apply-res-title">
                <div className="apply-res-h">
                  <h3 id="apply-res-title" className="apply-res-title">
                    {t("Reservations")} <span>{resRows.length}</span>
                  </h3>
                  <div className="apply-tools">
                    <button type="button" className="apply-tool" onClick={autoFill} disabled={busy || !canEdit}>
                      {t("Auto-fill")}
                    </button>
                    <button type="button" className="apply-tool" onClick={clear} disabled={busy || !canEdit}>
                      {t("Clear")}
                    </button>
                  </div>
                </div>

                <div className="apply-list">
                  {resRows.map((res, i) => {
                    const over = rowOver(res);
                    const overpaid = (res.remaining_int ?? 0) < 0;
                    const newGroup = res.invoice_number && res.invoice_number !== resRows[i - 1]?.invoice_number;
                    return (
                      <Fragment key={res.id}>
                        {newGroup && <div className="apply-group">{res.invoice_number}</div>}
                      <div className="apply-row">
                        <div className="apply-row-meta">
                          <span className="apply-row-no">{res.number}</span>
                          <span className="apply-row-sub">{res.hotel}</span>
                          <span className={cn("apply-row-rem", overpaid && "is-over")}>
                            {overpaid
                              ? <>{t("Overpaid")}: <strong>{fmt(-res.remaining_int)} SAR</strong></>
                              : <>{t("Remaining")}: <strong>{fmt(res.remaining_int ?? 0)} SAR</strong></>}
                          </span>
                        </div>
                        <div className="apply-row-in">
                          <Input
                            className="aps-input"
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
                            <span className="apply-row-max">{t("Max {n}", { n: fmt(over) })}</span>
                          )}
                        </div>
                      </div>
                      </Fragment>
                    );
                  })}
                  {unbilled.length > 0 && <div className="apply-group">{t("Not invoiced yet")}</div>}
                  {unbilled.map((cl) => (
                    <div className="apply-row is-blocked" key={`cl-${cl.id}`}>
                      <div className="apply-row-meta">
                        <span className="apply-row-no">{cl.number}</span>
                        <span className="apply-row-sub">{cl.hotel}</span>
                      </div>
                      <span className="apply-row-why">{t("Create its invoice first")}</span>
                    </div>
                  ))}
                </div>
                <p className="apply-foot-note">{t("Fully paid reservations are not listed: they cannot take more money.")}</p>
              </section>
            ) : (
              <p className="apply-note is-muted" style={{ marginTop: "22px" }}>
                {t("This payment has no reservations to allocate to.")}
              </p>
            )}
          </div>

          <div className="apply-footer">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              {t("Cancel")}
            </Button>
            <Button onClick={submit} disabled={busy || !!err || anyRowOver || !canEdit || resRows.length === 0}>
              {busy ? t("Saving…") : t("Apply")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}