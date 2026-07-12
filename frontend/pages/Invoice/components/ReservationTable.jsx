import Table from "../../../components/ui/Table.jsx";

const fmt = (n) => Math.round(n).toLocaleString("en-US");

// Reservations card ported from invoice_detail.html (incl. mobile m-* spans).
export default function ReservationTable({ reservations, invoice }) {
  return (
    <div className="card">
      <div className="card-header"><span className="card-title">Reservations</span></div>
      <Table
        columns={[
          {
            header: "Res#",
            className: "col-m-primary",
            style: { fontFamily: "'JetBrains Mono', monospace", fontWeight: 600, justifyContent: "space-between", alignItems: "flex-start" },
            render: (res) => (
              <>
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
              </>
            ),
          },
          { header: "Hotel", className: "col-m-hide", style: { color: "var(--text-2)" }, render: (res) => res.hotel },
          { header: "Check-in", className: "col-m-hide", style: { color: "var(--text-2)" }, render: (res) => res.check_in || "—" },
          { header: "Check-out", className: "col-m-hide", style: { color: "var(--text-2)" }, render: (res) => res.check_out || "—" },
          { header: "Total (SAR)", headerClassName: "col-num", className: "mono col-money col-m-hide", render: (res) => fmt(res.total_int) },
          { header: "Remaining (SAR)", headerClassName: "col-num", className: (res) => `${res.remaining_class} mono col-num col-m-hide`, render: (res) => fmt(res.remaining_int) },
        ]}
        rows={reservations}
        rowKey={(res, i) => i}
        empty="No reservations"
        footer={
          <tr>
            <td colSpan={4} className="col-m-hide"></td>
            <td className="tsum-v col-num"><span className="m-only tsum-k">Total Reservation</span>{fmt(invoice.total_sar)}<span className="m-only"> SAR</span></td>
            <td className={"tsum-v col-num " + (invoice.remaining_sar === 0 ? "green" : "red")}><span className="m-only tsum-k">Remaining</span>{fmt(invoice.remaining_sar)}<span className="m-only"> SAR</span></td>
          </tr>
        }
      />
    </div>
  );
}
