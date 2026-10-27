import { useState } from "react";
import { cn } from "@/lib/utils";
import { DA, DC, dBtnClass } from "./detail-a.jsx";
import { Link, router } from "@inertiajs/react";
import { useConfirm } from "./confirm-dialog.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "./ui/dialog.jsx";
import { Textarea } from "./ui/textarea.jsx";
import { Button } from "./ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtDate } from "../../utils/format.js";

/* Refunds and deposit transfers awaiting a second person
   (finance_views._pending_out_rows). Money leaves only once someone other
   than the recorder confirms; an admin may approve their own entry. Rows the
   viewer may not decide show who recorded them instead of the buttons. */
const ACTIONS = "inline-flex justify-end gap-1.5";

const base = (row) => (row.kind === "refund" ? `/finance/refunds/${row.id}` : `/finance/deposit-transfers/${row.id}`);

export default function PendingOutTable({ rows = [], showClient = false }) {
  const { t } = useI18n();
  const [confirm, confirmDialog] = useConfirm();
  const [rejecting, setRejecting] = useState(null);
  const [reason, setReason] = useState("");

  const approve = (row) => confirm({
    title: row.kind === "refund" ? t("Approve refund") : t("Approve deposit transfer"),
    message: t("Approve {number} for {amount} SAR? The journal is posted now.", {
      number: row.number, amount: fmt(row.amount_sar),
    }),
    confirmLabel: t("Approve"),
    icon: "check",
    onConfirm: () => router.post(`${base(row)}/confirm/`, {}, { preserveScroll: true }),
  });

  const submitReject = () => {
    router.post(`${base(rejecting)}/reject/`, { reason }, { preserveScroll: true });
    setRejecting(null);
    setReason("");
  };

  // The detail-page table (DA.table in detail-a.jsx), as on the Client Ledger.
  const table = (
    <div className={DA.scroll}>
      <table data-slot="detail-table" className={DA.table}>
        <thead>
          <tr>
            <th>{t("Document")}</th>
            {showClient ? <th>{t("Client")}</th> : null}
            <th>{t("Details")}</th><th>{t("Recorded by")}</th><th className={DC.n}>{t("Amount (SAR)")}</th>
            <th className={DC.n}><span className="sr-only">{t("Decision")}</span></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.kind}-${r.id}`} className={DA.rowMid}>
              <td className="align-middle"><span className={DC.mono}>{r.number}</span><span className={DC.sub}>{r.kind === "refund" ? t("Refund") : t("Deposit transfer")}, {fmtDate(r.date)}</span></td>
              {showClient ? <td className="align-middle"><Link href={`/finance/clients/${r.client_id}/statement/`}>{r.client}</Link></td> : null}
              <td className="align-middle">{r.detail}{r.note ? <span className={DC.sub}>{r.note}</span> : null}</td>
              <td className="align-middle">{r.created_by}</td>
              <td className={cn(DC.n, "align-middle font-semibold")}>{fmt(r.amount_sar)}</td>
              <td className={cn(DC.n, "align-middle")}>
                {r.can_decide ? (
                  <span className={ACTIONS}>
                    <button type="button" className={cn(dBtnClass(), "h-8 border border-input")} onClick={() => { setRejecting(r); setReason(""); }}>{t("Reject")}</button>
                    <button type="button" className={cn(dBtnClass({ primary: true }), "h-8")} onClick={() => approve(r)}>{t("Approve")}</button>
                  </span>
                ) : <span className={DC.sub}>{t("Awaiting another user")}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <>
      {table}
      {confirmDialog}
      {rejecting && (
        <Dialog open onOpenChange={(v) => { if (!v) setRejecting(null); }}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t("Reject {number}?", { number: rejecting.number })}</DialogTitle>
            </DialogHeader>
            <p className="mt-1.5 mb-0 text-[13px] leading-[1.6] text-muted-foreground">{t("No money moves. The document stays on record as rejected.")}</p>
            <label className="mt-4 mb-1.5 block text-[12px] font-medium text-muted-foreground" htmlFor="pot-reason">{t("Reason")}</label>
            <Textarea id="pot-reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
            <DialogFooter>
              <Button variant="outline" onClick={() => setRejecting(null)}>{t("Cancel")}</Button>
              <Button variant="destructive" disabled={!reason.trim()} onClick={submitReject}>{t("Reject")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}
