import { useContext, useMemo, useState } from "react";
import { useForm } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { FormModalContext, StandaloneFormModal } from "../../components/shadcn/form-modal.jsx";
import Combobox from "../../components/shadcn/combobox.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/shadcn/ui/select.jsx";
import { Dialog, DialogContent } from "../../components/shadcn/ui/dialog.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtDateShort } from "../../utils/format.js";

const TERMS = [["", "On receipt"], [7, "Net 7"], [14, "Net 14"], [30, "Net 30"]];
const addDays = (iso, days) => {
  const d = new Date(iso);
  if (Number.isNaN(+d) || !days) return iso;
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
};

const dShort = (iso) => fmtDateShort(iso) || "—";
const nightsOf = (a, b) => {
  const n = (new Date(b) - new Date(a)) / 86400000;
  return n > 0 ? n : 0;
};

export default function Form({ invoice, edit, suggested_number, cl_data = [], clients = [], branch_choices = [], initial, errors = {} }) {
  const { t } = useI18n();
  const src = initial || invoice;
  const initialClient = clients.find((c) => String(c.id) === String(src?.client_id)) || null;
  const [clientId, setClientId] = useState(src?.client_id || "");
  const [clientQuery, setClientQuery] = useState(initialClient ? initialClient.name : "");
  const [customerName, setCustomerName] = useState(src?.customer_name || "");
  const [invoiceNumber, setInvoiceNumber] = useState(src?.invoice_number || (edit ? "" : suggested_number) || "");
  const [issuedDate, setIssuedDate] = useState(src?.issued_date || "");
  const [dueDate, setDueDate] = useState(src?.due_date || "");
  // Issuing branch — picks the "Pay to" bank accounts. "auto" lets the server
  // take it from the CLs' reservations (fallback: the default branch).
  const [branch, setBranch] = useState(src?.branch || "auto");
  const [term, setTerm] = useState(null);

  // ── Reservations: an invoice bills confirmation letters. It can only be built
  //    from existing CLs that are not already on another invoice — there is no
  //    manual reservation entry. The searchable pick-list lives in a dialog. ──
  const seededIds = useMemo(() => (src?.linked_cl_ids || []).slice(), []);
  const ownClIds = useMemo(() => new Set(seededIds), [seededIds]);
  const [selectedClIds, setSelectedClIds] = useState(seededIds);

  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerSearch, setPickerSearch] = useState("");
  const [pickerSel, setPickerSel] = useState(() => new Set(seededIds));

  const form = useForm({});
  const errs = { ...errors, ...form.errors };

  // A CL is billable here only if it is not on another invoice (or it is
  // already on this one, when editing).
  const availableCls = useMemo(
    () => cl_data.filter((c) => !c.inv || ownClIds.has(c.id)),
    [cl_data, ownClIds],
  );
  const pickerList = useMemo(() => {
    const f = pickerSearch.trim().toLowerCase();
    return availableCls.filter((c) => !f
      || c.ref.toLowerCase().includes(f)
      || (c.hotel || "").toLowerCase().includes(f)
      || (c.guest || "").toLowerCase().includes(f));
  }, [availableCls, pickerSearch]);
  const selectedCls = useMemo(() => cl_data.filter((c) => selectedClIds.includes(c.id)), [cl_data, selectedClIds]);
  const totalRes = selectedCls.reduce((a, c) => a + (c.total || 0), 0);

  // ── Read-only payment figures — payments are recorded through the Payment
  //    module, not this form. On edit the server hands over the journal-derived
  //    totals; on a new invoice nothing is paid yet.
  const payments = src?.payments || [];
  const paidSar = edit ? (src?.paid_sar ?? 0) : 0;
  const dueOnIssue = Math.max(0, totalRes - paidSar);
  const paidPct = totalRes > 0 ? Math.min(100, Math.round((paidSar / totalRes) * 100)) : 0;
  const fxRow = payments.find((p) => p.currency && p.currency !== "SAR");

  const applyTerm = (days) => {
    setTerm(days === "" ? "" : days);
    if (issuedDate && days) setDueDate(addDays(issuedDate, days));
  };
  const onIssuedDate = (v) => {
    setIssuedDate(v);
    if (term) setDueDate(addDays(v, term));
  };

  const openPicker = () => { setPickerSel(new Set(selectedClIds)); setPickerSearch(""); setPickerOpen(true); };
  const togglePick = (id) => setPickerSel((s) => {
    const n = new Set(s);
    if (n.has(id)) n.delete(id); else n.add(id);
    return n;
  });
  const confirmPicker = () => {
    const ids = [...pickerSel];
    setSelectedClIds(ids);
    if (!clientId) {
      const cls = cl_data.filter((c) => ids.includes(c.id));
      const cids = [...new Set(cls.map((c) => c.client_id).filter(Boolean))];
      if (cids.length === 1) {
        const client = clients.find((c) => String(c.id) === String(cids[0]));
        if (client) { setClientId(String(client.id)); setClientQuery(client.name); setCustomerName(client.name); }
      } else if (cids.length === 0 && !customerName.trim()) {
        const guests = [...new Set(cls.map((c) => c.guest).filter(Boolean))];
        if (guests.length === 1) setCustomerName(guests[0]);
      }
    }
    setPickerOpen(false);
  };
  const removeCl = (id) => setSelectedClIds((prev) => prev.filter((x) => x !== id));

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
    if (selectedClIds.length === 0) {
      form.setError("reservations", t("Pick at least one confirmation letter to bill."));
      return;
    }
    const clRows = selectedCls.map((c) => ({
      reservation_number: c.ref, hotel: c.hotel,
      check_in: c.check_in, check_out: c.check_out,
      reservation_total: c.total || 0,
    }));
    form.transform(() => ({
      client_id: clientId, customer_name: customerName, invoice_number: invoiceNumber,
      issued_date: issuedDate, due_date: dueDate,
      branch: branch === "auto" ? "" : branch,
      reservations: JSON.stringify(clRows),
      linked_cl_ids: JSON.stringify(selectedClIds),
    }));
    const url = edit ? `/invoice/${src.pk}/edit/` : "/invoice/new/";
    form.post(url, { forceFormData: true });
  };

  const resCount = selectedCls.length;
  const checklist = [
    { ok: !!clientId || !!customerName.trim(), label: t("Client filled") },
    { ok: !!invoiceNumber.trim(), label: t("Invoice number set") },
    { ok: !!issuedDate && !!dueDate, label: t("Issue & due dates set") },
    { ok: resCount > 0, label: t("At least one confirmation letter selected") },
  ];

  const submitLabel = form.processing ? t("Saving…") : edit ? t("Update & Save") : t("Issue invoice");

  const inModal = useContext(FormModalContext)?.inModal;
  const closeHref = edit ? `/invoice/${src.pk}/` : "/invoice/";

  const page = (
    <div className="page inv-form shadcn-root">
      <style>{CSS}</style>
      <PageBack href="/invoice/" label={t("Back")} />
      <FormHeader
        kicker={t("Invoice Hotel")}
        title={edit ? t("Edit Invoice — {number}", { number: src?.invoice_number || "" }) : t("New hotel invoice")}
        sub={t("Number is issued when the invoice is issued")}
      />

      <form method="post" onSubmit={submit}>
       <div className="rd-card">
        <div className="rd-body">
          <div className="rd-main">

            {/* ── Client & terms ── */}
            <section className="rd-sec">
              <div className="rd-sec-h">
                <span className="rd-sec-title">{t("Client & terms")}</span>
                <span className="rd-sec-desc">{t("Due date is computed from the issue date plus the term.")}</span>
              </div>
              <div className="rd-sec-b">
                <FormField label={t("Bill to")} name="client_id">
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
                {branch_choices.length ? (
                  <FormField label={t("Branch")} name="branch"
                    hint={t("Decides which bank accounts appear under “Pay to”.")}>
                    <Select value={branch} onValueChange={setBranch}>
                      <SelectTrigger id="branch" className="w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="auto">{t("Automatic (from the confirmation letters)")}</SelectItem>
                        {branch_choices.map((b) => <SelectItem key={b.value} value={b.value}>{b.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </FormField>
                ) : null}
                <div className="rd-row3">
                  <FormField label={t("Invoice Number")} name="invoice_number" required
                    value={invoiceNumber} onChange={setInvoiceNumber} placeholder="INV-001"
                    error={errs.invoice_number} />
                  <FormField label={t("Issued Date")} name="issued_date">
                    <Input id="issued_date" name="issued_date" type="date" required value={issuedDate} onChange={(e) => onIssuedDate(e.target.value)} />
                  </FormField>
                  <FormField label={t("Due Date")} name="due_date">
                    <Input id="due_date" name="due_date" type="date" required value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
                  </FormField>
                </div>
                <FormField label={t("Payment terms")} name="terms">
                  <div className="rd-seg" role="radiogroup" aria-label={t("Payment terms")}>
                    {TERMS.map(([days, label]) => (
                      <button
                        type="button" key={label} role="radio"
                        aria-checked={term === days}
                        className={"rd-seg-opt" + (term === days ? " is-on" : "")}
                        onClick={() => applyTerm(days)}
                      >
                        {t(label)}
                      </button>
                    ))}
                  </div>
                </FormField>
              </div>
            </section>

            {/* ── Reservations ── an invoice bills existing confirmation letters */}
            <section className="rd-sec">
              <div className="rd-sec-h">
                <span className="rd-sec-title">{t("Reservations")}</span>
                <span className="rd-sec-desc">{t("An invoice bills confirmation letters that are not yet on another invoice.")}</span>
              </div>
              <div className="rd-sec-b">
                {selectedCls.length === 0 ? (
                  availableCls.length === 0 ? (
                    <div className="rd-empty">{t("No confirmation letter available — create a CL first.")}</div>
                  ) : (
                    <button type="button" className="rd-res-empty" onClick={openPicker}>
                      <Icon name="search" size={15} />
                      {t("Search & import confirmation letters")}
                    </button>
                  )
                ) : (
                  <div className="rd-res-list">
                    {selectedCls.map((cl) => {
                      const n = nightsOf(cl.check_in, cl.check_out);
                      return (
                        <div className="rd-res-row" key={cl.id}>
                          <div className="rd-res-info">
                            <span className="rd-res-t">{cl.hotel}<span className="rd-res-badge">{cl.ref}</span></span>
                            <span className="rd-res-sub">
                              {cl.check_in ? `${dShort(cl.check_in)} → ${dShort(cl.check_out)} · ${n} ${t(n === 1 ? "night" : "nights")}` : t("dates TBC")}
                              {cl.guest ? ` · ${cl.guest}` : ""}
                            </span>
                          </div>
                          <span className="rd-res-amt">{fmt(cl.total || 0)}</span>
                          <button type="button" className="rd-res-x" onClick={() => removeCl(cl.id)} aria-label={t("Remove")}>
                            <Icon name="close" size={13} />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}

                {errs.reservations && (
                  <div role="alert" style={{ fontSize: 12, color: "var(--destructive)" }}>{errs.reservations}</div>
                )}

                {availableCls.length > 0 && (
                  <div className="rd-pick-foot">
                    <button type="button" className="rd-link" onClick={openPicker}>
                      <Icon name="search" size={12} /> {selectedCls.length ? t("Edit selection") : t("Search confirmation letters")}
                    </button>
                    <span className="rd-pick-foot-sum">
                      {resCount} {t(resCount === 1 ? "reservation" : "reservations")} · <span className="rd-num">{fmt(totalRes)} SAR</span>
                    </span>
                  </div>
                )}
              </div>
            </section>

            {/* ── Payments (read-only) ── */}
            {edit && (
              <section className="rd-sec rd-sec-last">
                <div className="rd-sec-h">
                  <span className="rd-sec-title">{t("Payments received")}</span>
                  <span className="rd-sec-desc">{t("Recorded in the Payment module — read-only here.")}</span>
                  <a className="rd-link" href="/payment/">{t("Open Payments")}</a>
                </div>
                <div className="rd-sec-b">
                  {payments.length === 0 ? (
                    <div className="rd-empty">{t("No payments recorded yet.")}</div>
                  ) : (
                    <div className="rd-pay-list">
                      {payments.map((p, i) => (
                        <div className="rd-pay-row" key={i}>
                          <div className="rd-pay-main">
                            <span className="rd-pay-method">{p.method || t("Payment")}</span>
                            <span className="rd-pay-sub">{p.date ? p.date.split("-").reverse().join("/") : "—"}{p.ref ? ` · ${p.ref}` : ""}</span>
                          </div>
                          <div className="rd-pay-amt">
                            <span className="rd-num">{fmt(p.amount_sar)} <span className="cur">SAR</span></span>
                            {p.currency && p.currency !== "SAR" && (
                              <span className="rd-pay-fx">{fmt(p.amount)} {p.currency} @ {p.exchange}</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </section>
            )}
          </div>

          {/* ── Summary rail ── */}
          <aside className="rd-rail">
            <div className="rd-summary">
              <div className="rd-rail-block">
                <span className="rd-rail-lbl">{t("Amount due on issue")}</span>
                <div className={"rd-rail-total" + (dueOnIssue > 0 ? " is-due" : "")}>
                  <span>{fmt(dueOnIssue)}</span><span className="rd-rail-cur">SAR</span>
                </div>
                <div className="rd-bar">
                  <span style={{ flex: Math.max(paidPct, 0.001), background: "var(--green)" }} />
                  <span style={{ flex: Math.max(100 - paidPct, 0.001), background: "color-mix(in srgb, var(--red) 22%, transparent)" }} />
                </div>
                <span className="rd-rail-meta">{fmt(paidSar)} {t("of")} {fmt(totalRes)} SAR {t("paid")}{dueDate ? ` · ${t("due")} ${dueDate.split("-").reverse().join("/")}` : ""}</span>
              </div>

              <div className="rd-mix">
                <div className="rd-mix-row"><span>{t("Reservations")} ({resCount})</span><span className="rd-num">{fmt(totalRes)}</span></div>
                <div className="rd-mix-row"><span>{t("Payments")} ({payments.length})</span><span className="rd-num" style={{ color: "var(--green)" }}>{fmt(paidSar)}</span></div>
                {fxRow && (
                  <div className="rd-mix-row"><span>{t("FX")} {fxRow.currency} → SAR</span><span className="rd-num">{fxRow.exchange}</span></div>
                )}
                <div className="rd-mix-row rd-mix-total"><span>{t("Outstanding")}</span><span className="rd-num" style={{ color: dueOnIssue > 0 ? "var(--red)" : undefined }}>{fmt(dueOnIssue)}</span></div>
              </div>

              <div className="rd-rail-sep" />

              <div className="rd-rail-block">
                <span className="rd-rail-lbl">{t("Before issuing")}</span>
                {checklist.map((it) => (
                  <div className={"rd-check" + (it.ok ? " is-ok" : "")} key={it.label}>
                    <Icon name={it.ok ? "check" : "clock"} size={15} />{it.label}
                  </div>
                ))}
              </div>
            </div>

            <div className="rd-rail-spacer" />
            <div className="rd-rail-actions">
              <button type="submit" className="rd-cta" disabled={form.processing}>
                <Icon name="invoice" size={14} />{submitLabel}
              </button>
              {edit && (
                <a className="rd-cta-ghost" href={`/invoice/${src.pk}/pdf/`} target="_blank" rel="noreferrer">{t("Preview PDF")}</a>
              )}
            </div>
          </aside>
        </div>
       </div>
      </form>

      {/* ── Reservation search & import dialog ── */}
      <Dialog open={pickerOpen} onOpenChange={setPickerOpen}>
        <DialogContent className="form-modal-content rd-pick-dlg" showCloseButton={false}>
          <div className="hms-modal-head">
            <div style={{ minWidth: 0 }}>
              <div className="hms-modal-title">{t("Import reservations")}</div>
              <div className="hms-modal-sub">{t("Pick the uninvoiced confirmation letters to bill here")}</div>
            </div>
            <button type="button" className="rd-pick-dlg-x" onClick={() => setPickerOpen(false)} aria-label={t("Close")}>
              <Icon name="close" size={16} />
            </button>
          </div>
          <div className="rd-pick-dlg-search">
            <Icon name="search" size={15} />
            <input type="text" autoComplete="off" autoFocus value={pickerSearch}
              onChange={(e) => setPickerSearch(e.target.value)}
              placeholder={t("Search CL number, hotel, or guest")} />
          </div>
          <div className="rd-pick-dlg-body">
            {pickerList.length === 0 ? (
              <div className="rd-pick-dlg-empty">{availableCls.length === 0 ? t("No uninvoiced confirmation letters.") : t("No matching CL.")}</div>
            ) : pickerList.map((cl) => {
              const on = pickerSel.has(cl.id);
              const n = nightsOf(cl.check_in, cl.check_out);
              return (
                <button type="button" key={cl.id} className={"rd-pick" + (on ? " is-on" : "")}
                  aria-pressed={on} onClick={() => togglePick(cl.id)}>
                  <span className="rd-pick-box">{on && <Icon name="check" size={12} />}</span>
                  <span className="rd-pick-body">
                    <span className="rd-pick-t">{cl.hotel}<span className="rd-pick-badge">{cl.ref}</span></span>
                    <span className="rd-pick-sub">
                      {cl.check_in ? `${dShort(cl.check_in)} → ${dShort(cl.check_out)} · ${n} ${t(n === 1 ? "night" : "nights")}` : t("dates TBC")}
                      {cl.guest ? ` · ${cl.guest}` : ""}
                    </span>
                  </span>
                  <span className="rd-pick-amt">{fmt(cl.total || 0)}</span>
                </button>
              );
            })}
          </div>
          <div className="rd-pick-dlg-foot">
            <span>{pickerSel.size} {t("selected")}</span>
            <div style={{ display: "flex", gap: 8 }}>
              <Button type="button" variant="ghost" size="sm" onClick={() => setPickerOpen(false)}>{t("Cancel")}</Button>
              <Button type="button" size="sm" onClick={confirmPicker}>{t("Done")}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );

  return inModal ? page : <StandaloneFormModal closeHref={closeHref}>{page}</StandaloneFormModal>;
}

/* ── Layout ───────────────────────────────────────────────────────────────
   Two-pane redesign (Claude Design "HOMLU HMS Redesign" §5c/5d): a main
   column of label-left / field-right sections and a 300px summary rail that
   carries amount-due / outstanding, a paid bar, a readiness checklist and the
   submit CTA. Payments are NOT entered here — they are recorded through the
   Payment module and the ledger is the system of record; on edit the section
   below lists what has been posted, read-only. Above 1100px viewport the
   form-modal widens to hold both panes; under that the rail drops beneath the
   main column and the sections collapse to one stack.  */
const CSS = `
@media (min-width: 1100px) {
  .form-modal-content:has(.inv-form) { max-width: 1180px; }
}

/* The form body is one rounded card (design §5c): a main column of
   label-left / field-right sections and a flush 300px summary rail. The card's
   overflow:hidden clips the rail's border-left into the rounded corner. */
.inv-form form { margin-top: 22px; }
.hms-modal-body .inv-form form { margin-top: 0; }

.inv-form .rd-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-card, 22px);
  background: var(--card);
  overflow: visible;
  box-shadow: 0 1px 2px rgba(0,0,0,.04), 0 12px 40px -12px color-mix(in oklch, var(--primary) 16%, transparent);
}
/* In the modal the dialog itself is the card. */
.hms-modal-body .inv-form .rd-card {
  border: none; border-radius: 0; box-shadow: none;
  margin: -24px -20px;
}
@media (max-width: 600px) {
  .hms-modal-body .inv-form .rd-card { margin: -20px -16px; }
}

.inv-form .rd-body { display: flex; align-items: stretch; }
.inv-form .rd-main { flex: 1; min-width: 0; }
.inv-form .rd-rail {
  width: 300px; flex: none;
  border-left: 1px solid var(--border);
  background: color-mix(in oklch, var(--muted) 38%, var(--card));
  display: flex; flex-direction: column;
}
.inv-form .rd-summary {
  position: sticky; top: 0;
  display: flex; flex-direction: column; gap: 22px;
  padding: 28px 24px;
}

.inv-form .rd-sec {
  display: grid; grid-template-columns: 168px minmax(0, 1fr); gap: 28px;
  padding: 26px 30px;
  border-bottom: 1px solid var(--border);
}
.inv-form .rd-sec-last { border-bottom: none; }
.inv-form .rd-sec-h { display: flex; flex-direction: column; gap: 5px; }
.inv-form .rd-sec-title { font-size: 13px; font-weight: 600; color: var(--foreground); }
.inv-form .rd-sec-desc { font-size: 11.5px; line-height: 1.5; color: var(--muted-foreground); }
.inv-form .rd-sec-b { display: flex; flex-direction: column; gap: 14px; min-width: 0; }

.inv-form .rd-row3 { display: grid; grid-template-columns: minmax(150px, 1.5fr) 1fr 1fr; gap: 12px; }

.inv-form .rd-sec-b [data-slot="form-field"] label {
  font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
  color: var(--muted-foreground);
}

.inv-form .rd-link {
  display: inline-flex; align-items: center; gap: 5px; margin-top: 4px;
  background: none; border: none; padding: 0;
  font: inherit; font-size: 12px; font-weight: 600; color: var(--primary);
  cursor: pointer; text-decoration: none; width: fit-content;
}
.inv-form .rd-link:hover { color: var(--primary-hover); }

.inv-form .rd-seg {
  display: inline-flex; gap: 3px; padding: 3px; width: fit-content;
  border: 1px solid var(--border); border-radius: 999px;
  background: color-mix(in oklch, var(--muted) 50%, transparent);
}
.inv-form .rd-seg-opt {
  padding: 6px 14px; border: none; border-radius: 999px; background: transparent;
  font: inherit; font-size: 12px; font-weight: 500; color: var(--muted-foreground);
  cursor: pointer; transition: background .12s, color .12s;
}
.inv-form .rd-seg-opt.is-on {
  background: var(--card); color: var(--foreground); font-weight: 600;
  box-shadow: 0 1px 2px rgba(0,0,0,.06);
}

.inv-form .rd-rooms-foot {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  font-size: 11.5px; color: var(--muted-foreground); font-variant-numeric: tabular-nums;
}
.inv-form .rd-rooms-foot-total { font-weight: 600; color: var(--foreground); }
.inv-form .rd-rooms-foot .cur { font-weight: 400; color: var(--muted-foreground); }

.inv-form .rd-empty {
  padding: 18px; text-align: center; font-size: 12.5px; color: var(--muted-foreground);
  border: 1px dashed var(--border); border-radius: var(--radius-control, 16px);
}
.inv-form .rd-pay-list { display: flex; flex-direction: column; gap: 8px; }
.inv-form .rd-pay-row {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 12px 14px; border: 1px solid var(--border); border-radius: var(--radius-control, 16px);
  background: var(--card);
}
.inv-form .rd-pay-main { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.inv-form .rd-pay-method { font-size: 13px; font-weight: 500; color: var(--foreground); }
.inv-form .rd-pay-sub { font-size: 11.5px; color: var(--muted-foreground); font-variant-numeric: tabular-nums; }
.inv-form .rd-pay-amt { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; }
.inv-form .rd-pay-amt .rd-num { font-size: 13.5px; font-weight: 600; font-variant-numeric: tabular-nums; }
.inv-form .rd-pay-amt .cur { font-weight: 400; font-size: 11px; color: var(--muted-foreground); }
.inv-form .rd-pay-fx { font-size: 11px; color: var(--muted-foreground); font-variant-numeric: tabular-nums; }

/* ── Rail internals ── */
.inv-form .rd-rail-block { display: flex; flex-direction: column; gap: 10px; }
.inv-form .rd-rail-lbl {
  font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
  color: var(--muted-foreground);
}
.inv-form .rd-rail-total {
  display: flex; align-items: baseline; gap: 8px;
  font-size: 34px; font-weight: 600; letter-spacing: -.025em;
  font-variant-numeric: tabular-nums; color: var(--foreground);
}
.inv-form .rd-rail-total.is-due { color: var(--red); }
.inv-form .rd-rail-cur { font-size: 13px; font-weight: 500; color: var(--muted-foreground); }
.inv-form .rd-rail-meta { font-size: 11.5px; color: var(--muted-foreground); font-variant-numeric: tabular-nums; }

.inv-form .rd-bar { display: flex; gap: 3px; height: 8px; }
.inv-form .rd-bar > span { border-radius: 999px; min-width: 3px; }

.inv-form .rd-mix { display: flex; flex-direction: column; gap: 8px; font-size: 12.5px; }
.inv-form .rd-mix-row { display: flex; align-items: center; justify-content: space-between; color: var(--muted-foreground); }
.inv-form .rd-num { font-weight: 500; color: var(--foreground); font-variant-numeric: tabular-nums; }
.inv-form .rd-mix-total {
  padding-top: 9px; border-top: 1px solid var(--border);
  font-weight: 500; color: var(--foreground);
}

.inv-form .rd-rail-sep { height: 1px; background: var(--border); }
.inv-form .rd-rail-spacer { flex: 1; min-height: 8px; }

.inv-form .rd-check { display: flex; align-items: center; gap: 9px; font-size: 12.5px; color: var(--muted-foreground); }
.inv-form .rd-check svg { flex: none; color: var(--muted-foreground); }
.inv-form .rd-check.is-ok { color: var(--foreground); }
.inv-form .rd-check.is-ok svg { color: var(--green); }

.inv-form .rd-cta {
  display: flex; align-items: center; justify-content: center; gap: 7px;
  width: 100%; height: 42px; border: none; border-radius: 12px;
  background: var(--primary); color: var(--primary-foreground);
  font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; transition: background .12s;
}
.inv-form .rd-cta:hover { background: var(--primary-hover); }
.inv-form .rd-cta:disabled { opacity: .6; cursor: default; }
.inv-form .rd-cta-ghost {
  display: flex; align-items: center; justify-content: center; height: 38px;
  border-radius: 12px; border: 1px solid var(--border); background: var(--card);
  font-size: 12.5px; font-weight: 500; color: var(--foreground); text-decoration: none;
}
.inv-form .rd-cta-ghost:hover { background: var(--muted); }

.inv-form .rd-rail-actions {
  position: sticky; bottom: 0;
  display: flex; flex-direction: column; gap: 8px;
  padding: 0 24px 24px;
}

@media (max-width: 1099px) {
  .inv-form .rd-body { flex-direction: column; }
  .inv-form .rd-main { width: 100%; }
  .inv-form .rd-sec { grid-template-columns: 1fr; gap: 12px; padding: 22px 22px; }
  .inv-form .rd-rail {
    width: auto; border-left: none; border-top: 1px solid var(--border);
    background: color-mix(in oklch, var(--muted) 38%, var(--card));
  }
  .inv-form .rd-summary { position: static; padding: 22px; }
  .inv-form .rd-rail-spacer { display: none; }
  .inv-form .rd-rail-actions { position: static; padding: 0 22px 22px; }
}
@media (max-width: 600px) { .inv-form .rd-row3 { grid-template-columns: 1fr; } }

/* ── Reservations section: empty state + selected list + foot ── */
.inv-form .rd-res-empty {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  width: 100%; height: 44px; border: 1px dashed var(--border);
  border-radius: var(--radius-control, 16px); background: transparent;
  font: inherit; font-size: 13px; font-weight: 600; color: var(--primary);
  cursor: pointer; transition: background .12s, border-color .12s;
}
.inv-form .rd-res-empty:hover { background: var(--muted); border-color: var(--primary); }

.inv-form .rd-res-row {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 8px 12px 14px; border: 1px solid var(--border);
  border-radius: var(--radius-control, 16px); background: var(--card);
}
.inv-form .rd-res-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.inv-form .rd-res-t {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  font-size: 13.5px; font-weight: 500; color: var(--foreground);
}
.inv-form .rd-res-badge {
  font-family: var(--font-mono); font-size: 9.5px; font-weight: 600;
  padding: 1px 5px; border-radius: 6px;
  background: var(--muted); border: 1px solid var(--border); color: var(--muted-foreground);
}
.inv-form .rd-res-sub {
  font-size: 11.5px; color: var(--muted-foreground); font-variant-numeric: tabular-nums;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.inv-form .rd-res-amt {
  flex: none; font-size: 14px; font-weight: 600;
  color: var(--foreground); font-variant-numeric: tabular-nums;
}
.inv-form .rd-res-x {
  flex: none; width: 30px; height: 30px; border-radius: 8px; border: none; padding: 0;
  display: inline-flex; align-items: center; justify-content: center;
  background: transparent; color: var(--muted-foreground); cursor: pointer;
  transition: background .12s, color .12s;
}
.inv-form .rd-res-x:hover { background: var(--destructive); color: var(--destructive-foreground); }

.inv-form .rd-pick-foot {
  display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
  padding-top: 4px;
  font-size: 11.5px; color: var(--muted-foreground);
}
.inv-form .rd-pick-foot-l { display: flex; align-items: center; gap: 16px; }
.inv-form .rd-pick-foot-sum { font-weight: 500; color: var(--foreground); font-variant-numeric: tabular-nums; }
.inv-form .rd-pick-foot .rd-link { margin-top: 0; }

/* ── Import dialog (Radix portals it outside .inv-form) ── */
.form-modal-content.rd-pick-dlg { max-width: 560px; }
.rd-pick-dlg .rd-pick-dlg-x {
  flex: none; width: 30px; height: 30px; border: none; border-radius: 8px; padding: 0;
  display: inline-flex; align-items: center; justify-content: center;
  background: transparent; color: var(--muted-foreground); cursor: pointer;
}
.rd-pick-dlg .rd-pick-dlg-x:hover { background: var(--muted); color: var(--foreground); }
.rd-pick-dlg .rd-pick-dlg-search {
  display: flex; align-items: center; gap: 9px; flex: none;
  margin: 12px 20px 4px; padding: 0 12px; height: 40px;
  border: 1px solid var(--border); border-radius: 12px;
  background: color-mix(in oklch, var(--muted) 50%, transparent);
}
.rd-pick-dlg .rd-pick-dlg-search svg { flex: none; color: var(--muted-foreground); }
.rd-pick-dlg .rd-pick-dlg-search input {
  flex: 1; min-width: 0; height: 100%; margin: 0; padding: 0; border: none;
  background: transparent; box-shadow: none; font: inherit; font-size: 13px; color: var(--foreground);
}
.rd-pick-dlg .rd-pick-dlg-search input:focus { outline: none; box-shadow: none; }
.rd-pick-dlg .rd-pick-dlg-body {
  flex: 1 1 auto; min-height: 0; overflow-y: auto;
  padding: 8px 20px 12px; display: flex; flex-direction: column; gap: 8px;
}
.rd-pick-dlg .rd-pick-dlg-empty { padding: 32px; text-align: center; font-size: 13px; color: var(--muted-foreground); }
.rd-pick-dlg .rd-pick-dlg-foot {
  flex: none; display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 12px 20px; border-top: 1px solid var(--border);
  font-size: 13px; color: var(--muted-foreground);
}
.rd-pick-dlg .rd-pick {
  display: flex; align-items: center; gap: 12px; width: 100%; text-align: left;
  padding: 11px 14px; border: 1px solid var(--border);
  border-radius: var(--radius-control, 16px); background: var(--card);
  font: inherit; cursor: pointer; transition: border-color .12s, background .12s;
}
.rd-pick-dlg .rd-pick:hover { border-color: color-mix(in oklch, var(--primary) 40%, var(--border)); }
.rd-pick-dlg .rd-pick.is-on {
  border-color: color-mix(in oklch, var(--primary) 45%, transparent);
  background: color-mix(in oklch, var(--primary) 8%, var(--card));
}
.rd-pick-dlg .rd-pick-box {
  flex: none; width: 18px; height: 18px; border-radius: 6px;
  border: 1px solid var(--border); background: var(--card);
  display: flex; align-items: center; justify-content: center; color: transparent;
}
.rd-pick-dlg .rd-pick.is-on .rd-pick-box {
  border-color: var(--primary); background: var(--primary); color: var(--primary-foreground);
}
.rd-pick-dlg .rd-pick-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.rd-pick-dlg .rd-pick-t {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  font-size: 13.5px; font-weight: 500; color: var(--foreground);
}
.rd-pick-dlg .rd-pick-badge {
  font-family: var(--font-mono); font-size: 10px; font-weight: 600;
  padding: 1px 6px; border-radius: 6px;
  background: var(--muted); border: 1px solid var(--border); color: var(--muted-foreground);
}
.rd-pick-dlg .rd-pick-sub {
  font-size: 11.5px; color: var(--muted-foreground);
  font-variant-numeric: tabular-nums; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rd-pick-dlg .rd-pick-amt {
  flex: none; font-size: 14px; font-weight: 600;
  color: var(--foreground); font-variant-numeric: tabular-nums;
}

/* ── Manual reservation cards (the rare no-CL case) ── */
.inv-form .rd-res-list { display: flex; flex-direction: column; gap: 10px; }
.inv-form .rd-res-card {
  display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px;
  padding: 14px; border: 1px solid var(--border);
  border-radius: var(--radius-control, 16px); background: var(--card);
}
.inv-form .rd-res-card [data-slot="form-field"] { flex: 1 1 128px; min-width: 0; }
.inv-form .rd-res-card .rd-res-num { flex: 0 1 104px; }
.inv-form .rd-res-card .rd-res-hotel { flex: 3 1 176px; }
.inv-form .rd-res-card .rd-res-total { flex: 1 1 116px; }
.inv-form .rd-res-card [data-slot="form-field"] label {
  font-size: 10.5px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase;
  color: var(--muted-foreground);
}
.inv-form .rd-res-del {
  flex: 0 0 auto; height: 40px; width: 34px;
  display: inline-flex; align-items: center; justify-content: center;
  border: none; border-radius: 10px; padding: 0; background: transparent;
  color: var(--muted-foreground); cursor: pointer;
  transition: background .12s, color .12s;
}
.inv-form .rd-res-del:hover { background: var(--destructive); color: var(--destructive-foreground); }
.inv-form .rd-res-del:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }

@media (max-width: 600px) { .inv-form.page { padding-bottom: 24px; } }
`;
