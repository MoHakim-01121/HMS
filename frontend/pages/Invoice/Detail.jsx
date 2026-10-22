import { useState } from "react";
import { router } from "@inertiajs/react";
import { DPage, DTop, DHead, DBanner, DBtn, DCard, DTabs, DLog, DPill, dayMonth } from "../../components/shadcn/detail-a.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtStay, toDate } from "../../utils/format.js";

// Invoice detail, the "Invoice Detail" artboard on the Record View HMS canvas:
// the head card carries the balance and dates as facts, then Reservations and
// Payments as plain tables, then a tabbed card for Pay to and Activity.
// "Pay to" lists the issuing branch's accounts marked "Show on invoice".

function resStatus(r) {
  if (r.remaining_int <= 0 && r.paid_int <= 0 && r.credited_int > 0) return { label: "Credited", tone: "gray" };
  if (r.remaining_int <= 0) return { label: "Settled", tone: "green" };
  if (r.paid_int > 0) return { label: "Partial", tone: "amber" };
  return { label: "Unpaid", tone: "red" };
}

function openDraft(type, pk, waSend) {
  window.dispatchEvent(new CustomEvent("open-draft", { detail: { type, pk, waSend } }));
}

// One "Pay to" account with a copy button for the transfer details.
function PayTo({ t, acc }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    const text = [acc.bank_name, acc.account_identifier, acc.account_name ? `a/n ${acc.account_name}` : null].filter(Boolean).join(" ");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch { /* clipboard blocked — the number is still selectable */ }
  };
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
      <div>
        <div style={{ fontSize: 14, fontWeight: 600 }}>{acc.bank_name} <span style={{ marginLeft: 4, fontSize: 12, fontWeight: 500, color: "var(--muted-foreground)" }}>{acc.currency}</span></div>
        <div style={{ marginTop: 2, fontSize: 14, fontVariantNumeric: "tabular-nums" }}>{acc.account_identifier}</div>
        {acc.account_name ? <div style={{ fontSize: 12, color: "var(--muted-foreground)" }}>{acc.account_name}</div> : null}
      </div>
      <button type="button" className="da-btn soft" onClick={copy} aria-label={t("Copy account details")}>{copied ? t("Copied") : t("Copy")}</button>
    </div>
  );
}

