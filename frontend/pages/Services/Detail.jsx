import { Icon } from "../../components/icons.jsx";
import PageBack from "../../components/ui/PageBack.jsx";
import Table from "../../components/ui/Table.jsx";
import RowActions from "../../components/ui/RowActions.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");
function openDraft(type, pk) {
  window.dispatchEvent(new CustomEvent("open-draft", { detail: { type, pk } }));
}

export default function Detail({ invoice, visa_services, payments_history, services_remaining }) {
  const cur = invoice.currency;
  const unpaid = services_remaining > 0;
  return (
    <div className="page">
      <PageBack href="/services/" />
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
        <div className="card-header"><span className="card-title">Invoice Info</span></div>
        <div className="card-body">
          <div className="grid-3">
            <div className="field"><div className="field-label">Customer</div><div className="field-value">{invoice.customer_name}</div></div>
            <div className="field"><div className="field-label">Invoice #</div><div className="field-value" style={{ fontFamily: "'JetBrains Mono', monospace" }}>{invoice.invoice_number}</div></div>
            <div className="field"><div className="field-label">Currency</div><div className="field-value">{cur}</div></div>
            <div className="field"><div className="field-label">Issued Date</div><div className="field-value">{invoice.issued_date || "—"}</div></div>
            <div className="field"><div className="field-label">Due Date</div><div className="field-value">{invoice.due_date || "—"}</div></div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><span className="card-title">Services</span></div>
        <Table
          columns={[
            { header: "#", className: "col-m-hide", style: { color: "var(--text-2)" }, render: (svc) => svc.service_no },
            { header: "Service", className: "col-m-primary", render: (svc) => svc.product },
            { header: "Qty", className: "col-m-hide", render: (svc) => svc.qty },
            { header: "Price", className: "mono col-m-hide", render: (svc) => `${fmt(svc.price)} ${cur}` },
            { header: "Total", className: "mono col-m-amount", style: { fontWeight: 600 }, render: (svc) => `${fmt(svc.total)} ${cur}` },
            { header: "Remaining", className: (svc) => `${svc.remaining_class} mono col-m-hide`, render: (svc) => `${fmt(svc.remaining)} ${cur}` },
          ]}
          rows={visa_services}
          rowKey={(svc, i) => i}
          empty="No service data"
        />
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Payments</span>
          <button className="btn btn-ghost btn-sm" onClick={() => openDraft(unpaid ? "services" : "services_lunas", invoice.pk)}>
            <Icon name="message" size={13} /> {unpaid ? "Draft Message" : "Paid Message"}
          </button>
        </div>
        <Table
          columns={[
            { header: "Svc#", className: "col-m-hide", render: () => "—" },
            { header: "Date", className: "col-m-primary", style: { color: "var(--text-2)" }, render: (p) => p.payment_date || "—" },
            { header: "Method", className: "col-m-secondary", render: (p) => p.payment_method || "—" },
            { header: "Amount", className: "mono col-m-amount", render: (p) => fmt(p.payment_amount) },
            { header: "Currency", className: "col-m-hide", render: (p) => <span className="badge badge-gray">{p.payment_currency}</span> },
            { header: "Rate", className: "col-m-hide", style: { color: "var(--text-2)" }, render: (p) => p.payment_exchange },
            { header: "Note", className: "col-m-hide", style: { color: "var(--text-2)" }, render: (p) => p.payment_note || "—" },
            {
              header: "Proof",
              className: "col-m-actions",
              render: (p) => p.proof_url
                ? <RowActions actions={[{ icon: "search", label: "View proof", href: p.proof_url, external: true }]} />
                : <span className="col-dim">—</span>,
            },
          ]}
          rows={payments_history}
          rowKey={(p, i) => i}
          empty="No payment data"
        />
      </div>
    </div>
  );
}
