import { useMemo, useState } from "react";
import { useForm } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";

const PAY_COLS = "90px 120px 1fr 110px 80px 90px 1fr 80px 28px";
const CURRENCIES = ["SAR", "USD", "IDR"];
const fmt = (n) => Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 0 });

const blankService = () => ({ name: "", qty: 1, price: "" });
const blankPayment = (cur) => ({
  ref: "", date: "", method: "", amount: "", currency: cur || "SAR",
  exchange: 1, note: "", proof_keep: "", proof_url: null, file: null,
});

function seedFrom(src, fallbackCurrency) {
  if (!src) {
    return { items: [blankService()], payments: [blankPayment(fallbackCurrency)] };
  }
  const items = (src.service_items || []).map((it) => ({
    name: it.name || "", qty: it.qty ?? 1, price: it.price ?? "",
  }));
  const payments = (src.payments || []).map((p) => ({
    ref: String(p.ref ?? ""), date: p.date || "", method: p.method || "",
    amount: p.amount ?? "", currency: p.currency || fallbackCurrency || "SAR",
    exchange: p.exchange ?? 1, note: p.note || "",
    proof_keep: p.proof_keep || "", proof_url: p.proof_url || null, file: null,
  }));
  return {
    items: items.length ? items : [blankService()],
    payments,
  };
}

