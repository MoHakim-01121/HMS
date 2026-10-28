import { useContext, useMemo, useState } from "react";
import { useForm } from "@inertiajs/react";
import { actionsClass, FormModalContext, StandaloneFormModal } from "../../components/shadcn/form-modal.jsx";
import { Field, Picker, DatePicker, addDaysIso, dateLabel, todayIso, FormAFrame, Why, FA, Caption, btnClass } from "../../components/shadcn/form-a.jsx";
import { cn } from "@/lib/utils";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

const ICON = {
  client: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="9" cy="8" r="3.2" /><path strokeLinecap="round" d="M3 19c.8-3.2 3.2-5 6-5s5.2 1.8 6 5" /><path strokeLinecap="round" d="M15.5 4.8a3.2 3.2 0 010 6.2M17.5 14.4c1.8.6 3 2.2 3.5 4.6" /></svg>,
  clock: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="12" cy="12" r="8" /><path strokeLinecap="round" d="M12 8v4l3 2" /></svg>,
  tick: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M5 12l5 5 9-10" /></svg>,
  doc: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M7 3h7l5 5v13H7zM14 3v5h5" /></svg>,
};

// Payment terms of the approved form: a due date counted from the issue date,
// or back from the first check-in among the CLs billed.
const TERMS = [
  { id: "receipt", label: "On receipt", from: "issue", days: 0 },
  { id: "1d", label: "1 day after issue", from: "issue", days: 1 },
  { id: "2d", label: "2 days after issue", from: "issue", days: 2 },
  { id: "3d", label: "3 days after issue", from: "issue", days: 3 },
  { id: "27b", label: "27 days before check-in", from: "checkin", days: 27 },
];

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function stayLabel(a, b, t) {
  if (!a) return t("dates TBC");
  const [, am, ad] = a.split("-").map(Number);
  if (!b) return `${String(ad).padStart(2, "0")} ${MON[am - 1]}`;
  const [, bm, bd] = b.split("-").map(Number);
  const A = String(ad).padStart(2, "0"), B = String(bd).padStart(2, "0");
  return am === bm ? t("{a} to {b} {m}", { a: A, b: B, m: MON[am - 1] }) : t("{a} {am} to {b} {bm}", { a: A, am: MON[am - 1], b: B, bm: MON[bm - 1] });
}

