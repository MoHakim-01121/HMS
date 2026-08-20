import { useMemo, useRef, useState } from "react";
import { useForm } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import Combobox from "../../components/shadcn/combobox.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Dialog, DialogContent } from "../../components/shadcn/ui/dialog.jsx";
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
const METHODS = ["Cash", "Bank Transfer", "Direct", "Deposit"];
const fmt = (n) => Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 0 });

const blankRes = () => ({ reservation_number: "", hotel: "", check_in: "", check_out: "", reservation_total: "" });
let _paySeq = 0;
const blankPay = () => ({ _key: ++_paySeq, ref: "", date: "", method: "Cash", amount: "", currency: "SAR", exchange: 1, note: "", proof_keep: "", proof_url: null, file: null });

function seedFrom(src) {
  if (!src) return { reservations: [blankRes()], payments: [blankPay()], linkedClIds: [] };
  const reservations = (src.reservations || []).map((r) => ({
    reservation_number: r.reservation_number || "", hotel: r.hotel || "",
    check_in: r.check_in || "", check_out: r.check_out || "",
    reservation_total: r.reservation_total ?? "",
  }));
  const payments = (src.payments || []).map((p) => ({
    _key: ++_paySeq,
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

export default function Form({ invoice, edit, suggested_number, cl_data = [], clients = [], initial, errors = {} }) {
  const { t } = useI18n();
  const src = initial || invoice;
  const initialClient = clients.find((c) => String(c.id) === String(src?.client_id)) || null;
  const [clientId, setClientId] = useState(src?.client_id || "");
  const [clientQuery, setClientQuery] = useState(initialClient ? initialClient.name : "");
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
  // Open with whatever this invoice already carries ticked, so importing a
  // second time adds to the list instead of starting a new one. Without this
  // the dialog came up blank every time and Import overwrote the lot, which
  // meant adding one more CL required re-selecting all the earlier ones.
  const openModal = () => {
    const already = {};
    for (const cl of cl_data) if (linkedClIds.includes(cl.id)) already[cl.id] = cl;
    setSelected(already);
    setSearch("");
    setModalOpen(true);
  };
  const toggleSel = (cl) => setSelected((s) => { const n = { ...s }; if (n[cl.id]) delete n[cl.id]; else n[cl.id] = cl; return n; });
  const doImport = () => {
    const cls = Object.values(selected);
    if (!cls.length) return;
    const wanted = new Set(cls.map((cl) => cl.ref));
    // The only rows an import may drop are the ones a previous import put
    // there. A row typed by hand is the user's, whatever its number says.
    const fromCl = new Set(cl_data.filter((cl) => linkedClIds.includes(cl.id)).map((cl) => cl.ref));
    const present = new Set(reservations.map((r) => (r.reservation_number || "").trim()));

    const kept = reservations.filter((r) => {
      const ref = (r.reservation_number || "").trim();
      // Drop the untouched starter row rather than carry a blank line along.
      if (!ref && !(parseFloat(r.reservation_total) || 0)) return false;
      return fromCl.has(ref) ? wanted.has(ref) : true;
    });
    // Rows already on the invoice keep whatever the user edited into them —
    // re-importing a CL must not overwrite a corrected hotel name or total.
    const added = cls.filter((cl) => !present.has(cl.ref)).map((cl) => ({
      reservation_number: cl.ref, hotel: cl.hotel, check_in: cl.check_in || "",
      check_out: cl.check_out || "", reservation_total: cl.total || "",
    }));

    const next = [...kept, ...added];
    setReservations(next.length ? next : [blankRes()]);
    setLinkedClIds(cls.map((cl) => cl.id));
    // Auto-select client if all imported CLs share the same guest/client
    if (!clientId) {
      const guestNames = [...new Set(cls.map((cl) => cl.guest))];
      if (guestNames.length === 1) {
        setCustomerName(guestNames[0]);
      }
    }
    setModalOpen(false);
  };

  // ── Client selection ──
  const onClientText = (text) => {
    setClientQuery(text);
    const match = clients.find((c) => c.name.toLowerCase() === text.trim().toLowerCase());
    if (match) {
      setClientId(String(match.id));
      setCustomerName(match.name);
    } else {
      setClientId("");
      setCustomerName(text);
    }
  };
  const onClientSelect = (c) => {
    setClientQuery(c.name);
    setClientId(String(c.id));
    setCustomerName(c.name);
  };

  const submit = (e) => {
    e.preventDefault();
    const resRows = reservations.filter((r) => (r.reservation_number || "").trim() || (parseFloat(r.reservation_total) || 0) > 0);
    const payRows = payments.filter((p) => (parseFloat(p.amount) || 0) > 0);
    form.transform(() => {
      const data = {
        client_id: clientId, customer_name: customerName, invoice_number: invoiceNumber,
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
    <div className="page inv-form shadcn-root">
      <style>{CSS}</style>
      <PageBack href="/invoice/" label={t("Back")} />
      <FormHeader
        kicker={t("Invoice Hotel")}
        title={edit ? t("Edit Invoice — {number}", { number: src?.invoice_number || "" }) : t("Invoice Hotel")}
        sub={t("Hotel reservations + payments in SAR")}
      />

      <form method="post" onSubmit={submit}>
        <FormPanel>
          {/* ── Info ── */}
          <FormSection label={t("Invoice Info")}>
            {/* No Company picker: the server files every invoice under the
                session's active company, and list/detail/edit all filter by it
                too — so choosing the other one here only ever produced a record
                that vanished from the very list you created it from. Switch
                companies with the topbar switcher instead. */}
            <div className="inv-info-row" style={{ display: "grid", gridTemplateColumns: "1fr 160px 140px 140px", gap: 12 }}>
              <FormField label={t("Customer")} name="client_id">
                <Combobox
                  name="client_id"
                  value={clientQuery}
                  onTextChange={onClientText}
                  onSelect={onClientSelect}
                  options={clients}
                  getLabel={(o) => o.name}
                  placeholder={t("Search client…")}
                />
              </FormField>
              <FormField label={t("Invoice Number")} name="invoice_number" required
                value={invoiceNumber} onChange={setInvoiceNumber} placeholder="INV-001"
                error={errors.invoice_number} />
              <FormField label={t("Issued Date")} name="issued_date" type="date" required value={issuedDate} onChange={setIssuedDate} />
              <FormField label={t("Due Date")} name="due_date" type="date" required value={dueDate} onChange={setDueDate} />
            </div>
          </FormSection>

          {/* ── Reservations ── */}
          <FormSection
            label={t("Reservations")}
            action={
              cl_data.length > 0 && (
                <Button type="button" variant="ghost" size="sm" onClick={openModal}>
                  <Icon name="invoice" size={11} /> {t("Import from CL")}
                </Button>
              )
            }
          >
            <div className="inv-res-desktop">
              <div className="inv-tbl-wrap">
                <div className="inv-tbl-scroll">
                  <table className="inv-tbl inv-tbl-res" id="reservations">
                    <colgroup>
                      <col style={{ width: 124 }} />
                      <col />
                      <col style={{ width: 142 }} />
                      <col style={{ width: 142 }} />
                      <col style={{ width: 148 }} />
                      <col style={{ width: 48 }} />
                    </colgroup>
                    <thead>
                      <tr>
                        <th>Res#</th>
                        <th>{t("Hotel")}</th>
                        <th>{t("Check-in")}</th>
                        <th>{t("Check-out")}</th>
                        <th className="r">{t("Total SAR")}</th>
                        <th aria-label={t("Actions")} />
                      </tr>
                    </thead>
                    <tbody>
                      {reservations.map((r, i) => (
                        <tr key={i}>
                          <td><input className="c-in c-strong" type="text" placeholder="RES#" required inputMode="numeric" value={r.reservation_number} onChange={(e) => setRes(i, "reservation_number", e.target.value)} /></td>
                          <td><input className="c-in" type="text" placeholder={t("Hotel name")} value={r.hotel} onChange={(e) => setRes(i, "hotel", e.target.value)} /></td>
                          <td><input className="c-in" type="date" value={r.check_in} onChange={(e) => setRes(i, "check_in", e.target.value)} /></td>
                          <td><input className="c-in" type="date" min={r.check_in || undefined} value={r.check_out} onChange={(e) => setRes(i, "check_out", e.target.value)} /></td>
                          <td><input className="c-in c-num" type="number" placeholder="0.00" step="0.01" required value={r.reservation_total} onChange={(e) => setRes(i, "reservation_total", e.target.value)} /></td>
                          <td className="c-act">
                            <button type="button" className="inv-row-del" onClick={() => removeRes(i)} aria-label={t("Remove reservation")}><Icon name="trash" size={13} /></button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <button type="button" className="inv-tbl-add" onClick={addRes}>+ {t("Add reservation")}</button>
              </div>
            </div>
            <div className="inv-res-cards">
              {reservations.map((r, i) => (
                <div className="inv-row-card" key={i}>
                  <CardField name={`res-${i}-number`} cell="f-res">
                    <input id={`res-${i}-number`} type="text" inputMode="numeric" aria-label={t("Reservation number")}
                      placeholder="RES#" value={r.reservation_number} onChange={(e) => setRes(i, "reservation_number", e.target.value)} />
                  </CardField>
                  <CardField name={`res-${i}-hotel`} cell="f-hotel">
                    <input id={`res-${i}-hotel`} type="text" aria-label={t("Hotel")}
                      placeholder={t("Hotel name")} value={r.hotel} onChange={(e) => setRes(i, "hotel", e.target.value)} />
                  </CardField>
                  <CardField name={`res-${i}-in`} cell="f-in">
                    <input id={`res-${i}-in`} type="date" aria-label={t("Check-in")}
                      value={r.check_in} onChange={(e) => setRes(i, "check_in", e.target.value)} />
                  </CardField>
                  <CardField name={`res-${i}-out`} cell="f-out">
                    <input id={`res-${i}-out`} type="date" aria-label={t("Check-out")} min={r.check_in || undefined}
                      value={r.check_out} onChange={(e) => setRes(i, "check_out", e.target.value)} />
                  </CardField>
                  <CardField name={`res-${i}-total`} cell="f-total">
                    <input id={`res-${i}-total`} type="number" step="0.01" className="inv-num" aria-label={t("Total in SAR")}
                      placeholder={t("Total SAR")} value={r.reservation_total} onChange={(e) => setRes(i, "reservation_total", e.target.value)} />
                  </CardField>
                  <RemoveButton label={t("Remove reservation")} onClick={() => removeRes(i)} />
                </div>
              ))}
              <button type="button" className="btn-add-row inv-add-mobile" onClick={addRes}>+ {t("Add reservation")}</button>
              <div className="section-foot"><span className="lbl">{t("Total")}</span><span className="val">{fmt(totals.totalRes)} SAR</span></div>
            </div>
          </FormSection>

          {/* ── Payments ── */}
          <FormSection label={t("Payments")}>
            <div className="inv-pay-desktop">
              <div className="inv-tbl-wrap">
                <div className="inv-tbl-scroll">
                  <table className="inv-tbl inv-tbl-pay" id="payments">
                    {/* Widths tuned so all ten columns clear 910px — the panel is
                        ~950px at a 1440 viewport, so the Remove button stays on
                        screen instead of living past the scroll edge. */}
                    <colgroup>
                      <col style={{ width: 30 }} />
                      <col style={{ width: 96 }} />
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
                        <th>Res#</th>
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
                        <tr className="inv-tbl-empty">
                          <td colSpan={10}>{t("No payments recorded yet")}</td>
                        </tr>
                      ) : payments.map((p, i) => (
                        <tr key={p._key} onDragOver={onPayDragOver} onDrop={(e) => onPayDrop(e, i)}>
                          <td className="c-drag">
                            <span className="inv-drag" draggable onDragStart={(e) => onPayDragStart(e, i)} onDragEnd={onPayDragEnd} aria-label={t("Drag to reorder")}><DragIcon /></span>
                          </td>
                          <td>
                            <span className="c-sel">
                              <select className="c-in" value={p.ref} required onChange={(e) => setPay(i, { ref: e.target.value })}>
                                <option value="">—</option>
                                {resOptions.map((n) => <option key={n} value={n}>{n}</option>)}
                              </select>
                            </span>
                          </td>
                          <td><input className="c-in" type="date" required value={p.date} onChange={(e) => setPay(i, { date: e.target.value })} /></td>
                          <td>
                            <span className="c-sel">
                              <select className="c-in" value={p.method} required onChange={(e) => setPay(i, { method: e.target.value })}>
                                {METHODS.map((m) => <option key={m} value={m}>{t(m)}</option>)}
                              </select>
                            </span>
                          </td>
                          <td><input className="c-in c-num c-strong" type="number" step="0.01" placeholder="0.00" required value={p.amount} onChange={(e) => setPay(i, { amount: e.target.value })} /></td>
                          <td>
                            <span className="c-sel">
                              <select className="c-in" value={p.currency} onChange={(e) => onCurrencyChange(i, e.target.value)}>
                                {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                              </select>
                            </span>
                          </td>
                          <td><input className="c-in c-num" type="number" step="0.0001" placeholder="1" value={p.exchange} readOnly={p.currency === "SAR"} onChange={(e) => setPay(i, { exchange: e.target.value })} /></td>
                          <td><input className="c-in" type="text" placeholder="—" value={p.note} onChange={(e) => setPay(i, { note: e.target.value })} /></td>
                          <td className="c-proof">
                            <div className="inv-proof">
                              {p.proof_url && !p.file && <a href={p.proof_url} target="_blank" rel="noreferrer" className="inv-proof-link" title={t("View proof")}><Icon name="proof" size={13} /></a>}
                              <label className="inv-proof-btn" title={t("Upload proof")}>
                                <Icon name="proof" size={13} />
                                <input type="file" accept="image/*,.pdf" style={{ position: "absolute", width: 1, height: 1, opacity: 0, overflow: "hidden" }} onChange={(e) => setPay(i, { file: e.target.files[0] || null })} />
                              </label>
                              {p.file && <span className="inv-proof-name" title={p.file.name}>{p.file.name}</span>}
                            </div>
                          </td>
                          <td className="c-act">
                            <button type="button" className="inv-row-del" onClick={() => removePay(i)} aria-label={t("Remove payment")}><Icon name="trash" size={13} /></button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <button type="button" className="inv-tbl-add" onClick={addPay}>+ {t("Add payment")}</button>
              </div>
            </div>
            <div className="inv-pay-cards">
              <div className="tl-list">
                {payments.map((p, i) => (
                  <div className="tl-item" key={p._key}>
                    <span className="tl-dot" />
                    <div className="inv-row-card" data-cur={p.currency}>
                      <CardField name={`pay-${i}-date`} cell="f-date">
                        <input id={`pay-${i}-date`} type="date" aria-label={t("Payment date")}
                          value={p.date} onChange={(e) => setPay(i, { date: e.target.value })} />
                      </CardField>
                      <CardField name={`pay-${i}-amount`} cell="f-amount">
                        <input id={`pay-${i}-amount`} type="number" step="0.01" className="inv-num" aria-label={t("Amount")}
                          placeholder={t("Amount")} value={p.amount} onChange={(e) => setPay(i, { amount: e.target.value })} />
                      </CardField>
                      <CardField name={`pay-${i}-currency`} cell="f-cur">
                        <select id={`pay-${i}-currency`} aria-label={t("Currency")}
                          value={p.currency} onChange={(e) => onCurrencyChange(i, e.target.value)}>
                          {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                        </select>
                      </CardField>
                      <CardField name={`pay-${i}-method`} cell="f-method">
                        <select id={`pay-${i}-method`} aria-label={t("Payment method")}
                          value={p.method} onChange={(e) => setPay(i, { method: e.target.value })}>
                          {METHODS.map((m) => <option key={m} value={m}>{t(m)}</option>)}
                        </select>
                      </CardField>
                      <CardField name={`pay-${i}-ref`} cell="f-ref">
                        <select id={`pay-${i}-ref`} aria-label={t("Reservation number")}
                          value={p.ref} onChange={(e) => setPay(i, { ref: e.target.value })}>
                          <option value="">Res#</option>
                          {resOptions.map((n) => <option key={n} value={n}>{n}</option>)}
                        </select>
                      </CardField>
                      {/* Rate keeps its slot at SAR instead of being dropped —
                          the desktop table does the same. A field that comes
                          and goes reflows every cell after it, which is a worse
                          trade than one dimmed 1.0000 that can't be typed in. */}
                      <CardField name={`pay-${i}-rate`} cell="f-rate">
                        <input id={`pay-${i}-rate`} type="number" step="0.0001" className="inv-num" aria-label={t("Exchange rate")}
                          placeholder={t("Rate")} readOnly={p.currency === "SAR"}
                          value={p.exchange} onChange={(e) => setPay(i, { exchange: e.target.value })} />
                      </CardField>
                      <CardField name={`pay-${i}-note`} cell="f-note">
                        <input id={`pay-${i}-note`} type="text" aria-label={t("Note")}
                          placeholder={t("Note")} value={p.note} onChange={(e) => setPay(i, { note: e.target.value })} />
                      </CardField>
                      <RemoveButton label={t("Remove payment")} onClick={() => removePay(i)} />
                      <label className="inv-proof-box f-proof" data-has-file={p.file ? "true" : undefined}
                        title={p.file ? p.file.name : p.proof_url ? t("Replace proof") : t("Attach proof")}>
                        <Icon name="proof" size={14} />
                        <span className="sr-only">{p.file ? p.file.name : t("Attach proof")}</span>
                        <input type="file" accept="image/*,.pdf" aria-label={t("Attach proof")} style={{ position: "absolute", width: 1, height: 1, opacity: 0, overflow: "hidden" }} onChange={(e) => setPay(i, { file: e.target.files[0] || null })} />
                      </label>
                      {p.proof_url && !p.file && (
                        <a href={p.proof_url} target="_blank" rel="noreferrer" className="inv-proof-box f-view" aria-label={t("View current proof")} title={t("View current proof")}>
                          <Icon name="proof" size={14} />
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              <button type="button" className="btn-add-row inv-add-mobile" onClick={addPay}>+ {t("Add payment")}</button>
              <div className="section-foot"><span className="lbl">{t("Remaining")}</span><span className={"val " + remainingClass}>{fmt(totals.remaining)} SAR</span></div>
            </div>
          </FormSection>

          {/* ── Summary ── */}
          <div className="inv-summary">
            <div className="inv-summary-cell"><div className="lbl">{t("Total Reservations")}</div><div className="val">{fmt(totals.totalRes)} SAR</div></div>
            <div className="inv-summary-cell"><div className="lbl">{t("Total Paid")}</div><div className="val green">{fmt(totals.totalPaidSar)} SAR</div></div>
            <div className="inv-summary-cell"><div className="lbl">{t("Remaining")}</div><div className={"val " + remainingClass}>{fmt(totals.remaining)} SAR</div></div>
          </div>

          <div className="inv-desktop-actions">
            <FormActions
              cancelHref={edit ? `/invoice/${src.pk}/` : "/invoice/"}
              submitLabel={form.processing ? t("Saving…") : edit ? t("Update & Save") : t("Save & Open")}
              processing={form.processing}
            />
          </div>

          <div className="inv-mobile-save-wrap">
            <button type="submit" className="dv-cta" disabled={form.processing}>
              {form.processing ? t("Saving…") : edit ? t("Update & Save") : t("Save & Open")}
            </button>
          </div>
        </FormPanel>
      </form>

      {/* ── CL Import Modal ── */}
      {cl_data.length > 0 && (
        <Dialog open={modalOpen} onOpenChange={setModalOpen}>
          <DialogContent
            className="cl-modal-content overflow-hidden p-0"
            showCloseButton={false}
          >
            <div className="cl-modal-head">
              <h3>{t("Import from Confirmation Letter")}</h3>
              <Button type="button" variant="ghost" size="icon-sm" onClick={() => setModalOpen(false)}>
                <Icon name="close" size={14} />
              </Button>
            </div>
            <div className="cl-modal-search">
              <input type="text" placeholder={t("Search guest, hotel, CL number…")} autoComplete="off" value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
            <div className="cl-modal-body">
              <table>
                <thead><tr>
                  <th style={{ width: 32 }}></th><th>No CL</th><th>{t("Guest")}</th><th>{t("Hotel")}</th>
                  <th>{t("Check-in")}</th><th>{t("Check-out")}</th><th style={{ textAlign: "right" }}>{t("Total SAR")}</th>
                </tr></thead>
                <tbody>
                  {filteredCls.length === 0 ? (
                    <tr><td colSpan={7}><div className="cl-modal-empty">{t("No CL available")}</div></td></tr>
                  ) : filteredCls.map((cl) => {
                    const isSel = !!selected[cl.id];
                    return (
                      <tr
                        key={cl.id}
                        className={"cl-modal-row" + (isSel ? " selected" : "")}
                        onClick={() => toggleSel(cl)}
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.target !== e.currentTarget) return;
                          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleSel(cl); }
                        }}
                      >
                        <td style={{ textAlign: "center" }}><input type="checkbox" checked={isSel} onChange={() => toggleSel(cl)} onClick={(e) => e.stopPropagation()} style={{ width: "auto", margin: 0, accentColor: "var(--foreground)", cursor: "pointer" }} /></td>
                        <td style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>{cl.ref}{cl.inv && <span style={{ fontSize: 10, color: "var(--foreground)", marginLeft: 4 }}>● {cl.inv}</span>}</td>
                        <td>{cl.guest}</td>
                        <td style={{ color: "var(--muted-foreground)" }}>{cl.hotel}</td>
                        <td style={{ color: "var(--muted-foreground)" }}>{fmtDate(cl.check_in)}</td>
                        <td style={{ color: "var(--muted-foreground)" }}>{fmtDate(cl.check_out)}</td>
                        <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{cl.total ? cl.total.toLocaleString() : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="cl-modal-foot">
              <span className="cl-modal-sel-info"><strong>{Object.keys(selected).length}</strong> {t("CL selected")}</span>
              <div style={{ display: "flex", gap: 8 }}>
                <Button type="button" variant="ghost" size="sm" onClick={() => setModalOpen(false)}>{t("Cancel")}</Button>
                <Button type="button" size="sm" disabled={!Object.keys(selected).length} onClick={doImport}>{t("Import")}</Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

const CSS = `
.inv-sec-head { display:flex; align-items:center; justify-content:space-between; padding:11px 20px; border-top:1px solid var(--border); border-bottom:1px solid var(--border); background:var(--muted); }
.inv-summary { display:grid; grid-template-columns:1fr 1fr 1fr; border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; background:var(--muted); }
.inv-summary-cell { padding:14px 22px; border-right:1px solid var(--border); }
.inv-summary-cell:last-child { border-right:none; }
.inv-summary-cell .lbl { font-size:11px; font-weight:600; color:var(--muted-foreground); margin-bottom:6px; }
.inv-summary-cell .val { font-family:var(--font-mono); font-size:18px; font-weight:700; color:var(--foreground); font-variant-numeric:tabular-nums; }
.inv-summary-cell .val.green { color:var(--green); }
.inv-summary-cell .val.yellow { color:var(--yellow); }
.inv-summary-cell .val.red { color:var(--red); }
@media(max-width:640px) { .inv-summary { grid-template-columns:1fr; } .inv-summary-cell { border-right:none; border-bottom:1px solid var(--border); } .inv-summary-cell:last-child { border-bottom:none; } }
@media(max-width:900px) { .inv-info-row { grid-template-columns: 110px 1fr 160px !important; } }

/* ── Editable data tables (Reservations / Payments) ───────────────────────
   Rebuilt off hw/static/hw/css/invoice_form.css's CSS-grid rows, which were
   still painted from the retired token set (--bg-2 / --surface-2 / --border-2
   / --accent / --text-3 / --r-lg) and wrapped shadcn Inputs in their own
   bordered "card" per row — two borders and two radii per field, on two
   different design systems. These are real <table>s on the current tokens
   instead: the cell grid supplies the structure, and the controls inside are
   chromeless so a row reads as one line of data rather than a rack of inputs.
   Scoped under .inv-form so the legacy file's element rules can't reach them. */
.inv-form .inv-tbl-wrap {
  border: 1px solid var(--border);
  border-radius: var(--radius-control, 16px);
  background: var(--card);
  overflow: hidden;
}
.inv-form .inv-tbl-scroll { overflow-x: auto; }
.inv-form .inv-tbl { width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 0; }
.inv-form .inv-tbl-res { min-width: 700px; }
.inv-form .inv-tbl-pay { min-width: 910px; }

.inv-form .inv-tbl thead th {
  padding: 0 10px; height: 38px;
  font-size: 12px; font-weight: 500; line-height: 38px;
  color: var(--muted-foreground); text-align: left; white-space: nowrap;
  background: var(--muted); border-bottom: 1px solid var(--border);
  text-transform: none; letter-spacing: normal;
}
.inv-form .inv-tbl thead th.r { text-align: right; }
.inv-form .inv-tbl thead th + th { border-left: 1px solid var(--border); }

/* design.css staggers every tbody row in with a fade+slide. Fine for read-only
   lists, wrong here: these rows are edited in place, so React re-keying on an
   add/remove/reorder replays the animation on rows that never moved. */
.inv-form .inv-tbl tbody tr { animation: none; }
.inv-form .inv-tbl tbody td {
  padding: 0; height: 40px;
  border-bottom: 1px solid var(--border);
  background: transparent; vertical-align: middle;
  transition: background .1s;
}
.inv-form .inv-tbl tbody td + td { border-left: 1px solid var(--border); }
.inv-form .inv-tbl tbody tr:last-child td { border-bottom: 1px solid var(--border); }
.inv-form .inv-tbl tbody tr:hover td { background: color-mix(in oklch, var(--muted) 45%, transparent); }
/* design.css rounds the outer cells of a hovered row; inside a bordered,
   gridded table that just chips the corners off the row. */
.inv-form .inv-tbl tbody tr:hover td:first-child,
.inv-form .inv-tbl tbody tr:hover td:last-child { border-radius: 0; }
.inv-form .inv-tbl tbody tr.inv-tbl-empty:hover td { background: transparent; }
.inv-form .inv-tbl-empty td {
  text-align: center; color: var(--muted-foreground);
  font-size: 13px; font-weight: 400; padding: 6px 12px;
}

/* Chromeless cell controls — the cell edge is the border, and focus draws an
   inset ring so it stays inside the grid instead of overlapping neighbours. */
.inv-form .inv-tbl .c-in {
  width: 100%; height: 100%; min-height: 40px;
  padding: 0 10px; margin: 0;
  background: transparent; border: none; border-radius: 0; box-shadow: none;
  font-family: inherit; font-size: 13px; font-weight: 400; color: var(--foreground);
  -webkit-appearance: none; appearance: none;
}
.inv-form .inv-tbl .c-in:focus {
  outline: none; border-color: transparent;
  box-shadow: inset 0 0 0 2px var(--ring);
  background: var(--card);
}
.inv-form .inv-tbl .c-in::placeholder { color: var(--muted-foreground); opacity: .75; }
.inv-form .inv-tbl .c-in.c-num { text-align: right; font-variant-numeric: tabular-nums; }
.inv-form .inv-tbl .c-in.c-strong { font-weight: 600; }
.inv-form .inv-tbl .c-in[readonly] { color: var(--muted-foreground); }
.inv-form .inv-tbl .c-in[type="date"]::-webkit-calendar-picker-indicator { opacity: .5; cursor: pointer; }
.inv-form .inv-tbl .c-in[type="date"]:hover::-webkit-calendar-picker-indicator { opacity: 1; }
/* Hide the number spinners: they steal ~16px from already-tight money cells
   and the values here are typed, not stepped. */
.inv-form .inv-tbl .c-in[type="number"]::-webkit-outer-spin-button,
.inv-form .inv-tbl .c-in[type="number"]::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.inv-form .inv-tbl .c-in[type="number"] { -moz-appearance: textfield; }

.inv-form .inv-tbl .c-sel { position: relative; display: block; height: 100%; }
.inv-form .inv-tbl .c-sel select.c-in { padding-right: 24px; cursor: pointer; }
.inv-form .inv-tbl .c-sel::after {
  content: ''; position: absolute; right: 11px; top: 50%;
  width: 5px; height: 5px; pointer-events: none;
  border-right: 1.5px solid var(--muted-foreground);
  border-bottom: 1.5px solid var(--muted-foreground);
  transform: translateY(-70%) rotate(45deg);
}

.inv-form .inv-tbl .c-drag, .inv-form .inv-tbl .c-act { text-align: center; }
.inv-form .inv-tbl .c-proof { padding: 0 8px; }
.inv-form .inv-drag {
  display: inline-flex; align-items: center; justify-content: center;
  width: 100%; height: 40px; color: var(--muted-foreground);
  cursor: grab; user-select: none; opacity: 0; transition: opacity .12s;
}
.inv-form .inv-tbl tbody tr:hover .inv-drag { opacity: .7; }
.inv-form .inv-drag:active { cursor: grabbing; opacity: 1; }

.inv-form .inv-row-del {
  display: inline-flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; border-radius: 8px; border: none; padding: 0;
  background: transparent; color: var(--muted-foreground);
  cursor: pointer; opacity: .45; transition: opacity .12s, background .12s, color .12s;
}
.inv-form .inv-tbl tbody tr:hover .inv-row-del { opacity: 1; }
.inv-form .inv-row-del:hover { background: var(--destructive); color: var(--destructive-foreground); opacity: 1; }
.inv-form .inv-row-del:focus-visible { opacity: 1; outline: 2px solid var(--ring); outline-offset: 1px; }

.inv-form .inv-proof { display: flex; align-items: center; gap: 5px; min-width: 0; }
.inv-form .inv-proof-btn, .inv-form .inv-proof-link {
  position: relative; overflow: hidden; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; border-radius: 8px;
  border: 1px solid var(--border); background: var(--muted);
  color: var(--muted-foreground); cursor: pointer; text-decoration: none;
  transition: background .12s, color .12s, border-color .12s;
}
.inv-form .inv-proof-btn:hover, .inv-form .inv-proof-link:hover {
  background: var(--foreground); color: var(--background); border-color: var(--foreground);
}
.inv-form .inv-proof-name {
  font-size: 10.5px; color: var(--muted-foreground);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0;
}

/* Add-row lives inside the table frame rather than as a ghost button in the
   section header, so the affordance sits where the new row will appear. No
   totals row underneath it: with exactly one table per section its subtotal
   would be the same figure .inv-summary already states below. */
.inv-form .inv-tbl-add {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  width: 100%; height: 38px; padding: 0;
  background: transparent; border: none;
  font-family: inherit; font-size: 12.5px; font-weight: 500;
  color: var(--muted-foreground); cursor: pointer; transition: background .12s, color .12s;
}
.inv-form .inv-tbl-add:hover { background: var(--muted); color: var(--foreground); }

.cl-modal-content { width:700px; max-width:96vw; max-height:82vh; display:flex; flex-direction:column; }
.cl-modal-head { padding:16px 20px; border-bottom:1px solid var(--border); display:flex; align-items:center; justify-content:space-between; }
.cl-modal-head h3 { font-size:14px; font-weight:700; color:var(--foreground); margin:0; display:flex; align-items:center; gap:7px; }
.cl-modal-head h3::before { content:''; width:4px; height:4px; border-radius:50%; background:var(--foreground); display:inline-block; flex-shrink:0; }
.cl-modal-search { padding:10px 16px; border-bottom:1px solid var(--border); }
/* :not() pair only for specificity — see the card-control note below. The
   dialog is portaled to <body>, so it can't be reached with .inv-form. */
.cl-modal-search input:not([type="checkbox"]):not([type="radio"]) { width:100%; height:32px; font-size:13px; background:var(--muted); border:1px solid var(--border); border-radius:8px; color:var(--foreground); padding:0 10px; transition:border-color .12s; }
.cl-modal-search input:not([type="checkbox"]):not([type="radio"]):focus { outline:none; box-shadow:none; border-color:var(--ring); }
.cl-modal-body { overflow-y:auto; flex:1; }
.cl-modal-body table { width:100%; border-collapse:collapse; font-size:12px; }
.cl-modal-body th { padding:7px 10px; font-size:12px; font-weight:500; color:var(--muted-foreground); background:var(--muted); border-bottom:1px solid var(--border); position:sticky; top:0; }
.cl-modal-body td { padding:8px 10px; border-bottom:1px solid var(--border); color:var(--foreground); }
.cl-modal-row { cursor:pointer; transition:background .08s; }
.cl-modal-row:hover { background:var(--muted); }
.cl-modal-row.selected { background:color-mix(in srgb, var(--foreground) 8%, transparent); }
.cl-modal-empty { padding:40px; text-align:center; color:var(--muted-foreground); font-size:13px; }
.cl-modal-foot { padding:12px 16px; border-top:1px solid var(--border); display:flex; align-items:center; justify-content:space-between; gap:10px; }
.cl-modal-sel-info { font-size:13px; color:var(--muted-foreground); }
.cl-modal-sel-info strong { color:var(--foreground); }

/* ── Mobile-only redesign to match CL form (flat sections, cards, sticky CTA) ── */
.inv-res-cards, .inv-pay-cards, .inv-mobile-save-wrap { display:none; }
@media (max-width:600px) {
  .inv-info-row { grid-template-columns:1fr !important; }

  .inv-res-desktop, .inv-pay-desktop { display:none; }
  .inv-res-cards, .inv-pay-cards { display:flex; flex-direction:column; gap:12px; }
  .inv-add-mobile { display:inline-flex; margin-top:10px; }

  .inv-summary { display:none; }

  .inv-desktop-actions { display:none; }
  .inv-mobile-save-wrap { display:block; margin-top:20px; }

  /* .page's default 88px isn't enough clearance above the 70px fixed bottom
     nav — match .form-page's 112px so the CTA doesn't sit flush against it. */
  .inv-form.page { padding-bottom: 112px; }
}

/* ── Inside the form modal ────────────────────────────────────────────────
   This form opens as a dialog (~630px of usable width) as well as a full page.
   The narrow layout above is exactly what that needs, but it is gated on a
   VIEWPORT media query — and in a dialog the viewport is still 1440px wide
   while the container is not, so it never fires. The result was the desktop
   grids running at their full fixed widths inside a much narrower box: the
   Customer select crushed to a ~20px sliver, Due Date pushed past the dialog
   edge. Re-apply the same card layout on container terms instead.

   .inv-info-row goes to two columns rather than the mobile one, since 630px
   comfortably fits pairs. .inv-summary and the desktop action row are left
   alone — both already fit, and the dialog's own footer is the action row. */
.hms-modal-body .inv-info-row { grid-template-columns: repeat(2, 1fr) !important; }
.hms-modal-body .inv-res-desktop,
.hms-modal-body .inv-pay-desktop { display: none; }
.hms-modal-body .inv-res-cards,
.hms-modal-body .inv-pay-cards { display: flex; flex-direction: column; gap: 12px; }
.hms-modal-body .inv-add-mobile { display: inline-flex; margin-top: 10px; }

/* ── One row per record, in the dialog too ────────────────────────────────
   The card layout above exists because a record does not fit on one line in
   630px — not because a record wants to be a card. Where the room exists, the
   table is the better answer and it is already built: one row per
   reservation/payment, columns labelled once in the header instead of a
   placeholder per cell.

   So rather than a third layout, the dialog grows to fit the table it already
   has. .inv-tbl-pay is the widest thing on the form at a 910px min-width, and
   the dialog spends 84px on its own chrome before the scroll container starts
   (measured, not derived — body padding plus the panel's), so 1024px leaves
   the table ~30px of slack rather than a horizontal scrollbar. The media query
   is the viewport at which a 1024px dialog still has margin around it. Below
   it nothing changes: the cards keep the narrow case.

   :has() scopes the widening to this form. FormModal's DialogContent is shared
   by all 11 form pages, and the others are two-column layouts that would only
   get more diffuse at this width. */
@media (min-width: 1080px) {
  .form-modal-content:has(.inv-form) { max-width: 1024px; }
  .hms-modal-body .inv-res-desktop,
  .hms-modal-body .inv-pay-desktop { display: block; }
  .hms-modal-body .inv-res-cards,
  .hms-modal-body .inv-pay-cards { display: none; }
}

/* tailwind.css sticks the action row to the dialog's bottom edge via
   '.hms-modal-body .hms-form-actions', but position:sticky resolves against the
   element's CONTAINING BLOCK, not the scroll container alone. Every other form
   hands FormActions straight to FormPanel, so its containing block is the full
   -height panel and it has room to travel. Here it sits inside this wrapper
   (added only so the row can be hidden at <=600px in favour of .inv-mobile-
   save-wrap), which shrink-wraps to exactly the button row's height — zero
   travel, so sticky silently did nothing and Cancel/Save scrolled away.
   display:contents removes the wrapper's own box so the actions become a
   FormPanel flex item like everywhere else, while the element stays in the DOM
   for the mobile rule below. */
.hms-modal-body .inv-desktop-actions { display: contents; }
@media (max-width: 600px) {
  /* Same specificity as the rule above, so this must come after it to win. */
  .hms-modal-body .inv-desktop-actions { display: none; }
}

.inv-form .section-foot { display:flex; align-items:baseline; justify-content:space-between; margin-top:10px; padding-top:10px; border-top:1px solid var(--border); }
.inv-form .section-foot .lbl { font-size:11px; font-weight:500; color:var(--muted-foreground); }
.inv-form .section-foot .val { font-family:var(--font-mono); font-weight:700; font-size:14px; color:var(--foreground); font-variant-numeric:tabular-nums; }
.inv-form .section-foot .val.green { color:var(--green); }
.inv-form .section-foot .val.yellow { color:var(--yellow); }
.inv-form .section-foot .val.red { color:var(--red); }

/* ── Dynamic row cards (narrow layout: phones + this form in a dialog) ─────
   The controls in here are FormFields, so the design system paints them —
   tailwind.css's [data-slot="form-field"] rules give the same 40px height, 2px
   stroke, --radius-control and 14px text as the Invoice Info block above, and
   that is deliberately all that is said about them below. The previous
   .simple-* / .tl-* pass hand-rolled every control as chromeless text on an
   underline, which meant (a) it looked nothing like the rest of the form and
   (b) it had to out-specify design.css:556's global
   \`input:not([type=checkbox]):not([type=radio]), select, textarea\` reset —
   (0,2,1), unlayered — to keep even that. Going through FormField means that
   fight is already won upstream, once, for every form in the app.

   So all that is left here is the frame: the card and its three line layouts.
   The card's radius is control-radius + its own padding, which keeps its
   corners concentric with the field corners inside it rather than guessing. */
.inv-form .inv-res-cards, .inv-form .inv-pay-cards { min-width: 0; }

/* One grid per card, three equal field tracks plus a 40px utility column for
   the row's buttons. Every cell below is placed explicitly rather than left to
   auto-flow: the fields are a fixed vocabulary, so their positions can be too,
   and the reading order stays put instead of reshuffling when one of them
   changes width. Nothing is left half-empty — a reservation is two full rows,
   a payment three. */
.inv-form .inv-row-card {
  background: var(--muted);
  border: 1px solid var(--border);
  border-radius: calc(var(--radius-control) + 12px);
  padding: 12px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr)) 40px;
  gap: 10px; align-items: center; min-width: 0;
}

/* Reservation — who/where, then when, then how much.
   row 1: Res#   | Hotel ………………… | [del]
   row 2: In     | Out    | Total    | */
.inv-form .inv-res-cards .f-res   { grid-area: 1 / 1 / 2 / 2; }
.inv-form .inv-res-cards .f-hotel { grid-area: 1 / 2 / 2 / 4; }
.inv-form .inv-res-cards .f-in    { grid-area: 2 / 1 / 3 / 2; }
.inv-form .inv-res-cards .f-out   { grid-area: 2 / 2 / 3 / 3; }
.inv-form .inv-res-cards .f-total { grid-area: 2 / 3 / 3 / 4; }
.inv-form .inv-res-cards .f-del   { grid-area: 1 / 4 / 2 / 5; }

/* Payment — when/how much/in what, then how/against what/at what rate, then
   the note. Rate sits directly under Currency, which is what it qualifies.
   row 1: Date   | Amount | Currency | [del]
   row 2: Method | Res#   | Rate     |
   row 3: Note ………………………………………… | [proof] */
.inv-form .inv-pay-cards .f-date   { grid-area: 1 / 1 / 2 / 2; }
.inv-form .inv-pay-cards .f-amount { grid-area: 1 / 2 / 2 / 3; }
.inv-form .inv-pay-cards .f-cur    { grid-area: 1 / 3 / 2 / 4; }
.inv-form .inv-pay-cards .f-del    { grid-area: 1 / 4 / 2 / 5; }
.inv-form .inv-pay-cards .f-method { grid-area: 2 / 1 / 3 / 2; }
.inv-form .inv-pay-cards .f-ref    { grid-area: 2 / 2 / 3 / 3; }
.inv-form .inv-pay-cards .f-rate   { grid-area: 2 / 3 / 3 / 4; }
.inv-form .inv-pay-cards .f-note   { grid-area: 3 / 1 / 4 / 4; }
.inv-form .inv-pay-cards .f-proof  { grid-area: 3 / 4 / 4 / 5; }
/* Only rendered when an existing proof is on file, so it takes the utility
   slot beside the note and pushes the upload control up a row. */
.inv-form .inv-pay-cards .f-view   { grid-area: 2 / 4 / 3 / 5; }

.inv-form .f-del { color: var(--muted-foreground); justify-self: center; }
.inv-form .f-del:hover { color: var(--destructive); }
.inv-form .inv-row-card .inv-num { text-align: right; font-variant-numeric: tabular-nums; }
.inv-form .inv-row-card input[readonly] { color: var(--muted-foreground); cursor: default; }

/* A date field wants ~150px before the native picker starts crowding its text,
   which three tracks can't give below roughly this width — the standalone page
   only shows these cards under 600px, so it always lands here, and the dialog
   (~630px of content) keeps the three-track layout. */
@media (max-width: 620px) {
  .inv-form .inv-row-card { grid-template-columns: repeat(2, minmax(0, 1fr)) 40px; }

  .inv-form .inv-res-cards .f-res   { grid-area: 1 / 1 / 2 / 2; }
  .inv-form .inv-res-cards .f-total { grid-area: 1 / 2 / 2 / 3; }
  .inv-form .inv-res-cards .f-del   { grid-area: 1 / 3 / 2 / 4; }
  .inv-form .inv-res-cards .f-hotel { grid-area: 2 / 1 / 3 / 3; }
  .inv-form .inv-res-cards .f-in    { grid-area: 3 / 1 / 4 / 2; }
  .inv-form .inv-res-cards .f-out   { grid-area: 3 / 2 / 4 / 3; }

  .inv-form .inv-pay-cards .f-date   { grid-area: 1 / 1 / 2 / 2; }
  .inv-form .inv-pay-cards .f-amount { grid-area: 1 / 2 / 2 / 3; }
  .inv-form .inv-pay-cards .f-del    { grid-area: 1 / 3 / 2 / 4; }
  .inv-form .inv-pay-cards .f-method { grid-area: 2 / 1 / 3 / 2; }
  .inv-form .inv-pay-cards .f-cur    { grid-area: 2 / 2 / 3 / 3; }
  .inv-form .inv-pay-cards .f-ref    { grid-area: 3 / 1 / 4 / 2; }
  .inv-form .inv-pay-cards .f-rate   { grid-area: 3 / 2 / 4 / 3; }
  .inv-form .inv-pay-cards .f-note   { grid-area: 4 / 1 / 5 / 3; }
  .inv-form .inv-pay-cards .f-proof  { grid-area: 4 / 3 / 5 / 4; }
  .inv-form .inv-pay-cards .f-view   { grid-area: 3 / 3 / 4 / 4; }
}

/* Phones. Two tracks minus the utility column leaves ~116px a field, and a
   date control needs about 135 before "dd/mm/yyyy" and its picker start
   overlapping — measured, not guessed. So dates get a full row here and the
   remaining pairs tighten their side padding to buy back the difference. */
@media (max-width: 450px) {
  .inv-form .inv-row-card [data-slot="form-field"] input,
  .inv-form .inv-row-card [data-slot="form-field"] select { padding-inline: 10px; }

  .inv-form .inv-res-cards .f-res   { grid-area: 1 / 1 / 2 / 2; }
  .inv-form .inv-res-cards .f-total { grid-area: 1 / 2 / 2 / 3; }
  .inv-form .inv-res-cards .f-del   { grid-area: 1 / 3 / 2 / 4; }
  .inv-form .inv-res-cards .f-hotel { grid-area: 2 / 1 / 3 / 3; }
  .inv-form .inv-res-cards .f-in    { grid-area: 3 / 1 / 4 / 3; }
  .inv-form .inv-res-cards .f-out   { grid-area: 4 / 1 / 5 / 3; }

  .inv-form .inv-pay-cards .f-date   { grid-area: 1 / 1 / 2 / 3; }
  .inv-form .inv-pay-cards .f-del    { grid-area: 1 / 3 / 2 / 4; }
  .inv-form .inv-pay-cards .f-amount { grid-area: 2 / 1 / 3 / 2; }
  .inv-form .inv-pay-cards .f-cur    { grid-area: 2 / 2 / 3 / 3; }
  .inv-form .inv-pay-cards .f-proof  { grid-area: 2 / 3 / 3 / 4; }
  .inv-form .inv-pay-cards .f-method { grid-area: 3 / 1 / 4 / 2; }
  .inv-form .inv-pay-cards .f-ref    { grid-area: 3 / 2 / 4 / 3; }
  .inv-form .inv-pay-cards .f-view   { grid-area: 3 / 3 / 4 / 4; }
  .inv-form .inv-pay-cards .f-rate   { grid-area: 4 / 1 / 5 / 2; }
  .inv-form .inv-pay-cards .f-note   { grid-area: 4 / 2 / 5 / 3; }
  /* At SAR the rate is forced to 1 and can't be edited, so on a phone it is
     only taking room from the note. Elsewhere it stays put — there the row it
     sits in exists either way. !important because FormField sets display:flex
     as an inline style, which no stylesheet rule can outrank without it. */
  .inv-form .inv-pay-cards .inv-row-card[data-cur="SAR"] .f-rate { display: none !important; }
  .inv-form .inv-pay-cards .inv-row-card[data-cur="SAR"] .f-note { grid-area: 4 / 1 / 5 / 3; }
}

/* ── Payments timeline ──
   Kept from the previous layout: a payment list is a sequence of events, and
   the rail is the one thing on this form that says so. It sits outside the
   cards, so it costs nothing the fields need. */
.inv-form .tl-list { position: relative; padding-left: 22px; display: flex; flex-direction: column; gap: 12px; }
.inv-form .tl-list::before {
  content: ''; position: absolute; left: 5px; top: 12px; bottom: 12px;
  width: 1px; background: var(--border);
}
.inv-form .tl-item { position: relative; min-width: 0; }
/* 12px card padding + half a 40px field = the first row's optical centre. */
.inv-form .tl-dot {
  position: absolute; left: -22px; top: 26px;
  width: 11px; height: 11px; border-radius: 50%;
  background: var(--card); border: 2px solid var(--foreground);
}

/* Proof has no native control shaped like a field, so its trigger is built to
   the same spec by hand — the same thing tailwind.css's
   [data-slot="select-trigger"] rule does, for the same reason. */
.inv-form .inv-proof-box {
  position: relative; overflow: hidden; flex: 0 0 auto;
  display: inline-flex; align-items: center; justify-content: center;
  width: 40px; height: 40px;
  background: var(--card); border: 2px solid var(--border);
  border-radius: var(--radius-control);
  color: var(--muted-foreground); cursor: pointer; text-decoration: none;
  transition: border-color .14s ease, color .14s ease;
}
.inv-form .inv-proof-box:hover, .inv-form .inv-proof-box:focus-within { border-color: var(--ring); color: var(--foreground); }
.inv-form .inv-proof-box[data-has-file="true"] { border-color: var(--foreground); color: var(--foreground); }
.inv-form .sr-only {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
}

/* Typed, never stepped — and the spinner reserves width the money fields in a
   two-column card don't have to spare. */
.inv-form .inv-row-card input[type="number"]::-webkit-outer-spin-button,
.inv-form .inv-row-card input[type="number"]::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.inv-form .inv-row-card input[type="number"] { -moz-appearance: textfield; }
`;
