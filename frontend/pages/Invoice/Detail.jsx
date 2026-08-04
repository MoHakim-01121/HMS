import DetailCard from "../../components/shadcn/detail-card.jsx";
import DetailGrid from "../../components/shadcn/detail-grid.jsx";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import Section from "../../components/shadcn/section.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import { DvLink } from "../../components/shadcn/item-row.jsx";
import FooterSummary from "../../components/shadcn/footer-summary.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import LastBilling from "../../components/ui/LastBilling.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

function heroPill(total, remaining) {
  if (remaining === 0) return { label: "Paid", tone: "green" };
  if (remaining < total) return { label: "Partial", tone: "yellow" };
  return { label: "Unpaid", tone: "red" };
}

// Rentang menginap gabungan dari semua reservasi (dd/mm/yyyy).
function stayRange(reservations) {
  const key = (s) => { const [d, m, y] = s.split("/"); return `${y}${m}${d}`; };
  const ins = reservations.map((r) => r.check_in).filter(Boolean);
  const outs = reservations.map((r) => r.check_out).filter(Boolean);
  if (!ins.length || !outs.length) return null;
  const start = ins.reduce((a, b) => (key(a) <= key(b) ? a : b));
  const end = outs.reduce((a, b) => (key(a) >= key(b) ? a : b));
  return `${start} - ${end}`;
}

function openDraft(type, pk, waSend) {
  window.dispatchEvent(new CustomEvent("open-draft", { detail: { type, pk, waSend } }));
}

