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
import { fmt } from "../../utils/format.js";

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
            rem.amount_idr != null && { label: t("Amount IDR"), value: fmt(rem.amount_idr) + " IDR", icon: "invoice" },
            rem.exchange_rate != null && { label: t("Exchange rate"), value: fmt(rem.exchange_rate), icon: "invoice" },
            rem.expected_sar != null && { label: t("Expected (IDR/kurs)"), value: `${fmt(rem.expected_sar)} SAR`, icon: "invoice" },
            rem.received_amount_sar != null && { label: t("Received at HQ"), value: `${fmt(rem.received_amount_sar)} SAR`, icon: "remittance" },
            { label: t("Reservations"), value: lines.length === 1 ? t("1 line") : t("{n} lines", { n: lines.length }), icon: "hotels" },
            rem.note && { label: t("Note"), value: rem.note, icon: "message", span2: true, pre: true },
          ]}
        />

        {rem.received_amount_sar != null && (
          <Section
            label={t("Allocation")}
            icon="remittance"
            right={
              rem.unallocated_sar > 0
                ? <span className="badge badge-yellow">{t("{n} SAR unallocated", { n: fmt(rem.unallocated_sar) })}</span>
                : rem.unallocated_sar === 0 && rem.allocated_sar > 0
                  ? <span className="badge badge-green">{t("Fully allocated")}</span>
                  : null
            }
          >
            <div style={{ padding: "4px 0" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 6 }}>
                <span>{t("Allocated to reservations")}</span>
                <span className="mono">{fmt(rem.allocated_sar)} / {fmt(rem.received_amount_sar)} SAR</span>
              </div>
              <div style={{ height: 6, borderRadius: 3, background: "var(--muted)", overflow: "hidden" }}>
                <div style={{
                  height: "100%",
                  width: `${Math.min(100, rem.received_amount_sar ? (rem.allocated_sar / rem.received_amount_sar) * 100 : 0)}%`,
                  background: "var(--accent-2, var(--primary))",
                }} />
              </div>
              {rem.expected_sar != null && rem.received_amount_sar !== rem.expected_sar && (
                <div style={{ fontSize: 12, color: "var(--muted-foreground)", marginTop: 8 }}>
                  {t("FX/fee difference")}: {fmt(rem.received_amount_sar - rem.expected_sar)} SAR
                </div>
              )}
            </div>
          </Section>
        )}

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
