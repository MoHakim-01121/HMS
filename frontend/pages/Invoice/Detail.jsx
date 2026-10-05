import { useState } from "react";
import { router } from "@inertiajs/react";
import KebabMenu from "../../components/shadcn/kebab-menu.jsx";
import { RvBack } from "../../components/shadcn/record-view.jsx";
import { Icon } from "../../components/icons.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import CreditNotesSection from "../../components/shadcn/credit-notes-section.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtStay, toDate } from "../../utils/format.js";

// Invoice detail, from the Claude Design file "Invoice Detail.dc.html"
// (project 7cf7c6a1…), sharing CL Detail's language: identity + balance ring
// in the hero, one status sentence with the actions beside it, grid-row
// tables for reservations and payments, a key/value rail and an activity
// timeline. "Pay to" lists the issuing branch's bank accounts marked "Show on
// invoice" (Finance → Bank Balances); the design's "Notes" block is left out
// because invoices carry no note field.


function resStatus(r) {
  if (r.remaining_int <= 0 && r.paid_int <= 0 && r.credited_int > 0) return { label: "Credited", tone: "gray" };
  if (r.remaining_int <= 0) return { label: "Settled", tone: "green" };
  if (r.paid_int > 0) return { label: "Partial", tone: "yellow" };
  return { label: "Unpaid", tone: "red" };
}

function openDraft(type, pk, waSend) {
  window.dispatchEvent(new CustomEvent("open-draft", { detail: { type, pk, waSend } }));
}

function Pill({ tone, children, small }) {
  return <span className={`hms-dv-pill ${small ? "hms-iv-pill-sm" : "hms-cl-badge"} tone-${tone}`}>{children}</span>;
}

function RefChip({ href, children, mono }) {
  return (
    <a className={mono ? "hms-iv-chip mono" : "hms-iv-chip"} href={href} target={href.startsWith("/media") ? "_blank" : undefined} rel="noreferrer">
      {children}
      <Icon name="arrow-up-right" size={10} strokeWidth={2} aria-hidden="true" />
    </a>
  );
}

