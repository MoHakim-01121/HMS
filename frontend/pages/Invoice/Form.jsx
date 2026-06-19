import { useMemo, useState } from "react";
import { useForm } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";

const PAY_COLS = "28px 90px 130px 130px 110px 70px 90px 1fr 70px 28px";
const CURRENCIES = ["SAR", "USD", "IDR"];
const METHODS = ["Cash", "Bank Transfer", "Direct", "Deposit"];
const fmt = (n) => Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 0 });

const blankRes = () => ({ reservation_number: "", hotel: "", check_in: "", check_out: "", reservation_total: "" });
const blankPay = () => ({ ref: "", date: "", method: "Cash", amount: "", currency: "SAR", exchange: 1, note: "", proof_keep: "", proof_url: null, file: null });

function seedFrom(src) {
  if (!src) return { reservations: [blankRes()], payments: [blankPay()], linkedClIds: [] };
  const reservations = (src.reservations || []).map((r) => ({
    reservation_number: r.reservation_number || "", hotel: r.hotel || "",
    check_in: r.check_in || "", check_out: r.check_out || "",
    reservation_total: r.reservation_total ?? "",
  }));
  const payments = (src.payments || []).map((p) => ({
    ref: String(p.ref ?? ""), date: p.date || "", method: p.method || "Cash",
    amount: p.amount ?? "", currency: p.currency || "SAR", exchange: p.exchange ?? 1,
    note: p.note || "", proof_keep: p.proof_keep || "", proof_url: p.proof_url || null, file: null,
  }));
  return {
    reservations: reservations.length ? reservations : [blankRes()],
    payments,
    linkedClIds: src.linked_cl_ids || [],
  };
}

