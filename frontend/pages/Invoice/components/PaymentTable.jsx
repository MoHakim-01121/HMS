import { Icon } from "../../../components/icons.jsx";
import Table from "../../../components/ui/Table.jsx";

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
          <Icon name="message" size={13} /> {unpaid ? "Draft Message" : "Paid Message"}
        </button>
      </div>
      <Table
        columns={[
          { header: "Res#", className: "col-m-hide cell-id", style: { fontFamily: "'JetBrains Mono', monospace" }, render: (p) => p.linked_number || "—" },
          { header: "Date", className: "col-m-hide", render: (p) => p.payment_date || "—" },
          {
            header: "Method",
            className: "col-m-primary",
            render: (p) => (
              <>
                <span className="m-hide">{p.method || "—"}</span>
                <span className="m-only" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                  {p.linked_number || "—"}
                  {p.proof_url && <>&nbsp;&nbsp;<a href={p.proof_url} target="_blank" rel="noreferrer" style={{ fontFamily: "inherit", fontSize: 11, color: "var(--accent-2)", textDecoration: "none", fontWeight: 500 }}>(Proof ↗)</a></>}
                </span>
                <span className="m-sub" style={{ fontFamily: "inherit" }}>
                  {(p.method || "—") + " · " + (p.payment_date || "—")}
                  {p.currency !== "SAR" && <span style={{ fontFamily: "'JetBrains Mono', monospace", display: "block" }}>{fmt(p.amount_int)} {p.currency} ÷ {fmt(p.exchange_rate)}</span>}
                </span>
              </>
            ),
          },
          { header: "Amount", headerClassName: "col-num", className: "mono col-num col-m-hide", render: (p) => fmt(p.amount_int) },
          { header: "Currency", className: "col-m-hide", render: (p) => <span className="badge badge-gray">{p.currency}</span> },
          { header: "Rate", headerClassName: "col-num", className: "col-num col-m-hide", style: { color: "var(--text-2)" }, render: (p) => p.currency !== "SAR" ? p.exchange_rate_fmt : "—" },
          { header: "SAR", headerClassName: "col-num", className: "mono col-money col-m-amount", render: (p) => <>{fmt(p.amount_sar_int)}<span className="m-only"> SAR</span></> },
          {
            header: "Proof",
            className: "col-m-hide",
            render: (p) => p.proof_url
              ? <a href={p.proof_url} target="_blank" rel="noreferrer" title="View proof" style={{ color: "var(--accent-2)", textDecoration: "none", display: "inline-flex" }}><Icon name="proof" size={14} /></a>
              : "—",
          },
          { header: "Note", className: "col-m-hide", style: { color: "var(--text-2)" }, render: (p) => p.note || "—" },
        ]}
        rows={payments}
        rowKey={(p, i) => i}
        empty="No payments"
        footer={
          <tr>
            <td colSpan={6} className="col-m-hide"></td>
            <td className="tsum-v col-num green"><span className="m-only tsum-k">Total Paid</span>{fmt(invoice.total_paid_sar)}<span className="m-only"> SAR</span></td>
            <td colSpan={2} className="col-m-hide"></td>
          </tr>
        }
      />
    </div>
  );
}
