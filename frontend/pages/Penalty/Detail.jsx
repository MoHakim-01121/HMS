import { router } from "@inertiajs/react";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { DPage, DTop, DHead, DBanner, DCard, DA } from "../../components/shadcn/detail-a.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

// Penalty detail, in the detail-page language of the Record View HMS canvas
// (no artboard of its own): a strip when the penalty is not billed, the head
// card with its facts, then the reason.
export default function Detail({ penalty: p }) {
  const { t } = useI18n();
  const openForm = useFormModal();
  const perms = usePerms();
  const [confirm, confirmDialog] = useConfirm();
  const del = () => confirm({
    title: t("Delete penalty"),
    message: t("Delete penalty document {number}?", { number: p.penalty_number }),
    danger: true,
    onConfirm: () => router.post(`/penalty/${p.id}/delete/`),
  });

  return (
    <DPage>
      <DTop href={`/cl/${p.cl.id}/`} />

      {!p.is_paid && !p.invoice ? (
        <DBanner tone="danger">
          <b>{t("Not billed.")}</b> {t("The invoice that billed this penalty was voided. Put the reservation on an invoice to bill it again.")}
        </DBanner>
      ) : null}

      <DHead
        title={p.penalty_number}
        badge={p.is_paid ? { label: t("Paid"), tone: "green" } : { label: t("Unpaid"), tone: "amber" }}
        menu={[
          { label: t("Download PDF"), icon: "pdf", href: `/penalty/${p.id}/pdf/`, external: true },
          perms.can("penalty", "edit") && { label: t("Edit"), icon: "edit", onClick: () => openForm(`/penalty/${p.id}/edit/`) },
          perms.can("penalty", "delete") && { label: t("Delete penalty…"), icon: "trash", danger: true, separator: true, onClick: del },
        ]}
        facts={[
          { k: p.is_paid ? t("Paid") : t("Penalty due"), v: `${fmt(p.penalty_amount)} ${p.penalty_currency}`, strong: true, tone: p.is_paid ? "success" : undefined },
          !p.is_paid && p.paid_sar > 0 && { k: t("Paid so far"), v: `${fmt(p.paid_sar)} SAR` },
          { k: t("Cancellation date"), v: p.cancellation_date || t("Not set") },
          p.is_paid && p.payment_date && { k: t("Payment date"), v: p.payment_date },
          { k: t("Guest"), v: p.cl.guest_name },
          { k: t("Confirmation Letter"), v: <a href={`/cl/${p.cl.id}/`}>{p.cl.confirmation_number}</a> },
          { k: t("Invoice"), v: p.invoice ? <a href={`/invoice/${p.invoice.id}/`}>{p.invoice.invoice_number}</a> : <span className="font-normal text-muted-foreground">{t("Not billed")}</span> },
        ]}
        note={p.note ? { label: t("Notes"), text: p.note } : null}
      />

      {p.reason ? (
        <DCard pad title={t("Reason")}>
          <p className={DA.text}>{p.reason}</p>
        </DCard>
      ) : null}

      {confirmDialog}
    </DPage>
  );
}
