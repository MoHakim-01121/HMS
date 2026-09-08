import DetailTable from "../../components/shadcn/detail-table.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import { DvLink } from "../../components/shadcn/item-row.jsx";
import { RvBack, RvHero, RvFigure, RvCard, RvSection, RvRail, RvRailBlock } from "../../components/shadcn/record-view.jsx";
import { Icon } from "../../components/icons.jsx";
import LastBilling from "../../components/ui/LastBilling.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

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
  const canEdit = perms.can("services", "edit");

  const actions = (
    <>
      {!paid && <a className="hms-rv-btn primary" href={`/finance/payments/?invoice=${invoice.pk}`}>{t("Record Payment")}</a>}
      {canEdit && (
        <button type="button" className="hms-rv-btn" onClick={() => openDraft(paid ? "services_lunas" : "services", invoice.pk, wa_send)}>
          {paid ? t("Paid Message") : t("Draft Message")}
        </button>
      )}
      <a className="hms-rv-btn" href={`/services/${invoice.pk}/pdf/`} target="_blank" rel="noreferrer">PDF</a>
      {canEdit && (
        <button type="button" className={paid ? "hms-rv-btn primary" : "hms-rv-btn"} onClick={() => openForm(`/services/${invoice.pk}/edit/`)}>
          {t("Edit")}
        </button>
      )}
    </>
  );

  const facts = [
    { k: t("Invoice total"), v: `${fmt(servicesTotal)} ${cur}` },
    { k: t("Issued"), v: invoice.issued_date || invoice.created_at || t("Not issued") },
  ];
  if (!paid && invoice.due_date) facts.push({ k: t("Due"), v: invoice.due_date });
  facts.push({ k: t("Currency"), v: cur });

  return (
    <div className="page shadcn-root hms-rv-page">
      <RvBack href="/services/" label={t("Back")} />

      <RvHero
        kicker={invoice.invoice_number}
        badge={{ label: t(hero.label), tone: hero.tone }}
        title={invoice.customer_name}
        facts={facts}
        side={
          <RvFigure
            label={paid ? t("Paid in full") : t("Amount due")}
            value={fmt(paid ? servicesTotal : services_remaining)}
            unit={cur}
            color={paid ? "var(--green)" : "var(--red)"}
            bar={{
              pct: servicesTotal > 0 ? `${Math.min(100, (paidTotal / servicesTotal) * 100)}%` : "0%",
              color: paid ? "var(--green)" : "var(--yellow)",
            }}
            note={`${fmt(paidTotal)} ${t("of")} ${fmt(servicesTotal)} ${cur} ${t("paid")}`}
          />
        }
        note={
          paid
            ? { icon: <Icon name="check" size={12} strokeWidth={2.4} />, iconBg: "var(--green)", title: t("Paid in full") }
            : {
                icon: <Icon name="alert-circle" size={13} strokeWidth={2} />,
                iconBg: due_alert?.type === "red" ? "var(--red)" : "var(--yellow)",
                title: due_alert?.msg || t("Payment is still owed."),
                text: due_alert ? t("Payment is still owed.") : undefined,
              }
        }
        actions={actions}
      />

      <div className="hms-rv-grid">
        <div className="hms-rv-col">
          <RvCard>
            <RvSection title={t("Services")} meta={visa_services.length ? `${visa_services.length}` : undefined} first>
              <DetailTable
                columns={[
                  { header: "#SVC", strong: true, render: (svc) => svc.service_no },
                  { header: t("Product"), render: (svc) => svc.product },
                  { header: t("Qty"), render: (svc) => svc.qty },
                  { header: t("Price"), align: "right", render: (svc) => fmt(svc.price) },
                  {
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
            </RvSection>

            <RvSection title={t("Payments")} meta={payments_history.length ? `${payments_history.length}` : undefined}>
              <DetailTable
                columns={[
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
                  { header: t("Amount"), align: "right", render: (p) => `${fmt(p.payment_amount)} ${p.payment_currency}` },
                  { header: t("Rate"), align: "right", render: (p) => (p.payment_currency === cur ? "1.00" : p.payment_exchange) },
                  { header: t("Amount in {cur}", { cur }), align: "right", strong: true, render: (p) => fmt(p.payment_amount_main) },
                ]}
                rows={payments_history}
                empty={t("No payments")}
                footer={payments_history.length ? [{ label: t("Total received"), value: `${fmt(receivedTotal)} ${cur}`, total: true, tone: "green" }] : null}
              />
            </RvSection>
          </RvCard>
        </div>

        <RvRail
          rows={[
            { k: t("Issued"), v: invoice.issued_date || invoice.created_at || t("Not issued") },
            { k: t("Services"), v: `${visa_services.length}` },
            !paid && invoice.due_date ? { k: t("Due"), v: invoice.due_date } : null,
            { k: t("Currency"), v: cur },
          ].filter(Boolean)}
        >
          {last_billing ? (
            <RvRailBlock label={t("Billing")}>
              <LastBilling last={last_billing} />
            </RvRailBlock>
          ) : null}
        </RvRail>
      </div>
    </div>
  );
}