export default function Detail({ invoice, reservations, payments, due_alert, wa_send, last_billing }) {
  const openForm = useFormModal();
  const perms = usePerms();
  const { t } = useI18n();
  const paid = invoice.remaining_sar === 0;
  const pill = heroPill(invoice.total_sar, invoice.remaining_sar);
  const range = stayRange(reservations);
  const receivedTotal = payments.reduce((s, p) => s + (p.amount_sar_int || 0), 0);
  const reservationsTotal = reservations.reduce((s, r) => s + (r.total_int || 0), 0);
  const remainingTotal = reservations.reduce((s, r) => s + Math.max(0, r.remaining_int || 0), 0);

  return (
    <div className="page dv-page hms-dv-page shadcn-root">
      <PageBack href="/invoice/" label={t("Back")} />

      <DetailCard
        crumbs={[{ label: t("Invoices"), href: "/invoice/" }]}
        kicker={invoice.invoice_number}
        title={invoice.customer_name}
        sub={t("Hotel invoice")}
        pill={{ label: t(pill.label), tone: pill.tone }}
        actions={
          <>
            <a className="hms-dv-act" href={`/invoice/${invoice.pk}/pdf/`} target="_blank" rel="noreferrer">PDF</a>
            {perms.can("invoice", "edit") && (
              <button type="button" className="hms-dv-act" onClick={() => openForm(`/invoice/${invoice.pk}/edit/`)}>{t("Edit")}</button>
            )}
          </>
        }
      >
        {/* Empat baris, dua kolom penuh — persis anatomi CL detail. Nomor
            invoice tidak diulang di sini karena sudah jadi breadcrumb, dan
            angka sisa tagihan pindah dari tile kanan ke baris grid: tile itu
            memepetkan grid sampai rentang tanggal Reservations wrap, dan pada
            invoice yang belum dibayar sama sekali ia hanya mengulang Total
            Amount di footer. */}
        <DetailGrid
          rows={[
            { label: t("Issued"), value: invoice.issued_date || t("Not issued"), icon: "calendar" },
            {
              label: t("Reservations"),
              icon: "hotels",
              value: (
                <>
                  {reservations.length} {t(reservations.length === 1 ? "reservation" : "reservations")}
                  {range ? <span className="hms-dv-mval-sub"> · {range}</span> : null}
                </>
              ),
            },
            { label: t("Payments"), icon: "wallet", value: t("{count} received", { count: payments.length }) },
            {
              label: paid ? t("Paid in full") : t("Amount due"),
              icon: "invoice",
              color: paid ? "var(--green)" : "var(--red)",
              value: (
                <>
                  {fmt(paid ? invoice.total_paid_sar : invoice.remaining_sar)} SAR
                  {!paid && due_alert ? <span className="hms-dv-mval-sub"> · {due_alert.msg}</span> : null}
                </>
              ),
            },
          ]}
        />

        <Section label={t("Reservations")} icon="hotels" count={reservations.length || null}>
          <DetailTable
            columns={[
              {
                header: "#RSV",
                strong: true,
                render: (res) => (
                  <>
                    {res.number}
                    {res.cl_pk ? <DvLink href={`/cl/${res.cl_pk}/`}>CL</DvLink> : null}
                  </>
                ),
              },
              { header: t("Hotel"), render: (res) => res.hotel },
              { header: t("Check in"), render: (res) => res.check_in || t("Not set") },
              { header: t("Check out"), render: (res) => res.check_out || t("Not set") },
              {
                // Remaining now has its own column, so the pill carries the
                // state word only instead of repeating the figure.
                header: t("Status"),
                align: "right",
                render: (res) =>
                  res.remaining_int <= 0 ? (
                    <StatusPill small label={t("Settled")} tone="green" />
                  ) : res.remaining_int < res.total_int ? (
                    <StatusPill small label={t("Partial")} tone="yellow" />
                  ) : (
                    <StatusPill small label={t("Unpaid")} tone="red" />
                  ),
              },
              { header: t("Total"), align: "right", strong: true, render: (res) => fmt(res.total_int) },
              {
                header: t("Remaining"),
                align: "right",
                render: (res) => fmt(Math.max(0, res.remaining_int || 0)),
              },
            ]}
            rows={reservations}
            empty={t("No reservations")}
            footer={
              reservations.length
                ? [{
                    label: t("Total"),
                    value: [`${fmt(reservationsTotal)} SAR`, `${fmt(remainingTotal)} SAR`],
                    tone: [null, remainingTotal > 0 ? "red" : null],
                    total: true,
                  }]
                : null
            }
          />
        </Section>

        <Section label={t("Payments")} icon="wallet" count={payments.length || null} right="SAR">
          <DetailTable
            columns={[
              // The payload carries no payment reference of its own; the only
              // reference a payment has is the reservation it settles.
              { header: "#REF", strong: true, render: (p) => p.linked_number || t("Unlinked") },
              { header: t("Date"), render: (p) => p.payment_date || t("Not set") },
              {
                header: t("Method"),
                render: (p) => (
                  <>
                    {p.method || t("Payment")}
                    {p.proof_url ? <DvLink href={p.proof_url} newTab>{t("Proof")}</DvLink> : null}
                  </>
                ),
              },
              // Original currency and rate get their own columns now, so the
              // "20,000,000 IDR ÷ 4810.00" sub-line under Method is retired.
              { header: t("Amount"), align: "right", render: (p) => `${fmt(p.amount_int)} ${p.currency}` },
              // SAR pays itself at parity, so the column shows 1.00 rather than
              // a placeholder — every row keeps a real number.
              { header: t("Rate"), align: "right", render: (p) => (p.currency === "SAR" ? "1.00" : p.exchange_rate_fmt) },
              { header: t("Amount SAR"), align: "right", strong: true, render: (p) => fmt(p.amount_sar_int) },
            ]}
            rows={payments}
            empty={t("No payments")}
            footer={payments.length ? [{ label: t("Total received"), value: `${fmt(receivedTotal)} SAR`, total: true, tone: "green" }] : null}
          />
        </Section>

        {/* Billing turun jadi strip penutup kartu: isinya satu aksi plus log
            terakhir, tidak cukup berat untuk section sendiri. Angka Paid /
            Total Amount yang dulu di sini dihapus — masing-masing tabel sudah
            membawa totalnya, jadi footer hanya mengulang.
            Kirim pesan memanggil /billing/send/, yang di server dijaga
            invoice.edit — role read-only cuma melihat lognya. */}
        <FooterSummary
          left={<LastBilling last={last_billing} />}
          right={
            perms.can("invoice", "edit") ? (
              <Button type="button" onClick={() => openDraft(paid ? "invoice_lunas" : "invoice", invoice.pk, wa_send)}>
                {paid ? t("Paid Message") : t("Draft Message")}
              </Button>
            ) : null
          }
        />
      </DetailCard>
    </div>
  );
}
