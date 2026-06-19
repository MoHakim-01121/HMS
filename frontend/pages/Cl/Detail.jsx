import Attachments from "../../components/ui/Attachments.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

function heroBadge(s) {
  if (s === "DEFINITE") return ["badge badge-green", "Definite"];
  if (s === "CANCELLED") return ["badge badge-red", "Cancelled"];
  return ["badge badge-yellow", "Tentative"];
}

function MetaRail({ cl }) {
  return (
    <div className="dmeta">
      <div className="dmeta-head">Property</div>
      <div className="dmeta-row"><span className="dmeta-k">Hotel</span><span className="dmeta-v">{cl.hotel_name || "—"}</span></div>
      <div className="dmeta-row"><span className="dmeta-k">Travel Agent</span><span className="dmeta-v">
        {cl.client ? <a href={`/clients/${cl.client.pk}/`} style={{ color: "var(--accent-2)", textDecoration: "none" }}>{cl.client.name}</a> : (cl.guest_name || "—")}
      </span></div>
      <div className="dmeta-row"><span className="dmeta-k">Phone</span><span className="dmeta-v mono">{cl.guest_phone || "—"}</span></div>
      <div className="dmeta-row"><span className="dmeta-k">Check-in</span><span className="dmeta-v">{cl.check_in || "—"}</span></div>
      <div className="dmeta-row"><span className="dmeta-k">Check-out</span><span className="dmeta-v">{cl.check_out || "—"}</span></div>
      <div className="dmeta-row"><span className="dmeta-k">Nights</span><span className="dmeta-v">{cl.num_nights}</span></div>
      <div className="dmeta-row"><span className="dmeta-k">Guests</span><span className="dmeta-v">{cl.num_guests} people</span></div>
      {cl.note && <div className="dmeta-note">{cl.note}</div>}
    </div>
  );
}

function PenaltyCard({ cl, penalty }) {
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Cancellation Penalty</span>
        {penalty ? (
          <div style={{ display: "flex", gap: 6 }}>
            <a href={`/penalty/${penalty.pk}/pdf/`} target="_blank" rel="noreferrer" className="btn btn-ghost btn-sm">PDF</a>
            <a href={`/penalty/${penalty.pk}/edit/`} className="btn btn-ghost btn-sm">Edit</a>
          </div>
        ) : (
          <a href={`/cl/${cl.pk}/penalty/new/`} className="btn btn-primary btn-sm">+ Create Penalty Document</a>
        )}
      </div>
      <div className="card-body">
        {penalty ? (
          <div className="grid-2">
            <div className="field"><div className="field-label">Penalty No.</div><div className="field-value"><a href={`/penalty/${penalty.pk}/`} style={{ color: "var(--accent)", fontFamily: "monospace", fontWeight: 600 }}>{penalty.penalty_number}</a></div></div>
            <div className="field"><div className="field-label">Cancellation Date</div><div className="field-value">{penalty.cancellation_date}</div></div>
            <div className="field"><div className="field-label">Penalty Amount</div><div className="field-value" style={{ fontWeight: 700 }}>{fmt(penalty.penalty_amount)} {penalty.penalty_currency}</div></div>
            <div className="field"><div className="field-label">Payment Status</div><div className="field-value">{penalty.is_paid ? <span className="badge badge-green">Paid</span> : <span className="badge badge-red">Unpaid</span>}</div></div>
          </div>
        ) : (
          <p style={{ color: "var(--text-2)", fontSize: 13 }}>No penalty document for this CL yet.</p>
        )}
      </div>
    </div>
  );
}

function RoomsTable({ cl, rooms }) {
  return (
    <div className="card">
      <div className="card-header"><span className="card-title">Rooms</span></div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Type</th><th className="col-m-hide">Meals</th><th className="col-num col-m-hide">Qty</th><th className="col-num col-m-hide">Price/Night</th><th className="col-num">Subtotal</th></tr>
          </thead>
          <tbody>
            {rooms.length ? rooms.map((room, i) => (
              <tr key={i}>
                <td className="col-m-primary">
                  {room.room_type}
                  <span className="m-sub">{room.quantity} × {fmt(room.price)} SAR/night</span>
                </td>
                <td className="col-m-hide" style={{ color: "var(--text-2)" }}>{room.meals || "—"}</td>
                <td className="mono col-num col-m-hide">{room.quantity}</td>
                <td className="mono col-num col-m-hide">{fmt(room.price)}</td>
                <td className="mono col-num col-m-amount" style={{ fontWeight: 600 }}>{fmt(room.subtotal)} SAR</td>
              </tr>
            )) : (
              <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--text-3)", padding: 20 }}>No room data</td></tr>
            )}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={4} className="col-num col-m-hide" style={{ fontWeight: 700 }}>Total</td>
              <td className="tsum-v col-num" style={{ fontWeight: 700 }}><span className="m-only tsum-k">Total</span>{fmt(cl.total_price)} SAR</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}

export default function Detail({ cl, rooms, penalty, attachments }) {
  const [bcls, blabel] = heroBadge(cl.reservation_status);
  return (
    <div className="page">
      <a href="/cl/" className="page-back">
        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M19 12H5m7-7l-7 7 7 7" /></svg>
        Back
      </a>

      <div className="dhero">
        <div className="dhero-main">
          <div className="dhero-kicker">Confirmation Letter</div>
          <div className="dhero-title">{cl.confirmation_number}</div>
          <div className="dhero-sub">{cl.guest_name}</div>
        </div>
        <div className="dhero-side">
          <div className="dhero-badges">
            <span className={bcls}>{blabel}</span>
            {cl.invoice && (
              <a href={`/invoice/${cl.invoice.pk}/`} className="badge badge-blue" style={{ textDecoration: "none" }} title="Invoiced in this invoice">
                Invoiced → {cl.invoice.invoice_number}
              </a>
            )}
          </div>
          <div className="dhero-actions">
            <a href={`/cl/${cl.pk}/pdf/`} target="_blank" rel="noreferrer" className="btn btn-primary btn-sm">PDF</a>
            <a href={`/cl/${cl.pk}/edit/`} className="btn btn-secondary btn-sm">Edit</a>
          </div>
        </div>
      </div>

      <div className="dlayout rail-left">
        <MetaRail cl={cl} />
        <div>
          {cl.reservation_status === "CANCELLED" && <PenaltyCard cl={cl} penalty={penalty} />}
          <RoomsTable cl={cl} rooms={rooms} />
          <Attachments targetType="cl" targetId={cl.pk} initial={attachments} />
        </div>
      </div>
    </div>
  );
}
