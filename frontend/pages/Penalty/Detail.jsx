import { router } from "@inertiajs/react";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import KebabMenu from "../../components/shadcn/kebab-menu.jsx";
import { DvLink } from "../../components/shadcn/item-row.jsx";
import { RvBack, RvHero, RvFigure, RvCard, RvSection, RvRail } from "../../components/shadcn/record-view.jsx";
import { Icon } from "../../components/icons.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

export default function Detail({ penalty: p }) {
  const { t } = useI18n();
  const openForm = useFormModal();
  const perms = usePerms();
  const [confirm, confirmDialog] = useConfirm();
  const del = () => confirm({ title: t("Delete penalty"), message: t("Delete penalty document {number}?", { number: p.penalty_number }), onConfirm: () => router.post(`/penalty/${p.id}/delete/`) });

  const sections = [];
  if (p.reason) {
    sections.push({ title: t("Reason"), body: <div className="hms-rv-railtext">{p.reason}</div> });
  }
  if (p.note) {
    sections.push({ title: t("Notes"), body: <div className="hms-rv-railtext">{p.note}</div> });
  }

  return (
    <div className="page shadcn-root hms-rv-page">
      <RvBack href={`/cl/${p.cl.id}/`} label={t("Back to CL")} />

      <RvHero
        kicker={p.penalty_number}
        badge={p.is_paid ? { label: t("Paid"), tone: "green" } : { label: t("Unpaid"), tone: "yellow" }}
        title={p.cl.guest_name}
        facts={[
          p.cancellation_date ? { k: t("Cancellation Date"), v: p.cancellation_date } : null,
          p.is_paid && p.payment_date ? { k: t("Payment Date"), v: p.payment_date } : null,
          !p.is_paid && p.paid_sar > 0 ? { k: t("Paid so far"), v: `${fmt(p.paid_sar)} SAR` } : null,
        ].filter(Boolean)}
        side={
          <RvFigure
            label={p.is_paid ? t("Paid") : t("Penalty Due")}
            value={fmt(p.penalty_amount)}
            unit={p.penalty_currency}
            color={p.is_paid ? "var(--green)" : "var(--red)"}
          />
        }
        note={
          p.is_paid
            ? { icon: <Icon name="check" size={12} strokeWidth={2.4} />, iconBg: "var(--green)", title: t("Paid"), text: t("This penalty has been paid.") }
            : p.invoice
              ? { icon: <Icon name="alert-circle" size={13} strokeWidth={2} />, iconBg: "var(--yellow)", title: t("Penalty due"), text: t("This penalty has not been paid yet.") }
              : { icon: <Icon name="alert-circle" size={13} strokeWidth={2} />, iconBg: "var(--red)", title: t("Not billed"), text: t("The invoice that billed this penalty was voided. Put the reservation on an invoice to bill it again.") }
        }
        actions={
          <>
            <a className="hms-rv-btn" href={`/penalty/${p.id}/pdf/`} target="_blank" rel="noreferrer">{t("PDF")}</a>
            {perms.can("penalty", "edit") && (
              <button type="button" className="hms-rv-btn primary" onClick={() => openForm(`/penalty/${p.id}/edit/`)}>
                {t("Edit")}
              </button>
            )}
            <KebabMenu items={[perms.can("penalty", "delete") && { label: t("Delete"), onClick: del, danger: true }]} />
          </>
        }
      />

      <div className="hms-rv-grid">
        <div className="hms-rv-col">
          <RvCard>
            {sections.map((s, i) => (
              <RvSection key={s.title} title={s.title} first={i === 0}>
                {s.body}
              </RvSection>
            ))}
          </RvCard>
        </div>

        <RvRail rows={[
          { k: t("Confirmation Letter"), v: <DvLink href={`/cl/${p.cl.id}/`}>{p.cl.confirmation_number}</DvLink> },
          { k: t("Invoice"), v: p.invoice ? <DvLink href={`/invoice/${p.invoice.id}/`}>{p.invoice.invoice_number}</DvLink> : t("Not billed") },
        ]} />
      </div>

      {confirmDialog}
    </div>
  );
}