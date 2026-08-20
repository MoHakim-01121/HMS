import { useMemo, useState } from "react";
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

const CardField = ({ name, cell, children }) => (
  <FormField name={name} className={cell}>{children}</FormField>
);

const RemoveButton = ({ onClick, label }) => (
  <Button type="button" variant="ghost" size="icon-sm" className="f-del" onClick={onClick} aria-label={label}>
    <Icon name="trash" size={13} />
  </Button>
);

const fmt = (n) => Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 0 });

const blankRes = () => ({ reservation_number: "", hotel: "", check_in: "", check_out: "", reservation_total: "" });

function seedFrom(src) {
  if (!src) return { reservations: [blankRes()], linkedClIds: [] };
  const reservations = (src.reservations || []).map((r) => ({
    reservation_number: r.reservation_number || "", hotel: r.hotel || "",
    check_in: r.check_in || "", check_out: r.check_out || "",
    reservation_total: r.reservation_total ?? "",
  }));
  return {
    reservations: reservations.length ? reservations : [blankRes()],
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

  const resOptions = reservations.map((r) => (r.reservation_number || "").trim()).filter(Boolean);

  const totalRes = useMemo(() => reservations.reduce((a, r) => a + (parseFloat(r.reservation_total) || 0), 0), [reservations]);

  // ── CL Import ──
  const filteredCls = useMemo(() => {
    const f = search.toLowerCase();
    return cl_data.filter((cl) => !f || cl.ref.toLowerCase().includes(f) || cl.guest.toLowerCase().includes(f) || cl.hotel.toLowerCase().includes(f));
  }, [search, cl_data]);
  const fmtDate = (d) => (d ? d.split("-").reverse().join("/") : "—");
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
    const fromCl = new Set(cl_data.filter((cl) => linkedClIds.includes(cl.id)).map((cl) => cl.ref));
    const present = new Set(reservations.map((r) => (r.reservation_number || "").trim()));

    const kept = reservations.filter((r) => {
      const ref = (r.reservation_number || "").trim();
      if (!ref && !(parseFloat(r.reservation_total) || 0)) return false;
      return fromCl.has(ref) ? wanted.has(ref) : true;
    });
    const added = cls.filter((cl) => !present.has(cl.ref)).map((cl) => ({
      reservation_number: cl.ref, hotel: cl.hotel, check_in: cl.check_in || "",
      check_out: cl.check_out || "", reservation_total: cl.total || "",
    }));

    const next = [...kept, ...added];
    setReservations(next.length ? next : [blankRes()]);
    setLinkedClIds(cls.map((cl) => cl.id));
    // Auto-select client if all imported CLs share the same client
    if (!clientId) {
      const clientIds = [...new Set(cls.map((cl) => cl.client_id).filter(Boolean))];
      if (clientIds.length === 1) {
        const cid = clientIds[0];
        const client = clients.find((c) => String(c.id) === String(cid));
        if (client) {
          setClientId(String(client.id));
          setClientQuery(client.name);
          setCustomerName(client.name);
        }
      } else if (clientIds.length === 0) {
        const guestNames = [...new Set(cls.map((cl) => cl.guest))];
        if (guestNames.length === 1) setCustomerName(guestNames[0]);
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
    form.transform(() => ({
      client_id: clientId, customer_name: customerName, invoice_number: invoiceNumber,
      issued_date: issuedDate, due_date: dueDate,
      reservations: JSON.stringify(resRows.map((r) => ({
        reservation_number: r.reservation_number, hotel: r.hotel,
        check_in: r.check_in, check_out: r.check_out,
        reservation_total: parseFloat(r.reservation_total) || 0,
      }))),
      linked_cl_ids: JSON.stringify(linkedClIds),
    }));
    const url = edit ? `/invoice/${src.pk}/edit/` : "/invoice/new/";
    form.post(url);
  };

  return (
    <div className="page inv-form shadcn-root">
      <style>{CSS}</style>
      <PageBack href="/invoice/" label={t("Back")} />
      <FormHeader
        kicker={t("Invoice Hotel")}
        title={edit ? t("Edit Invoice — {number}", { number: src?.invoice_number || "" }) : t("Invoice Hotel")}
        sub={t("Hotel reservations")}
      />

      <form method="post" onSubmit={submit}>
        <FormPanel>
          {/* ── Info ── */}
          <FormSection label={t("Invoice Info")}>
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
              <div className="section-foot"><span className="lbl">{t("Total")}</span><span className="val">{fmt(totalRes)} SAR</span></div>
            </div>
          </FormSection>

          {/* ── Summary ── */}
          <div className="inv-summary">
            <div className="inv-summary-cell"><div className="lbl">{t("Total Reservations")}</div><div className="val">{fmt(totalRes)} SAR</div></div>
            <div className="inv-summary-cell"><div className="lbl">{t("Payments")}</div><div className="val green">{t("Record via Finance")}</div></div>
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
.inv-summary { display:grid; grid-template-columns:1fr 1fr; border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; background:var(--muted); }
.inv-summary-cell { padding:14px 22px; border-right:1px solid var(--border); }
.inv-summary-cell:last-child { border-right:none; }
.inv-summary-cell .lbl { font-size:11px; font-weight:600; color:var(--muted-foreground); margin-bottom:6px; }
.inv-summary-cell .val { font-family:var(--font-mono); font-size:18px; font-weight:700; color:var(--foreground); font-variant-numeric:tabular-nums; }
.inv-summary-cell .val.green { color:var(--green); }
@media(max-width:640px) { .inv-summary { grid-template-columns:1fr; } .inv-summary-cell { border-right:none; border-bottom:1px solid var(--border); } .inv-summary-cell:last-child { border-bottom:none; } }
@media(max-width:900px) { .inv-info-row { grid-template-columns: 110px 1fr 160px !important; } }

.inv-form .inv-tbl-wrap {
  border: 1px solid var(--border);
  border-radius: var(--radius-control, 16px);
  background: var(--card);
  overflow: hidden;
}
.inv-form .inv-tbl-scroll { overflow-x: auto; }
.inv-form .inv-tbl { width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 0; }
.inv-form .inv-tbl-res { min-width: 700px; }

.inv-form .inv-tbl thead th {
  padding: 0 10px; height: 38px;
  font-size: 12px; font-weight: 500; line-height: 38px;
  color: var(--muted-foreground); text-align: left; white-space: nowrap;
  background: var(--muted); border-bottom: 1px solid var(--border);
  text-transform: none; letter-spacing: normal;
}
.inv-form .inv-tbl thead th.r { text-align: right; }
.inv-form .inv-tbl thead th + th { border-left: 1px solid var(--border); }

.inv-form .inv-tbl tbody tr { animation: none; }
.inv-form .inv-tbl tbody td {
  padding: 0; height: 40px;
  border-bottom: 1px solid var(--border);
  background: transparent; vertical-align: middle;
}
.inv-form .inv-tbl tbody td + td { border-left: 1px solid var(--border); }
.inv-form .inv-tbl tbody tr:last-child td { border-bottom: 1px solid var(--border); }
.inv-form .inv-tbl tbody tr:hover td { background: color-mix(in oklch, var(--muted) 45%, transparent); }
.inv-form .inv-tbl tbody tr:hover td:first-child,
.inv-form .inv-tbl tbody tr:hover td:last-child { border-radius: 0; }

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
.inv-form .inv-tbl .c-in[type="date"]::-webkit-calendar-picker-indicator { opacity: .5; cursor: pointer; }
.inv-form .inv-tbl .c-in[type="date"]:hover::-webkit-calendar-picker-indicator { opacity: 1; }
.inv-form .inv-tbl .c-in[type="number"]::-webkit-outer-spin-button,
.inv-form .inv-tbl .c-in[type="number"]::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.inv-form .inv-tbl .c-in[type="number"] { -moz-appearance: textfield; }

.inv-form .inv-tbl .c-act { text-align: center; }

.inv-form .inv-row-del {
  display: inline-flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; border-radius: 8px; border: none; padding: 0;
  background: transparent; color: var(--muted-foreground);
  cursor: pointer; opacity: .45; transition: opacity .12s, background .12s, color .12s;
}
.inv-form .inv-tbl tbody tr:hover .inv-row-del { opacity: 1; }
.inv-form .inv-row-del:hover { background: var(--destructive); color: var(--destructive-foreground); opacity: 1; }
.inv-form .inv-row-del:focus-visible { opacity: 1; outline: 2px solid var(--ring); outline-offset: 1px; }

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

.inv-res-cards, .inv-mobile-save-wrap { display:none; }
@media (max-width:600px) {
  .inv-info-row { grid-template-columns:1fr !important; }
  .inv-res-desktop { display:none; }
  .inv-res-cards { display:flex; flex-direction:column; gap:12px; }
  .inv-add-mobile { display:inline-flex; margin-top:10px; }
  .inv-summary { display:none; }
  .inv-desktop-actions { display:none; }
  .inv-mobile-save-wrap { display:block; margin-top:20px; }
  .inv-form.page { padding-bottom: 112px; }
}

.hms-modal-body .inv-info-row { grid-template-columns: repeat(2, 1fr) !important; }
.hms-modal-body .inv-res-desktop { display: none; }
.hms-modal-body .inv-res-cards { display: flex; flex-direction: column; gap: 12px; }
.hms-modal-body .inv-add-mobile { display: inline-flex; margin-top: 10px; }

@media (min-width: 1080px) {
  .form-modal-content:has(.inv-form) { max-width: 1024px; }
  .hms-modal-body .inv-res-desktop { display: block; }
  .hms-modal-body .inv-res-cards { display: none; }
}

.hms-modal-body .inv-desktop-actions { display: contents; }
@media (max-width: 600px) {
  .hms-modal-body .inv-desktop-actions { display: none; }
}

.inv-form .section-foot { display:flex; align-items:baseline; justify-content:space-between; margin-top:10px; padding-top:10px; border-top:1px solid var(--border); }
.inv-form .section-foot .lbl { font-size:11px; font-weight:500; color:var(--muted-foreground); }
.inv-form .section-foot .val { font-family:var(--font-mono); font-weight:700; font-size:14px; color:var(--foreground); font-variant-numeric:tabular-nums; }

.inv-form .inv-row-card {
  display: grid; gap: 8px; padding: 12px 14px;
  border: 1px solid var(--border); border-radius: var(--radius-control, 16px);
  background: var(--card);
}
@media (max-width:600px) {
  .inv-row-card { grid-template-columns: 1fr 1fr; }
  .inv-row-card .f-res { grid-column: 1 / -1; }
  .inv-row-card .f-hotel { grid-column: 1 / -1; }
}
.btn-add-row {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 6px 12px; border-radius: 8px; border: 1px dashed var(--border);
  background: transparent; font-size: 12.5px; font-weight: 500;
  color: var(--muted-foreground); cursor: pointer; transition: all .12s;
}
.btn-add-row:hover { background: var(--muted); color: var(--foreground); border-color: var(--foreground); }
`;
