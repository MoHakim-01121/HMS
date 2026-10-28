import { Fragment } from "react";
import { cn } from "@/lib/utils";
import { router } from "@inertiajs/react";
import { DPage, DTop, DHead, DBanner, DBtn, DChip, DCard, DMenu, DLines, DLine, DLinesTotal, DA, DC } from "../../components/shadcn/detail-a.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtDate } from "../../utils/format.js";

// Remittance detail, the "Remittance Detail" artboard on the Record View HMS
// canvas: a strip says what HQ still has to do, the head card holds the
// transfer's facts, and Receipts at HQ groups each receipt with the
// reservations it was allocated to.

export default function Detail({ rem, lines = [], fx }) {
  const { t } = useI18n();
  const openForm = useFormModal();
  const perms = usePerms();
  const canEdit = perms.can("remittance", "edit");
  const canDelete = perms.can("remittance", "delete");
  // Receipts are head office's: a branch sends, head office records what came in.
  const canReceive = canEdit && perms.headOffice;
  const [confirm, confirmDialog] = useConfirm();

  // One status: rem.status, kept in sync by the backend once receipts exist
  // (hw/finance/settlement_service.py). `legacy` = an old remittance with a
  // manual received_amount_sar.
  const legacy = rem.received_amount_sar != null;
  const isReceived = rem.status === "received";
  const receivedSar = legacy ? rem.received_amount_sar : rem.settled_total_sar;
  const basisSar = legacy ? rem.expected_sar : rem.settlement_basis_sar;
  const partial = !legacy && !isReceived && receivedSar > 0;
  const remainingSar = basisSar != null ? Math.max(0, basisSar - receivedSar) : 0;
  const pos = rem.position;

  const deleteReceipt = (s) => confirm({
    title: t("Delete receipt"),
    message: t("Delete the {n} SAR receipt of {date}? Its journal entries and allocations are reversed; the remittance goes back to waiting for this money.", { n: fmt(s.received_amount_sar), date: s.received_date }),
    confirmLabel: "Delete",
    danger: true,
    onConfirm: () => router.post(`/remittance/${rem.id}/receipt/${s.id}/delete/`),
  });

  const closeDiff = () => confirm({
    title: t("Close Difference"),
    message: rem.diff_sar > 0
      ? t("Book the {n} SAR shortfall on {remittance} as a bank fee/FX loss and mark it received? No further receipts can be recorded unless you reopen it.", { n: fmt(rem.diff_sar), remittance: rem.remittance_number })
      : t("Book the {n} SAR surplus on {remittance} as an FX gain? It cannot be edited unless you reopen it.", { n: fmt(-rem.diff_sar), remittance: rem.remittance_number }),
    confirmLabel: "Close Difference",
    danger: false,
    icon: "alert",
    onConfirm: () => router.post(`/remittance/${rem.id}/close-diff/`),
  });

  const reopenDiff = () => confirm({
    title: t("Reopen Difference"),
    message: t("Reverse the difference booked on {remittance}? It goes back to pending if HQ has not received the full amount, so receipts can be corrected and the difference closed again.", { remittance: rem.remittance_number }),
    confirmLabel: "Reopen Difference",
    danger: false,
    icon: "alert",
    onConfirm: () => router.post(`/remittance/${rem.id}/reopen-diff/`),
  });

  const receiptUrl = `/remittance/${rem.id}/receipt/?next=/remittance/${rem.id}/`;
  const allocationUrl = (s) => `/remittance/${rem.id}/receipt/${s.id}/allocation/?next=/remittance/${rem.id}/`;
  const showRecord = canReceive && rem.can_record_receipt;
  const showCloseDiff = canReceive && rem.can_close_diff;
  const showReopenDiff = canReceive && rem.can_reopen_diff;

  // What the strip says: the one thing still open on this transfer.
  let sentence = null;
  let tone = "warning";
  if (pos && pos.received_unallocated > 0) {
    sentence = <><b>{fmt(pos.received_unallocated)} SAR</b> {t("received but not allocated. Use Change allocation on the receipt below.")}</>;
  } else if (!isReceived) {
    if (partial) {
      sentence = <><b>{fmt(receivedSar)} SAR</b> {t("received of {total}.", { total: fmt(basisSar) })} {t("Still {n} SAR outstanding.", { n: fmt(remainingSar) })}</>;
    } else if (legacy) {
      sentence = t("The HQ office has not confirmed this amount yet.");
    } else {
      sentence = <>{t("Awaiting receipt at HQ.")} {t("Record the receipt once HQ confirms the transfer arrived.")}</>;
    }
  } else if (rem.can_close_diff) {
    sentence = <><b>{fmt(-rem.diff_sar)} SAR</b> {t("more than sent. Close the difference to book it as an FX gain.")}</>;
  } else if (rem.unallocated_sar > 0) {
    sentence = <><b>{fmt(rem.unallocated_sar)} SAR</b> {t("of the received amount is not yet allocated.")}</>;
  } else if (showReopenDiff) {
    tone = "success";
    sentence = rem.diff_sar
      ? t("Fully received. {n} SAR difference booked as bank fee/FX.", { n: fmt(Math.abs(rem.diff_sar)) })
      : t("Fully received.");
  }
  const actions = (
    <>
      {showCloseDiff ? <DBtn primary={!showRecord} onClick={closeDiff}>{t("Close difference")}</DBtn> : null}
      {showReopenDiff ? <DBtn onClick={reopenDiff}>{t("Reopen difference")}</DBtn> : null}
      {showRecord ? (
        <DBtn primary onClick={() => openForm(receiptUrl)} onPointerEnter={() => openForm.prefetch?.(receiptUrl)}>{t("Record receipt")}</DBtn>
      ) : null}
    </>
  );
  const hasActions = showCloseDiff || showReopenDiff || showRecord;

  const allocated = pos ? pos.allocated : rem.allocated_sar;
  const notAllocated = pos ? pos.unallocated : rem.unallocated_sar;
  const facts = [
    { k: t("Sent"), v: `${fmt(rem.total_sar)} SAR`, strong: true },
    { k: t("Received at HQ"), v: `${fmt(receivedSar)} SAR` },
    allocated != null && { k: t("Allocated"), v: `${fmt(allocated)} SAR` },
    notAllocated != null && { k: t("Not allocated"), v: `${fmt(notAllocated)} SAR`, tone: notAllocated > 0 ? "warning" : undefined, strong: notAllocated > 0 },
    { k: t("Date"), v: fmtDate(rem.date) },
    rem.from_account && { k: t("From account"), v: rem.from_account },
    rem.receipt_reference && { k: t("Reference"), v: rem.receipt_reference },
    rem.amount_idr != null && { k: t("Amount IDR"), v: `${fmt(rem.amount_idr)} IDR` },
    rem.exchange_rate != null && { k: t("Exchange rate"), v: fmt(rem.exchange_rate) },
    fx?.avg_rate != null && !(fx.is_legacy && fx.original_amount == null) && { k: fx.is_legacy ? t("Original rate") : t("Average rate"), v: fmt(fx.avg_rate) },
    fx?.original_amount != null && { k: t("Original amount"), v: `${fmt(fx.original_amount)} IDR` },
    fx?.profit_idr != null && { k: t("FX profit"), v: `${fmt(fx.profit_idr)} IDR${fx.fully_covered ? "" : " *"}`, tone: fx.profit_idr >= 0 ? "success" : "danger" },
    fx?.is_legacy && fx.original_amount == null && { k: t("FX profit"), v: t("Fill in the original amount (Edit)") },
  ];

  const badge = isReceived ? { label: t("Received"), tone: "green" }
    : partial ? { label: t("Partially received"), tone: "info" }
      : { label: t("Pending"), tone: "amber" };

  const settlements = rem.settlements || [];

  return (
    <DPage>
      <DTop href="/remittance/" />

      {sentence ? <DBanner tone={tone} actions={hasActions ? actions : null}>{sentence}</DBanner> : null}
      {!sentence && hasActions ? <DBanner tone="gray" actions={actions}>{t("Fully received.")}</DBanner> : null}

      <DHead
        title={rem.remittance_number}
        badge={badge}
        menu={[canEdit && { label: t("Edit"), icon: "edit", onClick: () => openForm(`/remittance/${rem.id}/edit/`) }]}
        chips={rem.proof_url ? [<DChip key="proof" href={rem.proof_url} icon="clip" label={t("Open transfer proof")}>{decodeURIComponent(rem.proof_url.split("/").pop())}</DChip>] : null}
        cols={4}
        facts={facts}
        note={rem.note ? { text: rem.note } : null}
      />

      {lines.length ? (
        <DCard title={t("Allocated when sent")} count={lines.length}>
          <DLines>
            {lines.map((row, i) => (
              <DLine key={i} mono title={row.linked_number}
                sub={[row.invoice?.customer_name, row.hotel, row.check_in].filter(Boolean).join(" · ")}
                value={fmt(row.amount_sar)} valueSub={row.prev_sent ? t("{n} sent before", { n: fmt(row.prev_sent) }) : null} />
            ))}
            <DLinesTotal label={t("Total sent")}>{fmt(rem.total_sar)} SAR</DLinesTotal>
          </DLines>
          <div className={DA.scrollWide}>
            <table data-slot="detail-table" className={DA.table}>
              <thead><tr><th>{t("Reservation")}</th><th>{t("Stay")}</th><th className={DC.n}>{t("Sent before")}</th><th className={DC.n}>{t("Sent now")}</th></tr></thead>
              <tbody>
                {lines.map((row, i) => (
                  <tr key={i}>
                    <td><span className={DC.mono}>{row.linked_number}</span>{row.invoice ? <span className={DC.sub}>{row.invoice.customer_name}</span> : null}</td>
                    <td>{[row.hotel, row.check_in].filter(Boolean).join(", ") || t("Not set")}</td>
                    <td className={DC.n}>{row.prev_sent ? fmt(row.prev_sent) : ""}</td>
                    <td className={cn(DC.n, DC.bold)}>{fmt(row.amount_sar)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot><tr><td colSpan={3}>{t("Total sent")}</td><td className={DC.n}>{fmt(rem.total_sar)} SAR</td></tr></tfoot>
            </table>
          </div>
        </DCard>
      ) : null}

      <DCard title={t("Receipts at HQ")} count={settlements.length || null}>
        {settlements.length ? (
          <>
          <DLines>
            {settlements.map((s) => {
              const gap = s.received_amount_sar - s.allocations.reduce((sum, a) => sum + a.amount_sar, 0);
              return (
                <Fragment key={s.id}>
                  <DLine title={t("Received {date}", { date: fmtDate(s.received_date) })} sub={s.reference ? t("Ref {ref}", { ref: s.reference }) : null}
                    value={<span className="inline-flex items-center gap-1">{fmt(s.received_amount_sar)}
                      <DMenu small label={t("Receipt actions")} items={[
                        canReceive && rem.can_allocate && { label: t("Change allocation"), icon: "edit", onClick: () => openForm(allocationUrl(s)) },
                        canDelete && perms.headOffice && s.can_delete && { label: t("Delete receipt"), icon: "trash", danger: true, onClick: () => deleteReceipt(s) },
                      ]} /></span>} />
                  {rem.can_allocate ? s.allocations.map((a, i) => (
                    <DLine key={i} mono title={a.linked_number}
                      sub={[a.customer_name, a.hotel, a.check_in && fmtDate(a.check_in)].filter(Boolean).join(" · ")} value={fmt(a.amount_sar)} />
                  )) : null}
                  {rem.can_allocate && gap ? (
                    <DLine title={gap > 0 ? t("Not allocated yet") : t("Allocated beyond this receipt")} value={fmt(Math.abs(gap))} valueTone="text-warning-text" />
                  ) : null}
                </Fragment>
              );
            })}
            <DLinesTotal label={t("Total received")}>{fmt(receivedSar)} SAR</DLinesTotal>
          </DLines>
          <div className={DA.scrollWide}>
            <table data-slot="detail-table" className={DA.table}>
              <thead>
                <tr>
                  <th>{t("Reservation")}</th><th>{t("Stay")}</th><th className={DC.n}>{t("Amount (SAR)")}</th>
                  <th className={DC.acts} style={{ paddingLeft: 4, paddingRight: 12 }}><span className="sr-only">{t("Actions")}</span></th>
                </tr>
              </thead>
              {settlements.map((s) => {
                const alloc = s.allocations.reduce((sum, a) => sum + a.amount_sar, 0);
                const gap = s.received_amount_sar - alloc;
                return (
                  <Fragment key={s.id}>
                    <tbody>
                      <tr className={DA.rowGroup}>
                        <td colSpan={2}>
                          <span style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                            <span style={{ fontWeight: 600, color: "var(--foreground)" }}>{t("Received {date}", { date: fmtDate(s.received_date) })}</span>
                            {s.reference ? <span>{t("Ref {ref}", { ref: s.reference })}</span> : null}
                          </span>
                        </td>
                        <td className={DC.n} style={{ fontWeight: 600, color: "var(--foreground)" }}>{fmt(s.received_amount_sar)}</td>
                        <td style={{ paddingTop: 4, paddingBottom: 4, paddingLeft: 4, paddingRight: 12 }}>
                          <DMenu small label={t("Receipt actions")} items={[
                            canReceive && rem.can_allocate && { label: t("Change allocation"), icon: "edit", onClick: () => openForm(allocationUrl(s)) },
                            canDelete && perms.headOffice && s.can_delete && { label: t("Delete receipt"), icon: "trash", danger: true, onClick: () => deleteReceipt(s) },
                          ]} />
                        </td>
                      </tr>
                      {rem.can_allocate ? s.allocations.map((a, i) => (
                        <tr key={i} className={cn(i === s.allocations.length - 1 && !gap ? DA.rowLast : undefined)}>
                          <td><span className={DC.mono}>{a.linked_number}</span>{a.customer_name ? <span className={DC.sub}>{a.customer_name}</span> : null}</td>
                          <td>{a.hotel || t("Not set")}{a.check_in ? <span className={DC.sub}>{t("Check-in {date}", { date: fmtDate(a.check_in) })}</span> : null}</td>
                          <td className={DC.n}>{fmt(a.amount_sar)}</td>
                          <td />
                        </tr>
                      )) : null}
                      {rem.can_allocate && gap ? (
                        <tr className={DA.rowLast}>
                          <td colSpan={2} className={DC.mut}>{gap > 0 ? t("Not allocated yet") : t("Allocated beyond this receipt")}</td>
                          <td className={DC.n} style={{ color: "var(--warning-text)" }}>{fmt(Math.abs(gap))}</td>
                          <td />
                        </tr>
                      ) : null}
                      {rem.can_allocate && !s.allocations.length && !gap ? (
                        <tr className={DA.rowLast}><td colSpan={4} className={DC.mut}>{t("Not allocated to any reservation yet.")}</td></tr>
                      ) : null}
                    </tbody>
                  </Fragment>
                );
              })}
              <tfoot>
                <tr><td colSpan={2}>{t("Total received")}</td><td className={DC.n}>{fmt(receivedSar)} SAR</td><td /></tr>
                {pos && pos.in_transit > 0 ? (
                  <tr className={cn(DA.rowSoft, DA.rowAfter)}><td colSpan={2} style={{ paddingBottom: 16 }}>{t("Still in transit")}</td><td className={DC.n} style={{ paddingBottom: 16 }}>{fmt(pos.in_transit)} SAR</td><td /></tr>
                ) : null}
              </tfoot>
            </table>
          </div>
          </>
        ) : (
          <div className={DA.empty}>{t("No receipt yet. Money is allocated to reservations when HQ records the receipt.")}</div>
        )}
      </DCard>

      {confirmDialog}
    </DPage>
  );
}
