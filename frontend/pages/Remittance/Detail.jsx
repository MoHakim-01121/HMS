import { router } from "@inertiajs/react";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import { DvLink } from "../../components/shadcn/item-row.jsx";
import { RvBack, RvHero, RvFigure, RvSteps, RvCard, RvSection, RvRail } from "../../components/shadcn/record-view.jsx";
import { Icon } from "../../components/icons.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

const WARN = { icon: <Icon name="alert-circle" size={13} strokeWidth={2} />, iconBg: "var(--yellow)" };
const OK = { icon: <Icon name="check" size={12} strokeWidth={2.4} />, iconBg: "var(--green)" };

export default function Detail({ rem, lines, fx }) {
  const { t } = useI18n();
  const openForm = useFormModal();
  const perms = usePerms();
  const canEdit = perms.can("remittance", "edit");
  const canDelete = perms.can("remittance", "delete");
  // Receipts are head office's: a branch sends, head office records what came in.
  const canReceive = canEdit && perms.headOffice;
  const [confirm, confirmDialog] = useConfirm();

  // Satu status: rem.status. Untuk remittance dengan penerimaan tercatat,
  // status disinkronkan otomatis di backend (hw/finance/settlement_service.py).
  // `legacy` = remittance lama yang memakai received_amount_sar manual.
  const legacy = rem.received_amount_sar != null;
  const isReceived = rem.status === "received";
  const receivedSar = legacy ? rem.received_amount_sar : rem.settled_total_sar;
  const basisSar = legacy ? rem.expected_sar : rem.settlement_basis_sar;
  const partial = !legacy && !isReceived && receivedSar > 0;
  const remainingSar = basisSar != null ? Math.max(0, basisSar - receivedSar) : 0;

  const deleteReceipt = (s) => {
    confirm({
      title: t("Delete receipt"),
      message: t("Delete the {n} SAR receipt of {date}? Its journal entries and allocations are reversed; the remittance goes back to waiting for this money.", { n: fmt(s.received_amount_sar), date: s.received_date }),
      confirmLabel: "Delete",
      danger: true,
      onConfirm: () => router.post(`/remittance/${rem.id}/receipt/${s.id}/delete/`),
    });
  };

  const closeDiff = () => {
    confirm({
      title: t("Close Difference"),
      message: rem.diff_sar > 0
        ? t("Book the {n} SAR shortfall on {remittance} as a bank fee/FX loss and mark it received? No further receipts can be recorded unless you reopen it.", { n: fmt(rem.diff_sar), remittance: rem.remittance_number })
        : t("Book the {n} SAR surplus on {remittance} as an FX gain? It cannot be edited unless you reopen it.", { n: fmt(-rem.diff_sar), remittance: rem.remittance_number }),
      confirmLabel: "Close Difference",
      danger: false,
      icon: "alert",
      onConfirm: () => router.post(`/remittance/${rem.id}/close-diff/`),
    });
  };

  const reopenDiff = () => {
    confirm({
      title: t("Reopen Difference"),
      message: t("Reverse the difference booked on {remittance}? It goes back to pending if HQ has not received the full amount, so receipts can be corrected and the difference closed again.", { remittance: rem.remittance_number }),
      confirmLabel: "Reopen Difference",
      danger: false,
      icon: "alert",
      onConfirm: () => router.post(`/remittance/${rem.id}/reopen-diff/`),
    });
  };

  const steps = [
    { label: t("Sent"), state: "done" },
    { label: t("Received at HQ"), state: isReceived ? "done" : "now" },
    ...(rem.unallocated_sar > 0 ? [{ label: t("Allocated"), state: isReceived ? "now" : "todo" }] : []),
  ];

  const pos = rem.position;
  const receiptUrl = `/remittance/${rem.id}/receipt/?next=/remittance/${rem.id}/`;
  const allocationUrl = (s) => `/remittance/${rem.id}/receipt/${s.id}/allocation/?next=/remittance/${rem.id}/`;

  let note;
  if (pos && pos.received_unallocated > 0) {
    note = {
      ...WARN,
      title: t("{n} SAR received but not allocated", { n: fmt(pos.received_unallocated) }),
      text: t("Allocate it to reservations with Change allocation on the receipt below."),
    };
  } else if (!isReceived) {
    if (partial) {
      note = {
        ...WARN,
        title: t("{n} SAR received of {total}", { n: fmt(receivedSar), total: fmt(basisSar) }),
        text: rem.can_close_diff
          ? t("Still {n} SAR outstanding — record the next receipt as it arrives, or close the difference if nothing more will arrive.", { n: fmt(remainingSar) })
          : t("Received in stages — see receipts below."),
      };
    } else if (legacy) {
      note = { ...WARN, title: t("Awaiting confirmation"), text: t("The HQ office has not confirmed this amount yet.") };
    } else {
      note = { ...WARN, title: t("Awaiting receipt at HQ"), text: t("Record the receipt once HQ confirms the transfer arrived.") };
    }
  } else if (rem.can_close_diff) {
    note = { ...WARN, title: t("{n} SAR more than sent", { n: fmt(-rem.diff_sar) }), text: t("Close the difference to book it as an FX gain.") };
  } else if (rem.unallocated_sar > 0) {
    note = { ...WARN, title: t("{n} SAR unallocated", { n: fmt(rem.unallocated_sar) }), text: t("Some of the received amount is not yet allocated.") };
  } else {
    note = {
      ...OK,
      title: t("Fully received"),
      text: rem.diff_closed && rem.diff_sar
        ? t("{n} SAR difference booked as bank fee/FX.", { n: fmt(Math.abs(rem.diff_sar)) })
        : t("HQ has received the full amount."),
    };
  }

  const detailRows = [
    rem.from_account ? { k: t("From Account"), v: rem.from_account } : null,
    rem.receipt_reference ? { k: t("Reference"), v: rem.receipt_reference } : null,
    rem.amount_idr != null ? { k: t("Amount IDR"), v: `${fmt(rem.amount_idr)} IDR` } : null,
    rem.exchange_rate != null ? { k: t("Exchange rate"), v: fmt(rem.exchange_rate) } : null,
    rem.expected_sar != null ? { k: t("Expected in SAR"), v: `${fmt(rem.expected_sar)} SAR` } : null,
    fx?.original_amount != null ? { k: t("Original amount (IDR)"), v: `${fmt(fx.original_amount)} IDR` } : null,
    fx?.avg_rate != null && !(fx.is_legacy && fx.original_amount == null)
      ? { k: fx.is_legacy ? t("Original rate") : t("Average rate"), v: fmt(fx.avg_rate) } : null,
    fx?.profit_idr != null ? { k: t("FX profit (IDR)"), v: `${fmt(fx.profit_idr)} IDR${fx.fully_covered ? "" : " *"}` } : null,
    fx?.is_legacy && fx.original_amount == null ? { k: t("FX profit (IDR)"), v: t("— fill in the original amount (Edit)") } : null,
    pos
      ? { k: t("Not allocated"), v: `${fmt(pos.unallocated)} SAR` }
      : { k: t("Reservations"), v: lines.length === 1 ? t("1 line") : t("{n} lines", { n: lines.length }) },
  ].filter(Boolean);

  const figureColor = isReceived ? "var(--green)" : "var(--yellow)";
  const figureNote = legacy
    ? (rem.expected_sar != null && rem.received_amount_sar !== rem.expected_sar
        ? `${t("FX/fee difference")}: ${fmt(rem.received_amount_sar - rem.expected_sar)} SAR`
        : undefined)
    : t("{n} receipt(s)", { n: rem.settlements.length });

  const showRecord = canReceive && rem.can_record_receipt;
  const showCloseDiff = canReceive && rem.can_close_diff;
  const showReopenDiff = canReceive && rem.can_reopen_diff;

  return (
    <div className="page shadcn-root hms-rv-page">
      <style>{CSS}</style>
      <RvBack href="/remittance/" label={t("Back")} />

      <RvHero
        kicker={rem.remittance_number}
        badge={
          isReceived ? { label: t("Received"), tone: "green" }
            : partial ? { label: t("Partially received"), tone: "blue" }
              : { label: t("Pending"), tone: "yellow" }
        }
        title={`${fmt(rem.total_sar)} SAR`}
        facts={[
          { k: t("Date"), v: rem.date },
          pos
            ? { k: t("Allocated"), v: t("{a} of {b}", { a: fmt(pos.allocated), b: fmt(pos.expected) }) }
            : { k: t("Lines"), v: lines.length },
        ]}
        mainExtra={<RvSteps steps={steps} />}
        side={
          receivedSar > 0 ? (
            <RvFigure
              label={t("Received at HQ")}
              value={fmt(receivedSar)}
              unit="SAR"
              color={figureColor}
              bar={basisSar > 0 ? { pct: `${Math.min(100, (receivedSar / basisSar) * 100)}%`, color: figureColor } : undefined}
              note={figureNote}
            />
          ) : null
        }
        note={note}
        actions={
          <>
            {rem.proof_url ? (
              <a className="hms-rv-btn" href={rem.proof_url} target="_blank" rel="noreferrer">{t("Receipt")}</a>
            ) : null}
            {showRecord && (
              <button type="button" className="hms-rv-btn primary" onClick={() => openForm(receiptUrl)} onPointerEnter={() => openForm.prefetch?.(receiptUrl)}>
                {t("Record Receipt")}
              </button>
            )}
            {showCloseDiff && (showRecord ? (
              <button type="button" className="hms-rv-linkbtn" onClick={closeDiff}>{t("Close Difference")}</button>
            ) : (
              <button type="button" className="hms-rv-btn primary" onClick={closeDiff}>{t("Close Difference")}</button>
            ))}
            {showReopenDiff && (
              <button type="button" className="hms-rv-linkbtn" onClick={reopenDiff}>{t("Reopen Difference")}</button>
            )}
            {canEdit && (
              <button
                type="button"
                className={showRecord || showCloseDiff ? "hms-rv-btn" : "hms-rv-btn primary"}
                onClick={() => openForm(`/remittance/${rem.id}/edit/`)}
              >
                {t("Edit")}
              </button>
            )}
          </>
        }
      />

      {confirmDialog}

      <div className="hms-rv-grid">
        <div className="hms-rv-col">
          <RvCard>
            {(!pos || lines.length > 0) && (
            <RvSection title={pos ? t("Allocated when sent") : t("Per Reservation")} meta={lines.length ? `${lines.length}` : undefined} first>
              <DetailTable
                columns={[
                  {
                    header: t("Reservation"),
                    strong: true,
                    render: (row) => (
                      <>
                        {row.linked_number}
                        {row.invoice ? <DvLink href={`/invoice/${row.invoice.pk}/`}>INV</DvLink> : null}
                        {row.invoice ? <span className="sub">{row.invoice.customer_name}</span> : null}
                      </>
                    ),
                  },
                  {
                    header: t("Stay"),
                    render: (row) => [row.hotel, row.check_in].filter(Boolean).join(", ") || t("Not set"),
                  },
                  { header: t("Sent before"), align: "right", render: (row) => (row.prev_sent ? fmt(row.prev_sent) : null) },
                  { header: t("Sent now"), align: "right", strong: true, render: (row) => fmt(row.amount_sar) },
                ]}
                rows={lines}
                empty={t("No reservation lines")}
                footer={lines.length ? [{ label: t("Total sent"), value: `${fmt(rem.total_sar)} SAR`, total: true }] : null}
              />
            </RvSection>
            )}

            {rem.settlements.length ? (
              <RvSection title={t("Receipts at HQ")} meta={`${rem.settlements.length}`} first={!!pos && !lines.length}>
                {rem.settlements.map((s) => {
                  const allocated = s.allocations.reduce((sum, a) => sum + a.amount_sar, 0);
                  return (
                    <div className="rmt-receipt" key={s.id}>
                      <div className="rmt-receipt-h">
                        <span className="rmt-receipt-t">
                          {s.received_date} · <b>{fmt(s.received_amount_sar)} SAR</b>
                          {s.reference ? <span className="rmt-receipt-ref"> · {t("ref")} {s.reference}</span> : null}
                        </span>
                        <span className="rmt-receipt-acts">
                          {canReceive && rem.can_allocate && (
                            <button type="button" className="hms-rv-linkbtn" onClick={() => openForm(allocationUrl(s))}>
                              {t("Change allocation")}
                            </button>
                          )}
                          {canDelete && perms.headOffice && s.can_delete && (
                            <button type="button" className="hms-rv-linkbtn rmt-receipt-del" onClick={() => deleteReceipt(s)}>
                              {t("Delete")}
                            </button>
                          )}
                        </span>
                      </div>
                      {rem.can_allocate && (
                        <DetailTable
                          columns={[
                            {
                              header: t("Reservation"),
                              strong: true,
                              render: (a) => (<>{a.linked_number}{a.customer_name ? <span className="sub">{a.customer_name}</span> : null}</>),
                            },
                            { header: t("Stay"), render: (a) => [a.hotel, a.check_in].filter(Boolean).join(", ") || t("Not set") },
                            { header: t("Allocated (SAR)"), align: "right", strong: true, render: (a) => fmt(a.amount_sar) },
                          ]}
                          rows={s.allocations}
                          empty={t("Not allocated to any reservation yet.")}
                          footer={allocated !== s.received_amount_sar ? [{
                            label: allocated < s.received_amount_sar ? t("Not allocated yet") : t("Allocated beyond this receipt"),
                            value: `${fmt(Math.abs(s.received_amount_sar - allocated))} SAR`,
                          }] : null}
                        />
                      )}
                    </div>
                  );
                })}
                {pos && pos.in_transit > 0 ? (
                  <p className="rmt-receipt-foot">{t("{n} SAR still in transit.", { n: fmt(pos.in_transit) })}</p>
                ) : null}
              </RvSection>
            ) : pos && !lines.length ? (
              <RvSection title={t("Receipts at HQ")} first>
                <p className="rmt-receipt-foot" style={{ borderTop: "none" }}>
                  {t("No receipt yet. Money is allocated to reservations when HQ records the receipt.")}
                </p>
              </RvSection>
            ) : null}

            {rem.note ? (
              <RvSection title={t("Notes")}>
                <div className="hms-rv-railtext">{rem.note}</div>
              </RvSection>
            ) : null}
          </RvCard>
        </div>

        <RvRail rows={detailRows} />
      </div>
    </div>
  );
}

const CSS = `
.rmt-receipt { padding: 0 22px 14px; }
.rmt-receipt + .rmt-receipt { padding-top: 14px; border-top: 1px solid var(--border); }
.rmt-receipt-h { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
.rmt-receipt-t { font-size: 13px; color: var(--foreground); font-variant-numeric: tabular-nums; }
.rmt-receipt-t b { font-weight: 600; }
.rmt-receipt-ref { color: var(--muted-foreground); }
.rmt-receipt-acts { display: inline-flex; gap: 14px; }
.rmt-receipt-del { color: var(--destructive); }
.rmt-receipt-foot { margin: 0; padding: 12px 22px 16px; font-size: 12.5px; color: var(--muted-foreground); border-top: 1px solid var(--border); }
`;
