import DetailCard from "../../components/shadcn/detail-card.jsx";
import DetailGrid from "../../components/shadcn/detail-grid.jsx";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import Section from "../../components/shadcn/section.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import { DvLink } from "../../components/shadcn/item-row.jsx";
import FooterSummary from "../../components/shadcn/footer-summary.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import LastBilling from "../../components/ui/LastBilling.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

function heroPill(total, remaining) {
  if (remaining <= 0) return { label: "Paid", tone: "green" };
  if (remaining < total) return { label: "Partial", tone: "yellow" };
  return { label: "Unpaid", tone: "red" };
}

function openDraft(type, pk, waSend) {
  window.dispatchEvent(new CustomEvent("open-draft", { detail: { type, pk, waSend } }));
}

export default function Detail({ invoice, visa_services, payments_history, services_remaining, due_alert, wa_send, last_billing }) {
  const openForm = useFormModal();
  const perms = usePerms();
  const { t } = useI18n();
  const cur = invoice.currency;
  const paid = services_remaining <= 0;
  const servicesTotal = visa_services.reduce((s, v) => s + (v.total || 0), 0);
  const paidTotal = visa_services.reduce((s, v) => s + (v.paid_int || 0), 0);
  const remainingTotal = visa_services.reduce((s, v) => s + Math.max(0, v.remaining || 0), 0);
  const receivedTotal = payments_history.reduce((s, p) => s + (p.payment_amount_main || 0), 0);
  const hero = heroPill(servicesTotal, services_remaining);

  return (
    <div className="page dv-page hms-dv-page shadcn-root">
      <PageBack href="/services/" />

      <DetailCard
        crumbs={[{ label: t("Services"), href: "/services/" }]}
        kicker={invoice.invoice_number}
        title={invoice.customer_name}
        sub={t("Services invoice")}
        pill={{ ...hero, label: t(hero.label) }}
        actions={
          <>
            <a className="hms-dv-act" href={`/services/${invoice.pk}/pdf/`} target="_blank" rel="noreferrer">PDF</a>
            {perms.can("services", "edit") && (
              <button type="button" className="hms-dv-act" onClick={() => openForm(`/services/${invoice.pk}/edit/`)}>{t("Edit")}</button>
            )}
          </>
        }
      >
        {/* Four rows, two full columns — the same anatomy as Invoice and CL
            detail. The invoice number is not repeated here since it is already
            the kicker, the company is dropped (a record only ever renders under
            the company it belongs to), and the amount moves from the right-hand
            tile into the grid: that tile squeezed the grid until the Services
            row wrapped, and on a wholly unpaid invoice it only restated the
            footer's Total Amount. */}
        <DetailGrid
          rows={[
            { label: t("Issued"), value: invoice.issued_date || invoice.created_at || t("Not issued"), icon: "calendar" },
            {
              label: t("Services"),
              icon: "services",
              value: (
                <>
                  {visa_services.length} {t(visa_services.length === 1 ? "item" : "items")}
                  {invoice.due_date ? <span className="hms-dv-mval-sub"> · {t("due")} {invoice.due_date}</span> : null}
                </>
              ),
            },
            { label: t("Payments"), icon: "wallet", value: t("{count} received", { count: payments_history.length }) },
            {
              label: t(paid ? "Paid in full" : "Amount due"),
              icon: "invoice",
              color: paid ? "var(--green)" : "var(--red)",
              value: (
                <>
                  {fmt(paid ? servicesTotal : services_remaining)} {cur}
                  {!paid && due_alert ? <span className="hms-dv-mval-sub"> · {due_alert.msg}</span> : null}
                </>
              ),
            },
          ]}
        />

        <Section label={t("Services")} icon="services" count={visa_services.length || null} right={cur}>
          <DetailTable
            columns={[
              { header: "#SVC", strong: true, render: (svc) => svc.service_no },
              { header: t("Product"), render: (svc) => svc.product },
              { header: t("Qty"), render: (svc) => svc.qty },
              { header: t("Price"), align: "right", render: (svc) => fmt(svc.price) },
              {
                // Remaining has its own column, so the pill carries the state
                // word only instead of repeating the figure.
                header: t("Status"),
                align: "right",
                render: (svc) =>
                  svc.remaining <= 0 ? (
                    <StatusPill small label={t("Settled")} tone="green" />
                  ) : svc.remaining < svc.total ? (
                    <StatusPill small label={t("Partial")} tone="yellow" />
                  ) : (
                    <StatusPill small label={t("Unpaid")} tone="red" />
                  ),
              },
              { header: t("Total"), align: "right", strong: true, render: (svc) => fmt(svc.total) },
              { header: t("Paid"), align: "right", render: (svc) => <span style={{ color: svc.paid_int > 0 ? "var(--green)" : undefined }}>{fmt(svc.paid_int)}</span> },
              { header: t("Remaining"), align: "right", render: (svc) => fmt(Math.max(0, svc.remaining || 0)) },
            ]}
            rows={visa_services}
            empty={t("No service data")}
            footer={
              visa_services.length
                ? [{
                    label: t("Total"),
                    value: [`${fmt(servicesTotal)} ${cur}`, `${fmt(paidTotal)} ${cur}`, `${fmt(remainingTotal)} ${cur}`],
                    tone: [null, "green", remainingTotal > 0 ? "red" : null],
                    total: true,
                  }]
                : null
            }
          />
        </Section>

        <Section label={t("Payments")} icon="wallet" count={payments_history.length || null} right={cur}>
          <DetailTable
            columns={[
              // The only reference a services payment has is the service it
              // settles — same shape as Invoice's #REF column.
              { header: "#REF", strong: true, render: (p) => p.linked_number || t("Unlinked") },
              { header: t("Date"), render: (p) => p.payment_date || t("Not set") },
              {
                header: t("Method"),
                render: (p) => (
                  <>
                    {p.payment_method || t("Payment")}
                    {p.proof_url ? <DvLink href={p.proof_url} newTab>{t("Proof")}</DvLink> : null}
                  </>
                ),
              },
              // Original currency and rate get their own columns, so the
              // "IDR, rate 4810.00" sub-line under Method is retired.
              { header: t("Amount"), align: "right", render: (p) => `${fmt(p.payment_amount)} ${p.payment_currency}` },
              // A payment in the invoice's own currency settles at parity, so
              // the column shows 1.00 rather than a placeholder — every row
              // keeps a real number.
              { header: t("Rate"), align: "right", render: (p) => (p.payment_currency === cur ? "1.00" : p.payment_exchange) },
              { header: t("Amount {cur}", { cur }), align: "right", strong: true, render: (p) => fmt(p.payment_amount_main) },
            ]}
            rows={payments_history}
            empty={t("No payments")}
            footer={payments_history.length ? [{ label: t("Total received"), value: `${fmt(receivedTotal)} ${cur}`, total: true, tone: "green" }] : null}
          />
        </Section>

        {/* Billing collapses into the card's closing strip: one action plus the
            last log is not enough weight for a section of its own. The Paid /
            Total Amount figures that used to sit here are gone — each table
            already carries its own total, so the footer only repeated them.
            Sending calls /billing/send/, which the server guards with
            invoice.edit — a read-only role just sees the log. */}
        <FooterSummary
          left={<LastBilling last={last_billing} />}
          right={
            perms.can("invoice", "edit") ? (
              <Button type="button" onClick={() => openDraft(paid ? "services_lunas" : "services", invoice.pk, wa_send)}>
                {t(paid ? "Paid Message" : "Draft Message")}
              </Button>
            ) : null
          }
        />
      </DetailCard>
    </div>
  );
}