export default function Form({ invoice, edit, suggested_number, default_company, initial, errors = {} }) {
  const src = initial || invoice;
  const [company, setCompany] = useState(src?.company || default_company || "ijabah");
  const [customerName, setCustomerName] = useState(src?.customer_name || "");
  const [invoiceNumber, setInvoiceNumber] = useState(src?.invoice_number || (edit ? "" : suggested_number) || "");
  const [currency, setCurrency] = useState(src?.invoice_currency || "USD");
  const [issuedDate, setIssuedDate] = useState(src?.issued_date || "");
  const [dueDate, setDueDate] = useState(src?.due_date || "");

  const seeded = useMemo(() => seedFrom(src, src?.invoice_currency || "USD"), []);
  const [items, setItems] = useState(seeded.items);
  const [payments, setPayments] = useState(seeded.payments);

  const form = useForm({});

  // ── Services ──
  const setItem = (i, key, val) => setItems((rows) => rows.map((r, idx) => (idx === i ? { ...r, [key]: val } : r)));
  const addItem = () => setItems((rows) => [...rows, blankService()]);
  const removeItem = (i) => setItems((rows) => rows.filter((_, idx) => idx !== i));

  // ── Payments ──
  const setPay = (i, patch) => setPayments((rows) => rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  const addPay = () => setPayments((rows) => [...rows, blankPayment(currency)]);
  const removePay = (i) => setPayments((rows) => rows.filter((_, idx) => idx !== i));
  const onCurrencyChange = (i, cur) => {
    const patch = { currency: cur };
    if (cur === currency) patch.exchange = 1;
    else if (String(payments[i].exchange) === "1") patch.exchange = "";
    setPay(i, patch);
  };

  // ── Totals ──
  const totals = useMemo(() => {
    const totalServices = Math.floor(
      items.reduce((sum, it) => sum + (parseFloat(it.qty) || 0) * (parseFloat(it.price) || 0), 0)
    );
    let totalPayments = 0;
    for (const p of payments) {
      const amount = parseFloat(p.amount) || 0;
      const rate = parseFloat(p.exchange) || 1;
      let converted = amount;
      if (p.currency !== currency) {
        converted = p.currency === "IDR" ? (rate ? Math.floor(amount / rate) : 0) : amount / (rate || 1);
      }
      totalPayments += converted;
    }
    totalPayments = Math.floor(totalPayments);
    return { totalServices, totalPayments, remaining: Math.floor(totalServices - totalPayments) };
  }, [items, payments, currency]);

  const submit = (e) => {
    e.preventDefault();
    const serviceItems = items
      .filter((it) => (it.name || "").trim())
      .map((it) => ({ name: it.name.trim(), qty: parseFloat(it.qty) || 1, price: parseFloat(it.price) || 0 }));
    const payRows = payments.filter((p) => (parseFloat(p.amount) || 0) > 0);

    form.transform(() => {
      const data = {
        company, customer_name: customerName, invoice_number: invoiceNumber,
        invoice_currency: currency, issued_date: issuedDate, due_date: dueDate,
        service_items: JSON.stringify(serviceItems),
        payments: JSON.stringify(payRows.map((p) => ({
          ref: p.ref, date: p.date, method: p.method, amount: parseFloat(p.amount) || 0,
          currency: p.currency, exchange: parseFloat(p.exchange) || 1, note: p.note,
          proof_keep: p.file ? "" : p.proof_keep,
        }))),
      };
      payRows.forEach((p, i) => { if (p.file) data[`payment_proof_${i}`] = p.file; });
      return data;
    });
    const url = edit ? `/services/${src.pk}/edit/` : "/services/new/";
    form.post(url, { forceFormData: true });
  };

  const svcOptions = items.filter((it) => (it.name || "").trim()).map((_, i) => i + 1);

  return (
    <div className="page">
      <div className="page-header" style={{ marginBottom: 14 }}>
        <div>
          <div className="page-title">{edit ? "Edit Invoice Services" : "Invoice Services / Visa"}</div>
          <div className="page-sub">Layanan visa, umroh, dan services lainnya</div>
        </div>
      </div>

      <form method="post" onSubmit={submit}>
        {/* ── Info Invoice ── */}
        <div className="form-panel" style={{ marginBottom: 12 }}>
          <div className="form-section">
            <div className="form-section-label">Invoice Info</div>
            <div className="fg-3" style={{ marginBottom: 12 }}>
              <div className="ff">
                <label>Company *</label>
                <select value={company} onChange={(e) => setCompany(e.target.value)}>
                  <option value="ijabah">Ijabah</option>
                  <option value="konoz">Konoz</option>
                </select>
              </div>
              <div className="ff fg-span2">
                <label>Customer *</label>
                <input type="text" required placeholder="Customer name" value={customerName}
                  onChange={(e) => setCustomerName(e.target.value)} />
              </div>
            </div>
            <div className="fg-4">
              <div className="ff fg-span2">
                <label>Invoice Number *</label>
                <input type="text" required placeholder={suggested_number} value={invoiceNumber}
                  onChange={(e) => setInvoiceNumber(e.target.value)} />
                {errors.invoice_number && <div className="hint" style={{ marginTop: 6, color: "var(--red)" }}>{errors.invoice_number}</div>}
              </div>
              <div className="ff">
                <label>Currency *</label>
                <select value={currency} required onChange={(e) => setCurrency(e.target.value)}>
                  {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="ff">
                <label>Issued Date *</label>
                <input type="date" required value={issuedDate} onChange={(e) => setIssuedDate(e.target.value)} />
              </div>
            </div>
            <div style={{ marginTop: 12, maxWidth: "calc(25% - 6px)" }}>
              <div className="ff">
                <label>Due Date *</label>
                <input type="date" required value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
              </div>
            </div>
          </div>
        </div>

        {/* ── Services ── */}
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="card-header">
            <span className="card-title">Services</span>
            <button type="button" className="btn btn-ghost" style={{ height: 26, padding: "0 10px", fontSize: 12 }} onClick={addItem}>+ Add</button>
          </div>
          <div className="card-body" style={{ paddingBottom: 8 }}>
            <div className="svc-header"><div>#</div><div>Service</div><div>Qty</div><div>Amount</div><div></div></div>
            <div id="services-list">
              {items.map((it, i) => (
                <div className="svc-row" key={i}>
                  <div className="svc-num">{i + 1}</div>
                  <input type="text" className="service-input" placeholder="Service Name" required
                    value={it.name} onChange={(e) => setItem(i, "name", e.target.value)} />
                  <input type="number" className="qty-input" min="1" required
                    value={it.qty} onChange={(e) => setItem(i, "qty", e.target.value)} />
                  <input type="number" className="amount-input" min="0" step="0.01" required
                    value={it.price} onChange={(e) => setItem(i, "price", e.target.value)} />
                  <button type="button" className="btn-remove" onClick={() => removeItem(i)} aria-label="Remove">
                    <Icon name="trash" size={12} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── Payments ── */}
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="card-header">
            <span className="card-title">Payments</span>
            <button type="button" className="btn btn-ghost" style={{ height: 26, padding: "0 10px", fontSize: 12 }} onClick={addPay}>+ Add</button>
          </div>
          <div className="card-body" style={{ paddingBottom: 8 }}>
            <div className="pay-header" style={{ gridTemplateColumns: PAY_COLS }}>
              <div>SVC#</div><div>DATE</div><div>METHOD</div><div>AMOUNT</div>
              <div>CUR</div><div>RATE</div><div>NOTE</div><div>PROOF</div><div></div>
            </div>
            <div id="payments">
              {payments.map((p, i) => (
                <div className="payment-item" key={i} style={{ gridTemplateColumns: PAY_COLS }}>
                  <select value={p.ref} required onChange={(e) => setPay(i, { ref: e.target.value })}>
                    <option value="">Svc#</option>
                    {svcOptions.map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                  <input type="date" required value={p.date} onChange={(e) => setPay(i, { date: e.target.value })} />
                  <input type="text" placeholder="Method" required value={p.method} onChange={(e) => setPay(i, { method: e.target.value })} />
                  <input type="number" step="0.01" placeholder="Amount" required value={p.amount} onChange={(e) => setPay(i, { amount: e.target.value })} />
                  <select value={p.currency} onChange={(e) => onCurrencyChange(i, e.target.value)}>
                    {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                  <input type="number" step="0.0001" value={p.exchange} readOnly={p.currency === currency}
                    onChange={(e) => setPay(i, { exchange: e.target.value })} />
                  <textarea placeholder="Note" value={p.note} onChange={(e) => setPay(i, { note: e.target.value })} />
                  <div className="proof-cell">
                    {p.proof_url && !p.file && (
                      <a href={p.proof_url} target="_blank" rel="noreferrer" className="proof-link" title="View proof"><Icon name="proof" size={13} /></a>
                    )}
                    <label className="proof-btn" title="Upload proof">
                      <Icon name="proof" size={13} />
                      <input type="file" accept="image/*,.pdf" style={{ display: "none" }}
                        onChange={(e) => setPay(i, { file: e.target.files[0] || null })} />
                    </label>
                    <span className="proof-fname">{p.file ? p.file.name : ""}</span>
                  </div>
                  <button type="button" className="btn-remove" onClick={() => removePay(i)} aria-label="Remove">
                    <Icon name="trash" size={12} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── Summary ── */}
        <div className="form-summary">
          <div className="form-summary-cell">
            <div className="lbl">Total Services</div>
            <div className="val">{fmt(totals.totalServices)} {currency}</div>
          </div>
          <div className="form-summary-cell">
            <div className="lbl">Total Payments</div>
            <div className="val green">{fmt(totals.totalPayments)} {currency}</div>
          </div>
          <div className="form-summary-cell">
            <div className="lbl">Remaining</div>
            <div className={"val" + (totals.remaining === 0 ? " green" : totals.remaining < 0 ? " red" : "")}>
              {fmt(totals.remaining)} {currency}
            </div>
          </div>
        </div>

        <div className="form-actions" style={{ padding: "14px 0 4px" }}>
          <a href={edit ? `/services/${src.pk}/` : "/services/"} className="btn btn-ghost">Cancel</a>
          <button type="submit" className="btn btn-primary" disabled={form.processing}>
            {form.processing ? "Saving…" : edit ? "Update & Save" : "Save & Open"}
          </button>
        </div>
      </form>
    </div>
  );
}
