const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

export default function Detail({ rem, lines }) {
  return (
    <div className="page" style={{ maxWidth: 960 }}>
      <div className="page-header"></div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-body">
          <div className="grid-4">
            <div><div className="info-label">Remittance No</div><div style={{ fontSize: 14, fontWeight: 700, fontFamily: "monospace" }}>{rem.remittance_number}</div></div>
            <div><div className="info-label">Date</div><div style={{ fontSize: 14, fontWeight: 600 }}>{rem.date}</div></div>
            <div><div className="info-label">Status</div><div>{rem.status === "received" ? <span className="badge badge-green">Received</span> : <span className="badge badge-yellow">Pending</span>}</div></div>
            <div><div className="info-label">Receipt</div><div>{rem.proof_url ? <a href={rem.proof_url} target="_blank" rel="noreferrer" className="btn btn-ghost" style={{ fontSize: 12, padding: "4px 10px" }}>View ↗</a> : <span style={{ fontSize: 13, color: "var(--text-3)" }}>—</span>}</div></div>
          </div>
          {(rem.receipt_reference || rem.note) && (
            <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              {rem.receipt_reference && <div><div className="info-label">Receipt Reference</div><div style={{ fontSize: 13, fontWeight: 600, fontFamily: "monospace" }}>{rem.receipt_reference}</div></div>}
              {rem.note && <div><div className="info-label">Note</div><div style={{ fontSize: 13, color: "var(--text-2)" }}>{rem.note}</div></div>}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header"><span className="card-title">Detail per Reservation</span></div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Res</th><th>Invoice</th><th>Client / Travel</th><th>Hotel</th>
                <th style={{ textAlign: "right" }}>Check-in</th>
                <th style={{ textAlign: "right" }}>Previously Sent</th>
                <th style={{ textAlign: "right" }}>Sent Now</th>
              </tr>
            </thead>
            <tbody>
              {lines.length ? lines.map((row, i) => (
                <tr key={i}>
                  <td className="col-m-primary" style={{ fontFamily: "monospace", fontWeight: 600 }}>
                    {row.linked_number}
                    <span className="m-sub" style={{ fontFamily: "inherit" }}>{row.hotel || "—"}{row.check_in ? ` · ${row.check_in}` : ""}{row.prev_sent ? ` · prev ${fmt(row.prev_sent)}` : ""}</span>
                  </td>
                  <td className="col-m-hide">{row.invoice ? <a href={`/invoice/${row.invoice.pk}/`} style={{ color: "var(--accent-2)", textDecoration: "none", fontSize: 12 }}>{row.invoice.invoice_number}</a> : "—"}</td>
                  <td className="col-m-secondary" style={{ fontSize: 12, color: "var(--text-2)" }}>{row.invoice ? row.invoice.customer_name : "—"}</td>
                  <td className="col-m-hide" style={{ fontSize: 12, color: "var(--text-2)" }}>{row.hotel || "—"}</td>
                  <td className="col-m-hide" style={{ fontSize: 12, color: "var(--text-2)", textAlign: "right" }}>{row.check_in || "—"}</td>
                  <td className="col-m-hide" style={{ fontFamily: "monospace", textAlign: "right", color: "var(--text-2)" }}>{fmt(row.prev_sent)}</td>
                  <td className="mono col-m-amount" style={{ fontWeight: 600, textAlign: "right" }}>{fmt(row.amount_sar)}</td>
                </tr>
              )) : (
                <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--text-3)", padding: 20 }}>No data</td></tr>
              )}
            </tbody>
            {lines.length > 0 && (
              <tfoot>
                <tr style={{ borderTop: "2px solid var(--border)" }}>
                  <td colSpan={6} style={{ padding: "10px 12px", fontSize: 12, fontWeight: 600, color: "var(--text-2)", textAlign: "right" }}>Total</td>
                  <td style={{ padding: "10px 12px", fontFamily: "monospace", fontWeight: 700, textAlign: "right" }}>{fmt(rem.total_sar)} SAR</td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </div>
    </div>
  );
}
