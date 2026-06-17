import { Icon } from "../../../components/icons.jsx";

const fmt = (n) => Math.round(n).toLocaleString("en-US");

function openDraft(type, pk) {
  window.dispatchEvent(new CustomEvent("open-draft", { detail: { type, pk } }));
}

// Payments card ported from invoice_detail.html (incl. mobile m-* spans + draft button).
export default function PaymentTable({ payments, invoice }) {
  const unpaid = invoice.remaining_sar > 0;
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Payments</span>
        <button className="btn btn-ghost btn-sm" onClick={() => openDraft(unpaid ? "invoice" : "invoice_lunas", invoice.pk)}>
          <Icon name="message" size={13} /> {unpaid ? "Draft Message" : "Draf Lunas"}
        </button>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Res#</th><th>Date</th><th>Method</th><th className="col-num">Amount</th>
              <th>Currency</th><th className="col-num">Rate</th><th className="col-num">SAR</th><th>Proof</th><th>Note</th>
            </tr>
          </thead>
          <tbody>
            {payments.length ? payments.map((p, i) => (
              <tr key={i}>
                <td className="col-m-hide cell-id" style={{ fontFamily: "monospace" }}>{p.linked_number || "—"}</td>
                <td className="col-m-hide">{p.payment_date || "—"}</td>
                <td className="col-m-primary">
                  <span className="m-hide">{p.method || "—"}</span>
                  <span className="m-only" style={{ fontFamily: "monospace" }}>
                    {p.linked_number || "—"}
                    {p.proof_url && <>&nbsp;&nbsp;<a href={p.proof_url} target="_blank" rel="noreferrer" style={{ fontFamily: "inherit", fontSize: 11, color: "var(--accent-2)", textDecoration: "none", fontWeight: 500 }}>(Proof ↗)</a></>}
                  </span>
                  <span className="m-sub" style={{ fontFamily: "inherit" }}>
                    {(p.method || "—") + " · " + (p.payment_date || "—")}
                    {p.currency !== "SAR" && <span style={{ fontFamily: "monospace", display: "block" }}>{fmt(p.amount_int)} {p.currency} ÷ {fmt(p.exchange_rate)}</span>}
                  </span>
                </td>
                <td className="mono col-num col-m-hide">{fmt(p.amount_int)}</td>
                <td className="col-m-hide"><span className="badge badge-gray">{p.currency}</span></td>
                <td className="col-num col-m-hide" style={{ color: "var(--text-2)" }}>{p.currency !== "SAR" ? p.exchange_rate_fmt : "—"}</td>
                <td className="mono col-money col-m-amount">{fmt(p.amount_sar_int)}<span className="m-only"> SAR</span></td>
                <td className="col-m-hide">
                  {p.proof_url
                    ? <a href={p.proof_url} target="_blank" rel="noreferrer" title="View proof" style={{ color: "var(--accent-2)", textDecoration: "none", display: "inline-flex" }}><Icon name="proof" size={14} /></a>
                    : "—"}
                </td>
                <td className="col-m-hide" style={{ color: "var(--text-2)" }}>{p.note || "—"}</td>
              </tr>
            )) : (
              <tr><td colSpan={9} style={{ textAlign: "center", color: "var(--text-3)", padding: 20 }}>No payments</td></tr>
            )}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={6} className="col-m-hide"></td>
              <td className="tsum-v col-num green"><span className="m-only tsum-k">Total Paid</span>{fmt(invoice.total_paid_sar)}<span className="m-only"> SAR</span></td>
              <td colSpan={2} className="col-m-hide"></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
