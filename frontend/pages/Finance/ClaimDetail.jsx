import { useState } from "react";
import { router } from "@inertiajs/react";
import { DPage, DTop, DHead, DBanner, DBtn, DChip, DCard, DLines, DLine, DLinesTotal, DA, DC } from "../../components/shadcn/detail-a.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtDate } from "../../utils/format.js";
import { usePerms } from "../../utils/perms.js";

const idr = (n) => `${fmt(n)} IDR`;
// Local date, not UTC: before 07:00 WIB toISOString() is still yesterday.
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const TONE = { draft: "gray", submitted: "amber", paid: "green", rejected: "gray", cancelled: "gray" };
const LABEL = { draft: "Draft", submitted: "Submitted", paid: "Reimbursed", rejected: "Rejected", cancelled: "Cancelled" };

// One claim. Head office does not use HMS: branch Finance submits the claim,
// then records head office's answer here — the rupiah arriving (Reimbursed)
// or a rejection with its reason.
export default function ClaimDetail({ claim = {}, account_choices = [], journal_entries = [] }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canEdit = perms.can("expenses", "create");
  const canDecide = perms.can("expenses", "approve");
  const canBook = perms.can("bank", "edit");
  const [dialog, setDialog] = useState(null); // "pay" | "reject" | "cancel" | "unpay"
  const [pay, setPay] = useState({ account: account_choices.length === 1 ? account_choices[0].value : "", paid_date: today(), reference: "", proof: null });
  const [reason, setReason] = useState("");
  const close = () => { setDialog(null); setReason(""); };
  const post = (action, data = {}) => router.post(`/finance/claims/${claim.id}/${action}/`, data, { onSuccess: close, forceFormData: !!data.proof });
  const s = claim.status;
  const items = claim.items || [];

  let banner = null;
  if (s === "draft") {
    banner = (
      <DBanner actions={canEdit ? <DBtn primary onClick={() => post("submit")}>{t("Submit to head office")}</DBtn> : null}>
        <b>{idr(claim.total_amount)}</b> {t("is ready to claim. Print the PDF to send with it.")}
      </DBanner>
    );
  } else if (s === "submitted") {
    banner = (
      <DBanner actions={canBook ? <DBtn primary onClick={() => setDialog("pay")}>{t("Record reimbursement")}</DBtn> : null}>
        <b>{idr(claim.total_amount)}</b> {t("is waiting for head office. Record it when the rupiah arrives.")}
      </DBanner>
    );
  } else if (s === "paid") {
    banner = (
      <DBanner tone="success">
        <b>{t("Reimbursed")}</b> {t("on {d} into {a}.", { d: fmtDate(claim.paid_date), a: claim.paid_to })}
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
    s === "submitted" && canDecide && { label: t("Record rejection"), icon: "close", danger: true, onClick: () => setDialog("reject") },
    (s === "draft" || s === "submitted") && canEdit && { label: t("Cancel claim"), icon: "close", danger: true, onClick: () => setDialog("cancel") },
    s === "paid" && canBook && { label: t("Undo reimbursement"), icon: "close", danger: true, onClick: () => setDialog("unpay") },
  ];

  const reasonDialog = {
    reject: [t("Record rejection of {n}", { n: claim.claim_number }), t("Its expenses are freed to be claimed again."), t("Record rejection")],
    cancel: [t("Cancel {n}", { n: claim.claim_number }), t("Its expenses are freed to be claimed again."), t("Cancel claim")],
    unpay: [t("Undo reimbursement of {n}", { n: claim.claim_number }), t("The journal and the cash-book row are reversed; the claim goes back to submitted."), t("Undo")],
  }[dialog];

  return (
    <DPage>
      <DTop href="/finance/claims/" />
      {banner}
      <DHead
        title={claim.claim_number}
        badge={{ label: t(LABEL[s] || claim.status_display), tone: TONE[s] || "gray" }}
        menu={menu}
        chips={claim.proof_url ? [<DChip key="proof" href={claim.proof_url} icon="clip" label={t("Open transfer proof")}>{decodeURIComponent(claim.proof_url.split("/").pop())}</DChip>] : null}
        cols={3}
        facts={[
          { k: t("Branch"), v: claim.branch_name },
          { k: t("Total"), v: idr(claim.total_amount), strong: true },
          { k: t("Expenses dated"), v: `${fmtDate(claim.date_from)} – ${fmtDate(claim.date_to)}` },
          { k: t("Prepared by"), v: claim.created_by },
          s === "paid" && { k: t("Booked"), v: `${fmt(claim.total_sar)} SAR` },
          claim.reference && { k: t("Reference"), v: claim.reference },
          claim.decided_by && { k: t("Recorded by"), v: claim.decided_by },
        ]}
        note={claim.note ? { text: claim.note } : null}
      />

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

      {dialog === "pay" && (
        <Dialog open onOpenChange={(v) => { if (!v) close(); }}>
          <DialogContent>
            <DialogHeader><DialogTitle>{t("Record reimbursement of {n}", { n: claim.claim_number })}</DialogTitle></DialogHeader>
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>{idr(claim.total_amount)}</div>
              <FormField label={t("Received in")} name="account" required>
                <Select value={pay.account} onValueChange={(v) => setPay({ ...pay, account: v })}>
                  <SelectTrigger className="w-full"><SelectValue placeholder={t("Select account...")} /></SelectTrigger>
                  <SelectContent>{account_choices.map((a) => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}</SelectContent>
                </Select>
              </FormField>
              <FormField label={t("Date received")} name="paid_date" type="date" required
                hint={t("An earlier date is fine for an old reimbursement, while its month is open.")}
                value={pay.paid_date} onChange={(v) => setPay({ ...pay, paid_date: v })} />
              <FormField label={t("Reference")} name="reference" value={pay.reference} onChange={(v) => setPay({ ...pay, reference: v })} />
              <FormField label={t("Transfer proof")} name="proof">
                <input type="file" accept="image/*,application/pdf" onChange={(e) => setPay({ ...pay, proof: e.target.files[0] || null })} />
              </FormField>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={close}>{t("Cancel")}</Button>
              <Button onClick={() => post("pay", pay.proof ? pay : { ...pay, proof: undefined })} disabled={!pay.account}>{t("Record reimbursement")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {reasonDialog && (
        <Dialog open onOpenChange={(v) => { if (!v) close(); }}>
          <DialogContent>
            <DialogHeader><DialogTitle>{reasonDialog[0]}</DialogTitle></DialogHeader>
            <p style={{ fontSize: 13, color: "var(--muted-foreground)", margin: 0 }}>{reasonDialog[1]}</p>
            <FormField label={t("Reason")} name="reason" required={dialog !== "cancel"}>
              <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
            </FormField>
            <DialogFooter>
              <Button variant="outline" onClick={close}>{t("Back")}</Button>
              <Button variant="destructive" disabled={dialog !== "cancel" && !reason.trim()} onClick={() => post(dialog, { reason })}>{reasonDialog[2]}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </DPage>
  );
}
