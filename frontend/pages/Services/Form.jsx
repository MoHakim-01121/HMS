import { useMemo, useRef, useState } from "react";
import { useForm } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";

const DragIcon = () => (
  <svg width="10" height="16" viewBox="0 0 10 16" fill="currentColor" style={{ opacity: 0.45, display: "block" }}>
    <circle cx="3" cy="3" r="1.5"/><circle cx="7" cy="3" r="1.5"/>
    <circle cx="3" cy="8" r="1.5"/><circle cx="7" cy="8" r="1.5"/>
    <circle cx="3" cy="13" r="1.5"/><circle cx="7" cy="13" r="1.5"/>
  </svg>
);

/* A control inside a dynamic row card. FormField is what supplies the design
   system here — the styling in tailwind.css keys off its data-slot, so every
   control below gets the same 40px height, 2px stroke, --radius-control and
   14px text as the Invoice Info fields at the top of the form.

   The visible label is dropped and the field name moves into the placeholder
   plus aria-label. These rows repeat, and stacking a label over every field
   roughly doubles a card's height for names the placeholder already carries —
   the same trade the desktop table makes when it labels a column once in its
   header rather than once per cell. */
const CardField = ({ name, cell, children }) => (
  <FormField name={name} className={cell}>{children}</FormField>
);

const RemoveButton = ({ onClick, label }) => (
  <Button type="button" variant="ghost" size="icon-sm" className="f-del" onClick={onClick} aria-label={label}>
    <Icon name="trash" size={13} />
  </Button>
);

const CURRENCIES = ["SAR", "USD", "IDR"];
const fmt = (n) => Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 0 });

