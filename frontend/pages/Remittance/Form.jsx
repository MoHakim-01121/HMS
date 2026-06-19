import { useMemo, useState } from "react";
import { useForm } from "@inertiajs/react";

const fmt = (n) => Number(n || 0).toLocaleString("id-ID", { maximumFractionDigits: 0 });

export default function Form({ reservasi = [], today, error }) {
  const [amounts, setAmounts] = useState({});
  const form = useForm({
    date: today || "",
    receipt_reference: "",
    note: "",
    proof: null,
    lines: "[]",
  });

  const hasRows = reservasi.length > 0;
  const total = useMemo(
    () => Object.values(amounts).reduce((sum, v) => sum + (parseFloat(v) || 0), 0),
    [amounts]
  );

  const setAmount = (ln, v) => setAmounts((prev) => ({ ...prev, [ln]: v }));

  const isiSemua = () => {
    const next = {};
    for (const r of reservasi) if (r.mengendap > 0) next[r.linked_number] = r.mengendap;
    setAmounts(next);
  };

  const submit = (e) => {
    e.preventDefault();
    const lines = reservasi
      .filter((r) => r.mengendap > 0)
      .map((r) => ({
        linked_number: r.linked_number,
        invoice_id: r.invoice_id,
        amount_sar: parseFloat(amounts[r.linked_number]) || 0,
      }))
      .filter((l) => l.amount_sar > 0);
    form.transform((d) => ({ ...d, lines: JSON.stringify(lines) }));
    form.post("/remittance/new/", { forceFormData: true });
  };

  return (
    <div className="page">
      <style>{CSS}</style>

      <div className="page-header" style={{ marginBottom: 14 }}>
        <div>
          <div className="page-title">Kirim ke Pusat</div>
          <div className="page-sub">Rekap pembayaran yang mengendap untuk dikirim</div>
        </div>
      </div>

      {error && <div className="alert alert-error" style={{ marginBottom: 12 }}>{error}</div>}

      <form method="post" onSubmit={submit}>
        {/* ── Header ── */}
        <div className="form-panel" style={{ marginBottom: 12 }}>
          <div className="form-section">
            <div className="form-section-label">Info Pengiriman</div>
            <div className="fg-4">
              <div className="ff">
                <label>Tanggal Kirim *</label>
                <input type="date" value={form.data.date} required
                  onChange={(e) => form.setData("date", e.target.value)} />
              </div>
              <div className="ff">
                <label>Receipt Reference</label>
                <input type="text" value={form.data.receipt_reference} placeholder="Kode kwitansi dari Pusat"
                  onChange={(e) => form.setData("receipt_reference", e.target.value)} />
              </div>
              <div className="ff">
                <label>Note</label>
                <input type="text" value={form.data.note} placeholder="Transfer BCA 01/06"
                  onChange={(e) => form.setData("note", e.target.value)} />
              </div>
              <div className="ff">
                <label>Kwitansi <span style={{ fontWeight: 400, textTransform: "none", letterSpacing: 0, fontFamily: "inherit" }}>(opsional)</span></label>
                <input type="file" accept="image/*,.pdf"
                  onChange={(e) => form.setData("proof", e.target.files[0] || null)} />
              </div>
            </div>
          </div>
        </div>

        {/* ── Reservasi ── */}
        <div className="form-panel">
          <div className="form-section" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", paddingBottom: 12 }}>
            <div className="form-section-label" style={{ marginBottom: 0 }}>Reservasi</div>
            {hasRows && (
              <button type="button" className="btn btn-ghost" style={{ height: 26, padding: "0 10px", fontSize: 12 }} onClick={isiSemua}>Isi Semua</button>
            )}
          </div>

          {hasRows ? (
            <>
              <div className="table-wrap" style={{ overflowX: "auto" }}>
                <table className="rem-table">
                  <thead>
                    <tr>
                      <th>Res#</th>
                      <th>Invoice</th>
                      <th>Client</th>
                      <th className="r">Check-in</th>
                      <th className="r">Check-out</th>
                      <th className="r">Total</th>
                      <th className="r">Terbayar</th>
                      <th className="r">Sudah Kirim</th>
                      <th className="r">Mengendap</th>
                      <th className="r">Kirim Sekarang</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reservasi.map((res) => {
                      const lunas = res.mengendap <= 0 && res.sudah_dikirim >= res.total_sar;
                      return (
                        <tr key={res.linked_number} className={res.mengendap > 0 ? "row-pending" : lunas ? "row-lunas" : ""}>
                          <td className="td-res">{res.linked_number}</td>
                          <td>
                            <a href={`/invoice/${res.invoice_id}/`} target="_blank" rel="noreferrer" className="td-link">{res.invoice_number}</a>
                          </td>
                          <td className="td-muted">{res.customer_name}</td>
                          <td className="td-date" style={{ textAlign: "right" }}>{res.check_in || "-"}</td>
                          <td className="td-date" style={{ textAlign: "right" }}>{res.check_out || "-"}</td>
                          <td className="td-mono">{fmt(res.total_sar)}</td>
                          <td className="td-mono">{fmt(res.terbayar_total)}</td>
                          <td className="td-mono">{fmt(res.sudah_dikirim)}</td>
                          <td className="td-pending">{res.mengendap > 0 ? fmt(res.mengendap) : "-"}</td>
                          <td>
                            {res.mengendap > 0 ? (
                              <input type="number" className="rem-input" min="0" max={res.mengendap} step="1" placeholder="0"
                                value={amounts[res.linked_number] ?? ""}
                                onChange={(e) => setAmount(res.linked_number, e.target.value)} />
                            ) : lunas ? (
                              <span className="badge-lunas">Lunas</span>
                            ) : (
                              <span style={{ float: "right", color: "var(--text-3)", fontSize: 12 }}>-</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="rem-total-bar">
                <span className="rem-total-label">Total dikirim sekarang</span>
                <span className="rem-total-val">{fmt(total)} SAR</span>
              </div>
            </>
          ) : (
            <div className="empty" style={{ padding: 40 }}>
              <div className="empty-title">Tidak ada reservasi</div>
              <div className="empty-sub">Belum ada pembayaran yang tercatat</div>
            </div>
          )}
        </div>

        <div className="form-actions" style={{ padding: "14px 0 4px" }}>
          <a href="/remittance/" className="btn btn-ghost">Batal</a>
          {hasRows && (
            <button type="submit" className="btn btn-primary" disabled={form.processing}>
              <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
              {form.processing ? "Menyimpan..." : "Simpan Remittance"}
            </button>
          )}
        </div>
      </form>
    </div>
  );
}

const CSS = `
.rem-table { width:100%; border-collapse:collapse; }
.rem-table th {
  font-family:'JetBrains Mono',monospace; font-size:10px; font-weight:600; color:var(--text-3);
  text-transform:uppercase; letter-spacing:.7px;
  padding:8px 12px; text-align:left; white-space:nowrap;
  border-bottom:1px solid var(--border);
  background:var(--surface-2);
}
.rem-table th.r { text-align:right; }
.rem-table td { padding:10px 12px; border-bottom:1px solid var(--border); font-size:13px; vertical-align:middle; }
.rem-table tbody tr:last-child td { border-bottom:none; }
.rem-table tbody tr.row-pending { background:color-mix(in srgb, var(--yellow) 5%, transparent); }
.rem-table tbody tr.row-lunas td { opacity:.5; }

.td-res  { font-family:'JetBrains Mono',monospace; font-weight:700; font-size:12px; color:var(--text); white-space:nowrap; }
.td-link { color:var(--accent-2); text-decoration:none; font-size:12px; white-space:nowrap; }
.td-link:hover { text-decoration:underline; }
.td-muted { font-size:12px; color:var(--text-2); }
.td-date  { font-size:12px; color:var(--text-2); white-space:nowrap; }
.td-mono  { font-family:'JetBrains Mono',monospace; font-size:12px; color:var(--text-2); text-align:right; white-space:nowrap; }
.td-pending { font-family:'JetBrains Mono',monospace; font-size:12px; font-weight:700; color:var(--yellow); text-align:right; white-space:nowrap; }

.rem-input {
  width:110px; background:var(--surface-2);
  border:1px solid var(--border); border-radius:var(--r);
  color:var(--text); font-size:13px; font-family:'JetBrains Mono',monospace;
  padding:6px 10px; text-align:right;
  transition:border-color .12s;
  display:block; margin-left:auto;
}
.rem-input:focus { outline:none; border-color:var(--accent); }

.badge-lunas {
  font-size:11px; font-weight:600; color:var(--green);
  background:color-mix(in srgb, var(--green) 12%, transparent);
  border-radius:var(--r); padding:3px 8px;
  float:right;
}

.rem-total-bar {
  display:flex; align-items:center; justify-content:space-between;
  padding:13px 16px; border-top:1px solid var(--border);
  background:var(--surface-2);
}
.rem-total-label { font-family:'JetBrains Mono',monospace; font-size:10px; font-weight:600; text-transform:uppercase; letter-spacing:.7px; color:var(--text-3); }
.rem-total-val { font-family:'JetBrains Mono',monospace; font-size:18px; font-weight:700; color:var(--accent-2); }
`;
