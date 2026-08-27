import { useState } from "react";
import { router } from "@inertiajs/react";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import DetailCard from "../../components/shadcn/detail-card.jsx";
import DetailGrid from "../../components/shadcn/detail-grid.jsx";
import DetailAmount from "../../components/shadcn/detail-amount.jsx";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import Section from "../../components/shadcn/section.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

const needsWaGroup = (c) => c.reminder_target !== "PIC" && !c.wa_group;

const dateInputStyle = {
  fontSize: 12.5, fontFamily: "inherit", color: "var(--foreground)",
  background: "transparent", border: "1px solid var(--border)", borderRadius: 8,
  padding: "3px 8px", colorScheme: "light dark",
};

function StatementExport({ pk, t }) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const params = new URLSearchParams();
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  const qs = params.toString();
  return (
    <>
      <input type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} aria-label={t("From")} style={dateInputStyle} />
      <span style={{ color: "var(--muted-foreground)" }}>–</span>
      <input type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} aria-label={t("To")} style={dateInputStyle} />
      <a className="hms-dv-act" href={`/clients/${pk}/statement/pdf/${qs ? `?${qs}` : ""}`} target="_blank" rel="noreferrer">
        {t("Export Statement")}
      </a>
    </>
  );
}

function riskPill(risk) {
  if (risk === "high") return { label: "High Risk", tone: "red" };
  if (risk === "medium") return { label: "Overdue", tone: "yellow" };
  if (risk === "dormant") return { label: "Dormant", tone: "gray" };
  return { label: "OK", tone: "green" };
}

