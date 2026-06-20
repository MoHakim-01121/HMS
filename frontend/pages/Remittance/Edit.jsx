import { useMemo, useState } from "react";
import { useForm } from "@inertiajs/react";

const fmt = (n) => Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 0 });
const inputStyle = {
  width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)",
  borderRadius: "var(--r)", color: "var(--text)", fontSize: 13, padding: "8px 10px", fontFamily: "inherit",
};

export default function Edit({ rem, lines = [] }) {
  const [amounts, setAmounts] = useState(
    Object.fromEntries(lines.map((l) => [l.line_id, String(Math.round(l.amount_sar || 0))]))
  );
  const [removeProof, setRemoveProof] = useState(false);
  const form = useForm({
    date: rem.date || "",
    receipt_reference: rem.receipt_reference || "",
    status: rem.status || "pending",
    note: rem.note || "",
    proof: null,
    remove_proof: "",
    lines: "[]",
  });

  const total = useMemo(
    () => Object.values(amounts).reduce((sum, v) => sum + (parseFloat(v) || 0), 0),
    [amounts]
  );
  const setAmount = (id, v) => setAmounts((prev) => ({ ...prev, [id]: v }));

  const submit = (e) => {
    e.preventDefault();
    const payload = lines.map((l) => ({ line_id: l.line_id, amount_sar: parseFloat(amounts[l.line_id]) || 0 }));
    form.transform((d) => ({
      ...d,
      remove_proof: removeProof ? "1" : "",
      lines: JSON.stringify(payload),
    }));
    form.post(`/remittance/${rem.id}/edit/`, { forceFormData: true });
  };

  return (
    <div className="page">
      <style>{CSS}</style>
      <div className="page-header">
        <div className="page-title">Edit {rem.remittance_number}</div>
      </div>

      <form method="post" onSubmit={submit}>
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-body">
            <div className="form-header-grid">
              <div>
                <label className="field-label">Transfer Date</label>
                <input type="date" value={form.data.date} required style={inputStyle}
                  onChange={(e) => form.setData("date", e.target.value)} />
              </div>
              <div>
                <label className="field-label">Receipt Reference</label>
                <input type="text" value={form.data.receipt_reference} placeholder="Receipt code from HQ" style={inputStyle}
                  onChange={(e) => form.setData("receipt_reference", e.target.value)} />
              </div>
              <div>
                <label className="field-label">Status</label>
                <select value={form.data.status} style={inputStyle}
                  onChange={(e) => form.setData("status", e.target.value)}>
                  <option value="pending">Pending</option>
                  <option value="received">Received</option>
                </select>
              </div>
              <div>
                <label className="field-label">Note</label>
                <input type="text" value={form.data.note} placeholder="e.g. BCA Transfer 01/06" style={inputStyle}
                  onChange={(e) => form.setData("note", e.target.value)} />
              </div>
              <div>
                <label className="field-label">Receipt</label>
                <input type="file" accept="image/*,.pdf" style={{ ...inputStyle, color: "var(--text-2)", padding: "7px 10px", boxSizing: "border-box" }}
                  onChange={(e) => form.setData("proof", e.target.files[0] || null)} />
                {rem.proof_url && !removeProof && (
                  <div style={{ marginTop: 4, display: "flex", gap: 6 }}>
                    <a href={rem.proof_url} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: "var(--accent-2)" }}>View ↗</a>
                    <button type="button" onClick={() => setRemoveProof(true)} style={{ background: "none", border: "none", fontSize: 11, color: "var(--red)", cursor: "pointer", padding: 0 }}>Remove</button>
                  </div>
                )}
                {removeProof && (
                  <div style={{ marginTop: 4, fontSize: 11, color: "var(--red)" }}>
                    Receipt will be removed on save. <button type="button" onClick={() => setRemoveProof(false)} style={{ background: "none", border: "none", fontSize: 11, color: "var(--accent-2)", cursor: "pointer", padding: 0 }}>Cancel</button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">Reservations</span>
          </div>
          {lines.length > 0 ? (
            <>
              <div className="table-wrap">
                <table className="rem-table">
                  <thead>
                    <tr>
                      <th>Res#</th>
                      <th>Invoice</th>
                      <th>Client</th>
                      <th className="r">Amount (SAR)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lines.map((line) => (
                      <tr key={line.line_id}>
                        <td style={{ fontFamily: "monospace", fontWeight: 700 }}>{line.linked_number}</td>
                        <td>
                          {line.invoice ? (
                            <a href={`/invoice/${line.invoice.pk}/`} target="_blank" rel="noreferrer"
                              style={{ color: "var(--accent-2)", textDecoration: "none", fontSize: 12 }}>{line.invoice.invoice_number}</a>
                          ) : "—"}
                        </td>
                        <td style={{ fontSize: 12, color: "var(--text-2)" }}>{line.invoice?.customer_name || "—"}</td>
                        <td>
                          <input type="number" className="rem-input" min="0" step="1"
                            value={amounts[line.line_id] ?? ""}
                            onChange={(e) => setAmount(line.line_id, e.target.value)} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="rem-total-bar">
                <span className="rem-total-label">Total</span>
                <span className="rem-total-val">{fmt(total)} SAR</span>
              </div>
            </>
          ) : (
            <div className="empty" style={{ padding: 40 }}>
              <div className="empty-title">No reservations</div>
            </div>
          )}
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
          <a href={`/remittance/${rem.id}/`} className="btn btn-secondary">Cancel</a>
          <button type="submit" className="btn btn-primary" disabled={form.processing}>
            {form.processing ? "Saving..." : "Save"}
          </button>
        </div>
      </form>
    </div>
  );
}

const CSS = `
.form-header-grid { display:grid; grid-template-columns:1fr 1fr 1fr 1fr 1fr; gap:16px; }
@media(max-width:600px) { .form-header-grid { grid-template-columns:1fr; } }

.rem-table { width:100%; border-collapse:collapse; }
.rem-table th {
  font-size:11px; font-weight:600; color:var(--text-3);
  text-transform:uppercase; letter-spacing:.04em;
  padding:8px 12px; text-align:left; white-space:nowrap;
  border-bottom:1px solid var(--border);
}
.rem-table th.r { text-align:right; }
.rem-table td { padding:10px 12px; border-bottom:1px solid var(--border); font-size:13px; vertical-align:middle; }
.rem-table tbody tr:last-child td { border-bottom:none; }

.rem-input {
  width:120px; background:var(--surface-2);
  border:1px solid var(--border); border-radius:var(--r);
  color:var(--text); font-size:13px; font-family:monospace;
  padding:6px 10px; text-align:right;
  display:block; margin-left:auto;
}
.rem-input:focus { outline:none; border-color:var(--accent); }

.rem-total-bar {
  display:flex; align-items:center; justify-content:space-between;
  padding:12px 16px; border-top:2px solid var(--border);
  background:var(--surface-2);
}
.rem-total-label { font-size:12px; font-weight:600; color:var(--text-2); }
.rem-total-val { font-family:monospace; font-size:18px; font-weight:700; color:var(--accent-2); }
`;
