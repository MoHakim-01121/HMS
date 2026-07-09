import PageBack from "../../components/ui/PageBack.jsx";
import Table from "../../components/ui/Table.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

export default function Detail({ rem, lines }) {
  return (
    <div className="page" style={{ maxWidth: 960 }}>
      <PageBack href="/remittance/" />
      <div className="page-header">
        <div>
          <div className="page-title">{rem.remittance_number}</div>
          <div className="page-sub">{rem.date}</div>
        </div>
        <div className="page-actions">
          {rem.status === "received"
            ? <span className="badge badge-green">Received</span>
            : <span className="badge badge-yellow">Pending</span>}
          <a href={`/remittance/${rem.id}/edit/`} className="btn btn-secondary btn-sm">Edit</a>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-body">
          <div className="grid-4">
            <div><div className="info-label">Remittance No</div><div style={{ fontSize: 14, fontWeight: 700, fontFamily: "'JetBrains Mono', monospace" }}>{rem.remittance_number}</div></div>
            <div><div className="info-label">Date</div><div style={{ fontSize: 14, fontWeight: 600 }}>{rem.date}</div></div>
            <div><div className="info-label">Status</div><div>{rem.status === "received" ? <span className="badge badge-green">Received</span> : <span className="badge badge-yellow">Pending</span>}</div></div>
            <div><div className="info-label">Receipt</div><div>{rem.proof_url ? <a href={rem.proof_url} target="_blank" rel="noreferrer" className="btn btn-ghost" style={{ fontSize: 12, padding: "4px 10px" }}>View ↗</a> : <span style={{ fontSize: 13, color: "var(--text-3)" }}>—</span>}</div></div>
          </div>
          {(rem.receipt_reference || rem.note) && (
            <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              {rem.receipt_reference && <div><div className="info-label">Receipt Reference</div><div style={{ fontSize: 13, fontWeight: 600, fontFamily: "'JetBrains Mono', monospace" }}>{rem.receipt_reference}</div></div>}
              {rem.note && <div><div className="info-label">Note</div><div style={{ fontSize: 13, color: "var(--text-2)" }}>{rem.note}</div></div>}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header"><span className="card-title">Detail per Reservation</span></div>
        <Table
          columns={[
            {
              header: "Res",
              className: "col-m-primary",
              style: { fontFamily: "'JetBrains Mono', monospace", fontWeight: 600 },
              render: (row) => (
                <>
                  {row.linked_number}
                  <span className="m-sub" style={{ fontFamily: "inherit" }}>{row.hotel || "—"}{row.check_in ? ` · ${row.check_in}` : ""}{row.prev_sent ? ` · prev ${fmt(row.prev_sent)}` : ""}</span>
                </>
              ),
            },
            { header: "Invoice", className: "col-m-hide", render: (row) => row.invoice ? <a href={`/invoice/${row.invoice.pk}/`} style={{ color: "var(--accent-2)", textDecoration: "none", fontSize: 12 }}>{row.invoice.invoice_number}</a> : "—" },
            { header: "Client / Travel", className: "col-m-secondary", style: { fontSize: 12, color: "var(--text-2)" }, render: (row) => row.invoice ? row.invoice.customer_name : "—" },
            { header: "Hotel", className: "col-m-hide", style: { fontSize: 12, color: "var(--text-2)" }, render: (row) => row.hotel || "—" },
            { header: "Check-in", headerStyle: { textAlign: "right" }, className: "col-m-hide", style: { fontSize: 12, color: "var(--text-2)", textAlign: "right" }, render: (row) => row.check_in || "—" },
            { header: "Previously Sent", headerStyle: { textAlign: "right" }, className: "col-m-hide", style: { fontFamily: "'JetBrains Mono', monospace", textAlign: "right", color: "var(--text-2)" }, render: (row) => fmt(row.prev_sent) },
            { header: "Sent Now", headerStyle: { textAlign: "right" }, className: "mono col-m-amount", style: { fontWeight: 600, textAlign: "right" }, render: (row) => fmt(row.amount_sar) },
          ]}
          rows={lines}
          rowKey={(row, i) => i}
          footer={lines.length > 0 && (
            <tr style={{ borderTop: "2px solid var(--border)" }}>
              <td colSpan={6} style={{ padding: "10px 12px", fontSize: 12, fontWeight: 600, color: "var(--text-2)", textAlign: "right" }}>Total</td>
              <td style={{ padding: "10px 12px", fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, textAlign: "right" }}>{fmt(rem.total_sar)} SAR</td>
            </tr>
          )}
        />
      </div>
    </div>
  );
}
