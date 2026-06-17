// Hero block ported from invoice_detail.html. Hero badge uses the English
// Paid/Partial/Unpaid labels (distinct from the list's Indonesian labels).
function heroBadge(total, remaining) {
  if (remaining === 0) return ["badge badge-green", "Paid"];
  if (remaining < total) return ["badge badge-yellow", "Partial"];
  return ["badge badge-red", "Unpaid"];
}

export default function InvoiceHero({ invoice }) {
  const [cls, label] = heroBadge(invoice.total_sar, invoice.remaining_sar);
  return (
    <div className="dhero">
      <div className="dhero-main">
        <div className="dhero-kicker">Invoice Hotel</div>
        <div className="dhero-title">{invoice.invoice_number}</div>
        <div className="dhero-sub">
          {invoice.customer_name}
          {invoice.issued_date ? ` · ${invoice.issued_date}` : ""}
        </div>
      </div>
      <div className="dhero-side">
        <div className="dhero-badges">
          <span className={cls}>{label}</span>
        </div>
        <div className="dhero-actions">
          <a href={`/invoice/${invoice.pk}/pdf/`} target="_blank" rel="noreferrer" className="btn btn-primary btn-sm">PDF</a>
          <a href={`/invoice/${invoice.pk}/edit/`} className="btn btn-secondary btn-sm">Edit</a>
        </div>
      </div>
    </div>
  );
}
