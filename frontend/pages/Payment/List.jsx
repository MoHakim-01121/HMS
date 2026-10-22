import { useState } from "react";
import { router } from "@inertiajs/react";
import {
  ListPage, Kpis, Kpi, Delta, Toolbar, MonthNav, SearchTool, FilterMenu, FilterSection, Check,
  ExportMenu, Primary, TableCard, RowMenu, Pill, Amt, Pager, Empty, LIcon, MONTHS, fmtN, dShort, useListNav, rowNav,
} from "../../components/shadcn/list-a.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";
import RecordPayment from "./RecordPayment.jsx";

const GROUP = {
  pending: ["outline", "Waiting confirmation"], unallocated: ["amber", "Unapplied"],
  partial: ["amber-o", "Partially applied"], allocated: ["green", "Applied"], cancelled: ["gray", ""],
};
const monthName = (ym, t) => (ym ? t(MONTHS[+ym.slice(5, 7) - 1]) : "");

// Payments list, as on the Record View HMS canvas: cash received in the
// month (turn the card for each currency), payments waiting confirmation and
// unapplied cash (both filter the table), the toolbar and the table. The
// Record opens the approved form (RecordPayment.jsx).
export default function List({ payments = [], invoice_choices = [], client_choices = [], account_choices = [], kpis = null,
  filters: f, years = [], counts = {}, currency_counts = {}, method_counts = [], export_qs = "", pagination = null }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canCreate = perms.can("payments", "create");
  const canEdit = perms.can("payments", "edit");
  // Pencatat tidak mengonfirmasi pembayarannya sendiri (kecuali admin).
  const canConfirm = (p) => canEdit && (perms.isAdmin || p.created_by !== perms.user?.username);
  const canExport = perms.can("payments", "export");
  const [go, loading] = useListNav("/finance/payments/", f);
  const [draft, setDraft] = useState(f);
  const [flip, setFlip] = useState(false);
  const [confirmDialog, setConfirmDialog] = useState(null);
  const [rejectDialog, setRejectDialog] = useState(null);
  const [recordDialog, setRecordDialog] = useState(false);
  const confirmPayment = (payment) => {
    router.post(`/finance/payments/${payment.id}/confirm/`);
    setConfirmDialog(null);
  };

  const rejectPayment = () => {
    router.post(`/finance/payments/${rejectDialog.id}/reject/`, { reason: rejectDialog.reason });
    setRejectDialog(null);
  };

  const only = (k) => f.status.length === 1 && f.status[0] === k;
  const tog = (key, v) => setDraft((d) => ({ ...d, [key]: d[key].includes(v) ? d[key].filter((x) => x !== v) : [...d[key], v] }));
  const filterCount = (f.status.length ? 1 : 0) + (f.cur.length ? 1 : 0) + (f.method.length ? 1 : 0);
  const prevName = kpis ? monthName(kpis.prev_month, t) : "";

  return (
    <ListPage title={t("Payments")} loading={loading}>
      {kpis && (
        <Kpis>
          <button type="button" className={"la-kpi" + (flip ? " flip" : "")} aria-expanded={flip}
            aria-label={t("Cash received, {v} SAR. Show amounts by currency", { v: fmtN(kpis.received) })} onClick={() => setFlip((v) => !v)}>
            <span className="la-kt"><span className="l">{t("Cash received")}</span>
              <span className="la-kh">{!flip && kpis.delta && <Delta text={kpis.delta} good={!kpis.delta.startsWith("-")} title={t("{d} vs {m}", { d: kpis.delta, m: prevName })} />}<span className="la-tg">{LIcon.chev}</span></span>
            </span>
            <span className="la-face">
              <span className="la-fa" aria-hidden={flip}>
                <span className="la-kr"><span className="la-v">{fmtN(kpis.received)}<small>SAR</small></span></span>
                <span className="la-kb">{kpis.by_currency.length ? t("{list} received", { list: kpis.by_currency.map((c) => c.code).join(", ") }) : t("Nothing received yet")}</span>
              </span>
              <span className="la-fb" aria-hidden={!flip}>
                <span className="la-cg">{kpis.by_currency.map((c) => (
                  <span key={c.code} style={{ display: "contents" }}><span className="cc">{c.code}</span><span className="cn">{fmtN(c.amount)}</span><span className="cs">{fmtN(c.sar)} SAR</span></span>
                ))}</span>
              </span>
            </span>
          </button>
          <Kpi label={t("Waiting confirmation")} value={fmtN(kpis.pending_count)} unit={t("payments")}
            foot={t("{v} SAR not yet posted", { v: fmtN(kpis.pending_sar) })}
            on={only("pending")} onClick={() => go({ status: only("pending") ? [] : ["pending"] })} />
          <Kpi label={t("Unapplied cash")} value={fmtN(kpis.unapplied_sar)} unit="SAR" tone={kpis.unapplied_sar ? "warn" : undefined}
            foot={kpis.unapplied_count ? t("{n} receipts not yet applied to reservations", { n: kpis.unapplied_count }) : t("Everything is applied")}
            on={only("open")} onClick={() => go({ status: only("open") ? [] : ["open"] })} />
        </Kpis>
      )}

      <Toolbar spaced={!!kpis} left={<MonthNav month={f.month} year={f.year} years={years} onChange={(p) => go(p)} />}>
        <SearchTool value={f.q} onSearch={(q) => go({ q })} placeholder={t("Search payment, client, invoice, reference")} />
        <FilterMenu count={filterCount} onOpen={() => setDraft(f)}
          onReset={() => setDraft({ ...draft, status: [], cur: [], method: [] })}
          onApply={() => go({ status: draft.status, cur: draft.cur, method: draft.method })}>
          <FilterSection label={t("Status")}>
            <Check on={draft.status.includes("pending")} onClick={() => tog("status", "pending")} label={t("Waiting confirmation")} count={counts.pending} />
            <Check on={draft.status.includes("open")} onClick={() => tog("status", "open")} label={t("Not fully applied")} count={counts.open} />
            <Check on={draft.status.includes("allocated")} onClick={() => tog("status", "allocated")} label={t("Applied")} count={counts.allocated} />
            <Check on={draft.status.includes("cancelled")} onClick={() => tog("status", "cancelled")} label={t("Rejected, reversed or voided")} count={counts.cancelled} />
          </FilterSection>
          <FilterSection label={t("Currency received")}>
            {["IDR", "USD", "SAR"].map((c) => <Check key={c} on={draft.cur.includes(c)} onClick={() => tog("cur", c)} label={c} count={currency_counts[c] || 0} />)}
          </FilterSection>
          {method_counts.length > 0 && (
            <FilterSection label={t("Method")}>
              {method_counts.map((m) => <Check key={m.method} on={draft.method.includes(m.method)} onClick={() => tog("method", m.method)} label={t(m.method)} count={m.count} />)}
            </FilterSection>
          )}
        </FilterMenu>
        {canExport && <ExportMenu items={[{ label: "CSV", href: `/finance/payments/export/csv/${export_qs}` }]} />}
        {canCreate && <Primary label={t("Record payment")} onClick={() => setRecordDialog(true)} />}
      </Toolbar>

      <TableCard cols={[96, 70, null, 84, 150, 150, 88, 140, 48]}
        empty={!payments.length && <Empty title={t("No payments")} sub={t("Nothing matches this period and these filters.")} />}>
        <thead><tr>
          <th>{t("Payment")}</th>
          <th><button type="button" className="srt" style={{ border: 0, background: "none", padding: 0, font: "inherit", cursor: "pointer" }}
            onClick={() => go({ sort: f.sort === "date" ? "-date" : "date" })}>{t("Date")}{f.sort === "date" ? LIcon.sortUp : LIcon.sortDown}</button></th>
          <th>{t("Client")}</th><th>{t("For")}</th><th>{t("Received into")}</th>
          <th className="n">{t("Amount received")}</th><th className="n">{t("SAR value")}</th><th>{t("Status")}</th><th className="c">{t("Action")}</th>
        </tr></thead>
        <tbody>
          {payments.map((p) => {
            const [tone, label] = GROUP[p.group] || GROUP.cancelled;
            return (
              <tr key={p.id} className={p.group === "cancelled" ? "dim" : ""} {...rowNav(`/finance/payments/${p.id}/`)}>
                <td><span className="mono">{p.payment_number}</span></td>
                <td>{dShort(p.payment_date)}</td>
                <td className="ell strong">{p.client_name}</td>
                <td>{p.invoice_number ? <span className="mono">{p.invoice_number}</span> : <span className="mut">{t("Not assigned")}</span>}</td>
                <td className="ell">{p.account}<span className="sub">{t(p.method)}</span></td>
                <td className="n"><Amt code={p.currency} value={p.amount} /></td>
                <td className="n book">{fmtN(p.amount_sar)}</td>
                <td><Pill tone={tone}>{label ? t(label) : t(p.status_display)}</Pill>
                  {p.group === "partial" && p.unallocated_sar > 0 && <span className="sub">{t("{v} SAR left", { v: fmtN(p.unallocated_sar) })}</span>}</td>
                <td className="c">
                  <RowMenu label={t("Actions for {n}", { n: p.payment_number })} items={[
                    canConfirm(p) && p.status === "pending" && { label: t("Confirm"), onClick: () => setConfirmDialog(p) },
                    canEdit && ["unallocated", "partial"].includes(p.group) && { label: t("Apply"), onClick: () => router.visit(`/finance/payments/${p.id}/`) },
                    p.has_proof && { label: t("View proof"), href: p.proof_url, external: true },
                    canEdit && p.status === "pending" && { label: t("Reject…"), danger: true, onClick: () => setRejectDialog({ ...p, reason: "" }) },
                  ]} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </TableCard>

      <Pager p={pagination} perPage={f.per} onPage={(page) => go({ page })} onPerPage={(per) => go({ per })} />

      {recordDialog && (
        <RecordPayment onClose={() => setRecordDialog(false)} client_choices={client_choices}
          invoice_choices={invoice_choices} account_choices={account_choices} />
      )}

      {confirmDialog && (
        <Dialog open onOpenChange={(v) => { if (!v) setConfirmDialog(null); }}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t("Confirm Payment")}</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-muted-foreground">
              {t("Confirm payment {number} for {amount} SAR?", {
                number: confirmDialog.payment_number,
                amount: confirmDialog.amount_sar?.toLocaleString("en-US"),
              })}
            </p>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirmDialog(null)}>{t("Cancel")}</Button>
              <Button onClick={() => confirmPayment(confirmDialog)}>{t("Confirm")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {/* Reject Dialog */}
      {rejectDialog && (
        <Dialog open onOpenChange={(v) => { if (!v) setRejectDialog(null); }}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t("Reject Payment")}</DialogTitle>
            </DialogHeader>
            <FormField label={t("Reason")} name="reject_reason">
              <Textarea
                rows={3}
                placeholder={t("Reason for rejection...")}
                value={rejectDialog.reason}
                onChange={(e) => setRejectDialog({ ...rejectDialog, reason: e.target.value })}
              />
            </FormField>
            <DialogFooter>
              <Button variant="outline" onClick={() => setRejectDialog(null)}>{t("Cancel")}</Button>
              <Button variant="destructive" onClick={rejectPayment}>{t("Reject")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </ListPage>
  );
}
