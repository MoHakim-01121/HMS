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
  if (remaining === 0) return { label: "Paid", tone: "green" };
  if (remaining < total) return { label: "Partial", tone: "yellow" };
  return { label: "Unpaid", tone: "red" };
}

function stayRange(reservations) {
  const key = (s) => { const [d, m, y] = s.split("/"); return `${y}${m}${d}`; };
  const ins = reservations.map((r) => r.check_in).filter(Boolean);
  const outs = reservations.map((r) => r.check_out).filter(Boolean);
  if (!ins.length || !outs.length) return null;
  const start = ins.reduce((a, b) => (key(a) <= key(b) ? a : b));
  const end = outs.reduce((a, b) => (key(a) >= key(b) ? a : b));
  return `${start} - ${end}`;
}

function openDraft(type, pk, waSend) {
  window.dispatchEvent(new CustomEvent("open-draft", { detail: { type, pk, waSend } }));
}

export default function Detail({ invoice, reservations, payments, due_alert, wa_send, last_billing }) {
  const openForm = useFormModal();
  const perms = usePerms();
  const { t } = useI18n();
  const paid = invoice.remaining_sar === 0;
  const pill = heroPill(invoice.total_sar, invoice.remaining_sar);
  const range = stayRange(reservations);
  const receivedTotal = payments.reduce((s, p) => s + (p.amount_sar_int || 0), 0);
  const reservationsTotal = reservations.reduce((s, r) => s + (r.total_int || 0), 0);
  const paidTotal = reservations.reduce((s, r) => s + (r.paid_int || 0), 0);
  const remainingTotal = reservations.reduce((s, r) => s + Math.max(0, r.remaining_int || 0), 0);
  const canEdit = perms.can("invoice", "edit");

  const actions = (
    <>
      {!paid && <a className="hms-rv-btn primary" href={`/finance/payments/?invoice=${invoice.pk}`}>{t("Record Payment")}</a>}
      {canEdit && (
        <button type="button" className="hms-rv-btn" onClick={() => openDraft(paid ? "invoice_lunas" : "invoice", invoice.pk, wa_send)}>
          {paid ? t("Paid Message") : t("Draft Message")}
        </button>
      )}
      <a className="hms-rv-btn" href={`/invoice/${invoice.pk}/pdf/`} target="_blank" rel="noreferrer">PDF</a>
      {canEdit && (
        <button type="button" className={paid ? "hms-rv-btn primary" : "hms-rv-btn"} onClick={() => openForm(`/invoice/${invoice.pk}/edit/`)}>
          {t("Edit")}
        </button>
      )}
    </>
  );

  return (
    <div className="page shadcn-root hms-rv-page">
      <RvBack href="/invoice/" label={t("Back")} />

      <RvHero
        kicker={invoice.invoice_number}
        badge={{ label: t(pill.label), tone: pill.tone }}
        title={invoice.customer_name}
        facts={[
          { k: t("Invoice total"), v: `${fmt(invoice.total_sar)} SAR` },
          { k: t("Issued"), v: invoice.issued_date || t("Not issued") },
          { k: t("Currency"), v: "SAR" },
        ]}
        side={
          <RvFigure
            label={paid ? t("Paid in full") : t("Amount due")}
            value={fmt(paid ? invoice.total_paid_sar : invoice.remaining_sar)}
            unit="SAR"
            color={paid ? "var(--green)" : "var(--red)"}
            bar={{
              pct: reservationsTotal > 0 ? `${Math.min(100, (paidTotal / reservationsTotal) * 100)}%` : "0%",
              color: paid ? "var(--green)" : "var(--yellow)",
            }}
            note={`${fmt(paidTotal)} ${t("of")} ${fmt(reservationsTotal)} SAR ${t("paid")}`}
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
            <RvSection title={t("Reservations")} meta={reservations.length ? `${reservations.length}` : undefined} first>
              <DetailTable
                columns={[
                  {
                    header: "#RSV",
                    strong: true,
                    render: (res) => (
                      <>
                        {res.number}
                        {res.cl_pk ? <DvLink href={`/cl/${res.cl_pk}/`}>CL</DvLink> : null}
                      </>
                    ),
                  },
                  { header: t("Hotel"), render: (res) => res.hotel },
                  { header: t("Check in"), render: (res) => res.check_in || t("Not set") },
                  { header: t("Check out"), render: (res) => res.check_out || t("Not set") },
                  {
                    header: t("Status"),
                    align: "right",
                    render: (res) =>
                      res.remaining_int <= 0 ? (
                        <StatusPill small label={t("Settled")} tone="green" />
                      ) : res.remaining_int < res.total_int ? (
                        <StatusPill small label={t("Partial")} tone="yellow" />
                      ) : (
                        <StatusPill small label={t("Unpaid")} tone="red" />
                      ),
                  },
                  { header: t("Total"), align: "right", strong: true, render: (res) => fmt(res.total_int) },
                  { header: t("Paid"), align: "right", render: (res) => <span style={{ color: res.paid_int > 0 ? "var(--green)" : undefined }}>{fmt(res.paid_int)}</span> },
                  { header: t("Remaining"), align: "right", render: (res) => fmt(Math.max(0, res.remaining_int || 0)) },
                ]}
                rows={reservations}
                empty={t("No reservations")}
                footer={
                  reservations.length
                    ? [{
                        label: t("Total"),
                        value: [`${fmt(reservationsTotal)} SAR`, `${fmt(paidTotal)} SAR`, `${fmt(remainingTotal)} SAR`],
                        tone: [null, "green", remainingTotal > 0 ? "red" : null],
                        total: true,
                      }]
                    : null
                }
              />
            </RvSection>

            <RvSection title={t("Payments")} meta={payments.length ? `${payments.length}` : undefined}>
              <DetailTable
                columns={[
                  { header: "#REF", strong: true, render: (p) => p.linked_number || t("Unlinked") },
                  { header: t("Date"), render: (p) => p.payment_date || t("Not set") },
                  {
                    header: t("Method"),
                    render: (p) => (
                      <>
                        {p.method || t("Payment")}
                        {p.proof_url ? <DvLink href={p.proof_url} newTab>{t("Proof")}</DvLink> : null}
                      </>
                    ),
                  },
                  { header: t("Amount"), align: "right", render: (p) => `${fmt(p.amount_int)} ${p.currency}` },
                  { header: t("Rate"), align: "right", render: (p) => (p.currency === "SAR" ? "1.00" : p.exchange_rate_fmt) },
                  { header: t("Amount SAR"), align: "right", strong: true, render: (p) => fmt(p.amount_sar_int) },
                  {
                    header: "",
                    align: "right",
                    render: (p) =>
                      p.unallocated_sar > 0 ? (
                        <a className="hms-dv-act" href={`/finance/payments/${p.id}/`}>{t("Apply")}</a>
                      ) : null,
                  },
                ]}
                rows={payments}
                empty={t("No payments")}
                footer={payments.length ? [{ label: t("Total received"), value: `${fmt(receivedTotal)} SAR`, total: true, tone: "green" }] : null}
              />
            </RvSection>
          </RvCard>
        </div>

        <RvRail
          rows={[
            { k: t("Issued"), v: invoice.issued_date || t("Not issued") },
            { k: t("Reservations"), v: `${reservations.length}${range ? ` – ${range}` : ""}` },
            !paid && due_alert ? { k: t("Due"), v: due_alert.msg } : null,
            { k: t("Currency"), v: "SAR" },
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