import Attachments from "../../components/ui/Attachments.jsx";
import DetailHero from "../../components/detail/DetailHero.jsx";
import FloatCard from "../../components/detail/FloatCard.jsx";
import Section from "../../components/detail/Section.jsx";
import ItemRow from "../../components/detail/ItemRow.jsx";
import FooterSummary from "../../components/detail/FooterSummary.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");
const fmtPrice = (n) => Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 2 });

function heroPill(s) {
  if (s === "DEFINITE") return { label: "Definite", tone: "green" };
  if (s === "CANCELLED") return { label: "Cancelled", tone: "red" };
  return { label: "Tentative", tone: "yellow" };
}

function PenaltySection({ cl, penalty }) {
  return (
    <Section
      label="Cancellation Penalty"
      action={
        penalty ? (
          <span style={{ display: "inline-flex", gap: 14 }}>
            <a className="dv-sec-action" href={`/penalty/${penalty.pk}/pdf/`} target="_blank" rel="noreferrer">PDF</a>
            <a className="dv-sec-action" href={`/penalty/${penalty.pk}/edit/`}>Edit</a>
          </span>
        ) : (
          <a className="dv-sec-action" href={`/cl/${cl.pk}/penalty/new/`}>+ Create Penalty Document</a>
        )
      }
    >
      {penalty ? (
        <ItemRow
          small
          name={<a href={`/penalty/${penalty.pk}/`} style={{ color: "var(--accent-2)", textDecoration: "none" }}>{penalty.penalty_number}</a>}
          sub={penalty.cancellation_date}
          amount={`${fmt(penalty.penalty_amount)} ${penalty.penalty_currency}`}
          amountSub={
            <small style={{ color: penalty.is_paid ? "var(--green)" : "var(--red)" }}>
              {penalty.is_paid ? "Paid" : "Unpaid"}
            </small>
          }
        />
      ) : (
        <div className="dv-empty">No penalty document for this CL yet.</div>
      )}
    </Section>
  );
}

export default function Detail({ cl, rooms, penalty, attachments }) {
  const guestLines = [];
  if (cl.client) {
    guestLines.push(
      <a key="travel" href={`/clients/${cl.client.pk}/`} style={{ color: "var(--accent-2)", textDecoration: "none" }}>{cl.client.name}</a>
    );
  }
  if (cl.guest_phone) guestLines.push(cl.guest_phone);
  if (cl.hotel_name) guestLines.push(cl.hotel_name);

  return (
    <div className="page dv-page">
      <a href="/cl/" className="page-back">
        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 12H5m7-7l-7 7 7 7" />
        </svg>
        Back
      </a>

      <DetailHero
        kicker="Confirmation Letter"
        title={cl.confirmation_number}
        sub={cl.invoice ? <>Invoiced : <a href={`/invoice/${cl.invoice.pk}/`}>{cl.invoice.invoice_number}</a></> : null}
        pill={heroPill(cl.reservation_status)}
        menuItems={[
          { label: "PDF", href: `/cl/${cl.pk}/pdf/`, target: "_blank" },
          { label: "Edit", href: `/cl/${cl.pk}/edit/` },
        ]}
      />

      <FloatCard>
        <div className="dv-l">Guest</div>
        <div className="dv-float-name">{cl.guest_name}</div>
        {guestLines.length ? (
          <div className="dv-item-sub">
            {guestLines.map((line, i) => <span key={i}>{i > 0 ? <br /> : null}{line}</span>)}
          </div>
        ) : null}
      </FloatCard>

      <div className="dv-body">
      <Attachments targetType="cl" targetId={cl.pk} initial={attachments} />

      {cl.reservation_status === "CANCELLED" ? <PenaltySection cl={cl} penalty={penalty} /> : null}

      <Section label="Stay">
        <ItemRow
          small
          name={`${cl.check_in || "?"} - ${cl.check_out || "?"}`}
          sub="Check-in sampai Check-out"
          amount={`${cl.num_nights} nights`}
          amountSub={<small style={{ color: "var(--text-2)" }}>{cl.num_guests} guests</small>}
        />
      </Section>

      <Section label="Rooms" right="Subtotal">
        {rooms.length ? rooms.map((room, i) => (
          <ItemRow
            key={i}
            name={room.room_type}
            sub={`${room.quantity} kamar × ${fmtPrice(room.price)}/night${room.meals ? `, ${room.meals}` : ""}`}
            amount={fmt(room.subtotal)}
          />
        )) : <div className="dv-empty">No room data</div>}
      </Section>

      {cl.note ? (
        <Section label="Notes">
          <div className="dv-item-sub" style={{ marginTop: 6 }}>{cl.note}</div>
        </Section>
      ) : null}

      <FooterSummary
        right={
          <>
            <div className="dv-l">Total Price</div>
            <div className="dv-foot-total">{fmt(cl.total_price)}<span className="cur"> SAR</span></div>
          </>
        }
      />
      </div>
    </div>
  );
}
