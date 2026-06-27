import { router } from "@inertiajs/react";
import { useConfirm } from "../../components/ui/ConfirmDialog.jsx";
import PageBack from "../../components/ui/PageBack.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

function Field({ label, children }) {
  return <div className="field"><div className="field-label">{label}</div><div className="field-value">{children}</div></div>;
}

export default function Detail({ penalty: p }) {
  const [confirm, confirmDialog] = useConfirm();
  const del = () => confirm({ title: "Delete penalty", message: `Delete penalty document ${p.penalty_number}?`, onConfirm: () => router.post(`/penalty/${p.id}/delete/`) });
  return (
    <div className="page">
      <PageBack href={`/cl/${p.cl.id}/`} label="Back to CL" />
      <div className="page-header">
        <div>
          <div className="page-title">{p.penalty_number}</div>
          <div className="page-sub">Cancellation penalty — {p.cl.confirmation_number}</div>
        </div>
        <div className="page-actions">
          <a href={`/penalty/${p.id}/edit/`} className="btn btn-secondary btn-sm">Edit</a>
          <a href={`/penalty/${p.id}/pdf/`} className="btn btn-ghost btn-sm" target="_blank" rel="noreferrer">PDF</a>
        </div>
      </div>

      <div className="detail-grid">
        <div>
          <div className="card">
            <div className="card-header">
              <span className="card-title">Penalty Details</span>
              <span className={"badge " + (p.is_paid ? "badge-green" : "badge-yellow")}>{p.is_paid ? "Paid" : "Unpaid"}</span>
            </div>
            <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <Field label="Guest / CL">{p.cl.guest_name} — {p.cl.confirmation_number}</Field>
              <Field label="Cancellation Date">{p.cancellation_date || "—"}</Field>
              <Field label="Penalty Amount">{fmt(p.penalty_amount)} {p.penalty_currency}</Field>
              {p.exchange_rate !== 1 && <Field label="Exchange Rate">{p.exchange_rate}</Field>}
              {p.reason && <Field label="Reason">{p.reason}</Field>}
              {p.is_paid && <Field label="Payment Date">{p.payment_date || "—"}</Field>}
              {p.payment_method && <Field label="Payment Method">{p.payment_method}</Field>}
              {p.payment_note && <Field label="Payment Note">{p.payment_note}</Field>}
              {p.note && (
                <div className="field">
                  <div className="field-label">Note</div>
                  <div style={{ fontSize: 13, color: "var(--text-2)", whiteSpace: "pre-wrap" }}>{p.note}</div>
                </div>
              )}
            </div>
            <div style={{ padding: "12px 20px", borderTop: "1px solid var(--border)" }}>
              <button onClick={del} className="btn btn-danger btn-sm btn-full">Delete Penalty</button>
            </div>
          </div>
        </div>
      </div>
      {confirmDialog}
    </div>
  );
}
