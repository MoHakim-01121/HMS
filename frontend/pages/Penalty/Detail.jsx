import { router } from "@inertiajs/react";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import DetailCard from "../../components/shadcn/detail-card.jsx";
import DetailGrid from "../../components/shadcn/detail-grid.jsx";
import DetailAmount from "../../components/shadcn/detail-amount.jsx";
import FooterSummary, { FooterTotal } from "../../components/shadcn/footer-summary.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

export default function Detail({ penalty: p }) {
  const { t } = useI18n();
  const openForm = useFormModal();
  const perms = usePerms();
  const [confirm, confirmDialog] = useConfirm();
  const del = () => confirm({ title: t("Delete penalty"), message: t("Delete penalty document {number}?", { number: p.penalty_number }), onConfirm: () => router.post(`/penalty/${p.id}/delete/`) });

  return (
    <div className="page dv-page hms-dv-page shadcn-root">
      <PageBack href={`/cl/${p.cl.id}/`} label={t("Back to CL")} />

      <DetailCard
        crumbs={[{ label: p.cl.confirmation_number, href: `/cl/${p.cl.id}/` }]}
        kicker={t("Cancellation Penalty")}
        title={p.penalty_number}
        sub={p.cl.guest_name}
        pill={p.is_paid ? { label: t("Paid"), tone: "green" } : { label: t("Unpaid"), tone: "yellow" }}
        actions={
          <>
            <a className="hms-dv-act" href={`/penalty/${p.id}/pdf/`} target="_blank" rel="noreferrer">{t("PDF")}</a>
            {perms.can("penalty", "edit") && (
              <button type="button" className="hms-dv-act" onClick={() => openForm(`/penalty/${p.id}/edit/`)}>{t("Edit")}</button>
            )}
          </>
        }
        menuItems={[perms.can("penalty", "delete") && { label: t("Delete"), onClick: del, danger: true }]}
      >
        <DetailGrid
          rows={[
            { label: t("Guest"), value: p.cl.guest_name, icon: "user" },
            { label: t("Confirmation Letter"), icon: "cl", value: <a href={`/cl/${p.cl.id}/`}>{p.cl.confirmation_number}</a> },
            p.cancellation_date && { label: t("Cancellation Date"), value: p.cancellation_date, icon: "calendar" },
            p.exchange_rate !== 1 && { label: t("Exchange Rate"), value: p.exchange_rate, icon: "invoice" },
            p.is_paid && { label: t("Payment Method"), value: p.payment_method || "—", icon: "wallet" },
            p.is_paid && p.payment_date && { label: t("Payment Date"), value: p.payment_date, icon: "calendar" },
            p.reason && { label: t("Reason"), value: p.reason, icon: "alert-circle", span2: true },
            p.is_paid && p.payment_note && { label: t("Payment Note"), value: p.payment_note, icon: "message", span2: true, pre: true },
            p.note && { label: t("Notes"), value: p.note, icon: "file-text", span2: true, pre: true },
          ]}
          right={
            <DetailAmount
              label={p.is_paid ? t("Paid") : t("Penalty Due")}
              value={fmt(p.penalty_amount)}
              currency={p.penalty_currency}
              tone={p.is_paid ? "green" : "red"}
            />
          }
        />

        <FooterSummary right={<FooterTotal label={t("Total Penalty")} value={fmt(p.penalty_amount)} currency={p.penalty_currency} />} />
      </DetailCard>
      {confirmDialog}
    </div>
  );
}