export default function Detail({
  invoice, reservations, payments, due_alert, wa_send, logs = [], pay_to = [], excess_sar = 0,
  overpaid = [], overpaid_payments = [],
  void: voidInfo = null, credit_notes = [], credited_sar = 0, can_void = false,
}) {
  const openForm = useFormModal();
  const perms = usePerms();
  const { t } = useI18n();
  const [confirm, confirmDialog] = useConfirm();
  const [tab, setTab] = useState(pay_to.length ? "pay" : "act");

  const isVoid = !!voidInfo;
  const dueSar = isVoid ? 0 : invoice.total_sar - credited_sar;
  const paid = !isVoid && invoice.remaining_sar <= 0;
  const partial = !paid && invoice.total_paid_sar > 0;
  const badge = isVoid ? { label: "Void", tone: "gray" }
    : paid ? { label: "Paid", tone: "green" } : partial ? { label: "Partial", tone: "amber" } : { label: "Unpaid", tone: "red" };
  const pct = dueSar > 0 ? Math.min(100, Math.round((invoice.total_paid_sar / dueSar) * 100)) : isVoid ? 0 : 100;

  const ins = reservations.map((r) => toDate(r.check_in)).filter(Boolean);
  const outs = reservations.map((r) => toDate(r.check_out)).filter(Boolean);
  const stay = ins.length && outs.length ? fmtStay(new Date(Math.min(...ins)), new Date(Math.max(...outs))) : null;

  const canEdit = perms.can("invoice", "edit") && !isVoid;
  // Voiding and credit notes change what the client owes: a money decision.
  const canCredit = perms.can("payments", "approve");
  const canMoveMoney = perms.can("payments", "edit");
  const moveExcessToDeposit = () =>
    confirm({
      title: t("Move {n} SAR to deposit?", { n: fmt(excess_sar) }),
      message: t("What {client} paid beyond this invoice becomes their deposit. It can then pay other invoices, be transferred, or be refunded.", { client: invoice.customer_name }),
      confirmLabel: t("Move to deposit"),
      onConfirm: () => router.post(`/finance/invoices/${invoice.pk}/excess-to-deposit/`),
    });

  const menu = [
    !paid && !isVoid && { label: t("Record payment"), icon: "pay", href: `/finance/payments/?invoice=${invoice.pk}` },
    canEdit && { label: paid ? t("Paid message") : t("Draft message"), icon: "message", onClick: () => openDraft(paid ? "invoice_lunas" : "invoice", invoice.pk, wa_send) },
    { label: t("Download PDF"), icon: "pdf", href: `/invoice/${invoice.pk}/pdf/`, external: true },
    paid && invoice.receipt && { label: t("Receipt"), icon: "receipt", href: `/receipts/${invoice.receipt.pk}/pdf/`, external: true },
    canEdit && { label: t("Edit"), icon: "edit", separator: true, onClick: () => openForm(`/invoice/${invoice.pk}/edit/`) },
    canCredit && !isVoid && { label: t("Credit note…"), icon: "file", separator: !canEdit, onClick: () => openForm(`/finance/invoices/${invoice.pk}/credit-notes/new/`) },
    canCredit && can_void && { label: t("Void invoice…"), icon: "close", danger: true, separator: true, onClick: () => openForm(`/finance/invoices/${invoice.pk}/void/`) },
    perms.can("invoice", "delete") && {
      label: t("Delete invoice…"),
      icon: "trash",
      danger: true,
      separator: !(canCredit && can_void),
      onClick: () =>
        confirm({
          title: t("Delete {number}?", { number: invoice.invoice_number }),
          message: t("The invoice for {client} will be removed. Invoices with recorded payments can't be deleted. This can't be undone.", {
            client: invoice.customer_name,
          }),
          danger: true,
          onConfirm: () => router.post(`/invoice/${invoice.pk}/delete/`),
        }),
    },
  ];

  const dueTone = due_alert?.type === "red" ? "danger" : due_alert ? "warning" : undefined;
  const facts = [
    {
      k: isVoid ? t("Invoice total (void)") : t("Balance due"),
      strong: true,
      v: isVoid
        ? <s>{fmt(invoice.total_sar)} SAR</s>
        : <>{fmt(Math.max(0, invoice.remaining_sar))} SAR <span className="dim">· {t("{pct}% paid", { pct })}</span></>,
    },
    !isVoid && (paid
      ? invoice.settled_date && { k: t("Settled"), v: invoice.settled_date }
      : { k: t("Due"), v: invoice.due_date || t("No due date"), tone: dueTone }),
    { k: t("Issued"), v: invoice.issued_date || t("Not issued") },
    stay && { k: t("Stay"), v: stay },
    {
      k: t("Client"),
      v: invoice.client ? <a href={`/clients/${invoice.client.pk}/`}>{invoice.client.name}</a> : invoice.customer_name,
    },
    invoice.client?.phone && { k: t("Phone"), v: invoice.client.phone },
    invoice.prepared_by && { k: t("Prepared by"), v: invoice.prepared_by },
    invoice.branch && { k: t("Branch"), v: invoice.branch.name },
  ];

  // Activity: audit log + credit notes + recorded payments, newest first.
  const events = [
    ...logs.map((l, i) => {
      const c = l.changes?.length === 1 ? l.changes[0] : null;
      let body;
      if (l.action === "create") body = t("Invoice created");
      else if (c) body = <>{t(c.label)} {c.before ? <s>{c.before}</s> : t("(empty)")} → <b>{c.after || t("(empty)")}</b></>;
      else body = [t("Invoice edited"), l.changes?.length ? l.changes.map((x) => t(x.label)).join(", ") : null].filter(Boolean).join(": ");
      return { key: `log-${i}`, iso: l.date, when: dayMonth(l.date || l.timestamp), body, by: l.by };
    }),
    ...credit_notes.map((cn) => ({
      key: `cn-${cn.id}`,
      iso: cn.date,
      when: dayMonth(cn.date),
      body: <>{cn.status === "voided" ? t("Credit note voided") : t("Credit note issued")} <a href={`/finance/credit-notes/${cn.id}/pdf/`} target="_blank" rel="noreferrer">{cn.number}</a> <span className="by">· {cn.reason}, −{fmt(cn.amount_sar)} SAR</span></>,
      by: t("Finance"),
    })),
    ...payments.map((p) => ({
      key: `pay-${p.id}`,
      iso: p.payment_iso,
      when: dayMonth(p.payment_iso || p.payment_label),
      body: <>{t("Payment recorded")} <a href={`/finance/payments/${p.id}/`}>{p.payment_number}</a> <span className="by">· {[p.method, p.proof_url ? t("proof attached") : null, `${fmt(p.amount_sar_int)} SAR`].filter(Boolean).join(", ")}</span></>,
      by: p.confirmed_by || t("Finance"),
    })),
  ].sort((a, b) => (b.iso || "").localeCompare(a.iso || ""));

  return (
    <DPage>
      <DTop href="/invoice/" stamp={invoice.created_at ? t("Created {date}", { date: invoice.created_at }) : undefined} />

      {isVoid ? (
        <DBanner tone="gray">
          <b>{t("This invoice is void.")}</b>{" "}
          {[voidInfo.reason, voidInfo.by && voidInfo.at ? t("Voided by {name} on {date}.", { name: voidInfo.by, date: voidInfo.at }) : null].filter(Boolean).join(". ")}
        </DBanner>
      ) : null}

      {!isVoid && overpaid.length > 0 ? (
        <DBanner
          actions={canMoveMoney ? (
            <>
              {overpaid_payments.map((p) => (
                <DBtn key={p.id} href={`/finance/payments/${p.id}/?apply=1`}>
                  {overpaid_payments.length > 1 ? t("Reallocate {number}", { number: p.number }) : t("Allocate to another reservation")}
                </DBtn>
              ))}
              <DBtn primary onClick={moveExcessToDeposit}>{t("Move to deposit")}</DBtn>
            </>
          ) : null}
        >
          <b>{t("Overpaid {n} SAR.", { n: fmt(excess_sar) })}</b>{" "}
          {overpaid.map((o) => `${o.number}: ${fmt(o.excess_sar)} SAR`).join(" · ")}
        </DBanner>
      ) : null}

      <DHead title={invoice.invoice_number} badge={{ label: t(badge.label), tone: badge.tone }} menu={menu} facts={facts} />

      <DCard title={t("Reservations")} meta={t("Amounts in SAR")}>
        <div className="da-scroll">
          <table className="da-t">
            <thead><tr><th>{t("Reservation")}</th><th>{t("Stay")}</th><th>{t("Status")}</th><th className="n">{t("Total")}</th><th className="n">{t("Paid")}</th><th className="n">{t("Remaining")}</th></tr></thead>
            <tbody>
              {reservations.length ? reservations.map((r) => {
                const st = isVoid ? { label: "Void", tone: "gray" } : resStatus(r);
                const a = toDate(r.check_in);
                const b = toDate(r.check_out);
                const nights = a && b ? Math.round((b - a) / 86400000) : null;
                return (
                  <tr key={r.id}>
                    <td>
                      {r.cl_pk ? <a href={`/cl/${r.cl_pk}/`}>{r.number}</a> : <b>{r.number}</b>}
                      <span className="sub">{r.hotel}</span>
                      {r.penalty_int > 0 ? (
                        <span className="sub">
                          {t("incl. cancellation penalty {n}", { n: fmt(r.penalty_int) })}
                          {r.penalty_pk ? <> · <a href={`/penalty/${r.penalty_pk}/`}>{r.penalty_number}</a></> : null}
                        </span>
                      ) : null}
                    </td>
                    <td className="nw">
                      {fmtStay(a, b) || t("Not set")}
                      {nights != null ? <span className="sub">{nights} {t(nights === 1 ? "night" : "nights")}</span> : null}
                    </td>
                    <td><DPill sm tone={st.tone}>{t(st.label)}</DPill></td>
                    <td className="n">{fmt(r.total_int)}</td>
                    <td className="n mut">{fmt(r.paid_int)}</td>
                    <td className="n bold">
                      {fmt(Math.max(0, r.remaining_int || 0))}
                      {r.credited_int > 0 && !isVoid ? <span className="sub">{t("−{n} credited", { n: fmt(r.credited_int) })}</span> : null}
                    </td>
                  </tr>
                );
              }) : <tr><td colSpan={6} className="empty">{t("No reservations")}</td></tr>}
            </tbody>
            <tfoot>
              {credited_sar > 0 ? (
                <>
                  <tr className="soft"><td colSpan={5}>{t("Invoice total")}</td><td className="n">{fmt(invoice.total_sar)} SAR</td></tr>
                  <tr className="soft after"><td colSpan={5}>{t("Credit notes")}</td><td className="n">−{fmt(credited_sar)} SAR</td></tr>
                  <tr className="after"><td colSpan={5}>{t("Amount due")}</td><td className="n">{fmt(dueSar)} SAR</td></tr>
                </>
              ) : (
                <tr>
                  <td colSpan={5}>{isVoid ? t("Invoice total (void)") : t("Invoice total")}</td>
                  <td className="n">{isVoid ? <s>{fmt(invoice.total_sar)}</s> : fmt(invoice.total_sar)} SAR</td>
                </tr>
              )}
            </tfoot>
          </table>
        </div>
      </DCard>

      <DCard title={t("Payments")} meta={t("Read-only, managed in Finance")}>
        {payments.length ? (
          <div className="da-scroll">
            <table className="da-t">
              <thead><tr><th>{t("Payment")}</th><th>{t("Method")}</th><th className="n">{t("Amount")}</th><th className="n">SAR</th></tr></thead>
              <tbody>
                {payments.map((p) => (
                  <tr key={p.id}>
                    <td><a href={`/finance/payments/${p.id}/`}>{p.payment_number}</a><span className="sub nw">{p.payment_label || t("Not set")}</span></td>
                    <td>
                      {p.method || t("Payment")}
                      {p.proof_url ? <a className="da-tag xs" style={{ marginLeft: 6 }} href={p.proof_url} target="_blank" rel="noreferrer">{t("Proof")}</a> : null}
                      {p.unallocated_sar > 0 ? <a className="da-tag xs" style={{ marginLeft: 6, color: "var(--warning-text)" }} href={`/finance/payments/${p.id}/`}>{t("Apply")}</a> : null}
                    </td>
                    <td className="n">
                      {fmt(p.amount_int)} {p.currency}
                      {p.currency !== "SAR" ? <span className="sub">1 SAR = {fmt(p.exchange_rate)} {p.currency}</span> : null}
                    </td>
                    <td className="n bold">{fmt(p.amount_sar_int)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot><tr><td colSpan={3}>{t("Total received")}</td><td className="n good">{fmt(invoice.total_paid_sar)} SAR</td></tr></tfoot>
            </table>
          </div>
        ) : <div className="da-empty">{t("No payments recorded yet.")}</div>}
      </DCard>

      {credit_notes.length ? (
        <DCard title={t("Credit notes")} meta={t("Reduce what this invoice bills")}>
          <div className="da-scroll">
            <table className="da-t">
              <thead><tr><th>{t("Credit note")}</th><th>{t("Reason")}</th><th className="n">SAR</th><th className="acts" /></tr></thead>
              <tbody>
                {credit_notes.map((cn) => {
                  const voided = cn.status === "voided";
                  return (
                    <tr key={cn.id} className={voided ? "void" : undefined}>
                      <td>
                        <a href={`/finance/credit-notes/${cn.id}/pdf/`} target="_blank" rel="noreferrer">{cn.number}</a>
                        {voided ? <> <DPill sm>{t("Void")}</DPill></> : null}
                        <span className="sub nw">{cn.date}</span>
                      </td>
                      <td className="desc">
                        {voided && cn.voided_reason ? `${cn.reason} · ${t("voided")}: ${cn.voided_reason}` : cn.reason}
                        {cn.to_deposit_sar > 0 && !voided ? <span className="sub">{t("{n} SAR to client deposit", { n: fmt(cn.to_deposit_sar) })}</span> : null}
                      </td>
                      <td className="n bold">{voided ? fmt(cn.amount_sar) : `−${fmt(cn.amount_sar)}`}</td>
                      <td className="n">
                        {canCredit && !voided ? (
                          <button type="button" className="da-btn soft" onClick={() => openForm(`/finance/credit-notes/${cn.id}/void/`)}>{t("Void")}</button>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </DCard>
      ) : null}

      <section className="da-card">
        <DTabs
          value={tab}
          onChange={setTab}
          tabs={[
            ...(pay_to.length ? [{ key: "pay", label: t("Pay to") }] : []),
            { key: "act", label: t("Activity"), count: events.length },
          ]}
        />
        {tab === "pay" ? (
          <div role="tabpanel" className="da-rows" style={{ paddingTop: 8, paddingBottom: 12 }}>
            {pay_to.map((acc) => <div key={acc.id} style={{ display: "block", padding: "12px 0" }}><PayTo t={t} acc={acc} /></div>)}
          </div>
        ) : (
          <div role="tabpanel"><DLog rows={events} empty={t("No activity recorded yet.")} /></div>
        )}
      </section>

      {confirmDialog}
    </DPage>
  );
}
