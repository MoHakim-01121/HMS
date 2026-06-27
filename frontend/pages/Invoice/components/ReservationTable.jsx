const fmt = (n) => Math.round(n).toLocaleString("en-US");

// Reservations card ported from invoice_detail.html (incl. mobile m-* spans).
export default function ReservationTable({ reservations, invoice }) {
  return (
    <div className="card">
      <div className="card-header"><span className="card-title">Reservations</span></div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Res#</th><th>Hotel</th><th>Check-in</th><th>Check-out</th>
              <th className="col-num">Total (SAR)</th><th className="col-num">Remaining (SAR)</th>
            </tr>
          </thead>
          <tbody>
            {reservations.length ? reservations.map((res, i) => (
              <tr key={i}>
                <td className="col-m-primary" style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 600, justifyContent: "space-between", alignItems: "flex-start" }}>
                  <span>
                    <span className="cell-id">{res.number}</span>
                    {res.cl_pk && <>&nbsp;&nbsp;<a href={`/cl/${res.cl_pk}/`} style={{ fontSize: 11, color: "var(--accent-2)", textDecoration: "none", fontFamily: "inherit", fontWeight: 500 }}>(CL ↗)</a></>}
                  </span>
                  <span className="m-only mono" style={{ fontWeight: 600, color: "var(--text)", fontFamily: "inherit" }}>{fmt(res.total_int)} SAR</span>
                  <span className="m-sub" style={{ fontFamily: "inherit" }}>
                    <span style={{ display: "block" }}>{res.hotel}</span>
                    <span style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                      <span>{res.check_in || "—"} → {res.check_out || "—"}</span>
                      <span className={res.remaining_class} style={{ marginLeft: 12, whiteSpace: "nowrap" }}>{fmt(res.remaining_int)} SAR</span>
                    </span>
                  </span>
                </td>
                <td className="col-m-hide">{res.hotel}</td>
                <td className="col-m-hide" style={{ color: "var(--text-2)" }}>{res.check_in || "—"}</td>
                <td className="col-m-hide" style={{ color: "var(--text-2)" }}>{res.check_out || "—"}</td>
                <td className="mono col-money col-m-hide">{fmt(res.total_int)}</td>
                <td className={`${res.remaining_class} mono col-num col-m-hide`}>{fmt(res.remaining_int)}</td>
              </tr>
            )) : (
              <tr><td colSpan={6} style={{ textAlign: "center", color: "var(--text-3)" }}>No reservations</td></tr>
            )}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={4} className="col-m-hide"></td>
              <td className="tsum-v col-num"><span className="m-only tsum-k">Total Reservation</span>{fmt(invoice.total_sar)}<span className="m-only"> SAR</span></td>
              <td className={"tsum-v col-num " + (invoice.remaining_sar === 0 ? "green" : "red")}><span className="m-only tsum-k">Remaining</span>{fmt(invoice.remaining_sar)}<span className="m-only"> SAR</span></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
