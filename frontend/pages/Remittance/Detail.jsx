import DetailHero from "../../components/detail/DetailHero.jsx";
import FloatCard from "../../components/detail/FloatCard.jsx";
import Section from "../../components/detail/Section.jsx";
import ItemRow, { DvLink } from "../../components/detail/ItemRow.jsx";
import FooterSummary from "../../components/detail/FooterSummary.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

export default function Detail({ rem, lines }) {
  const cardSub = [rem.receipt_reference, rem.note].filter(Boolean);
  return (
    <div className="page dv-page">
      <a href="/remittance/" className="page-back">
        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 12H5m7-7l-7 7 7 7" />
        </svg>
        Back
      </a>

      <DetailHero
        kicker="Remittance"
        title={rem.remittance_number}
        sub={rem.date}
        pill={rem.status === "received" ? { label: "Received", tone: "green" } : { label: "Pending", tone: "yellow" }}
        menuItems={[
          { label: "Edit", href: `/remittance/${rem.id}/edit/` },
          ...(rem.proof_url ? [{ label: "View Receipt", href: rem.proof_url, target: "_blank" }] : []),
        ]}
      />

      <FloatCard>
        <div className="dv-l">Remittance</div>
        <div className="dv-float-name">{rem.remittance_number}</div>
        {cardSub.length ? (
          <div className="dv-item-sub">
            {cardSub.map((l, i) => <span key={i}>{i > 0 ? <br /> : null}{l}</span>)}
          </div>
        ) : null}
      </FloatCard>

      <div className="dv-body">
      <Section label="Per Reservation" right="Sent Now">
        {lines.length ? lines.map((row, i) => {
          const subLines = [];
          const stay = [row.hotel, row.check_in].filter(Boolean).join(", ");
          if (stay) subLines.push(stay);
          const who = [row.invoice ? row.invoice.customer_name : null, row.prev_sent ? `prev ${fmt(row.prev_sent)}` : null].filter(Boolean).join(", ");
          if (who) subLines.push(who);
          return (
            <ItemRow
              key={i}
              small
              name={row.linked_number}
              link={row.invoice ? <DvLink href={`/invoice/${row.invoice.pk}/`}>INV</DvLink> : null}
              sub={subLines.length ? subLines.map((l, j) => <span key={j}>{j > 0 ? <br /> : null}{l}</span>) : null}
              amount={fmt(row.amount_sar)}
            />
          );
        }) : <div className="dv-empty">No reservation lines</div>}
      </Section>

      <FooterSummary
        right={
          <>
            <div className="dv-l">Total</div>
            <div className="dv-foot-total">{fmt(rem.total_sar)}<span className="cur"> SAR</span></div>
          </>
        }
      />
      </div>
    </div>
  );
}
