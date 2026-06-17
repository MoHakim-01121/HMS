import { Icon } from "../../components/icons.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");
function openDraft(type, pk) {
  window.dispatchEvent(new CustomEvent("open-draft", { detail: { type, pk } }));
}

export default function Detail({ invoice, visa_services, payments_history, services_remaining }) {
  const cur = invoice.currency;
  const unpaid = services_remaining > 0;
  return (
    <div className="page">
      <div className="page-header" style={{ marginBottom: 20 }}>
        <div>
          <div className="page-title">{invoice.invoice_number}</div>
          <div className="page-sub">{invoice.customer_name} · {invoice.created_at}</div>
        </div>
        <div className="page-actions">
          <span className="badge badge-gray">{cur}</span>
          {invoice.company === "ijabah" ? <span className="badge badge-yellow">Ijabah</span> : <span className="badge badge-blue">Konoz</span>}
        </div>
      </div>

      <div className="card">
        <div className="card-header"><span className="card-title">Info Invoice</span></div>
        <div className="card-body">
          <div className="grid-3">
            <div className="field"><div className="field-label">Customer</div><div className="field-value">{invoice.customer_name}</div></div>
            <div className="field"><div className="field-label">Invoice #</div><div className="field-value" style={{ fontFamily: "monospace" }}>{invoice.invoice_number}</div></div>
            <div className="field"><div className="field-label">Currency</div><div className="field-value">{cur}</div></div>
            <div className="field"><div className="field-label">Issued Date</div><div className="field-value">{invoice.issued_date || "—"}</div></div>
            <div className="field"><div className="field-label">Due Date</div><div className="field-value">{invoice.due_date || "—"}</div></div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><span className="card-title">Services</span></div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>#</th><th>Layanan</th><th>Qty</th><th>Harga</th><th>Total</th><th>Sisa</th></tr>
            </thead>
            <tbody>
              {visa_services.length ? visa_services.map((svc, i) => (
                <tr key={i}>
                  <td className="col-m-hide" style={{ color: "var(--text-2)" }}>{svc.service_no}</td>
                  <td className="col-m-primary">{svc.product}</td>
                  <td className="col-m-hide">{svc.qty}</td>
                  <td className="mono col-m-hide">{fmt(svc.price)} {cur}</td>
                  <td className="mono col-m-amount" style={{ fontWeight: 600 }}>{fmt(svc.total)} {cur}</td>
                  <td className={`${svc.remaining_class} mono col-m-hide`}>{fmt(svc.remaining)} {cur}</td>
                </tr>
              )) : (
                <tr><td colSpan={6} style={{ textAlign: "center", color: "var(--text-3)" }}>Tidak ada data layanan</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Pembayaran</span>
          <button className="btn btn-ghost btn-sm" onClick={() => openDraft(unpaid ? "services" : "services_lunas", invoice.pk)}>
            <Icon name="message" size={13} /> {unpaid ? "Buat Pesan" : "Draf Lunas"}
          </button>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Svc#</th><th>Tanggal</th><th>Metode</th><th>Jumlah</th><th>Mata Uang</th><th>Rate</th><th>Catatan</th><th>Bukti</th></tr>
            </thead>
            <tbody>
              {payments_history.length ? payments_history.map((p, i) => (
                <tr key={i}>
                  <td className="col-m-hide">—</td>
                  <td className="col-m-primary" style={{ color: "var(--text-2)" }}>{p.payment_date || "—"}</td>
                  <td className="col-m-secondary">{p.payment_method || "—"}</td>
                  <td className="mono col-m-amount">{fmt(p.payment_amount)}</td>
                  <td className="col-m-hide"><span className="badge badge-gray">{p.payment_currency}</span></td>
                  <td className="col-m-hide" style={{ color: "var(--text-2)" }}>{p.payment_exchange}</td>
                  <td className="col-m-hide" style={{ color: "var(--text-2)" }}>{p.payment_note || "—"}</td>
                  <td className="col-m-actions">{p.proof_url ? <a href={p.proof_url} target="_blank" rel="noreferrer" title="Lihat bukti" style={{ color: "var(--accent-2)", textDecoration: "none", display: "inline-flex" }}><Icon name="search" size={14} /></a> : <span className="col-dim">—</span>}</td>
                </tr>
              )) : (
                <tr><td colSpan={8} style={{ textAlign: "center", color: "var(--text-3)" }}>Tidak ada data pembayaran</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