export default function Detail({ client, invoices, cls, activity }) {
  const { t } = useI18n();
  const c = client;
  const openForm = useFormModal();
  const perms = usePerms();
  const [confirm, confirmDialog] = useConfirm();
  const del = () => confirm({ title: t("Delete client"), message: t("Delete client \"{name}\"?", { name: c.name }), onConfirm: () => router.post(`/clients/${c.pk}/delete/`) });
  const scoreColor = c.score >= 70 ? "var(--green)" : c.score >= 40 ? undefined : "var(--red)";
  const pill = riskPill(c.risk_label);
  const contactLines = [];
  if (c.wa) contactLines.push(<a key="wa" href={`https://wa.me/${c.wa}`} target="_blank" rel="noreferrer">{c.wa}</a>);
  if (c.wa_group) contactLines.push(t("Group: {name}", { name: c.wa_group }));
  if (c.email) contactLines.push(c.email);

  const locationLine = c.address
    ? c.address + (c.city ? ` · ${c.city}${c.province ? `, ${c.province}` : ""}` : "")
    : c.city
      ? `${c.city}${c.province ? `, ${c.province}` : ""}`
      : null;
  const subLines = [c.brand, locationLine].filter(Boolean);

  return (
    <div className="page dv-page hms-dv-page shadcn-root">
      <PageBack href="/clients/" label={t("Back")} />

      <DetailCard
        crumbs={[{ label: t("Clients"), href: "/clients/" }]}
        title={c.name}
        sub={subLines.length ? subLines.map((l, i) => <div key={i}>{l}</div>) : null}
        pill={pill ? { ...pill, label: t(pill.label) } : null}
        actions={
          <>
            {c.wa ? <a className="hms-dv-act" href={`https://wa.me/${c.wa}`} target="_blank" rel="noreferrer">{t("WhatsApp")}</a> : null}
            {perms.can("clients", "edit") && (
              <button type="button" className="hms-dv-act" onClick={() => openForm(`/clients/${c.pk}/edit/`)}>{t("Edit")}</button>
            )}
            <a className="hms-dv-act" href={`/finance/clients/${c.pk}/statement/`}>{t("Finance Statement")}</a>
          </>
        }
        menuItems={[
          perms.can("clients", "edit") && { label: t("Move Funds"), onClick: () => openForm(`/clients/${c.pk}/transfer/`) },
          perms.can("clients", "edit") && { label: t("Refund"), onClick: () => openForm(`/clients/${c.pk}/refund/`) },
          perms.can("clients", "delete") && { label: t("Delete"), onClick: del, danger: true },
        ]}
      >
        <DetailGrid
          rows={[
            {
              label: t("Contact"),
              icon: "user",
              span2: true,
              value: (
                <>
                  <div>{c.pic || c.name}</div>
                  {contactLines.length ? (
                    contactLines.map((l, i) => <div key={i} className="hms-dv-mval-sub">{l}</div>)
                  ) : (
                    <div className="hms-dv-mval-sub">{t("No contact details on file yet.")}</div>
                  )}
                  {needsWaGroup(c) ? (
                    <div style={{ color: "var(--red)", fontWeight: 400, marginTop: 4 }}>
                      {t("Reminder is set to {target} but the WhatsApp Group is not set.", { target: c.reminder_target === "BOTH" ? t("PIC & Group") : t("Group") })}
                    </div>
                  ) : null}
                </>
              ),
            },
            { label: t("Total Billed"), value: `${fmt(c.total_billed)} SAR`, icon: "invoice" },
            c.avg_days_to_pay != null && { label: t("Avg Payment"), value: `${c.avg_days_to_pay} days`, icon: "clock" },
            { label: t("Client Score"), value: `${c.score}/100`, icon: "trend-up", color: scoreColor },
            c.days_since_last_order != null && {
              label: t("Last Order"),
              value: t("{n} days ago", { n: c.days_since_last_order }),
              icon: "calendar",
              color: c.days_since_last_order > 45 ? "var(--red)" : undefined,
            },
            c.note && { label: t("Notes"), value: c.note, icon: "file-text", span2: true, pre: true },
          ]}
          right={
            <div style={{ display: "flex", flexDirection: "column", gap: 12, alignItems: "flex-end" }}>
              <DetailAmount
                label={c.outstanding > 0 ? t("Outstanding") : t("Clear")}
                value={fmt(c.outstanding)}
                currency="SAR"
                tone={c.outstanding > 0 ? "red" : "green"}
              />
              {c.saldo_dana !== 0 && (
                <DetailAmount
                  label={t("Fund Balance")}
                  value={fmt(c.saldo_dana)}
                  currency="SAR"
                  tone={c.saldo_dana > 0 ? "yellow" : "green"}
                />
              )}
            </div>
          }
        />

        <Section
          label={t("Invoices")}
          icon="invoice"
          count={invoices.length || null}
          action={invoices.length > 0 ? <a className="hms-dv-act" href={`/invoice/?client=${c.pk}`}>{t("View all")}</a> : null}
        >
          <DetailTable
            columns={[
              {
                header: t("Invoice"),
                strong: true,
                render: (inv) => (
                  <>
                    <a href={`/invoice/${inv.pk}/`}>{inv.invoice_number}</a>
                    <span className="sub">{[inv.invoice_type_display, inv.issued_date].filter(Boolean).join(" · ")}</span>
                  </>
                ),
              },
              { header: t("Billed"), align: "right", render: (inv) => fmt(inv.total_sar) },
              {
                header: t("Status"),
                render: (inv) =>
                  inv.remaining_sar > 0 ? (
                    <StatusPill small label={inv.remaining_sar < inv.total_sar ? t("Partial") : t("Unpaid")} tone={inv.remaining_sar < inv.total_sar ? "yellow" : "red"} />
                  ) : (
                    <StatusPill small label={t("Paid")} tone="green" />
                  ),
              },
              {
                header: t("Remaining"),
                align: "right",
                strong: true,
                render: (inv) => (
                  <span style={{ color: inv.remaining_sar > 0 ? "var(--red)" : "var(--green)" }}>{fmt(inv.remaining_sar)}</span>
                ),
              },
            ]}
            rows={invoices.slice(0, 10)}
            rowKey={(inv) => inv.pk}
            empty={t("No invoices yet")}
            footer={c.outstanding > 0 ? [{ label: t("Outstanding total"), value: `${fmt(c.outstanding)} SAR`, total: true, tone: "red" }] : null}
          />
        </Section>

        <Section
          label={t("Fund Activity")}
          icon="wallet"
          count={activity.length || null}
          action={perms.can("clients", "export") ? <StatementExport pk={c.pk} t={t} /> : null}
        >
          <DetailTable
            columns={[
              { header: t("Date"), render: (r) => r.date || "—" },
              {
                header: t("Description"),
                strong: true,
                render: (r) => (
                  <>
                    {r.description}
                    {r.type === "memo" && <span className="sub">{t("Transfer — no cash movement")}</span>}
                  </>
                ),
              },
              { header: t("Debit"), align: "right", render: (r) => (r.debit ? fmt(r.debit) : "—") },
              { header: t("Credit"), align: "right", render: (r) => (r.credit ? fmt(r.credit) : "—") },
              {
                header: t("Balance"),
                align: "right",
                strong: true,
                render: (r) => (
                  <span style={{ color: r.balance > 0 ? "var(--red)" : r.balance < 0 ? "var(--yellow)" : "var(--green)" }}>
                    {fmt(r.balance)}
                  </span>
                ),
              },
            ]}
            rows={activity}
            rowKey={(r, i) => i}
            empty={t("No fund activity yet")}
          />
        </Section>

        <Section label={t("Confirmation Letters")} icon="cl" count={cls.length || null}>
          <DetailTable
            columns={[
              { header: "CL", strong: true, render: (cl) => <a href={`/cl/${cl.pk}/`}>{cl.confirmation_number}</a> },
              { header: t("Guest"), render: (cl) => cl.guest_name || "—" },
              { header: t("Hotel"), render: (cl) => cl.hotel_name || "—" },
              { header: t("Check-in"), align: "right", render: (cl) => cl.check_in || "—" },
            ]}
            rows={cls.slice(0, 8)}
            rowKey={(cl) => cl.pk}
            empty={t("No confirmation letters yet")}
          />
        </Section>
      </DetailCard>
      {confirmDialog}
    </div>
  );
}