const blankService = () => ({ name: "", qty: 1, price: "" });
let _paySeq = 0;
const blankPayment = (cur) => ({
  _key: ++_paySeq, ref: "", date: "", method: "", amount: "", currency: cur || "SAR",
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
    _key: ++_paySeq,
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

export default function Form({ invoice, edit, suggested_number, initial, errors = {} }) {
  const src = initial || invoice;
  const { t } = useI18n();
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
  const lineTotal = (it) => (parseFloat(it.qty) || 0) * (parseFloat(it.price) || 0);

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

  // ── Payment drag-to-reorder ──
  const dragIndex = useRef(null);
  const onPayDragStart = (e, i) => { dragIndex.current = i; e.dataTransfer.effectAllowed = "move"; };
  // Only intercept dragover/drop when a payment drag is actually in progress.
  // Without this guard, dragging text between inputs or dropping files would
  // also trigger these handlers and could cause unexpected reorders.
  const onPayDragOver = (e) => { if (dragIndex.current === null) return; e.preventDefault(); e.dataTransfer.dropEffect = "move"; };
  const onPayDrop = (e, i) => {
    if (dragIndex.current === null) return;
    e.preventDefault();
    const from = dragIndex.current;
    dragIndex.current = null;
    if (from === i) return;
    setPayments((rows) => { const next = [...rows]; next.splice(i, 0, next.splice(from, 1)[0]); return next; });
  };
  const onPayDragEnd = () => { dragIndex.current = null; };

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

  const remainingClass = totals.remaining <= 0 ? "green" : totals.remaining < totals.totalServices ? "yellow" : "red";

  const submit = (e) => {
    e.preventDefault();
    const serviceItems = items
      .filter((it) => (it.name || "").trim())
      .map((it) => ({ name: it.name.trim(), qty: parseFloat(it.qty) || 1, price: parseFloat(it.price) || 0 }));
    const payRows = payments.filter((p) => (parseFloat(p.amount) || 0) > 0);

    form.transform(() => {
      const data = {
        customer_name: customerName, invoice_number: invoiceNumber,
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

  // Service numbers follow the server's: only named rows are stored, numbered
  // 1..n in order, so an unnamed row must not consume a number here either.
  const svcOptions = items.filter((it) => (it.name || "").trim()).map((_, i) => i + 1);

  return (
    <div className="page svc-form shadcn-root">
      <style>{CSS}</style>
      <PageBack href="/services/" />
      <FormHeader
        kicker={t("Invoice Services")}
        title={edit ? t("Edit Invoice — {number}", { number: src?.invoice_number || "" }) : t("Invoice Services / Visa")}
        sub={t("Visa, umrah, and other services")}
      />

      <form method="post" onSubmit={submit}>
        <FormPanel>
          {/* ── Info ── */}
          <FormSection label={t("Invoice Info")}>
            {/* No Company picker: the server files every services invoice under
                the session's active company, and list/detail/edit all filter by
                it too — so choosing the other one here only ever produced a
                record that vanished from the very list you created it from.
                Switch companies with the topbar switcher instead. */}
            <div className="svc-info-row" style={{ display: "grid", gridTemplateColumns: "1fr 160px 100px 140px 140px", gap: 12 }}>
              <FormField label={t("Customer")} name="customer_name" required
                value={customerName} onChange={setCustomerName} placeholder={t("Customer name")} />
              <FormField label={t("Invoice Number")} name="invoice_number" required
                value={invoiceNumber} onChange={setInvoiceNumber}
                placeholder={suggested_number} error={errors.invoice_number} />
              <FormField label={t("Currency")} name="invoice_currency" required>
                <select id="invoice_currency" value={currency} onChange={(e) => setCurrency(e.target.value)}>
                  {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </FormField>
              <FormField label={t("Issued Date")} name="issued_date" type="date" required value={issuedDate} onChange={setIssuedDate} />
              <FormField label={t("Due Date")} name="due_date" type="date" required value={dueDate} onChange={setDueDate} />
            </div>
          </FormSection>

          {/* ── Services ── */}
          <FormSection label={t("Services")}>
            <div className="svc-items-desktop">
              <div className="svc-tbl-wrap">
                <div className="svc-tbl-scroll">
                  <table className="svc-tbl svc-tbl-items" id="services-list">
                    <colgroup>
                      <col style={{ width: 44 }} />
                      <col />
                      <col style={{ width: 92 }} />
                      <col style={{ width: 140 }} />
                      <col style={{ width: 148 }} />
                      <col style={{ width: 48 }} />
                    </colgroup>
                    <thead>
                      <tr>
                        <th className="c">#</th>
                        <th>{t("Service")}</th>
                        <th className="r">{t("Qty")}</th>
                        <th className="r">{t("Price")}</th>
                        <th className="r">{t("Amount {currency}", { currency })}</th>
                        <th aria-label={t("Actions")} />
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((it, i) => (
                        <tr key={i}>
                          <td className="c-idx">{i + 1}</td>
                          <td><input className="c-in c-strong" type="text" placeholder={t("Service name")} required value={it.name} onChange={(e) => setItem(i, "name", e.target.value)} /></td>
                          <td><input className="c-in c-num" type="number" min="1" required value={it.qty} onChange={(e) => setItem(i, "qty", e.target.value)} /></td>
                          <td><input className="c-in c-num" type="number" min="0" step="0.01" placeholder="0.00" required value={it.price} onChange={(e) => setItem(i, "price", e.target.value)} /></td>
                          {/* Amount is qty × price — derived, so it is read as a
                              cell rather than offered as a fourth input. */}
                          <td className="c-calc">{fmt(lineTotal(it))}</td>
                          <td className="c-act">
                            <button type="button" className="svc-row-del" onClick={() => removeItem(i)} aria-label={t("Remove service")}><Icon name="trash" size={13} /></button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <button type="button" className="svc-tbl-add" onClick={addItem}>{t("+ Add service")}</button>
              </div>
            </div>
            <div className="svc-items-cards">
              {items.map((it, i) => (
                <div className="svc-card" key={i}>
                  <CardField name={`svc-${i}-name`} cell="f-name">
                    <input id={`svc-${i}-name`} type="text" aria-label={t("Service name")}
                      placeholder={t("Service name")} value={it.name} onChange={(e) => setItem(i, "name", e.target.value)} />
                  </CardField>
                  <CardField name={`svc-${i}-qty`} cell="f-qty">
                    <input id={`svc-${i}-qty`} type="number" min="1" className="svc-num" aria-label={t("Quantity")}
                      placeholder={t("Qty")} value={it.qty} onChange={(e) => setItem(i, "qty", e.target.value)} />
                  </CardField>
                  <CardField name={`svc-${i}-price`} cell="f-price">
                    <input id={`svc-${i}-price`} type="number" min="0" step="0.01" className="svc-num" aria-label={t("Price")}
                      placeholder={t("Price")} value={it.price} onChange={(e) => setItem(i, "price", e.target.value)} />
                  </CardField>
                  <div className="svc-calc f-amount" aria-label={t("Line total {currency}", { currency })}>{fmt(lineTotal(it))}</div>
                  <RemoveButton label={t("Remove service")} onClick={() => removeItem(i)} />
                </div>
              ))}
              <button type="button" className="btn-add-row svc-add-mobile" onClick={addItem}>{t("+ Add service")}</button>
              <div className="section-foot"><span className="lbl">{t("Total")}</span><span className="val">{fmt(totals.totalServices)} {currency}</span></div>
            </div>
          </FormSection>

          {/* ── Payments ── */}
          <FormSection label={t("Payments")}>
            <div className="svc-pay-desktop">
              <div className="svc-tbl-wrap">
                <div className="svc-tbl-scroll">
                  <table className="svc-tbl svc-tbl-pay" id="payments">
                    <colgroup>
                      <col style={{ width: 30 }} />
                      <col style={{ width: 84 }} />
                      <col style={{ width: 132 }} />
                      <col style={{ width: 130 }} />
                      <col style={{ width: 112 }} />
                      <col style={{ width: 76 }} />
                      <col style={{ width: 86 }} />
                      <col />
                      <col style={{ width: 84 }} />
                      <col style={{ width: 44 }} />
                    </colgroup>
                    <thead>
                      <tr>
                        <th aria-label={t("Reorder")} />
                        <th>Svc#</th>
                        <th>{t("Date")}</th>
                        <th>{t("Method")}</th>
                        <th className="r">{t("Amount")}</th>
                        <th>Cur</th>
                        <th className="r">{t("Rate")}</th>
                        <th>{t("Note")}</th>
                        <th>{t("Proof")}</th>
                        <th aria-label={t("Actions")} />
                      </tr>
                    </thead>
                    <tbody>
                      {payments.length === 0 ? (
                        <tr className="svc-tbl-empty">
                          <td colSpan={10}>{t("No payments recorded yet")}</td>
                        </tr>
                      ) : payments.map((p, i) => (
                        <tr key={p._key} onDragOver={onPayDragOver} onDrop={(e) => onPayDrop(e, i)}>
                          <td className="c-drag">
                            <span className="svc-drag" draggable onDragStart={(e) => onPayDragStart(e, i)} onDragEnd={onPayDragEnd} aria-label={t("Drag to reorder")}><DragIcon /></span>
                          </td>
                          <td>
                            <span className="c-sel">
                              <select className="c-in" value={p.ref} required onChange={(e) => setPay(i, { ref: e.target.value })}>
                                <option value="">—</option>
                                {svcOptions.map((n) => <option key={n} value={n}>{n}</option>)}
                              </select>
                            </span>
                          </td>
                          <td><input className="c-in" type="date" required value={p.date} onChange={(e) => setPay(i, { date: e.target.value })} /></td>
                          {/* Method is free text, not the Invoice form's fixed
                              list: services payments already on file carry
                              arbitrary methods, and a select would silently
                              blank them on edit. */}
                          <td><input className="c-in" type="text" placeholder={t("Method")} required value={p.method} onChange={(e) => setPay(i, { method: e.target.value })} /></td>
                          <td><input className="c-in c-num c-strong" type="number" step="0.01" placeholder="0.00" required value={p.amount} onChange={(e) => setPay(i, { amount: e.target.value })} /></td>
                          <td>
                            <span className="c-sel">
                              <select className="c-in" value={p.currency} onChange={(e) => onCurrencyChange(i, e.target.value)}>
                                {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                              </select>
                            </span>
                          </td>
                          <td><input className="c-in c-num" type="number" step="0.0001" placeholder="1" value={p.exchange} readOnly={p.currency === currency} onChange={(e) => setPay(i, { exchange: e.target.value })} /></td>
                          <td><input className="c-in" type="text" placeholder="—" value={p.note} onChange={(e) => setPay(i, { note: e.target.value })} /></td>
                          <td className="c-proof">
                            <div className="svc-proof">
                              {p.proof_url && !p.file && <a href={p.proof_url} target="_blank" rel="noreferrer" className="svc-proof-link" title={t("View proof")}><Icon name="proof" size={13} /></a>}
                              <label className="svc-proof-btn" title={t("Upload proof")}>
                                <Icon name="proof" size={13} />
                                <input type="file" accept="image/*,.pdf" style={{ position: "absolute", width: 1, height: 1, opacity: 0, overflow: "hidden" }} onChange={(e) => setPay(i, { file: e.target.files[0] || null })} />
                              </label>
                              {p.file && <span className="svc-proof-name" title={p.file.name}>{p.file.name}</span>}
                            </div>
                          </td>
                          <td className="c-act">
                            <button type="button" className="svc-row-del" onClick={() => removePay(i)} aria-label={t("Remove payment")}><Icon name="trash" size={13} /></button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <button type="button" className="svc-tbl-add" onClick={addPay}>{t("+ Add payment")}</button>
              </div>
            </div>
            <div className="svc-pay-cards">
              <div className="tl-list">
                {payments.map((p, i) => (
                  <div className="tl-item" key={p._key}>
                    <span className="tl-dot" />
                    {/* The rate is only meaningful when the payment is in some
                        other currency than the invoice — which is a runtime
                        comparison, not a fixed value, so it is flagged here for
                        the phone layout rather than matched on in CSS. */}
                    <div className="svc-card" data-rate-locked={p.currency === currency ? "true" : undefined}>
                      <CardField name={`pay-${i}-date`} cell="f-date">
                        <input id={`pay-${i}-date`} type="date" aria-label={t("Payment date")}
                          value={p.date} onChange={(e) => setPay(i, { date: e.target.value })} />
                      </CardField>
                      <CardField name={`pay-${i}-amount`} cell="f-pay-amount">
                        <input id={`pay-${i}-amount`} type="number" step="0.01" className="svc-num" aria-label={t("Amount")}
                          placeholder={t("Amount")} value={p.amount} onChange={(e) => setPay(i, { amount: e.target.value })} />
                      </CardField>
                      <CardField name={`pay-${i}-currency`} cell="f-cur">
                        <select id={`pay-${i}-currency`} aria-label={t("Currency")}
                          value={p.currency} onChange={(e) => onCurrencyChange(i, e.target.value)}>
                          {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                        </select>
                      </CardField>
                      <CardField name={`pay-${i}-method`} cell="f-method">
                        <input id={`pay-${i}-method`} type="text" aria-label={t("Payment method")}
                          placeholder={t("Method")} value={p.method} onChange={(e) => setPay(i, { method: e.target.value })} />
                      </CardField>
                      <CardField name={`pay-${i}-ref`} cell="f-ref">
                        <select id={`pay-${i}-ref`} aria-label={t("Service number")}
                          value={p.ref} onChange={(e) => setPay(i, { ref: e.target.value })}>
                          <option value="">Svc#</option>
                          {svcOptions.map((n) => <option key={n} value={n}>{n}</option>)}
                        </select>
                      </CardField>
                      {/* Rate keeps its slot at the invoice currency instead of
                          being dropped — the desktop table does the same. A
                          field that comes and goes reflows every cell after it,
                          which is a worse trade than one dimmed 1.0000 that
                          can't be typed in. */}
                      <CardField name={`pay-${i}-rate`} cell="f-rate">
                        <input id={`pay-${i}-rate`} type="number" step="0.0001" className="svc-num" aria-label={t("Exchange rate")}
                          placeholder={t("Rate")} readOnly={p.currency === currency}
                          value={p.exchange} onChange={(e) => setPay(i, { exchange: e.target.value })} />
                      </CardField>
                      <CardField name={`pay-${i}-note`} cell="f-note">
                        <input id={`pay-${i}-note`} type="text" aria-label={t("Note")}
                          placeholder={t("Note")} value={p.note} onChange={(e) => setPay(i, { note: e.target.value })} />
                      </CardField>
                      <RemoveButton label={t("Remove payment")} onClick={() => removePay(i)} />
                      <label className="svc-proof-box f-proof" data-has-file={p.file ? "true" : undefined}
                        title={p.file ? p.file.name : p.proof_url ? t("Replace proof") : t("Attach proof")}>
                        <Icon name="proof" size={14} />
                        <span className="sr-only">{p.file ? p.file.name : t("Attach proof")}</span>
                        <input type="file" accept="image/*,.pdf" aria-label={t("Attach proof")} style={{ position: "absolute", width: 1, height: 1, opacity: 0, overflow: "hidden" }} onChange={(e) => setPay(i, { file: e.target.files[0] || null })} />
                      </label>
                      {p.proof_url && !p.file && (
                        <a href={p.proof_url} target="_blank" rel="noreferrer" className="svc-proof-box f-view" aria-label={t("View current proof")} title={t("View current proof")}>
                          <Icon name="proof" size={14} />
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              <button type="button" className="btn-add-row svc-add-mobile" onClick={addPay}>{t("+ Add payment")}</button>
              <div className="section-foot"><span className="lbl">{t("Remaining")}</span><span className={"val " + remainingClass}>{fmt(totals.remaining)} {currency}</span></div>
            </div>
          </FormSection>

          {/* ── Summary ── */}
          <div className="svc-summary">
            <div className="svc-summary-cell"><div className="lbl">{t("Total Services")}</div><div className="val">{fmt(totals.totalServices)} {currency}</div></div>
            <div className="svc-summary-cell"><div className="lbl">{t("Total Payments")}</div><div className="val green">{fmt(totals.totalPayments)} {currency}</div></div>
            <div className="svc-summary-cell"><div className="lbl">{t("Remaining")}</div><div className={"val " + remainingClass}>{fmt(totals.remaining)} {currency}</div></div>
          </div>

          <div className="svc-desktop-actions">
            <FormActions
              cancelHref={edit ? `/services/${src.pk}/` : "/services/"}
              submitLabel={form.processing ? t("Saving…") : edit ? t("Update & Save") : t("Save & Open")}
              processing={form.processing}
            />
          </div>

          <div className="svc-mobile-save-wrap">
            <button type="submit" className="dv-cta" disabled={form.processing}>
              {form.processing ? t("Saving…") : edit ? t("Update & Save") : t("Save & Open")}
            </button>
          </div>
        </FormPanel>
      </form>
    </div>
  );
}

const CSS = `
.svc-summary { display:grid; grid-template-columns:1fr 1fr 1fr; border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; background:var(--muted); }
.svc-summary-cell { padding:14px 22px; border-right:1px solid var(--border); }
.svc-summary-cell:last-child { border-right:none; }
.svc-summary-cell .lbl { font-size:11px; font-weight:600; color:var(--muted-foreground); margin-bottom:6px; }
.svc-summary-cell .val { font-family:var(--font-mono); font-size:18px; font-weight:700; color:var(--foreground); font-variant-numeric:tabular-nums; }
.svc-summary-cell .val.green { color:var(--green); }
.svc-summary-cell .val.yellow { color:var(--yellow); }
.svc-summary-cell .val.red { color:var(--red); }
@media(max-width:640px) { .svc-summary { grid-template-columns:1fr; } .svc-summary-cell { border-right:none; border-bottom:1px solid var(--border); } .svc-summary-cell:last-child { border-bottom:none; } }
@media(max-width:900px) { .svc-info-row { grid-template-columns: 1fr 1fr 100px !important; } }

/* ── Editable data tables (Services / Payments) ───────────────────────────
   Same construction as the Invoice Hotel form, for the same reasons: the old
   .svc-row / .payment-item grids in hw/static/hw/css/invoice_form.css were
   still painted from the retired token set and wrapped a shadcn Input in its
   own bordered box per cell — two borders and two radii per field, on two
   different design systems. These are real <table>s on the current tokens
   instead: the cell grid supplies the structure, and the controls inside are
   chromeless so a row reads as one line of data rather than a rack of inputs.
   Scoped under .svc-form so the legacy file's rules can't reach them. */
.svc-form .svc-tbl-wrap {
  border: 1px solid var(--border);
  border-radius: var(--radius-control, 16px);
  background: var(--card);
  overflow: hidden;
}
.svc-form .svc-tbl-scroll { overflow-x: auto; }
.svc-form .svc-tbl { width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 0; }
.svc-form .svc-tbl-items { min-width: 640px; }
.svc-form .svc-tbl-pay { min-width: 900px; }

.svc-form .svc-tbl thead th {
  padding: 0 10px; height: 38px;
  font-size: 12px; font-weight: 500; line-height: 38px;
  color: var(--muted-foreground); text-align: left; white-space: nowrap;
  background: var(--muted); border-bottom: 1px solid var(--border);
  text-transform: none; letter-spacing: normal;
}
.svc-form .svc-tbl thead th.r { text-align: right; }
.svc-form .svc-tbl thead th.c { text-align: center; }
.svc-form .svc-tbl thead th + th { border-left: 1px solid var(--border); }

/* design.css staggers every tbody row in with a fade+slide. Fine for read-only
   lists, wrong here: these rows are edited in place, so React re-keying on an
   add/remove/reorder replays the animation on rows that never moved. */
.svc-form .svc-tbl tbody tr { animation: none; }
.svc-form .svc-tbl tbody td {
  padding: 0; height: 40px;
  border-bottom: 1px solid var(--border);
  background: transparent; vertical-align: middle;
  transition: background .1s;
}
.svc-form .svc-tbl tbody td + td { border-left: 1px solid var(--border); }
.svc-form .svc-tbl tbody tr:last-child td { border-bottom: 1px solid var(--border); }
.svc-form .svc-tbl tbody tr:hover td { background: color-mix(in oklch, var(--muted) 45%, transparent); }
/* design.css rounds the outer cells of a hovered row; inside a bordered,
   gridded table that just chips the corners off the row. */
.svc-form .svc-tbl tbody tr:hover td:first-child,
.svc-form .svc-tbl tbody tr:hover td:last-child { border-radius: 0; }
.svc-form .svc-tbl tbody tr.svc-tbl-empty:hover td { background: transparent; }
.svc-form .svc-tbl-empty td {
  text-align: center; color: var(--muted-foreground);
  font-size: 13px; font-weight: 400; padding: 6px 12px;
}

/* Row number and line total are read, not typed — plain cells rather than
   disabled inputs, so they don't advertise an edit that isn't there. */
.svc-form .svc-tbl .c-idx {
  text-align: center; font-family: var(--font-mono); font-size: 12px;
  color: var(--muted-foreground); font-variant-numeric: tabular-nums;
}
.svc-form .svc-tbl .c-calc {
  padding: 0 10px; text-align: right;
  font-family: var(--font-mono); font-size: 13px; font-weight: 600;
  color: var(--foreground); font-variant-numeric: tabular-nums;
}

/* Chromeless cell controls — the cell edge is the border, and focus draws an
   inset ring so it stays inside the grid instead of overlapping neighbours. */
.svc-form .svc-tbl .c-in {
  width: 100%; height: 100%; min-height: 40px;
  padding: 0 10px; margin: 0;
  background: transparent; border: none; border-radius: 0; box-shadow: none;
  font-family: inherit; font-size: 13px; font-weight: 400; color: var(--foreground);
  -webkit-appearance: none; appearance: none;
}
.svc-form .svc-tbl .c-in:focus {
  outline: none; border-color: transparent;
  box-shadow: inset 0 0 0 2px var(--ring);
  background: var(--card);
}
.svc-form .svc-tbl .c-in::placeholder { color: var(--muted-foreground); opacity: .75; }
.svc-form .svc-tbl .c-in.c-num { text-align: right; font-variant-numeric: tabular-nums; }
.svc-form .svc-tbl .c-in.c-strong { font-weight: 600; }
.svc-form .svc-tbl .c-in[readonly] { color: var(--muted-foreground); }
.svc-form .svc-tbl .c-in[type="date"]::-webkit-calendar-picker-indicator { opacity: .5; cursor: pointer; }
.svc-form .svc-tbl .c-in[type="date"]:hover::-webkit-calendar-picker-indicator { opacity: 1; }
/* Hide the number spinners: they steal ~16px from already-tight money cells
   and the values here are typed, not stepped. */
.svc-form .svc-tbl .c-in[type="number"]::-webkit-outer-spin-button,
.svc-form .svc-tbl .c-in[type="number"]::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.svc-form .svc-tbl .c-in[type="number"] { -moz-appearance: textfield; }

.svc-form .svc-tbl .c-sel { position: relative; display: block; height: 100%; }
.svc-form .svc-tbl .c-sel select.c-in { padding-right: 24px; cursor: pointer; }
.svc-form .svc-tbl .c-sel::after {
  content: ''; position: absolute; right: 11px; top: 50%;
  width: 5px; height: 5px; pointer-events: none;
  border-right: 1.5px solid var(--muted-foreground);
  border-bottom: 1.5px solid var(--muted-foreground);
  transform: translateY(-70%) rotate(45deg);
}

.svc-form .svc-tbl .c-drag, .svc-form .svc-tbl .c-act { text-align: center; }
.svc-form .svc-tbl .c-proof { padding: 0 8px; }
.svc-form .svc-drag {
  display: inline-flex; align-items: center; justify-content: center;
  width: 100%; height: 40px; color: var(--muted-foreground);
  cursor: grab; user-select: none; opacity: 0; transition: opacity .12s;
}
.svc-form .svc-tbl tbody tr:hover .svc-drag { opacity: .7; }
.svc-form .svc-drag:active { cursor: grabbing; opacity: 1; }

.svc-form .svc-row-del {
  display: inline-flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; border-radius: 8px; border: none; padding: 0;
  background: transparent; color: var(--muted-foreground);
  cursor: pointer; opacity: .45; transition: opacity .12s, background .12s, color .12s;
}
.svc-form .svc-tbl tbody tr:hover .svc-row-del { opacity: 1; }
.svc-form .svc-row-del:hover { background: var(--destructive); color: var(--destructive-foreground); opacity: 1; }
.svc-form .svc-row-del:focus-visible { opacity: 1; outline: 2px solid var(--ring); outline-offset: 1px; }

.svc-form .svc-proof { display: flex; align-items: center; gap: 5px; min-width: 0; }
.svc-form .svc-proof-btn, .svc-form .svc-proof-link {
  position: relative; overflow: hidden; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; border-radius: 8px;
  border: 1px solid var(--border); background: var(--muted);
  color: var(--muted-foreground); cursor: pointer; text-decoration: none;
  transition: background .12s, color .12s, border-color .12s;
}
.svc-form .svc-proof-btn:hover, .svc-form .svc-proof-link:hover {
  background: var(--foreground); color: var(--background); border-color: var(--foreground);
}
.svc-form .svc-proof-name {
  font-size: 10.5px; color: var(--muted-foreground);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0;
}

/* Add-row lives inside the table frame rather than as a ghost button in the
   section header, so the affordance sits where the new row will appear. */
.svc-form .svc-tbl-add {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  width: 100%; height: 38px; padding: 0;
  background: transparent; border: none;
  font-family: inherit; font-size: 12.5px; font-weight: 500;
  color: var(--muted-foreground); cursor: pointer; transition: background .12s, color .12s;
}
.svc-form .svc-tbl-add:hover { background: var(--muted); color: var(--foreground); }

/* ── Mobile: flat sections, cards, sticky CTA ── */
.svc-items-cards, .svc-pay-cards, .svc-mobile-save-wrap { display:none; }
@media (max-width:600px) {
  .svc-info-row { grid-template-columns:1fr !important; }

  .svc-items-desktop, .svc-pay-desktop { display:none; }
  .svc-items-cards, .svc-pay-cards { display:flex; flex-direction:column; gap:12px; }
  .svc-add-mobile { display:inline-flex; margin-top:10px; }

  .svc-summary { display:none; }

  .svc-desktop-actions { display:none; }
  .svc-mobile-save-wrap { display:block; margin-top:20px; }

  /* .page's default 88px isn't enough clearance above the 70px fixed bottom
     nav — match .form-page's 112px so the CTA doesn't sit flush against it. */
  .svc-form.page { padding-bottom: 112px; }
}

/* ── Inside the form modal ────────────────────────────────────────────────
   This form opens as a dialog (~630px of usable width) as well as a full page.
   The narrow layout above is exactly what that needs, but it is gated on a
   VIEWPORT media query — and in a dialog the viewport is still 1440px wide
   while the container is not, so it never fires. Re-apply the same card layout
   on container terms instead. .svc-info-row goes to two columns rather than the
   mobile one, since 630px comfortably fits pairs. */
.hms-modal-body .svc-info-row { grid-template-columns: repeat(2, 1fr) !important; }
.hms-modal-body .svc-items-desktop,
.hms-modal-body .svc-pay-desktop { display: none; }
.hms-modal-body .svc-items-cards,
.hms-modal-body .svc-pay-cards { display: flex; flex-direction: column; gap: 12px; }
.hms-modal-body .svc-add-mobile { display: inline-flex; margin-top: 10px; }

/* Where the room exists the table is the better answer, and it is already
   built: one row per service/payment, columns labelled once in the header
   instead of a placeholder per cell. So rather than a third layout, the dialog
   grows to fit the table it already has. .svc-tbl-pay is the widest thing on
   the form at 900px, and the dialog spends 84px on its own chrome before the
   scroll container starts, so 1024px leaves the table ~40px of slack rather
   than a horizontal scrollbar. Below this width nothing changes: the cards keep
   the narrow case. :has() scopes the widening to this form — FormModal's
   DialogContent is shared by all 11 form pages. */
@media (min-width: 1080px) {
  .form-modal-content:has(.svc-form) { max-width: 1024px; }
  .hms-modal-body .svc-items-desktop,
  .hms-modal-body .svc-pay-desktop { display: block; }
  .hms-modal-body .svc-items-cards,
  .hms-modal-body .svc-pay-cards { display: none; }
}

/* tailwind.css sticks the action row to the dialog's bottom edge via
   '.hms-modal-body .hms-form-actions', but position:sticky resolves against the
   element's containing block, and this wrapper (added only so the row can be
   hidden at <=600px in favour of .svc-mobile-save-wrap) shrink-wraps to exactly
   the button row's height — zero travel. display:contents removes the wrapper's
   own box so the actions become a FormPanel flex item like everywhere else,
   while the element stays in the DOM for the mobile rule below. */
.hms-modal-body .svc-desktop-actions { display: contents; }
@media (max-width: 600px) {
  /* Same specificity as the rule above, so this must come after it to win. */
  .hms-modal-body .svc-desktop-actions { display: none; }
}

.svc-form .section-foot { display:flex; align-items:baseline; justify-content:space-between; margin-top:10px; padding-top:10px; border-top:1px solid var(--border); }
.svc-form .section-foot .lbl { font-size:11px; font-weight:500; color:var(--muted-foreground); }
.svc-form .section-foot .val { font-family:var(--font-mono); font-weight:700; font-size:14px; color:var(--foreground); font-variant-numeric:tabular-nums; }
.svc-form .section-foot .val.green { color:var(--green); }
.svc-form .section-foot .val.yellow { color:var(--yellow); }
.svc-form .section-foot .val.red { color:var(--red); }

/* ── Dynamic row cards (narrow layout: phones + this form in a dialog) ─────
   The controls in here are FormFields, so the design system paints them —
   tailwind.css's [data-slot="form-field"] rules give the same 40px height, 2px
   stroke, --radius-control and 14px text as the Invoice Info block above, and
   that is deliberately all that is said about them below. All that is left here
   is the frame: the card and its line layouts. The card's radius is
   control-radius + its own padding, which keeps its corners concentric with the
   field corners inside it rather than guessing. */
.svc-form .svc-items-cards, .svc-form .svc-pay-cards { min-width: 0; }

/* One grid per card, three equal field tracks plus a 40px utility column for
   the row's buttons. Every cell below is placed explicitly rather than left to
   auto-flow: the fields are a fixed vocabulary, so their positions can be too,
   and the reading order stays put instead of reshuffling when one of them
   changes width. */
.svc-form .svc-card {
  background: var(--muted);
  border: 1px solid var(--border);
  border-radius: calc(var(--radius-control) + 12px);
  padding: 12px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr)) 40px;
  gap: 10px; align-items: center; min-width: 0;
}

/* Service — what it is, then how many at what price for how much.
   row 1: Service ……………………………… | [del]
   row 2: Qty    | Price  | Amount   | */
.svc-form .svc-items-cards .f-name   { grid-area: 1 / 1 / 2 / 4; }
.svc-form .svc-items-cards .f-qty    { grid-area: 2 / 1 / 3 / 2; }
.svc-form .svc-items-cards .f-price  { grid-area: 2 / 2 / 3 / 3; }
.svc-form .svc-items-cards .f-amount { grid-area: 2 / 3 / 3 / 4; }
.svc-form .svc-items-cards .f-del    { grid-area: 1 / 4 / 2 / 5; }

/* Payment — when/how much/in what, then how/against what/at what rate, then
   the note. Rate sits directly under Currency, which is what it qualifies.
   row 1: Date   | Amount | Currency | [del]
   row 2: Method | Svc#   | Rate     |
   row 3: Note ………………………………………… | [proof] */
.svc-form .svc-pay-cards .f-date       { grid-area: 1 / 1 / 2 / 2; }
.svc-form .svc-pay-cards .f-pay-amount { grid-area: 1 / 2 / 2 / 3; }
.svc-form .svc-pay-cards .f-cur        { grid-area: 1 / 3 / 2 / 4; }
.svc-form .svc-pay-cards .f-del        { grid-area: 1 / 4 / 2 / 5; }
.svc-form .svc-pay-cards .f-method     { grid-area: 2 / 1 / 3 / 2; }
.svc-form .svc-pay-cards .f-ref        { grid-area: 2 / 2 / 3 / 3; }
.svc-form .svc-pay-cards .f-rate       { grid-area: 2 / 3 / 3 / 4; }
.svc-form .svc-pay-cards .f-note       { grid-area: 3 / 1 / 4 / 4; }
.svc-form .svc-pay-cards .f-proof      { grid-area: 3 / 4 / 4 / 5; }
/* Only rendered when an existing proof is on file, so it takes the utility
   slot beside the note and pushes the upload control up a row. */
.svc-form .svc-pay-cards .f-view       { grid-area: 2 / 4 / 3 / 5; }

.svc-form .f-del { color: var(--muted-foreground); justify-self: center; }
.svc-form .f-del:hover { color: var(--destructive); }
.svc-form .svc-card .svc-num { text-align: right; font-variant-numeric: tabular-nums; }
.svc-form .svc-card input[readonly] { color: var(--muted-foreground); cursor: default; }

/* The line total, built to the same spec as a field so the card's second row
   reads as three equal cells — but flat, since there is nothing to type in it. */
.svc-form .svc-calc {
  display: flex; align-items: center; justify-content: flex-end;
  height: 40px; padding: 0 12px; min-width: 0;
  border: 2px solid transparent; border-radius: var(--radius-control);
  background: color-mix(in oklch, var(--card) 55%, transparent);
  font-family: var(--font-mono); font-size: 14px; font-weight: 600;
  color: var(--foreground); font-variant-numeric: tabular-nums;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* A date field wants ~150px before the native picker starts crowding its text,
   which three tracks can't give below roughly this width — the standalone page
   only shows these cards under 600px, so it always lands here, and the dialog
   (~630px of content) keeps the three-track layout. */
@media (max-width: 620px) {
  .svc-form .svc-card { grid-template-columns: repeat(2, minmax(0, 1fr)) 40px; }

  .svc-form .svc-items-cards .f-name   { grid-area: 1 / 1 / 2 / 3; }
  .svc-form .svc-items-cards .f-del    { grid-area: 1 / 3 / 2 / 4; }
  .svc-form .svc-items-cards .f-qty    { grid-area: 2 / 1 / 3 / 2; }
  .svc-form .svc-items-cards .f-price  { grid-area: 2 / 2 / 3 / 3; }
  .svc-form .svc-items-cards .f-amount { grid-area: 3 / 1 / 4 / 3; }

  .svc-form .svc-pay-cards .f-date       { grid-area: 1 / 1 / 2 / 2; }
  .svc-form .svc-pay-cards .f-pay-amount { grid-area: 1 / 2 / 2 / 3; }
  .svc-form .svc-pay-cards .f-del        { grid-area: 1 / 3 / 2 / 4; }
  .svc-form .svc-pay-cards .f-method     { grid-area: 2 / 1 / 3 / 2; }
  .svc-form .svc-pay-cards .f-cur        { grid-area: 2 / 2 / 3 / 3; }
  .svc-form .svc-pay-cards .f-ref        { grid-area: 3 / 1 / 4 / 2; }
  .svc-form .svc-pay-cards .f-rate       { grid-area: 3 / 2 / 4 / 3; }
  .svc-form .svc-pay-cards .f-note       { grid-area: 4 / 1 / 5 / 3; }
  .svc-form .svc-pay-cards .f-proof      { grid-area: 4 / 3 / 5 / 4; }
  .svc-form .svc-pay-cards .f-view       { grid-area: 3 / 3 / 4 / 4; }
}

/* Phones. Two tracks minus the utility column leaves ~116px a field, and a
   date control needs about 135 before "dd/mm/yyyy" and its picker start
   overlapping — measured, not guessed. So dates get a full row here and the
   remaining pairs tighten their side padding to buy back the difference. */
@media (max-width: 450px) {
  .svc-form .svc-card [data-slot="form-field"] input,
  .svc-form .svc-card [data-slot="form-field"] select { padding-inline: 10px; }

  .svc-form .svc-pay-cards .f-date       { grid-area: 1 / 1 / 2 / 3; }
  .svc-form .svc-pay-cards .f-del        { grid-area: 1 / 3 / 2 / 4; }
  .svc-form .svc-pay-cards .f-pay-amount { grid-area: 2 / 1 / 3 / 2; }
  .svc-form .svc-pay-cards .f-cur        { grid-area: 2 / 2 / 3 / 3; }
  .svc-form .svc-pay-cards .f-proof      { grid-area: 2 / 3 / 3 / 4; }
  .svc-form .svc-pay-cards .f-method     { grid-area: 3 / 1 / 4 / 2; }
  .svc-form .svc-pay-cards .f-ref        { grid-area: 3 / 2 / 4 / 3; }
  .svc-form .svc-pay-cards .f-view       { grid-area: 3 / 3 / 4 / 4; }
  .svc-form .svc-pay-cards .f-rate       { grid-area: 4 / 1 / 5 / 2; }
  .svc-form .svc-pay-cards .f-note       { grid-area: 4 / 2 / 5 / 3; }
  /* At the invoice's own currency the rate is forced to 1 and can't be edited,
     so on a phone it is only taking room from the note. Elsewhere it stays put
     — there the row it sits in exists either way. !important because FormField
     sets display:flex as an inline style, which no stylesheet rule can outrank
     without it. */
  .svc-form .svc-pay-cards .svc-card[data-rate-locked="true"] .f-rate { display: none !important; }
  .svc-form .svc-pay-cards .svc-card[data-rate-locked="true"] .f-note { grid-area: 4 / 1 / 5 / 3; }
}

/* ── Payments timeline ──
   A payment list is a sequence of events, and the rail is the one thing on this
   form that says so. It sits outside the cards, so it costs nothing the fields
   need. */
.svc-form .tl-list { position: relative; padding-left: 22px; display: flex; flex-direction: column; gap: 12px; }
.svc-form .tl-list::before {
  content: ''; position: absolute; left: 5px; top: 12px; bottom: 12px;
  width: 1px; background: var(--border);
}
.svc-form .tl-item { position: relative; min-width: 0; }
/* 12px card padding + half a 40px field = the first row's optical centre. */
.svc-form .tl-dot {
  position: absolute; left: -22px; top: 26px;
  width: 11px; height: 11px; border-radius: 50%;
  background: var(--card); border: 2px solid var(--foreground);
}

/* Proof has no native control shaped like a field, so its trigger is built to
   the same spec by hand — the same thing tailwind.css's
   [data-slot="select-trigger"] rule does, for the same reason. */
.svc-form .svc-proof-box {
  position: relative; overflow: hidden; flex: 0 0 auto;
  display: inline-flex; align-items: center; justify-content: center;
  width: 40px; height: 40px;
  background: var(--card); border: 2px solid var(--border);
  border-radius: var(--radius-control);
  color: var(--muted-foreground); cursor: pointer; text-decoration: none;
  transition: border-color .14s ease, color .14s ease;
}
.svc-form .svc-proof-box:hover, .svc-form .svc-proof-box:focus-within { border-color: var(--ring); color: var(--foreground); }
.svc-form .svc-proof-box[data-has-file="true"] { border-color: var(--foreground); color: var(--foreground); }
.svc-form .sr-only {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
}

/* Typed, never stepped — and the spinner reserves width the money fields in a
   two-column card don't have to spare. */
.svc-form .svc-card input[type="number"]::-webkit-outer-spin-button,
.svc-form .svc-card input[type="number"]::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.svc-form .svc-card input[type="number"] { -moz-appearance: textfield; }
`;
