import DetailTable from "../../components/shadcn/detail-table.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import { DvLink } from "../../components/shadcn/item-row.jsx";
import { RvBack, RvHero, RvFigure, RvCard, RvSection, RvRail } from "../../components/shadcn/record-view.jsx";
import { Icon } from "../../components/icons.jsx";
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

export default function Detail({
  invoice, visa_services, payments_history, services_remaining, due_alert, wa_send,
  void: voidInfo = null, credit_notes = [], credited_sar = 0, can_void = false,
}) {
  const openForm = useFormModal();
  const perms = usePerms();
  const { t } = useI18n();
  const cur = invoice.currency;
  const isVoid = !!voidInfo;
  const paid = !isVoid && services_remaining <= 0;
  const servicesTotal = visa_services.reduce((s, v) => s + (v.total || 0), 0);
  const paidTotal = visa_services.reduce((s, v) => s + (v.paid_int || 0), 0);
  const remainingTotal = visa_services.reduce((s, v) => s + Math.max(0, v.remaining || 0), 0);
  const receivedTotal = payments_history.reduce((s, p) => s + (p.payment_amount_main || 0), 0);
  const dueTotal = isVoid ? 0 : servicesTotal - credited_sar;
  const hero = isVoid ? { label: "Void", tone: "gray" } : heroPill(dueTotal, services_remaining);
  const canEdit = perms.can("services", "edit") && !isVoid;
  const canCredit = perms.can("invoice", "delete");

  const actions = (
    <>
      {!paid && !isVoid && <a className="hms-rv-btn primary" href={`/finance/payments/?invoice=${invoice.pk}`}>{t("Record Payment")}</a>}
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
      {canCredit && !isVoid && (
        <button type="button" className="hms-rv-btn" onClick={() => openForm(`/finance/invoices/${invoice.pk}/credit-notes/new/`)}>
          {t("Credit note")}
        </button>
      )}
      {canCredit && can_void && (
        <button type="button" className="hms-rv-btn" onClick={() => openForm(`/finance/invoices/${invoice.pk}/void/`)}>
          {t("Void")}
        </button>
      )}
    </>
  );

  const facts = [
    { k: t("Invoice total"), v: `${fmt(servicesTotal)} ${cur}` },
    ...(credited_sar > 0 ? [{ k: t("Credit notes"), v: `−${fmt(credited_sar)} ${cur}` }] : []),
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
            label={isVoid ? t("Void") : paid ? t("Paid in full") : t("Amount due")}
            value={fmt(isVoid ? 0 : paid ? dueTotal : services_remaining)}
            unit={cur}
            color={paid ? "var(--green)" : "var(--red)"}
            bar={{
              pct: dueTotal > 0 ? `${Math.min(100, (paidTotal / dueTotal) * 100)}%` : "0%",
              color: paid ? "var(--green)" : "var(--yellow)",
            }}
            note={`${fmt(paidTotal)} ${t("of")} ${fmt(dueTotal)} ${cur} ${t("paid")}`}
          />
        }
        note={
          isVoid
            ? {
                icon: <Icon name="close" size={12} strokeWidth={2.4} />,
                iconBg: "var(--muted-foreground)",
                title: t("This invoice is void."),
                text: voidInfo.reason,
              }
            : paid
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
                      isVoid ? (
                        <StatusPill small label={t("Void")} tone="gray" />
                      ) : svc.remaining <= 0 && svc.paid_int <= 0 && svc.credited_int > 0 ? (
                        <StatusPill small label={t("Credited")} tone="gray" />
                      ) : svc.remaining <= 0 ? (
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

            {credit_notes.length ? (
              <RvSection title={t("Credit notes")} meta={`${credit_notes.length}`}>
                <DetailTable
                  columns={[
                    {
                      header: t("Credit note"), strong: true,
                      render: (cn) => (
                        <DvLink href={`/finance/credit-notes/${cn.id}/pdf/`} newTab>
                          {cn.status === "voided" ? <s>{cn.number}</s> : cn.number}
                        </DvLink>
                      ),
                    },
                    { header: t("Date"), render: (cn) => cn.date },
                    { header: t("Reason"), render: (cn) => (cn.status === "voided" ? `${cn.reason} · ${t("voided")}` : cn.reason) },
                    { header: t("Amount"), align: "right", strong: true, render: (cn) => (cn.status === "voided" ? <s>{fmt(cn.amount_sar)}</s> : `−${fmt(cn.amount_sar)}`) },
                    {
                      header: "", align: "right",
                      render: (cn) => canCredit && cn.status !== "voided" ? (
                        <button type="button" className="hms-iv-chip" onClick={() => openForm(`/finance/credit-notes/${cn.id}/void/`)}>{t("Void")}</button>
                      ) : null,
                    },
                  ]}
                  rows={credit_notes}
                />
              </RvSection>
            ) : null}
          </RvCard>
        </div>

        <RvRail
          rows={[
            { k: t("Issued"), v: invoice.issued_date || invoice.created_at || t("Not issued") },
            { k: t("Services"), v: `${visa_services.length}` },
            !paid && !isVoid && invoice.due_date ? { k: t("Due"), v: invoice.due_date } : null,
            { k: t("Currency"), v: cur },
          ].filter(Boolean)}
        />
      </div>
    </div>
  );
}