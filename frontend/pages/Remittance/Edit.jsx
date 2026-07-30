import { useMemo, useState } from "react";
import { useForm } from "@inertiajs/react";
import PageBack from "../../components/ui/PageBack.jsx";
import { REM_TABLE_CSS } from "./remittanceStyles.js";

const fmt = (n) => Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 0 });
const inputStyle = {
  width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)",
  borderRadius: "var(--r)", color: "var(--text)", fontSize: 13, padding: "8px 10px", fontFamily: "inherit",
};

export default function Edit({ rem, lines = [], reservasi = [] }) {
  const [amounts, setAmounts] = useState(
    Object.fromEntries(lines.map((l) => [l.line_id, String(Math.round(l.amount_sar || 0))]))
  );
  const [removedIds, setRemovedIds] = useState([]);
  const [added, setAdded] = useState({});
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

  const keptLines = useMemo(() => lines.filter((l) => !removedIds.includes(l.line_id)), [lines, removedIds]);
  const total = useMemo(() => {
    const kept = keptLines.reduce((sum, l) => sum + (parseFloat(amounts[l.line_id]) || 0), 0);
    const extra = Object.values(added).reduce((sum, v) => sum + (parseFloat(v) || 0), 0);
    return kept + extra;
  }, [keptLines, amounts, added]);

  const setAmount = (id, v) => setAmounts((prev) => ({ ...prev, [id]: v }));
  const setAdd = (ln, v) => setAdded((prev) => ({ ...prev, [ln]: v }));
  const removeLine = (id) => setRemovedIds((prev) => [...prev, id]);
  const undoRemove = (id) => setRemovedIds((prev) => prev.filter((x) => x !== id));

  const submit = (e) => {
    e.preventDefault();
    const payload = [
      ...keptLines.map((l) => ({ line_id: l.line_id, amount_sar: parseFloat(amounts[l.line_id]) || 0 })),
      ...reservasi
        .map((r) => ({
          linked_number: r.linked_number,
          invoice_id: r.invoice_id,
          amount_sar: parseFloat(added[r.linked_number]) || 0,
        }))
        .filter((l) => l.amount_sar > 0),
    ];
    form.transform((d) => ({
      ...d,
      remove_proof: removeProof ? "1" : "",
      lines: JSON.stringify(payload),
    }));
    form.post(`/remittance/${rem.id}/edit/`, { forceFormData: true });
  };

  return (
    <div className="page">
      <style>{REM_TABLE_CSS + CSS}</style>
      <PageBack href={`/remittance/${rem.id}/`} />
      <div className="page-header">
        <div className="page-title">Edit {rem.remittance_number}</div>
      </div>

      <form method="post" onSubmit={submit}>
        {rem.status === "received" && (
          <div className="rem-received-note">
            Transfer ini sudah ditandai <strong>Received</strong> oleh HQ. Perubahan di sini akan mengubah catatan yang sudah dikonfirmasi.
          </div>
        )}

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
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {lines.map((line) => {
                      const removed = removedIds.includes(line.line_id);
                      return (
                        <tr key={line.line_id} style={removed ? { opacity: 0.45 } : undefined}>
                          <td style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, textDecoration: removed ? "line-through" : "none" }}>{line.linked_number}</td>
                          <td>
                            {line.invoice ? (
                              <a href={`/invoice/${line.invoice.pk}/`} target="_blank" rel="noreferrer"
                                style={{ color: "var(--accent-2)", textDecoration: "none", fontSize: 12 }}>{line.invoice.invoice_number}</a>
                            ) : "—"}
                          </td>
                          <td style={{ fontSize: 12, color: "var(--text-2)" }}>{line.invoice?.customer_name || "—"}</td>
                          <td>
                            <input type="number" className="rem-input" min="0" step="1" disabled={removed}
                              value={amounts[line.line_id] ?? ""}
                              onChange={(e) => setAmount(line.line_id, e.target.value)} />
                          </td>
                          <td style={{ textAlign: "right" }}>
                            {removed ? (
                              <button type="button" onClick={() => undoRemove(line.line_id)} className="rem-linkbtn">Undo</button>
                            ) : (
                              <button type="button" onClick={() => removeLine(line.line_id)} className="rem-linkbtn danger" title="Remove from this transfer">Remove</button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="empty" style={{ padding: 40 }}>
              <div className="empty-title">No reservations</div>
            </div>
          )}
        </div>

        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-header">
            <span className="card-title">Add Reservation</span>
          </div>
          {reservasi.length > 0 ? (
            <div className="table-wrap">
              <table className="rem-table">
                <thead>
                  <tr>
                    <th>Res#</th>
                    <th>Invoice</th>
                    <th>Client</th>
                    <th>Check-in</th>
                    <th className="r">Idle (SAR)</th>
                    <th className="r">Add (SAR)</th>
                  </tr>
                </thead>
                <tbody>
                  {reservasi.map((r) => (
                    <tr key={r.linked_number}>
                      <td style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 700 }}>{r.linked_number}</td>
                      <td>
                        {r.invoice_id ? (
                          <a href={`/invoice/${r.invoice_id}/`} target="_blank" rel="noreferrer"
                            style={{ color: "var(--accent-2)", textDecoration: "none", fontSize: 12 }}>{r.invoice_number}</a>
                        ) : "—"}
                      </td>
                      <td style={{ fontSize: 12, color: "var(--text-2)" }}>{r.customer_name || "—"}</td>
                      <td style={{ fontSize: 12 }}>{r.check_in || "—"}</td>
                      <td className="r" style={{ fontFamily: "'JetBrains Mono', monospace" }}>{fmt(r.mengendap)}</td>
                      <td>
                        <input type="number" className="rem-input" min="0" step="1" max={r.mengendap}
                          placeholder="0"
                          value={added[r.linked_number] ?? ""}
                          onChange={(e) => setAdd(r.linked_number, e.target.value)} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty" style={{ padding: 28 }}>
              <div className="empty-title">Nothing left to add</div>
              <div className="empty-sub">All idle payments are already covered</div>
            </div>
          )}
          <div className="rem-total-bar">
            <span className="rem-total-label">Total transfer</span>
            <span className="rem-total-val">{fmt(total)} SAR</span>
          </div>
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

// Edit-specific layout only; shared table/input/total styles come from REM_TABLE_CSS.
const CSS = `
.form-header-grid { display:grid; grid-template-columns:1fr 1fr 1fr 1fr 1fr; gap:16px; }
@media(max-width:600px) { .form-header-grid { grid-template-columns:1fr; } }
`;
