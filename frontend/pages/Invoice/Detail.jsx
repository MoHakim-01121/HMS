import DetailHero from "../../components/detail/DetailHero.jsx";
import FloatCard from "../../components/detail/FloatCard.jsx";
import Section from "../../components/detail/Section.jsx";
import ItemRow, { DvLink } from "../../components/detail/ItemRow.jsx";
import FooterSummary from "../../components/detail/FooterSummary.jsx";
import LastBilling from "../../components/ui/LastBilling.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

function heroPill(total, remaining) {
  if (remaining === 0) return { label: "Paid", tone: "green" };
  if (remaining < total) return { label: "Partial", tone: "yellow" };
  return { label: "Unpaid", tone: "red" };
}

// Rentang menginap gabungan dari semua reservasi (dd/mm/yyyy).
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
  const paid = invoice.remaining_sar === 0;
  const range = stayRange(reservations);
  return (
    <div className="page dv-page">
      <a href="/invoice/" className="page-back">
        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 12H5m7-7l-7 7 7 7" />
        </svg>
        Back
      </a>

      <DetailHero
        kicker="Invoice Hotel"
        title={invoice.invoice_number}
        sub={invoice.issued_date ? `issued ${invoice.issued_date}` : null}
        pill={heroPill(invoice.total_sar, invoice.remaining_sar)}
        menuItems={[
          { label: "PDF", href: `/invoice/${invoice.pk}/pdf/`, target: "_blank" },
          { label: "Edit", href: `/invoice/${invoice.pk}/edit/` },
        ]}
      />

      <FloatCard
        right={
          <div className={"dv-amtbox" + (paid ? " paid" : "")}>
            <div className="dv-l">{paid ? "Paid" : "Amount Due"}</div>
            <div className="dv-amtbox-num">{fmt(paid ? invoice.total_paid_sar : invoice.remaining_sar)}</div>
            <div className="dv-amtbox-cur">SAR</div>
            {!paid && due_alert ? <div className={`dv-amtbox-due ${due_alert.type}`}>{due_alert.msg}</div> : null}
          </div>
        }
      >
        <div className="dv-l">Invoice For</div>
        <div className="dv-float-name">{invoice.customer_name}</div>
        <div className="dv-item-sub">
          {reservations.length} reservation{reservations.length === 1 ? "" : "s"}
          {range ? <><br />{range}</> : null}
        </div>
      </FloatCard>

      <div className="dv-body">
      <Section label="Reservation" right="Total">
        {reservations.length ? reservations.map((res, i) => (
          <ItemRow
            key={i}
            name={res.hotel}
            link={res.cl_pk ? <DvLink href={`/cl/${res.cl_pk}/`}>CL</DvLink> : null}
            sub={
              <>
                No {res.number}
                {res.check_in || res.check_out ? <><br />{res.check_in || "?"} - {res.check_out || "?"}</> : null}
              </>
            }
            amount={fmt(res.total_int)}
            amountSub={res.remaining_int > 0 ? <small style={{ color: "var(--red)" }}>sisa {fmt(res.remaining_int)}</small> : null}
          />
        )) : <div className="dv-empty">No reservations</div>}
      </Section>

      <Section label="Payment" right="SAR">
        {payments.length ? payments.map((p, i) => {
          const subLines = [];
          if (p.linked_number || p.payment_date) {
            subLines.push([p.linked_number ? `Res ${p.linked_number}` : null, p.payment_date].filter(Boolean).join(", "));
          }
          if (p.currency !== "SAR") subLines.push(`${fmt(p.amount_int)} ${p.currency} ÷ ${p.exchange_rate_fmt}`);
          return (
            <ItemRow
              key={i}
              small
              name={p.method || "Payment"}
              link={p.proof_url ? <DvLink href={p.proof_url} newTab>Proof</DvLink> : null}
              sub={subLines.length ? subLines.map((l, j) => <span key={j}>{j > 0 ? <br /> : null}{l}</span>) : null}
              amount={fmt(p.amount_sar_int)}
              amountColor="green"
            />
          );
        }) : <div className="dv-empty">No payments</div>}
      </Section>

      <FooterSummary
        left={
          <>
            <div className="dv-l">Paid</div>
            <div style={{ color: "var(--green)", fontSize: 13, fontWeight: 700, marginTop: 5 }}>{fmt(invoice.total_paid_sar)} SAR</div>
            <div className="dv-item-sub">{payments.length} pembayaran diterima</div>
          </>
        }
        right={
          <>
            <div className="dv-l">Total Amount</div>
            <div className="dv-foot-total">{fmt(invoice.total_sar)}<span className="cur"> SAR</span></div>
          </>
        }
      />

      <div className="dv-sec">
        <button type="button" className="dv-cta" onClick={() => openDraft(paid ? "invoice_lunas" : "invoice", invoice.pk, wa_send)}>
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