export default function Form({ invoice, edit, suggested_number, default_company, cl_data = [], initial, errors = {} }) {
  const src = initial || invoice;
  const [company, setCompany] = useState(src?.company || default_company || "konoz");
  const [customerName, setCustomerName] = useState(src?.customer_name || "");
  const [invoiceNumber, setInvoiceNumber] = useState(src?.invoice_number || (edit ? "" : suggested_number) || "");
  const [issuedDate, setIssuedDate] = useState(src?.issued_date || "");
  const [dueDate, setDueDate] = useState(src?.due_date || "");

  const seeded = useMemo(() => seedFrom(src), []);
  const [reservations, setReservations] = useState(seeded.reservations);
  const [payments, setPayments] = useState(seeded.payments);
  const [linkedClIds, setLinkedClIds] = useState(seeded.linkedClIds);

  const form = useForm({});

  // ── Modal ──
  const [modalOpen, setModalOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState({});

  // ── Reservations ──
  const setRes = (i, key, val) => setReservations((rows) => rows.map((r, idx) => (idx === i ? { ...r, [key]: val } : r)));
  const addRes = () => setReservations((rows) => [...rows, blankRes()]);
  const removeRes = (i) => setReservations((rows) => rows.filter((_, idx) => idx !== i));

  // ── Payments ──
  const setPay = (i, patch) => setPayments((rows) => rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  const addPay = () => setPayments((rows) => [...rows, blankPay()]);
  const removePay = (i) => setPayments((rows) => rows.filter((_, idx) => idx !== i));
  const onCurrencyChange = (i, cur) => {
    const patch = { currency: cur };
    if (cur === "SAR") patch.exchange = 1;
    else if (String(payments[i].exchange) === "1") patch.exchange = "";
    setPay(i, patch);
  };

  const resOptions = reservations.map((r) => (r.reservation_number || "").trim()).filter(Boolean);

  // ── Totals (mirror invoice_form.js) ──
  const totals = useMemo(() => {
    const totalRes = reservations.reduce((a, r) => a + (parseFloat(r.reservation_total) || 0), 0);
    let totalPaidSar = 0;
    for (const p of payments) {
      const amount = parseFloat(p.amount) || 0;
      const ex = parseFloat(p.exchange) || 1;
      let sar = amount;
      if (p.currency === "IDR") sar = ex ? amount / ex : 0;
      else if (p.currency !== "SAR") sar = amount * ex;
      totalPaidSar += sar;
    }
    return { totalRes, totalPaidSar: Math.round(totalPaidSar), remaining: Math.round(totalRes - totalPaidSar) };
  }, [reservations, payments]);

  const remainingClass = totals.remaining <= 0 ? "green" : totals.remaining < totals.totalRes ? "yellow" : "red";

  // ── CL Import ──
  const filteredCls = useMemo(() => {
    const f = search.toLowerCase();
    return cl_data.filter((cl) => !f || cl.ref.toLowerCase().includes(f) || cl.guest.toLowerCase().includes(f) || cl.hotel.toLowerCase().includes(f));
  }, [search, cl_data]);
  const fmtDate = (d) => (d ? d.split("-").reverse().join("/") : "—");
  const openModal = () => { setSelected({}); setSearch(""); setModalOpen(true); };
  const toggleSel = (cl) => setSelected((s) => { const n = { ...s }; if (n[cl.id]) delete n[cl.id]; else n[cl.id] = cl; return n; });
  const doImport = () => {
    const cls = Object.values(selected);
    if (!cls.length) return;
    setReservations(cls.map((cl) => ({
      reservation_number: cl.ref, hotel: cl.hotel, check_in: cl.check_in || "",
      check_out: cl.check_out || "", reservation_total: cl.total || "",
    })));
    setLinkedClIds(cls.map((cl) => cl.id));
    if (!customerName.trim()) setCustomerName(cls[0].guest);
    setModalOpen(false);
  };

  const submit = (e) => {
    e.preventDefault();
    const resRows = reservations.filter((r) => (r.reservation_number || "").trim() || (parseFloat(r.reservation_total) || 0) > 0);
    const payRows = payments.filter((p) => (parseFloat(p.amount) || 0) > 0);
    form.transform(() => {
      const data = {
        company, customer_name: customerName, invoice_number: invoiceNumber,
        issued_date: issuedDate, due_date: dueDate,
        reservations: JSON.stringify(resRows.map((r) => ({
          reservation_number: r.reservation_number, hotel: r.hotel,
          check_in: r.check_in, check_out: r.check_out,
          reservation_total: parseFloat(r.reservation_total) || 0,
        }))),
        payments: JSON.stringify(payRows.map((p) => ({
          ref: p.ref, date: p.date, method: p.method, amount: parseFloat(p.amount) || 0,
          currency: p.currency, exchange: parseFloat(p.exchange) || 1, note: p.note,
          proof_keep: p.file ? "" : p.proof_keep,
        }))),
        linked_cl_ids: JSON.stringify(linkedClIds),
      };
      payRows.forEach((p, i) => { if (p.file) data[`payment_proof_${i}`] = p.file; });
      return data;
    });
    const url = edit ? `/invoice/${src.pk}/edit/` : "/invoice/new/";
    form.post(url, { forceFormData: true });
  };

  return (
    <div className="page">
      <style>{CSS}</style>
      <div className="page-header" style={{ marginBottom: 14 }}>
        <div>
          <div className="page-title">{edit ? `Edit Invoice — ${src?.invoice_number || ""}` : "Invoice Hotel"}</div>
          <div className="page-sub">Reservasi hotel + pembayaran dalam SAR</div>
        </div>
      </div>

      <form method="post" onSubmit={submit}>
        <div className="form-panel">
          {/* ── Info ── */}
          <div className="form-section">
            <div className="form-section-label">Info Invoice</div>
            <div className="inv-info-row" style={{ display: "grid", gridTemplateColumns: "110px 1fr 160px 140px 140px", gap: 12 }}>
              <div className="ff">
                <label>Company *</label>
                <select value={company} required onChange={(e) => setCompany(e.target.value)}>
                  <option value="konoz">Konoz</option>
                  <option value="ijabah">Ijabah</option>
                </select>
              </div>
              <div className="ff">
                <label>Customer *</label>
                <input type="text" required placeholder="Nama customer / agen travel" value={customerName} onChange={(e) => setCustomerName(e.target.value)} />
              </div>
              <div className="ff">
                <label>Invoice Number *</label>
                <input type="text" required placeholder="INV-001" value={invoiceNumber} style={{ fontFamily: "'JetBrains Mono',monospace", letterSpacing: ".3px" }} onChange={(e) => setInvoiceNumber(e.target.value)} />
                {errors.invoice_number && <div className="hint" style={{ marginTop: 6, color: "var(--red)" }}>{errors.invoice_number}</div>}
              </div>
              <div className="ff">
                <label>Issued Date *</label>
                <input type="date" required value={issuedDate} onChange={(e) => setIssuedDate(e.target.value)} />
              </div>
              <div className="ff">
                <label>Due Date *</label>
                <input type="date" required value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
              </div>
            </div>
          </div>

          {/* ── Reservations ── */}
          <div className="inv-sec-head">
            <div className="form-section-label">Reservations</div>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              {cl_data.length > 0 && (
                <button type="button" className="btn btn-ghost" style={{ height: 28, padding: "0 10px", fontSize: 12 }} onClick={openModal}>
                  <Icon name="invoice" size={11} /> Impor dari CL
                </button>
              )}
              <button type="button" className="btn btn-ghost" style={{ height: 28, padding: "0 10px", fontSize: 12 }} onClick={addRes}>+ Add</button>
            </div>
          </div>
          <div className="inv-sec-body">
            <div className="res-header" style={{ padding: "0 4px 7px" }}>
              <div>Res#</div><div>Hotel</div><div>Check-in</div><div>Check-out</div><div>Total SAR</div><div></div>
            </div>
            <div id="reservations">
              {reservations.map((r, i) => (
                <div className="item" key={i}>
                  <input type="text" placeholder="RES#" required inputMode="numeric" value={r.reservation_number} onChange={(e) => setRes(i, "reservation_number", e.target.value)} />
                  <input type="text" placeholder="Hotel Name" value={r.hotel} onChange={(e) => setRes(i, "hotel", e.target.value)} />
                  <input type="date" value={r.check_in} onChange={(e) => setRes(i, "check_in", e.target.value)} />
                  <input type="date" min={r.check_in || undefined} value={r.check_out} onChange={(e) => setRes(i, "check_out", e.target.value)} />
                  <input type="number" placeholder="Total SAR" step="0.01" required value={r.reservation_total} onChange={(e) => setRes(i, "reservation_total", e.target.value)} />
                  <button type="button" className="btn-remove" onClick={() => removeRes(i)} aria-label="Hapus"><Icon name="trash" size={12} /></button>
                </div>
              ))}
            </div>
          </div>

          {/* ── Payments ── */}
          <div className="inv-sec-head">
            <div className="form-section-label">Payments</div>
            <button type="button" className="btn btn-ghost" style={{ height: 28, padding: "0 10px", fontSize: 12 }} onClick={addPay}>+ Add</button>
          </div>
          <div className="inv-sec-body-scroll">
            <div className="pay-header" style={{ gridTemplateColumns: PAY_COLS }}>
              <div></div><div>Res#</div><div>Tanggal</div><div>Metode</div>
              <div>Amount</div><div>Cur</div><div>Rate</div><div>Note</div><div>Bukti</div><div></div>
            </div>
            <div id="payments">
              {payments.map((p, i) => (
                <div className="payment-item" key={i} style={{ gridTemplateColumns: PAY_COLS }}>
                  <div className="drag-handle" style={{ cursor: "default" }} />
                  <select value={p.ref} required onChange={(e) => setPay(i, { ref: e.target.value })}>
                    <option value="">Res#</option>
                    {resOptions.map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                  <input type="date" required value={p.date} onChange={(e) => setPay(i, { date: e.target.value })} />
                  <select value={p.method} required onChange={(e) => setPay(i, { method: e.target.value })}>
                    {METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                  <input type="number" step="0.01" placeholder="Amount" required value={p.amount} onChange={(e) => setPay(i, { amount: e.target.value })} />
                  <select value={p.currency} onChange={(e) => onCurrencyChange(i, e.target.value)}>
                    {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                  <input type="number" step="0.0001" placeholder="Rate" value={p.exchange} readOnly={p.currency === "SAR"} onChange={(e) => setPay(i, { exchange: e.target.value })} />
                  <textarea placeholder="Note" value={p.note} onChange={(e) => setPay(i, { note: e.target.value })} />
                  <div className="proof-cell">
                    {p.proof_url && !p.file && <a href={p.proof_url} target="_blank" rel="noreferrer" className="proof-link" title="Lihat bukti"><Icon name="proof" size={13} /></a>}
                    <label className="proof-btn" title="Upload bukti">
                      <Icon name="proof" size={13} />
                      <input type="file" accept="image/*,.pdf" style={{ position: "absolute", width: 1, height: 1, opacity: 0, overflow: "hidden" }} onChange={(e) => setPay(i, { file: e.target.files[0] || null })} />
                    </label>
                    <span className="proof-fname">{p.file ? p.file.name : ""}</span>
                  </div>
                  <button type="button" className="btn-remove" onClick={() => removePay(i)} aria-label="Hapus"><Icon name="trash" size={12} /></button>
                </div>
              ))}
            </div>
          </div>

          {/* ── Summary ── */}
          <div className="inv-summary">
            <div className="inv-summary-cell"><div className="lbl">Total Reservasi</div><div className="val">{fmt(totals.totalRes)} SAR</div></div>
            <div className="inv-summary-cell"><div className="lbl">Total Terbayar</div><div className="val green">{fmt(totals.totalPaidSar)} SAR</div></div>
            <div className="inv-summary-cell"><div className="lbl">Sisa</div><div className={"val " + remainingClass}>{fmt(totals.remaining)} SAR</div></div>
          </div>

          <div className="form-actions" style={{ borderTop: "1px solid var(--border)" }}>
            <a href={edit ? `/invoice/${src.pk}/` : "/invoice/"} className="btn btn-ghost">Batal</a>
            <button type="submit" id="submit-btn" className="btn btn-primary" disabled={form.processing}>
              <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
              {form.processing ? "Menyimpan…" : edit ? "Update & Simpan" : "Simpan & Buka"}
            </button>
          </div>
        </div>
      </form>

      {/* ── CL Import Modal ── */}
      {cl_data.length > 0 && (
        <div className={"cl-modal-overlay" + (modalOpen ? " open" : "")} onClick={(e) => { if (e.target === e.currentTarget) setModalOpen(false); }}>
          <div className="cl-modal">
            <div className="cl-modal-head">
              <h3>Impor dari Confirmation Letter</h3>
              <button type="button" className="btn btn-ghost" style={{ width: 28, height: 28, padding: 0, display: "inline-flex", alignItems: "center", justifyContent: "center" }} onClick={() => setModalOpen(false)}>
                <Icon name="close" size={14} />
              </button>
            </div>
            <div className="cl-modal-search">
              <input type="text" placeholder="Cari tamu, hotel, nomor CL…" autoComplete="off" value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
            <div className="cl-modal-body">
              <table>
                <thead><tr>
                  <th style={{ width: 32 }}></th><th>No CL</th><th>Tamu</th><th>Hotel</th>
                  <th>Check-in</th><th>Check-out</th><th style={{ textAlign: "right" }}>Total SAR</th>
                </tr></thead>
                <tbody>
                  {filteredCls.length === 0 ? (
                    <tr><td colSpan={7}><div className="cl-modal-empty">Tidak ada CL tersedia</div></td></tr>
                  ) : filteredCls.map((cl) => {
                    const isSel = !!selected[cl.id];
                    return (
                      <tr key={cl.id} className={"cl-modal-row" + (isSel ? " selected" : "")} onClick={() => toggleSel(cl)}>
                        <td style={{ textAlign: "center" }}><input type="checkbox" checked={isSel} readOnly style={{ width: "auto", margin: 0, accentColor: "var(--accent)", cursor: "pointer" }} /></td>
                        <td style={{ fontFamily: "'JetBrains Mono',monospace", fontWeight: 600 }}>{cl.ref}{cl.inv && <span style={{ fontSize: 10, color: "var(--accent)", marginLeft: 4 }}>● {cl.inv}</span>}</td>
                        <td>{cl.guest}</td>
                        <td style={{ color: "var(--text-2)" }}>{cl.hotel}</td>
                        <td style={{ color: "var(--text-2)" }}>{fmtDate(cl.check_in)}</td>
                        <td style={{ color: "var(--text-2)" }}>{fmtDate(cl.check_out)}</td>
                        <td style={{ textAlign: "right", fontFamily: "'JetBrains Mono',monospace" }}>{cl.total ? cl.total.toLocaleString() : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="cl-modal-foot">
              <span className="cl-modal-sel-info"><strong>{Object.keys(selected).length}</strong> CL dipilih</span>
              <div style={{ display: "flex", gap: 8 }}>
                <button type="button" className="btn btn-ghost" style={{ height: 32, padding: "0 14px", fontSize: 13 }} onClick={() => setModalOpen(false)}>Batal</button>
                <button type="button" className="btn btn-primary" style={{ height: 32, padding: "0 16px", fontSize: 13 }} disabled={!Object.keys(selected).length} onClick={doImport}>Impor →</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const CSS = `
.inv-sec-head { display:flex; align-items:center; justify-content:space-between; padding:11px 20px; border-top:1px solid var(--border); border-bottom:1px solid var(--border); background:var(--bg-2); }
.inv-sec-head .form-section-label { margin-bottom:0; }
.inv-sec-body { padding:14px 20px; }
.inv-sec-body-scroll { padding:14px 20px; overflow-x:auto; }
.inv-sec-body-scroll > .pay-header, .inv-sec-body-scroll > #payments { min-width:820px; }
.inv-summary { display:grid; grid-template-columns:1fr 1fr 1fr; border-top:1px solid var(--border); background:var(--bg-2); }
.inv-summary-cell { padding:14px 22px; border-right:1px solid var(--border); }
.inv-summary-cell:last-child { border-right:none; }
.inv-summary-cell .lbl { font-family:'JetBrains Mono',monospace; font-size:9.5px; font-weight:600; text-transform:uppercase; letter-spacing:.7px; color:var(--text-3); margin-bottom:6px; }
.inv-summary-cell .val { font-family:'JetBrains Mono',monospace; font-size:18px; font-weight:700; color:var(--text); font-variant-numeric:tabular-nums; }
.inv-summary-cell .val.green { color:var(--green); }
.inv-summary-cell .val.yellow { color:var(--yellow); }
.inv-summary-cell .val.red { color:var(--red); }
@media(max-width:640px) { .inv-summary { grid-template-columns:1fr; } .inv-summary-cell { border-right:none; border-bottom:1px solid var(--border); } .inv-summary-cell:last-child { border-bottom:none; } }
@media(max-width:900px) { .inv-info-row { grid-template-columns: 110px 1fr 160px !important; } }

.cl-modal-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,.6); z-index:var(--z-overlay); align-items:center; justify-content:center; }
.cl-modal-overlay.open { display:flex; }
.cl-modal { background:var(--surface); border:1px solid var(--border); border-radius:14px; width:700px; max-width:96vw; max-height:82vh; display:flex; flex-direction:column; box-shadow:0 24px 64px rgba(0,0,0,.6); }
.cl-modal-head { padding:16px 20px; border-bottom:1px solid var(--border); display:flex; align-items:center; justify-content:space-between; }
.cl-modal-head h3 { font-size:14px; font-weight:700; color:var(--text); margin:0; display:flex; align-items:center; gap:7px; }
.cl-modal-head h3::before { content:''; width:4px; height:4px; border-radius:50%; background:var(--accent); display:inline-block; flex-shrink:0; }
.cl-modal-search { padding:10px 16px; border-bottom:1px solid var(--border); }
.cl-modal-search input { width:100%; height:32px; font-size:13px; background:var(--bg-2); border:1px solid var(--border); border-radius:var(--r); color:var(--text); padding:0 10px; transition:border-color .12s; }
.cl-modal-search input:focus { outline:none; border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-muted); }
.cl-modal-body { overflow-y:auto; flex:1; }
.cl-modal-body table { width:100%; border-collapse:collapse; font-size:12px; }
.cl-modal-body th { padding:7px 10px; font-size:10px; font-weight:600; color:var(--text-3); font-family:'JetBrains Mono',monospace; text-transform:uppercase; letter-spacing:.5px; background:var(--surface-2); border-bottom:1px solid var(--border); position:sticky; top:0; }
.cl-modal-body td { padding:8px 10px; border-bottom:1px solid rgba(255,255,255,.035); color:var(--text); }
.cl-modal-row { cursor:pointer; transition:background .08s; }
.cl-modal-row:hover { background:var(--surface-2); }
.cl-modal-row.selected { background:var(--accent-muted); }
.cl-modal-empty { padding:40px; text-align:center; color:var(--text-3); font-size:13px; }
.cl-modal-foot { padding:12px 16px; border-top:1px solid var(--border); display:flex; align-items:center; justify-content:space-between; gap:10px; }
.cl-modal-sel-info { font-size:13px; color:var(--text-2); }
.cl-modal-sel-info strong { color:var(--text); }
`;
