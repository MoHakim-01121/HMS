import { router } from "@inertiajs/react";
import { useConfirm } from "../../components/ui/ConfirmDialog.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

function Field({ label, children }) {
  return <div className="field"><div className="field-label">{label}</div><div className="field-value">{children}</div></div>;
}

export default function Detail({ penalty: p }) {
  const [confirm, confirmDialog] = useConfirm();
  const del = () => confirm({ title: "Delete penalty", message: `Delete penalty document ${p.penalty_number}?`, onConfirm: () => router.post(`/penalty/${p.id}/delete/`) });
  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">{p.penalty_number}</div>
          <div className="page-sub">Penalti pembatalan — {p.cl.confirmation_number}</div>
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
              <span className="card-title">Detail Penalti</span>
              <span className={"badge " + (p.is_paid ? "badge-green" : "badge-yellow")}>{p.is_paid ? "Lunas" : "Belum"}</span>
            </div>
            <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <Field label="Tamu / CL">{p.cl.guest_name} — {p.cl.confirmation_number}</Field>
              <Field label="Tanggal Pembatalan">{p.cancellation_date || "—"}</Field>
              <Field label="Jumlah Penalti">{fmt(p.penalty_amount)} {p.penalty_currency}</Field>
              {p.exchange_rate !== 1 && <Field label="Kurs">{p.exchange_rate}</Field>}
              {p.reason && <Field label="Alasan">{p.reason}</Field>}
              {p.is_paid && <Field label="Tanggal Bayar">{p.payment_date || "—"}</Field>}
              {p.payment_method && <Field label="Metode Bayar">{p.payment_method}</Field>}
              {p.payment_note && <Field label="Catatan Bayar">{p.payment_note}</Field>}
              {p.note && (
                <div className="field">
                  <div className="field-label">Catatan</div>
                  <div style={{ fontSize: 13, color: "var(--text-2)", whiteSpace: "pre-wrap" }}>{p.note}</div>
                </div>
              )}
            </div>
            <div style={{ padding: "12px 20px", borderTop: "1px solid var(--border)" }}>
              <button onClick={del} className="btn btn-danger btn-sm btn-full">Hapus Penalti</button>
            </div>
          </div>
        </div>
      </div>
      {confirmDialog}
    </div>
  );
}