// Hotel invoice form, as approved on the Record View HMS canvas: bill to a
// client, an issue date and payment terms, then tick that client's
// confirmation letters not yet invoiced. The number is issued on save.
export default function Form({ invoice, edit, cl_data = [], clients = [], initial, errors = {} }) {
  const { t } = useI18n();
  const src = initial || invoice || {};
  const ownIds = useMemo(() => new Set(invoice?.linked_cl_ids || []), [invoice]);
  const seeded = (src.linked_cl_ids || []).map(Number);
  const seededClient = src.client_id
    || (seeded.length ? cl_data.find((c) => c.id === seeded[0])?.client_id : "")
    || "";

  const [clientId, setClientId] = useState(seededClient ? String(seededClient) : "");
  const [issue, setIssue] = useState(src.issued_date || todayIso());
  const [sel, setSel] = useState(seeded);
  // Editing: the stored due date, kept until a term is picked.
  const [term, setTerm] = useState(edit && src.due_date ? "keep" : "receipt");
  const form = useForm({});
  const errs = { ...errors, ...form.errors };

  const avail = useMemo(
    () => (clientId ? cl_data.filter((c) => String(c.client_id) === String(clientId) && (!c.inv || ownIds.has(c.id))) : []),
    [cl_data, clientId, ownIds],
  );
  const chosen = avail.filter((c) => sel.includes(c.id));
  const total = chosen.reduce((s, c) => s + (c.total || 0), 0);
  const firstIn = chosen.map((c) => c.check_in).filter(Boolean).sort()[0] || null;

  const dueOf = (tm) => {
    if (tm.id === "keep") return src.due_date || null;
    if (tm.from === "issue") return issue ? addDaysIso(issue, tm.days) : null;
    return firstIn ? addDaysIso(firstIn, -tm.days) : null;
  };
  const terms = [
    ...(edit && src.due_date ? [{ id: "keep", label: t("Keep the current due date"), from: "fixed" }] : []),
    ...TERMS.map((x) => ({ ...x, label: t(x.label) })),
  ];
  const curTerm = terms.find((x) => x.id === term) || terms[0];
  const due = dueOf(curTerm);

  const allOn = avail.length > 0 && avail.every((c) => sel.includes(c.id));
  const someOn = chosen.length > 0;
  const toggle = (id) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const toggleAll = () => setSel(allOn ? [] : avail.map((c) => c.id));

  const client = clients.find((c) => String(c.id) === String(clientId));
  const why = !clientId ? t("Select the client to bill first.")
    : chosen.length === 0 ? t("Add at least one confirmation letter to issue the invoice.")
    : !issue ? t("Pick the issue date.")
    : "";

  const submit = (e) => {
    e.preventDefault();
    if (why) return;
    const rows = chosen.map((c) => ({
      reservation_number: c.ref, hotel: c.hotel,
      check_in: c.check_in, check_out: c.check_out, reservation_total: c.total || 0,
    }));
    form.transform(() => ({
      client_id: clientId, customer_name: client?.name || "",
      invoice_number: edit ? invoice.invoice_number : "",
      issued_date: issue, due_date: due || issue,
      reservations: JSON.stringify(rows),
      linked_cl_ids: JSON.stringify(chosen.map((c) => c.id)),
    }));
    form.post(edit ? `/invoice/${invoice.pk}/edit/` : "/invoice/new/", { forceFormData: true });
  };

  const ctx = useContext(FormModalContext);
  const inModal = ctx?.inModal;
  const closeHref = edit ? `/invoice/${invoice.pk}/` : "/invoice/";

  const page = (
    <FormAFrame title={edit ? t("Edit Invoice {number}", { number: invoice.invoice_number }) : t("New Invoice")}>
      
      <form method="post" onSubmit={submit} noValidate>
        <div className={FA.fields}>
          <Field label={t("Bill to")} required className={FA.wide} error={errs.client_id && t(errs.client_id)}>
            <Picker icon={ICON.client} value={clientId} placeholder={t("Select a client")} heading={t("Clients")}
              options={clients.map((c) => ({ value: String(c.id), label: c.name, meta: c.city || "" }))}
              onPick={(o) => { if (o.value !== clientId) { setClientId(o.value); setSel([]); } }}
              invalid={!!errs.client_id} />
          </Field>
          <Field label={t("Issue date")} required error={errs.issued_date && t(errs.issued_date)}>
            <DatePicker value={issue} onChange={setIssue} label={t("Choose issue date")} />
          </Field>
          <Field label={t("Payment terms")} required>
            <Picker searchable={false} icon={ICON.clock} value={curTerm.id} heading={t("Payment terms")}
              extra={due ? <span className={FA.meta}>{t("Due {date}", { date: dateLabel(due) })}</span> : null}
              options={terms.map((x) => {
                const d = dueOf(x);
                const meta = x.id === "receipt" ? t("Due on the issue date")
                  : d ? t("Due {date}", { date: dateLabel(d) })
                  : t("Add a CL to see the due date");
                return { value: x.id, label: x.label, meta };
              })}
              onPick={(o) => setTerm(o.value)} />
          </Field>
        </div>

        <div className={FA.sectionHead}>
          <Caption>{t("Confirmation letters")}</Caption>
          <span className={FA.muted}>{t("{n} of {m} selected", { n: chosen.length, m: avail.length })}</span>
        </div>
        <div className={FA.box}>
          <div className={FA.scroll}>
            <div className={cn(FA.checkRow, FA.checkRowHead)}>
              <button type="button" role="checkbox" aria-checked={allOn ? "true" : someOn ? "mixed" : "false"} aria-label={t("Select all")}
                className={cn(FA.checkBox, allOn ? FA.checkBoxOn : someOn && FA.checkBoxMid)} onClick={toggleAll} disabled={!avail.length}>{ICON.tick}</button>
              <span>CL</span><span>{t("Hotel")}</span><span>{t("Stay")}</span><span className="text-right">{t("Amount")}</span>
            </div>
            {avail.map((c) => {
              const on = sel.includes(c.id);
              return (
                <button type="button" key={c.id} className={cn(FA.checkRow, on && FA.checkRowOn)} role="checkbox" aria-checked={on} onClick={() => toggle(c.id)}>
                  <span className={cn(FA.checkBox, on && FA.checkBoxOn)}>{ICON.tick}</span>
                  <span className="font-mono text-[13px] font-semibold">{c.ref}</span>
                  <span className="truncate font-medium">{c.hotel}</span>
                  <span className={FA.num}>{stayLabel(c.check_in, c.check_out, t)}</span>
                  <span className="text-right font-semibold tabular-nums">{fmt(c.total || 0)}<span className={FA.unit}>SAR</span></span>
                </button>
              );
            })}
          </div>
          {!clientId && <div className={FA.checkNote}>{t("Select a client to see their confirmation letters.")}</div>}
          {clientId && avail.length === 0 && <div className={FA.checkNote}>{t("No uninvoiced confirmation letters for this client.")}</div>}
          <div className={FA.checkTotal}><b>{t("Total")}</b><span className={FA.num}><b className="text-[17px]">{fmt(total)}</b><span className={FA.unit}>SAR</span></span></div>
        </div>
        {errs.reservations && <div className={FA.alert} role="alert">{t(errs.reservations)}</div>}
        {/* The server refuses a save the ledger cannot follow (a reservation
            with money on it taken off the invoice, a closed period). */}
        {errs.finance && <div className={FA.alert} role="alert">{errs.finance}</div>}
        {errs.invoice_number && <div className={FA.alert} role="alert">{t(errs.invoice_number)}</div>}

        <div className={actionsClass("a")}>
          {why && <Why>{why}</Why>}
          {inModal ? (
            <button type="button" className={cn(btnClass("o"), "max-[600px]:hidden")} onClick={ctx.close}>{t("Cancel")}</button>
          ) : (
            <a className={cn(btnClass("o"), "max-[600px]:hidden")} href={closeHref}>{t("Cancel")}</a>
          )}
          {edit && (
            <a className={btnClass("o")} href={`/invoice/${invoice.pk}/pdf/`} target="_blank" rel="noreferrer">{ICON.doc}{t("Preview PDF")}</a>
          )}
          <button type="submit" className={btnClass("p")} aria-disabled={!!why || form.processing} disabled={form.processing}>
            {edit ? t("Save changes") : t("Issue invoice")}
          </button>
        </div>
      </form>
    </FormAFrame>
  );

  return inModal ? page : <StandaloneFormModal closeHref={closeHref}>{page}</StandaloneFormModal>;
}
