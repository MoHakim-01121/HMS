import DetailTable from "../../components/shadcn/detail-table.jsx";
import { DvLink } from "../../components/shadcn/item-row.jsx";
import { RvBack, RvHero, RvFigure, RvSteps, RvCard, RvSection, RvRail } from "../../components/shadcn/record-view.jsx";
import { Icon } from "../../components/icons.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

export default function Detail({ rem, lines }) {
  const { t } = useI18n();
  const openForm = useFormModal();
  const perms = usePerms();

  const received = rem.received_amount_sar != null;
  const fullyAllocated = received && rem.unallocated_sar === 0 && rem.allocated_sar > 0;
  const steps = [
    { label: t("Sent"), state: "done" },
    { label: t("Received at HQ"), state: received ? "done" : "now" },
    { label: t("Allocated"), state: fullyAllocated ? "done" : received ? "now" : "todo" },
  ];

  const note = !received
    ? {
        icon: <Icon name="alert-circle" size={13} strokeWidth={2} />,
        iconBg: "var(--yellow)",
        title: t("Awaiting confirmation"),
        text: t("The HQ office has not confirmed this amount yet."),
      }
    : fullyAllocated
      ? {
          icon: <Icon name="check" size={12} strokeWidth={2.4} />,
          iconBg: "var(--green)",
          title: t("Fully allocated"),
          text: t("Every SAR of this remittance is assigned to a reservation."),
        }
      : {
          icon: <Icon name="alert-circle" size={13} strokeWidth={2} />,
          iconBg: "var(--yellow)",
          title: t("{n} SAR unallocated", { n: fmt(rem.unallocated_sar) }),
          text: t("Some of the received amount is not yet allocated."),
        };

  const detailRows = [
    rem.receipt_reference ? { label: t("Reference"), value: rem.receipt_reference } : null,
    rem.amount_idr != null ? { label: t("Amount IDR"), value: `${fmt(rem.amount_idr)} IDR` } : null,
    rem.exchange_rate != null ? { label: t("Exchange rate"), value: fmt(rem.exchange_rate) } : null,
    rem.expected_sar != null ? { label: t("Expected in SAR"), value: `${fmt(rem.expected_sar)} SAR` } : null,
    { label: t("Reservations"), value: lines.length === 1 ? t("1 line") : t("{n} lines", { n: lines.length }) },
  ].filter(Boolean);

  return (
    <div className="page shadcn-root hms-rv-page">
      <RvBack href="/remittance/" label={t("Back")} />

      <RvHero
        kicker={rem.remittance_number}
        badge={received ? { label: t("Received"), tone: "green" } : { label: t("Pending"), tone: "yellow" }}
        title={`${fmt(rem.total_sar)} SAR`}
        facts={[
          { k: t("Date"), v: rem.date },
          { k: t("Lines"), v: lines.length },
        ]}
        mainExtra={<RvSteps steps={steps} />}
        side={
          received ? (
            <RvFigure
              label={t("Received at HQ")}
              value={fmt(rem.received_amount_sar)}
              unit="SAR"
              color={fullyAllocated ? "var(--green)" : "var(--yellow)"}
              bar={{
                pct: rem.received_amount_sar > 0 ? `${Math.min(100, (rem.allocated_sar / rem.received_amount_sar) * 100)}%` : "0%",
                color: fullyAllocated ? "var(--green)" : "var(--yellow)",
              }}
              note={
                rem.expected_sar != null && rem.received_amount_sar !== rem.expected_sar
                  ? `${t("FX/fee difference")}: ${fmt(rem.received_amount_sar - rem.expected_sar)} SAR`
                  : undefined
              }
            />
          ) : null
        }
        note={note}
        actions={
          <>
            {rem.proof_url ? (
              <a className="hms-rv-btn" href={rem.proof_url} target="_blank" rel="noreferrer">{t("Receipt")}</a>
            ) : null}
            {perms.can("remittance", "edit") && (
              <button type="button" className="hms-rv-btn primary" onClick={() => openForm(`/remittance/${rem.id}/edit/`)}>
                {t("Edit")}
              </button>
            )}
          </>
        }
      />

      <div className="hms-rv-grid">
        <div className="hms-rv-col">
          <RvCard>
            <RvSection title={t("Per Reservation")} meta={lines.length ? `${lines.length}` : undefined} first>
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

            {rem.note ? (
              <RvSection title={t("Notes")}>
                <div className="hms-rv-railtext">{rem.note}</div>
              </RvSection>
            ) : null}
          </RvCard>
        </div>

        <RvRail
          rows={detailRows}
        />
      </div>
    </div>
  );
}