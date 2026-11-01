import { useState } from "react";
import { router } from "@inertiajs/react";
import { DPage, DTop, DHead, DBanner, DBtn, DCard, DLines, DLine, DLinesTotal, DA, DC } from "../../components/shadcn/detail-a.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import { FaDialog, Field, Picker, DatePicker, AmountIn, TextIn, FileDrop, Foot, Effect, EffectRow, digitsOf, FA } from "../../components/shadcn/form-a.jsx";
import { Check } from "../../components/shadcn/list-a.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtDate } from "../../utils/format.js";
import { usePerms } from "../../utils/perms.js";

const idr = (n) => `${fmt(n)} IDR`;
// Local date, not UTC: before 07:00 WIB toISOString() is still yesterday.
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const TONE = { draft: "gray", submitted: "amber", partial: "amber", paid: "green", rejected: "gray", cancelled: "gray" };
const LABEL = { draft: "Draft", submitted: "Submitted", partial: "Partly paid", paid: "Reimbursed", rejected: "Rejected", cancelled: "Cancelled" };

// One claim. Head office does not use HMS: branch Finance submits the claim,
// then records head office's answer here — the rupiah arriving, all of it or
// part of it (the rest stays claimed, or the branch bears it), or a rejection.
export default function ClaimDetail({ claim = {}, account_choices = [], journal_entries = [], head_office_credit: credit = 0 }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canEdit = perms.can("expenses", "create");
  const canDecide = perms.can("expenses", "approve");
  const canBook = perms.can("bank", "edit");
  const [dialog, setDialog] = useState(null); // "pay" | "reject" | "cancel" | "unpay" | "close"
  const [pay, setPay] = useState(null);
  const openPay = () => {
    setPay({ account: account_choices.length === 1 ? account_choices[0].value : "", paid_date: today(), amount: String(claim.remaining), remainder: "", excess_use: "", reference: "", proof: null });
    setDialog("pay");
  };
  const [reason, setReason] = useState("");
  const close = () => { setDialog(null); setReason(""); };
  const post = (action, data = {}) => router.post(`/finance/claims/${claim.id}/${action}/`, data, { onSuccess: close, forceFormData: !!data.proof });
  const s = claim.status;
  const items = claim.items || [];
  const payments = claim.payments || [];
  const received = pay ? Number(digitsOf(pay.amount)) || 0 : 0;
  const short = Math.max(claim.remaining - received, 0);
  const excess = Math.max(received - claim.remaining, 0);
  const payWhy = !pay ? "" : !pay.account ? t("Choose the account it arrived in.")
    : !received ? t("Enter the amount received.")
      : short > 0 && !pay.remainder ? t("Choose what happens to the rest.")
        : excess > 0 && !pay.excess_use ? t("Choose what happens to the extra.")
          : "";
  const submitPay = (e) => {
    e.preventDefault();
    if (payWhy) return;
    post("pay", { ...pay, amount: received, remainder: short > 0 ? pay.remainder : "", excess_use: excess > 0 ? pay.excess_use : "", proof: pay.proof || undefined });
  };

  let banner = null;
  if (s === "draft") {
    banner = (
      <DBanner actions={canEdit ? <DBtn primary onClick={() => post("submit")}>{t("Submit to head office")}</DBtn> : null}>
        <b>{idr(claim.total_amount)}</b> {t("is ready to claim. Print the PDF to send with it.")}
        {credit > 0 && <> {t("{v} of head office credit is deducted when you submit it.", { v: idr(Math.min(credit, claim.total_amount)) })}</>}
      </DBanner>
    );
  } else if (s === "submitted") {
    banner = (
      <DBanner actions={canBook ? <DBtn primary onClick={openPay}>{t("Record reimbursement")}</DBtn> : null}>
        {claim.credit_used > 0 && <>{t("{v} is cut by head office credit.", { v: idr(claim.credit_used) })} </>}
        <b>{idr(claim.remaining)}</b> {t("is waiting for head office. Record it when the rupiah arrives.")}
      </DBanner>
    );
  } else if (s === "partial") {
    banner = (
      <DBanner actions={canBook ? <><DBtn onClick={() => setDialog("close")}>{t("Close the rest")}</DBtn><DBtn primary onClick={openPay}>{t("Record reimbursement")}</DBtn></> : null}>
        <b>{idr(claim.received_amount)}</b> {t("received.")} <b>{idr(claim.remaining)}</b> {t("is still waiting for head office.")}
      </DBanner>
    );
  } else if (s === "paid") {
    banner = (
      <DBanner tone="success">
        <b>{t("Reimbursed")}</b> {claim.paid_by_credit ? t("on {d} from head office credit.", { d: fmtDate(claim.paid_date) }) : t("on {d} into {a}.", { d: fmtDate(claim.paid_date), a: claim.paid_to })}
        {claim.borne_amount > 0 && <> <b>{idr(claim.borne_amount)}</b> {t("is borne by the branch.")}</>}
      </DBanner>
    );
  } else {
    banner = (
      <DBanner tone="gray">
        <b>{s === "rejected" ? t("Rejected by head office.") : t("Cancelled.")}</b>{" "}
        {claim.decision_note || t("Its expenses can be claimed again.")}
      </DBanner>
    );
  }

  const menu = [
    { label: t("Download PDF"), icon: "pdf", href: `/finance/claims/${claim.id}/pdf/` },
    perms.can("expenses", "export") && { label: "CSV", icon: "download", href: `/finance/claims/${claim.id}/export/csv/` },
    (s === "submitted" || claim.paid_by_credit) && canDecide && { label: t("Record rejection"), icon: "close", danger: true, onClick: () => setDialog("reject") },
    (s === "draft" || s === "submitted" || claim.paid_by_credit) && canEdit && { label: t("Cancel claim"), icon: "close", danger: true, onClick: () => setDialog("cancel") },
    (s === "paid" || s === "partial") && !claim.paid_by_credit && canBook && { label: t("Undo reimbursement"), icon: "close", danger: true, onClick: () => setDialog("unpay") },
  ];

  const reasonDialog = {
    reject: [t("Record rejection of {n}", { n: claim.claim_number }), t("Its expenses are freed to be claimed again."), t("Record rejection")],
    cancel: [t("Cancel {n}", { n: claim.claim_number }), t("Its expenses are freed to be claimed again."), t("Cancel claim")],
    unpay: [t("Undo reimbursement of {n}", { n: claim.claim_number }), t("The journal and the cash-book row are reversed; the claim goes back to submitted."), t("Undo")],
    close: [t("Close the rest of {n}", { n: claim.claim_number }), t("{v} stays with the branch as its own cost. No money moves.", { v: idr(claim.remaining) }), t("Close the rest")],
  }[dialog];

  return (
    <DPage>
      <DTop href="/finance/claims/" />
      {banner}
      <DHead
        title={claim.claim_number}
        badge={{ label: t(LABEL[s] || claim.status_display), tone: TONE[s] || "gray" }}
        menu={menu}
        cols={3}
        facts={[
          { k: t("Branch"), v: claim.branch_name },
          { k: t("Total"), v: idr(claim.total_amount), strong: true },
          { k: t("Expenses dated"), v: `${fmtDate(claim.date_from)} – ${fmtDate(claim.date_to)}` },
          { k: t("Prepared by"), v: claim.created_by },
          claim.credit_used > 0 && { k: t("Cut by head office credit"), v: idr(claim.credit_used) },
          claim.received_amount > claim.credit_used && { k: t("Received"), v: idr(claim.received_amount - claim.credit_used) },
          (s === "partial" || (s === "submitted" && claim.credit_used > 0)) && { k: t("Remaining"), v: idr(claim.remaining) },
          claim.borne_amount > 0 && { k: t("Borne by the branch"), v: idr(claim.borne_amount) },
          claim.received_sar > 0 && { k: t("Booked"), v: `${fmt(claim.received_sar)} SAR` },
          claim.reference && { k: t("Reference"), v: claim.reference },
          claim.decided_by && { k: t("Recorded by"), v: claim.decided_by },
        ]}
        note={claim.note ? { text: claim.note } : null}
      />

      {payments.length ? (
        <DCard title={t("Reimbursements")} count={payments.length}>
          <DLines>
            {payments.map((p) => (
              <DLine key={p.id} title={fmtDate(p.date)} sub={[p.account || t("Head office credit"), p.reference, p.excess_amount > 0 && t(p.excess_kept ? "{v} extra funds for the branch" : "{v} extra to head office credit", { v: fmt(p.excess_amount) })].filter(Boolean).join(" · ")} value={fmt(p.amount)} />
            ))}
          </DLines>
          <div className={DA.scrollWide}>
            <table data-slot="detail-table" className={DA.table}>
              <thead><tr><th>{t("Date")}</th><th>{t("Received in")}</th><th>{t("Reference")}</th><th>{t("Transfer proof")}</th><th className={DC.n}>{t("Amount (IDR)")}</th></tr></thead>
              <tbody>
                {payments.map((p) => (
                  <tr key={p.id}>
                    <td className={DC.nw}>{fmtDate(p.date)}</td><td>{p.account || t("Head office credit")}{p.excess_amount > 0 && <span className="mt-0.5 block text-[12px] text-muted-foreground">{t(p.excess_kept ? "{v} extra funds for the branch" : "{v} extra to head office credit", { v: fmt(p.excess_amount) })}</span>}</td><td className={DC.mut}>{p.reference}</td>
                    <td>{p.proof_url ? <a href={p.proof_url} target="_blank" rel="noreferrer">{t("Open transfer proof")}</a> : "—"}</td>
                    <td className={DC.n}>{fmt(p.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </DCard>
      ) : null}

      <DCard title={t("Expenses")} count={items.length}>
        <DLines>
          {items.map((e) => (
            <DLine key={e.id} href={`/finance/expenses/${e.id}/`} mono title={e.expense_number}
              sub={[fmtDate(e.expense_date), e.description].filter(Boolean).join(" · ")} value={fmt(e.amount)} />
          ))}
          <DLinesTotal label={t("Total")}>{idr(claim.total_amount)}</DLinesTotal>
        </DLines>
        <div className={DA.scrollWide}>
          <table data-slot="detail-table" className={DA.table}>
            <thead><tr><th>{t("Expense")}</th><th>{t("Date")}</th><th>{t("Description")}</th><th className={DC.n}>{t("Amount (IDR)")}</th></tr></thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.id}>
                  <td className={DC.mono}><a href={`/finance/expenses/${e.id}/`}>{e.expense_number}</a></td>
                  <td className={DC.nw}>{fmtDate(e.expense_date)}</td>
                  <td>{e.description}</td>
                  <td className={DC.n}>{fmt(e.amount)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot><tr>
              <td colSpan={3} style={{ paddingBottom: 16 }}>{t("Total")}</td>
              <td className={DC.n} style={{ paddingBottom: 16 }}>{idr(claim.total_amount)}</td>
            </tr></tfoot>
          </table>
        </div>
      </DCard>

      {journal_entries.length ? (
        <DCard title={t("Journal Entries")} count={journal_entries.length}>
          <DLines>
            {journal_entries.map((e) => (
              <DLine key={e.id} mono title={e.entry_number} sub={[e.entry_type_display, e.entry_date, e.description].filter(Boolean).join(" · ")}
                value={fmt(e.total_debit)} />
            ))}
          </DLines>
          <div className={DA.scrollWide}>
            <table data-slot="detail-table" className={DA.table}>
              <thead><tr><th>{t("Entry #")}</th><th>{t("Type")}</th><th>{t("Description")}</th><th>{t("Date")}</th><th className={DC.n}>{t("Debit")}</th><th className={DC.n}>{t("Credit")}</th></tr></thead>
              <tbody>
                {journal_entries.map((e) => (
                  <tr key={e.id}>
                    <td className={DC.mono}>{e.entry_number}</td><td className={DC.strong}>{e.entry_type_display}</td>
                    <td className={DC.mut}>{e.description}</td><td className={DC.nw}>{e.entry_date}</td>
                    <td className={DC.n}>{fmt(e.total_debit)}</td><td className={DC.n}>{fmt(e.total_credit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </DCard>
      ) : null}

      {dialog === "pay" && pay && (
        <FaDialog title={t("Record reimbursement of {n}", { n: claim.claim_number })} onClose={close}>
          <form onSubmit={submitPay} noValidate>
            <div className={FA.fields}>
              <Field label={t("Received in")} required>
                <Picker searchable={false} value={pay.account} placeholder={t("Select account...")} heading={t("Received in")}
                  options={account_choices.map((a) => ({ value: a.value, label: a.label }))}
                  onPick={(o) => setPay({ ...pay, account: o.value })} />
              </Field>
              <Field label={t("Date received")} required hint={t("An earlier date is fine for an old reimbursement, while its month is open.")}>
                <DatePicker label={t("Date received")} value={pay.paid_date} onChange={(v) => setPay({ ...pay, paid_date: v })} />
              </Field>
              <Field label={t("Amount received")} required>
                <AmountIn ccy="IDR" value={pay.amount} onChange={(v) => setPay({ ...pay, amount: v })} />
              </Field>
              <Field label={t("Reference")} optional>
                <TextIn value={pay.reference} onChange={(v) => setPay({ ...pay, reference: v })} />
              </Field>
            </div>
            <div className="mt-5">
              <Effect>
                <EffectRow><span>{claim.received_amount > 0 ? t("Still owed") : t("Claim total")}</span><span>{idr(claim.remaining)}</span></EffectRow>
                <EffectRow><span>{t("This transfer")}</span><span>{idr(received)}</span></EffectRow>
                {excess > 0
                  ? <EffectRow result><span>{t("Extra")}</span><b>{idr(excess)}</b></EffectRow>
                  : <EffectRow result><span>{t("Remaining")}</span><b>{idr(short)}</b></EffectRow>}
              </Effect>
            </div>
            {short > 0 && (
              <div className="mt-4" role="radiogroup" aria-label={t("Choose what happens to the rest.")}>
                <Check radio on={pay.remainder === "open"} onClick={() => setPay({ ...pay, remainder: "open" })} label={t("Head office will still pay it")} />
                <Check radio on={pay.remainder === "borne"} onClick={() => setPay({ ...pay, remainder: "borne" })} label={t("The branch bears it")} />
              </div>
            )}
            {excess > 0 && (
              <div className="mt-4" role="radiogroup" aria-label={t("Choose what happens to the extra.")}>
                <Check radio on={pay.excess_use === "credit"} onClick={() => setPay({ ...pay, excess_use: "credit" })} label={t("Cut it from the next claim")} />
                <Check radio on={pay.excess_use === "keep"} onClick={() => setPay({ ...pay, excess_use: "keep" })} label={t("Extra funds for the branch, not cut")} />
              </div>
            )}
            <div className="mt-5">
              <FileDrop file={pay.proof} onFile={(f) => setPay({ ...pay, proof: f })} title={t("Transfer proof")} sub={t("Image or PDF")} />
            </div>
            <Foot why={payWhy} onCancel={close} submitLabel={t("Record reimbursement")} />
          </form>
        </FaDialog>
      )}

      {reasonDialog && (
        <Dialog open onOpenChange={(v) => { if (!v) close(); }}>
          <DialogContent>
            <DialogHeader><DialogTitle>{reasonDialog[0]}</DialogTitle></DialogHeader>
            <p style={{ fontSize: 13, color: "var(--muted-foreground)", margin: 0 }}>{reasonDialog[1]}</p>
            <FormField label={t("Reason")} name="reason" required={dialog !== "cancel" && dialog !== "close"}>
              <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
            </FormField>
            <DialogFooter>
              <Button variant="outline" onClick={close}>{t("Back")}</Button>
              <Button variant="destructive" disabled={dialog !== "cancel" && dialog !== "close" && !reason.trim()} onClick={() => post(dialog, { reason })}>{reasonDialog[2]}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </DPage>
  );
}