// One "Pay to" account with a copy button for the transfer details.
function PayToAccount({ t, acc }) {
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
    <div className="hms-iv-payto">
      <div className="h">
        <span className="bank">{acc.bank_name} <span className="cur">{acc.currency}</span></span>
        <button type="button" className="hms-iv-copy" onClick={copy} aria-label={t("Copy account details")}>
          <Icon name={copied ? "check" : "copy"} size={12} strokeWidth={1.8} />
          {copied ? t("Copied") : t("Copy")}
        </button>
      </div>
      <div className="no">{acc.account_identifier}</div>
      {acc.account_name ? <div className="holder">{acc.account_name}</div> : null}
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
  const [showAll, setShowAll] = useState(false);

  const isVoid = !!voidInfo;
  const dueSar = isVoid ? 0 : invoice.total_sar - credited_sar;
  const paid = !isVoid && invoice.remaining_sar <= 0;
  const partial = !paid && invoice.total_paid_sar > 0;
  const badge = isVoid ? { label: "Void", tone: "gray" }
    : paid ? { label: "Paid", tone: "green" } : partial ? { label: "Partial", tone: "yellow" } : { label: "Unpaid", tone: "red" };
  const pct = dueSar > 0 ? Math.min(100, Math.round((invoice.total_paid_sar / dueSar) * 100)) : isVoid ? 0 : 100;

  const ins = reservations.map((r) => toDate(r.check_in)).filter(Boolean);
  const outs = reservations.map((r) => toDate(r.check_out)).filter(Boolean);
  const stay = ins.length && outs.length
    ? fmtStay(new Date(Math.min(...ins)), new Date(Math.max(...outs)))
    : null;

  const note = isVoid
    ? {
        tone: "gray",
        title: t("This invoice is void."),
        text: [voidInfo.reason && !/[.!?]$/.test(voidInfo.reason) ? `${voidInfo.reason}.` : voidInfo.reason, voidInfo.by && voidInfo.at ? t("Voided by {name} on {date}.", { name: voidInfo.by, date: voidInfo.at }) : null].filter(Boolean).join(" "),
      }
    : paid
    ? {
        tone: "green",
        title: t("Paid in full."),
        text: reservations.length
          ? t(reservations.length === 1 ? "The reservation is settled." : "All {n} reservations are settled.", { n: reservations.length })
          : "",
      }
    : due_alert
      ? { tone: due_alert.type === "red" ? "red" : "yellow", title: t(due_alert.msg), text: t("Payment is still owed.") }
      : {
          tone: partial ? "yellow" : "red",
          title: t("Payment is still owed."),
          text: invoice.due_date ? "" : t("No due date is set on this invoice."),
        };

  const dueLine = isVoid ? null : paid
    ? invoice.settled_date ? { k: t("Settled"), v: invoice.settled_date } : null
    : invoice.due_date ? { k: t("Due"), v: invoice.due_date } : null;

  const canEdit = perms.can("invoice", "edit") && !isVoid;
  const canCredit = perms.can("invoice", "delete");
  const canMoveMoney = perms.can("payments", "edit");
  const moveExcessToDeposit = () =>
    confirm({
      title: t("Move {n} SAR to deposit?", { n: fmt(excess_sar) }),
      message: t("What {client} paid beyond this invoice becomes their deposit. It can then pay other invoices, be transferred, or be refunded.", { client: invoice.customer_name }),
      confirmLabel: t("Move to deposit"),
      onConfirm: () => router.post(`/finance/invoices/${invoice.pk}/excess-to-deposit/`),
    });
  const menuItems = [
    canEdit && { label: t("Edit"), icon: "edit", onClick: () => openForm(`/invoice/${invoice.pk}/edit/`) },
    canCredit && !isVoid && { label: t("Credit note…"), icon: "file-text", onClick: () => openForm(`/finance/invoices/${invoice.pk}/credit-notes/new/`) },
    canCredit && can_void && { label: t("Void invoice…"), icon: "close", danger: true, separator: true, onClick: () => openForm(`/finance/invoices/${invoice.pk}/void/`) },
    perms.can("invoice", "delete") && {
      label: t("Delete invoice…"),
      icon: "trash",
      danger: true,
      separator: true,
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

  // Activity: audit log + recorded payments + a passed due date, newest first.
  const events = [
    ...logs.map((l, i) => {
      const c = l.changes?.length === 1 ? l.changes[0] : null;
      return {
        // Index, not timestamp: two edits in the same minute share one.
        key: `log-${i}`,
        iso: l.date,
        kind: l.action === "create" ? "doc" : "status",
        title: l.action === "create" ? t("Invoice created") : c ? t(c.label) : t("Invoice edited"),
        from: c ? c.before : null,
        to: c ? c.after : null,
        detail: !c && l.changes?.length ? l.changes.map((x) => t(x.label)).join(", ") : "",
        when: l.timestamp.slice(0, 11),
        actor: l.by,
      };
    }),
    ...credit_notes.map((cn) => ({
      key: `cn-${cn.id}`,
      iso: cn.date,
      kind: "status",
      title: cn.status === "voided" ? t("Credit note voided") : t("Credit note issued"),
      ref: cn.number,
      refHref: `/finance/credit-notes/${cn.id}/pdf/`,
      detail: `${cn.reason} · −${fmt(cn.amount_sar)} SAR`,
      when: cn.date,
      actor: t("Finance"),
    })),
    ...payments.map((p) => ({
      key: `pay-${p.id}`,
      iso: p.payment_iso,
      kind: "pay",
      title: t("Payment recorded"),
      ref: p.payment_number,
      refHref: `/finance/payments/${p.id}/`,
      detail: [p.method, p.proof_url ? t("proof attached") : null, `${fmt(p.amount_sar_int)} SAR`].filter(Boolean).join(", "),
      when: p.payment_label,
      actor: p.confirmed_by || t("Finance"),
    })),
    ...(!paid && !isVoid && due_alert?.type === "red" && invoice.due_iso && invoice.due_iso < new Date().toISOString().slice(0, 10)
      ? [{ key: "due", iso: invoice.due_iso, kind: "alert", title: t("Due date passed"), detail: t("Payment is still owed."), when: invoice.due_date, actor: t("System") }]
      : []),
  ].sort((a, b) => (b.iso || "").localeCompare(a.iso || ""));
  const shownEvents = showAll ? events : events.slice(0, 3);

  return (
    <div className="page shadcn-root hms-rv-page hms-cl hms-iv">
      <RvBack href="/invoice/" label={t("Back")} stamp={invoice.created_at ? t("Created {date}", { date: invoice.created_at }) : undefined} />

      <header className="hms-cl-hero">
        <div className="hms-cl-hero-top hms-iv-hero-top">
          <div className="hms-cl-hero-id">
            <div className="hms-rv-hero-kicker">
              <span className="hms-rv-kicker">{invoice.invoice_number}</span>
              <Pill tone={badge.tone}>{t(badge.label)}</Pill>
            </div>
            <h1 className="hms-cl-h1">{invoice.customer_name}</h1>
            {invoice.issued_date || stay ? (
              <div className="hms-iv-sub">
                {invoice.issued_date ? <span>{t("Issued {date}", { date: invoice.issued_date })}</span> : <span>{t("Not issued")}</span>}
                {stay ? <><span className="sep" /><span>{stay}</span></> : null}
              </div>
            ) : null}
          </div>

          <div className="hms-iv-balance">
            <div className="fig">
              <div className="hms-rv-lbl">{t("Balance due")}</div>
              <div className="amt">
                <span className="n">{fmt(Math.max(0, invoice.remaining_sar))}</span>
                <span className="u">SAR</span>
              </div>
              {dueLine ? (
                <div className="line">{dueLine.k} <strong>{dueLine.v}</strong></div>
              ) : null}
            </div>
            <div
              className="hms-iv-ring"
              style={{ background: `conic-gradient(${paid ? "var(--green)" : "var(--foreground)"} 0 ${pct}%, var(--secondary) ${pct}% 100%)`, opacity: isVoid ? 0.4 : 1 }}
              role="img"
              aria-label={t("{pct}% paid", { pct })}
            >
              <span>{pct}%</span>
            </div>
          </div>
        </div>

        {!isVoid && overpaid.length > 0 && (
          <div className="hms-cl-note hms-iv-note">
            <div className="l">
              <span className="hms-cl-note-ico tone-yellow">!</span>
              <p>
                <strong>{t("Overpaid {n} SAR.", { n: fmt(excess_sar) })}</strong>{" "}
                {overpaid.map((o) => `${o.number}: ${fmt(o.excess_sar)} SAR`).join(" · ")}.{" "}
                {t("Allocate it to another reservation of this client, or move it to their deposit.")}
              </p>
            </div>
            {canMoveMoney && (
              <div className="hms-cl-actions">
                {overpaid_payments.map((p) => (
                  <a key={p.id} className="hms-rv-btn" href={`/finance/payments/${p.id}/?apply=1`}>
                    {overpaid_payments.length > 1
                      ? t("Reallocate {number}", { number: p.number })
                      : t("Allocate to another reservation")}
                  </a>
                ))}
                <button type="button" className="hms-rv-btn" onClick={moveExcessToDeposit}>{t("Move to deposit")}</button>
              </div>
            )}
          </div>
        )}

        <div className="hms-cl-note hms-iv-note">
          <div className="l">
            <span className={`hms-cl-note-ico tone-${note.tone}`}>
              {note.tone === "green" ? <Icon name="check" size={11} strokeWidth={2.2} /> : "!"}
            </span>
            <p>
              <strong>{note.title}</strong> {note.text}
            </p>
          </div>
          <div className="hms-cl-actions">
            {!paid && !isVoid && (
              <a className="hms-rv-btn primary" href={`/finance/payments/?invoice=${invoice.pk}`}>{t("Record payment")}</a>
            )}
            {canEdit && (
              <button type="button" className="hms-rv-btn" onClick={() => openDraft(paid ? "invoice_lunas" : "invoice", invoice.pk, wa_send)}>
                <Icon name="message" size={14} strokeWidth={1.6} />
                {paid ? t("Paid message") : t("Draft message")}
              </button>
            )}
            <a className="hms-rv-btn" href={`/invoice/${invoice.pk}/pdf/`} target="_blank" rel="noreferrer">
              <Icon name="download" size={14} strokeWidth={1.6} />
              PDF
            </a>
            {paid && invoice.receipt ? (
              <a className="hms-rv-btn" href={`/receipts/${invoice.receipt.pk}/pdf/`} target="_blank" rel="noreferrer">
                <Icon name="invoice" size={14} strokeWidth={1.6} />
                {t("Receipt")}
              </a>
            ) : null}
            <KebabMenu items={menuItems} />
          </div>
        </div>
      </header>

      <div className="hms-cl-grid">
        <main className="hms-cl-main">
          <section className="hms-cl-sec">
            <div className="hms-cl-sech">
              <h2>{t("Reservations")}</h2>
              <span className="meta">{t("Amounts in SAR")}</span>
            </div>
            <div className="hms-iv-grid res">
              <div className="hms-iv-gh">
                <span>{t("Reservation")}</span><span>{t("Stay")}</span><span>{t("Status")}</span>
                <span className="r">{t("Total")}</span><span className="r">{t("Paid")}</span><span className="r">{t("Remaining")}</span>
              </div>
              {reservations.length ? reservations.map((r) => {
                const st = isVoid ? { label: "Void", tone: "gray" } : resStatus(r);
                const a = toDate(r.check_in);
                const b = toDate(r.check_out);
                const nights = a && b ? Math.round((b - a) / 86400000) : null;
                return (
                  <div className="hms-iv-gr" key={r.id}>
                    <div className="c-id">
                      <div className="top">
                        <span className="mono strong">{r.number}</span>
                        {r.cl_pk ? <RefChip href={`/cl/${r.cl_pk}/`}>CL</RefChip> : null}
                      </div>
                      <div className="sub ell">{r.hotel}</div>
                      {r.penalty_int > 0 ? (
                        <div className="sub">
                          {t("incl. cancellation penalty {n}", { n: fmt(r.penalty_int) })}
                          {r.penalty_pk ? <> · <a className="hms-dv-link" href={`/penalty/${r.penalty_pk}/`}>{r.penalty_number}</a></> : null}
                        </div>
                      ) : null}
                    </div>
                    <div className="c-stay">
                      <div className="tab nowrap">{fmtStay(a, b) || t("Not set")}</div>
                      {nights != null ? <div className="sub">{nights} {t(nights === 1 ? "night" : "nights")}</div> : null}
                    </div>
                    <div className="c-st"><Pill small tone={st.tone}>{t(st.label)}</Pill></div>
                    <span className="r tab" data-label={t("Total")}>{fmt(r.total_int)}</span>
                    <span className="r tab dim" data-label={t("Paid")}>{fmt(r.paid_int)}</span>
                    <span className="r tab strong" data-label={t("Remaining")}>
                      {fmt(Math.max(0, r.remaining_int || 0))}
                      {r.credited_int > 0 && !isVoid ? <div className="sub tab">{t("−{n} credited", { n: fmt(r.credited_int) })}</div> : null}
                    </span>
                  </div>
                );
              }) : <div className="hms-iv-empty">{t("No reservations")}</div>}
              {credited_sar > 0 ? (
                <>
                  <div className="hms-iv-gf sub-row">
                    <span>{t("Invoice total")}</span>
                    <span className="v dim">{fmt(invoice.total_sar)} SAR</span>
                  </div>
                  <div className="hms-iv-gf sub-row">
                    <span>{t("Credit notes")}</span>
                    <span className="v dim">−{fmt(credited_sar)} SAR</span>
                  </div>
                  <div className="hms-iv-gf">
                    <span>{t("Amount due")}</span>
                    <span className="v">{fmt(dueSar)} SAR</span>
                  </div>
                </>
              ) : (
                <div className="hms-iv-gf">
                  <span>{isVoid ? t("Invoice total (void)") : t("Invoice total")}</span>
                  <span className="v">{isVoid ? <s>{fmt(invoice.total_sar)}</s> : fmt(invoice.total_sar)} SAR</span>
                </div>
              )}
            </div>
          </section>

          <section className="hms-cl-sec">
            <div className="hms-cl-sech">
              <h2>{t("Payments")}</h2>
              <span className="meta">{t("Read-only, managed in Finance")}</span>
            </div>
            {payments.length ? (
              <div className="hms-iv-grid pay">
                <div className="hms-iv-gh">
                  <span>{t("Payment")}</span><span>{t("Method")}</span><span className="r">{t("Amount")}</span><span className="r">SAR</span>
                </div>
                {payments.map((p) => (
                  <div className="hms-iv-gr" key={p.id}>
                    <div className="c-id">
                      <a className="mono strong hms-iv-link" href={`/finance/payments/${p.id}/`}>{p.payment_number}</a>
                      <div className="sub tab">{p.payment_label || t("Not set")}</div>
                    </div>
                    <div className="c-method">
                      <span>{p.method || t("Payment")}</span>
                      {p.proof_url ? <RefChip href={p.proof_url}>{t("Proof")}</RefChip> : null}
                      {p.unallocated_sar > 0 ? (
                        <a className="hms-iv-chip warn" href={`/finance/payments/${p.id}/`}>{t("Apply")}</a>
                      ) : null}
                    </div>
                    <div className="r c-amt" data-label={t("Amount")}>
                      <div className="tab nowrap">{fmt(p.amount_int)} {p.currency}</div>
                      {p.currency !== "SAR" ? (
                        <div className="sub tab nowrap">1 SAR = {fmt(p.exchange_rate)} {p.currency}</div>
                      ) : null}
                    </div>
                    <span className="r tab strong" data-label="SAR">{fmt(p.amount_sar_int)}</span>
                  </div>
                ))}
                <div className="hms-iv-gf">
                  <span>{t("Total received")}</span>
                  <span className="v green">{fmt(invoice.total_paid_sar)} SAR</span>
                </div>
              </div>
            ) : (
              <div className="hms-iv-empty pad">{t("No payments recorded yet.")}</div>
            )}
          </section>

          <CreditNotesSection creditNotes={credit_notes} canVoid={canCredit} openForm={openForm} />
        </main>

        <aside className="hms-iv-aside">
        <div className="hms-cl-rail hms-iv-rail">
          <dl className="hms-cl-raillist">
            <div>
              <dt>{t("Client")}</dt>
              <dd>
                {invoice.client ? (
                  <a href={`/clients/${invoice.client.pk}/`}>
                    {invoice.client.name}
                    <Icon name="arrow-up-right" size={13} strokeWidth={1.8} aria-hidden="true" />
                  </a>
                ) : <span className="none">{invoice.customer_name}</span>}
              </dd>
            </div>
            {invoice.client?.phone ? (
              <div>
                <dt>{t("Phone")}</dt>
                <dd className="tab">{invoice.client.phone}</dd>
              </div>
            ) : null}
            {invoice.prepared_by ? (
              <div>
                <dt>{t("Prepared by")}</dt>
                <dd>{invoice.prepared_by}</dd>
              </div>
            ) : null}
            <div>
              <dt>{t("Terms")}</dt>
              <dd>
                {invoice.terms_days != null
                  ? t(invoice.terms_days === 0 ? "Due on issue" : "{n} days after issue", { n: invoice.terms_days })
                  : invoice.due_date || <span className="none">{t("No due date")}</span>}
              </dd>
            </div>
            {invoice.branch ? (
              <div>
                <dt>{t("Branch")}</dt>
                <dd>{invoice.branch.name}</dd>
              </div>
            ) : null}
          </dl>
        </div>
        {pay_to.length ? (
          <div className="hms-cl-rail hms-iv-rail">
            <div className="hms-iv-payto-h">
              <span className="hms-rv-lbl">{t("Pay to")}</span>
            </div>
            {pay_to.map((acc) => <PayToAccount key={acc.id} t={t} acc={acc} />)}
          </div>
        ) : null}
        </aside>
      </div>

      {events.length ? (
        <section className="hms-iv-activity">
          <div className="hms-cl-sech flush">
            <h2>{t("Activity")}</h2>
            {events.length > 3 ? (
              <button type="button" className="hms-cl-histcount" onClick={() => setShowAll((v) => !v)} aria-expanded={showAll}>
                {showAll ? t("Show less") : t("Show all {n} events", { n: events.length })}
              </button>
            ) : null}
          </div>
          <ol>
            {shownEvents.map((e) => (
              <li key={e.key}>
                <span className="when">{e.when}</span>
                <div className="what">
                  <span className={`ico ${e.kind}`}>
                    {e.kind === "pay" ? <Icon name="check" size={12} strokeWidth={2.2} />
                      : e.kind === "alert" ? "!"
                      : e.kind === "doc" ? <Icon name="file-text" size={12} strokeWidth={1.7} />
                      : <Icon name="swap" size={12} strokeWidth={1.7} />}
                  </span>
                  <div className="ttl">
                    <span>{e.title}</span>
                    {e.ref ? <RefChip href={e.refHref} mono>{e.ref}</RefChip> : null}
                    {e.from != null || e.to != null ? (
                      <span className="chg">
                        {e.from ? <s>{e.from}</s> : <span className="none">{t("empty")}</span>}
                        <Icon name="arrow-right" size={12} strokeWidth={1.8} className="arr" aria-hidden="true" />
                        {e.to ? <b>{e.to}</b> : <span className="none">{t("empty")}</span>}
                      </span>
                    ) : null}
                  </div>
                </div>
                <span className="detail">{e.detail}</span>
                <span className="actor">{e.actor}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {confirmDialog}
    </div>
  );
}
