import { router } from "@inertiajs/react";
import { useConfirm } from "../../components/ui/ConfirmDialog.jsx";
import DetailHero from "../../components/detail/DetailHero.jsx";
import FloatCard from "../../components/detail/FloatCard.jsx";
import Section from "../../components/detail/Section.jsx";
import ItemRow from "../../components/detail/ItemRow.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");
const needsWaGroup = (c) => c.reminder_target !== "PIC" && !c.wa_group;

function riskPill(risk) {
  if (risk === "high") return { label: "High Risk", tone: "red" };
  if (risk === "medium") return { label: "Overdue", tone: "yellow" };
  if (risk === "dormant") return { label: "Dormant", tone: "gray" };
  return { label: "OK", tone: "green" };
}

export default function Detail({ client, invoices, cls }) {
  const c = client;
  const [confirm, confirmDialog] = useConfirm();
  const del = () => confirm({ title: "Delete client", message: `Delete client "${c.name}"?`, onConfirm: () => router.post(`/clients/${c.pk}/delete/`) });
  const scoreColor = c.score >= 70 ? "green" : c.score >= 40 ? null : "red";
  const contactLines = [];
  if (c.city) contactLines.push(`${c.city}${c.province ? `, ${c.province}` : ""}`);
  if (c.wa) contactLines.push(<a key="wa" href={`https://wa.me/${c.wa}`} target="_blank" rel="noreferrer" style={{ color: "var(--green)", textDecoration: "none" }}>{c.wa}</a>);
  if (c.wa_group) contactLines.push(`Group: ${c.wa_group}`);
  if (c.email) contactLines.push(c.email);
  return (
    <div className="page dv-page">
      <a href="/clients/" className="page-back">
        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 12H5m7-7l-7 7 7 7" />
        </svg>
        Back
      </a>

      <DetailHero
        kicker="Client"
        title={c.name}
        pill={riskPill(c.risk_label)}
        menuItems={[
          { label: "Edit", href: `/clients/${c.pk}/edit/` },
          ...(c.wa ? [{ label: "WhatsApp", href: `https://wa.me/${c.wa}`, target: "_blank" }] : []),
          { label: "Delete", onClick: del, danger: true },
        ]}
      />

      <FloatCard
        right={
          <div className={"dv-amtbox" + (c.outstanding > 0 ? "" : " paid")}>
            <div className="dv-l">{c.outstanding > 0 ? "Outstanding" : "Clear"}</div>
            <div className="dv-amtbox-num" style={c.outstanding > 0 ? { color: "var(--red)" } : undefined}>{fmt(c.outstanding)}</div>
            <div className="dv-amtbox-cur">SAR</div>
          </div>
        }
      >
        <div className="dv-l">Contact</div>
        <div className="dv-float-name">{c.pic || c.name}</div>
        {contactLines.length ? (
          <div className="dv-item-sub">
            {contactLines.map((l, i) => <span key={i}>{i > 0 ? <br /> : null}{l}</span>)}
          </div>
        ) : (
          <div className="dv-item-sub">No contact details on file yet.</div>
        )}
        {needsWaGroup(c) ? (
          <div className="dv-item-sub" style={{ color: "var(--red)", marginTop: 6 }}>
            Reminder diset ke {c.reminder_target === "BOTH" ? "PIC & Group" : "Group"} tapi WhatsApp Group belum diisi.
          </div>
        ) : null}
      </FloatCard>

      <div className="dv-body">
      <Section label="Stats">
        <ItemRow small name="Total Billed" amount={`${fmt(c.total_billed)} SAR`} />
        {c.avg_days_to_pay != null ? <ItemRow small name="Avg Payment" amount={`${c.avg_days_to_pay} days`} /> : null}
        <ItemRow small name="Client Score" amount={`${c.score}/100`} amountColor={scoreColor || undefined} />
        {c.days_since_last_order != null ? (
          <ItemRow small name="Last Order" amount={`${c.days_since_last_order} days ago`} amountColor={c.days_since_last_order > 45 ? "red" : undefined} />
        ) : null}
      </Section>

      {c.note ? (
        <Section label="Notes">
          <div className="dv-item-sub" style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{c.note}</div>
        </Section>
      ) : null}

      <Section
        label={`Invoices (${invoices.length})`}
        right="Remaining"
        action={invoices.length > 0 ? <a className="dv-sec-action" href={`/invoice/?client=${c.pk}`}>View all</a> : null}
      >
        {invoices.length ? invoices.slice(0, 10).map((inv) => (
          <ItemRow
            key={inv.pk}
            small
            name={<a href={`/invoice/${inv.pk}/`} style={{ color: "var(--text)", textDecoration: "none" }}>{inv.invoice_number}</a>}
            sub={[inv.invoice_type_display, inv.issued_date, `billed ${fmt(inv.total_sar)}`].filter(Boolean).join(", ")}
            amount={`${fmt(inv.remaining_sar)} SAR`}
            amountColor={inv.remaining_sar > 0 ? "red" : "green"}
          />
        )) : <div className="dv-empty">No invoices yet</div>}
      </Section>

      <Section label={`Confirmation Letters (${cls.length})`}>
        {cls.length ? cls.slice(0, 8).map((cl) => (
          <ItemRow
            key={cl.pk}
            small
            name={<a href={`/cl/${cl.pk}/`} style={{ color: "var(--text)", textDecoration: "none" }}>{cl.confirmation_number}</a>}
            sub={[cl.guest_name, cl.hotel_name, cl.check_in].filter(Boolean).join(", ")}
          />
        )) : <div className="dv-empty">No confirmation letters yet</div>}
      </Section>
      </div>
      {confirmDialog}
    </div>
  );
}
