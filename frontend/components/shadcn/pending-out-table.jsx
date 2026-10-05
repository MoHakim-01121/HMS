import { useState } from "react";
import { Link, router } from "@inertiajs/react";
import DetailTable from "./detail-table.jsx";
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
const CSS = `
.pot-actions { display:inline-flex; gap:6px; justify-content:flex-end; }
.pot-sub { display:block; font-size:11.5px; color:var(--muted-foreground); }
.pot-dlgdesc { font-size:13px; color:var(--muted-foreground); margin:6px 0 0; line-height:1.6; }
.pot-dlglabel { display:block; font-size:12px; color:var(--muted-foreground); margin:16px 0 6px; }
`;

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

  const columns = [
    {
      header: t("Document"),
      render: (r) => (
        <span>
          <span className="mono">{r.number}</span>
          <span className="pot-sub">{r.kind === "refund" ? t("Refund") : t("Deposit transfer")} · {fmtDate(r.date)}</span>
        </span>
      ),
    },
    showClient && {
      header: t("Client"),
      render: (r) => <Link href={`/finance/clients/${r.client_id}/statement/`}>{r.client}</Link>,
    },
    {
      header: t("Details"),
      render: (r) => (
        <span>
          {r.detail}
          {r.note ? <span className="pot-sub">{r.note}</span> : null}
        </span>
      ),
    },
    { header: t("Recorded by"), render: (r) => r.created_by },
    { header: t("Amount (SAR)"), align: "right", strong: true, render: (r) => fmt(r.amount_sar) },
    {
      header: "",
      align: "right",
      render: (r) => (r.can_decide ? (
        <span className="pot-actions">
          <Button size="sm" variant="outline" onClick={() => { setRejecting(r); setReason(""); }}>{t("Reject")}</Button>
          <Button size="sm" onClick={() => approve(r)}>{t("Approve")}</Button>
        </span>
      ) : (
        <span className="pot-sub">{t("Awaiting another user")}</span>
      )),
    },
  ];

  return (
    <>
      <style>{CSS}</style>
      <DetailTable columns={columns} rows={rows} rowKey={(r) => `${r.kind}-${r.id}`} empty={t("Nothing awaiting approval.")} />
      {confirmDialog}
      {rejecting && (
        <Dialog open onOpenChange={(v) => { if (!v) setRejecting(null); }}>
          <DialogContent className="hms-dialog">
            <DialogHeader>
              <DialogTitle>{t("Reject {number}?", { number: rejecting.number })}</DialogTitle>
            </DialogHeader>
            <p className="pot-dlgdesc">{t("No money moves. The document stays on record as rejected.")}</p>
            <label className="pot-dlglabel" htmlFor="pot-reason">{t("Reason")}</label>
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
