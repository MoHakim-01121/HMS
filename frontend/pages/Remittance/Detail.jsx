import DetailCard from "../../components/shadcn/detail-card.jsx";
import DetailGrid from "../../components/shadcn/detail-grid.jsx";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import Section from "../../components/shadcn/section.jsx";
import { DvLink } from "../../components/shadcn/item-row.jsx";
import FooterSummary, { FooterTotal } from "../../components/shadcn/footer-summary.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

export default function Detail({ rem, lines }) {
  const { t } = useI18n();
  const openForm = useFormModal();
  const perms = usePerms();

  return (
    <div className="page dv-page hms-dv-page shadcn-root">
      <PageBack href="/remittance/" />

      <DetailCard
        crumbs={[{ label: t("Remittance"), href: "/remittance/" }]}
        kicker={rem.remittance_number}
        title={`${fmt(rem.total_sar)} SAR`}
        sub={t("Sent to HQ · {date}", { date: rem.date })}
        pill={rem.status === "received" ? { label: t("Received"), tone: "green" } : { label: t("Pending"), tone: "yellow" }}
        actions={
          <>
            {rem.proof_url ? (
              <a className="hms-dv-act" href={rem.proof_url} target="_blank" rel="noreferrer">{t("Receipt")}</a>
            ) : null}
            {perms.can("remittance", "edit") && (
              <button type="button" className="hms-dv-act" onClick={() => openForm(`/remittance/${rem.id}/edit/`)}>{t("Edit")}</button>
            )}
          </>
        }
      >
        <DetailGrid
          rows={[
            { label: t("Remittance no"), value: rem.remittance_number, icon: "remittance" },
            { label: t("Date"), value: rem.date, icon: "calendar" },
            rem.receipt_reference && { label: t("Reference"), value: rem.receipt_reference, icon: "file-text" },
            { label: t("Reservations"), value: lines.length === 1 ? t("1 line") : t("{n} lines", { n: lines.length }), icon: "hotels" },
            rem.note && { label: t("Note"), value: rem.note, icon: "message", span2: true, pre: true },
          ]}
        />

        <Section label={t("Per Reservation")} icon="hotels" count={lines.length || null} right={t("Sent Now")}>
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
                render: (row) => [row.hotel, row.check_in].filter(Boolean).join(", ") || "—",
              },
              { header: t("Sent before"), align: "right", render: (row) => (row.prev_sent ? fmt(row.prev_sent) : "—") },
              { header: t("Sent now"), align: "right", strong: true, render: (row) => fmt(row.amount_sar) },
            ]}
            rows={lines}
            empty={t("No reservation lines")}
            footer={lines.length ? [{ label: t("Total sent"), value: `${fmt(rem.total_sar)} SAR`, total: true }] : null}
          />
        </Section>

        <FooterSummary right={<FooterTotal label={t("Total")} value={fmt(rem.total_sar)} currency="SAR" />} />
      </DetailCard>
    </div>
  );
}
