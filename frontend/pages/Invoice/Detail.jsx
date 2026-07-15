import InvoiceHero from "./components/InvoiceHero.jsx";
import ReservationTable from "./components/ReservationTable.jsx";
import PaymentTable from "./components/PaymentTable.jsx";
import LastBilling from "../../components/ui/LastBilling.jsx";

export default function Detail({ invoice, reservations, payments, due_alert, wa_send, last_billing }) {
  return (
    <div className="page">
      <a href="/invoice/" className="page-back">
        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 12H5m7-7l-7 7 7 7" />
        </svg>
        Back
      </a>

      <InvoiceHero invoice={invoice} />
      <LastBilling last={last_billing} />

      {due_alert && (
        <div className={`alert alert-${due_alert.type}`} style={{ marginBottom: 12 }}>{due_alert.msg}</div>
      )}

      <ReservationTable reservations={reservations} invoice={invoice} />
      <PaymentTable payments={payments} invoice={invoice} waSend={wa_send} />
    </div>
  );
}
