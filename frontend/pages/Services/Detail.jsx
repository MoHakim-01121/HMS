import DetailHero from "../../components/detail/DetailHero.jsx";
import FloatCard from "../../components/detail/FloatCard.jsx";
import Section from "../../components/detail/Section.jsx";
import ItemRow, { DvLink } from "../../components/detail/ItemRow.jsx";
import FooterSummary from "../../components/detail/FooterSummary.jsx";
import LastBilling from "../../components/ui/LastBilling.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

function openDraft(type, pk, waSend) {
  window.dispatchEvent(new CustomEvent("open-draft", { detail: { type, pk, waSend } }));
}

export default function Detail({ invoice, visa_services, payments_history, services_remaining, wa_send, last_billing }) {
  const cur = invoice.currency;
  const totalAll = visa_services.reduce((s, v) => s + (v.total || 0), 0);
  const paid = services_remaining <= 0;
  const pill = paid
    ? { label: "Paid", tone: "green" }
    : services_remaining < totalAll ? { label: "Partial", tone: "yellow" } : { label: "Unpaid", tone: "red" };
  const cardSub = [
    invoice.issued_date ? `issued ${invoice.issued_date}` : null,
    invoice.due_date ? `due ${invoice.due_date}` : null,
    invoice.company === "ijabah" ? "Ijabah" : "Konoz",
  ].filter(Boolean);
  return (
    <div className="page dv-page">
      <a href="/services/" className="page-back">
        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 12H5m7-7l-7 7 7 7" />
        </svg>
        Back
      </a>

      <DetailHero
        kicker="Invoice Services"
        title={invoice.invoice_number}
        sub={`${invoice.customer_name}, ${invoice.created_at}`}
        pill={pill}
      />

      <FloatCard
        right={
          <div className={"dv-amtbox" + (paid ? " paid" : "")}>
            <div className="dv-l">{paid ? "Paid" : "Amount Due"}</div>
            <div className="dv-amtbox-num">{fmt(paid ? totalAll : services_remaining)}</div>
            <div className="dv-amtbox-cur">{cur}</div>
          </div>
        }
      >
        <div className="dv-l">Invoice For</div>
        <div className="dv-float-name">{invoice.customer_name}</div>
        <div className="dv-item-sub">
          {cardSub.map((l, i) => <span key={i}>{i > 0 ? <br /> : null}{l}</span>)}
        </div>
      </FloatCard>

      <div className="dv-body">
      <Section label="Services" right="Total">
        {visa_services.length ? visa_services.map((svc, i) => (
          <ItemRow
            key={i}
            name={svc.product}
            sub={`${svc.qty} × ${fmt(svc.price)} ${cur}`}
            amount={fmt(svc.total)}
            amountSub={svc.remaining > 0 ? <small style={{ color: "var(--red)" }}>sisa {fmt(svc.remaining)}</small> : null}
          />
        )) : <div className="dv-empty">No service data</div>}
      </Section>

      <Section label="Payments" right={cur}>
        {payments_history.length ? payments_history.map((p, i) => {
          const subLines = [];
          if (p.payment_date) subLines.push(p.payment_date);
          if (p.payment_currency && p.payment_currency !== cur) subLines.push(`${p.payment_currency}, rate ${p.payment_exchange}`);
          if (p.payment_note) subLines.push(p.payment_note);
          return (
            <ItemRow
              key={i}
              small
              name={p.payment_method || "Payment"}
              link={p.proof_url ? <DvLink href={p.proof_url} newTab>Proof</DvLink> : null}
              sub={subLines.length ? subLines.map((l, j) => <span key={j}>{j > 0 ? <br /> : null}{l}</span>) : null}
              amount={fmt(p.payment_amount)}
              amountColor="green"
            />
          );
        }) : <div className="dv-empty">No payment data</div>}
      </Section>

      <FooterSummary
        left={
          <>
            <div className="dv-l">Paid</div>
            <div style={{ color: "var(--green)", fontSize: 13, fontWeight: 700, marginTop: 5 }}>{fmt(totalAll - services_remaining)} {cur}</div>
            <div className="dv-item-sub">{payments_history.length} pembayaran diterima</div>
          </>
        }
        right={
          <>
            <div className="dv-l">Total Amount</div>
            <div className="dv-foot-total">{fmt(totalAll)}<span className="cur"> {cur}</span></div>
          </>
        }
      />

      <div className="dv-sec">
        <button type="button" className="dv-cta" onClick={() => openDraft(paid ? "services_lunas" : "services", invoice.pk, wa_send)}>
          {paid ? "Paid Message" : "Draft Message"}
        </button>
        <div style={{ marginTop: 10 }}>
          <LastBilling last={last_billing} />
        </div>
      </div>
      </div>
    </div>
  );
}
