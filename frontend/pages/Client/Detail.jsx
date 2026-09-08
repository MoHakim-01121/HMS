import { router } from "@inertiajs/react";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import KebabMenu from "../../components/shadcn/kebab-menu.jsx";
import { RvBack, RvHero, RvFigure, RvCard, RvSection, RvRail, RvRailBlock } from "../../components/shadcn/record-view.jsx";
import { Icon } from "../../components/icons.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

const needsWaGroup = (c) => c.reminder_target !== "PIC" && !c.wa_group;

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

  const locTail = [c.city, c.province].filter(Boolean).join(", ");
  const locationLine = c.address
    ? [c.address, locTail].filter(Boolean).join(", ")
    : locTail || null;

  return (
    <div className="page shadcn-root hms-rv-page">
      <RvBack href="/clients/" label={t("Back")} />

      <RvHero
        badge={{ label: t(pill.label), tone: pill.tone }}
        title={c.name}
        facts={[
          c.brand ? { k: t("Brand"), v: c.brand } : null,
          locationLine ? { k: t("Location"), v: locationLine } : null,
        ].filter(Boolean)}
        side={
          <RvFigure
            label={c.outstanding > 0 ? t("Outstanding") : t("Clear")}
            value={fmt(c.outstanding)}
            unit="SAR"
            color={c.outstanding > 0 ? "var(--red)" : "var(--green)"}
            bar={
              c.total_billed > 0 && c.outstanding > 0
                ? { pct: `${Math.min(100, (c.outstanding / c.total_billed) * 100)}%`, color: "var(--red)" }
                : undefined
            }
            note={c.avg_days_to_pay != null ? `${c.avg_days_to_pay} ${t("days average")}` : undefined}
          />
        }
        note={
          c.outstanding > 0
            ? {
                icon: <Icon name="alert-circle" size={13} strokeWidth={2} />,
                iconBg: "var(--red)",
                title: t("Outstanding balance"),
                text: t("{n} SAR still owed across invoices.", { n: fmt(c.outstanding) }),
              }
            : {
                icon: <Icon name="check" size={12} strokeWidth={2.4} />,
                iconBg: "var(--green)",
                title: t("All settled"),
                text: t("This client owes nothing right now."),
              }
        }
        actions={
          <>
            {c.wa ? <a className="hms-rv-btn" href={`https://wa.me/${c.wa}`} target="_blank" rel="noreferrer">{t("WhatsApp")}</a> : null}
            {perms.can("clients", "edit") && (
              <button type="button" className="hms-rv-btn primary" onClick={() => openForm(`/cl/new/?client=${c.pk}`)}>
                {t("Create CL")}
              </button>
            )}
            {perms.can("clients", "edit") && (
              <button type="button" className="hms-rv-btn" onClick={() => openForm(`/clients/${c.pk}/edit/`)}>
                {t("Edit")}
              </button>
            )}
            <KebabMenu items={[perms.can("clients", "delete") && { label: t("Delete"), onClick: del, danger: true }]} />
          </>
        }
      />

      <div className="hms-rv-grid">
        <div className="hms-rv-col">
          <RvCard>
            <RvSection
              title={t("Invoices")}
              meta={invoices.length > 0 ? <a className="hms-dv-act" href={`/invoice/?client=${c.pk}`}>{t("View all")}</a> : undefined}
              first
            >
              <DetailTable
                columns={[
                  {
                    header: t("Invoice"),
                    strong: true,
                    render: (inv) => (
                      <>
                        <a href={`/invoice/${inv.pk}/`}>{inv.invoice_number}</a>
                        <span className="sub">{[inv.invoice_type_display, inv.issued_date].filter(Boolean).join(" – ")}</span>
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
                    render: (inv) => <span style={{ color: inv.remaining_sar > 0 ? "var(--red)" : "var(--green)" }}>{fmt(inv.remaining_sar)}</span>,
                  },
                ]}
                rows={invoices.slice(0, 10)}
                rowKey={(inv) => inv.pk}
                empty={t("No invoices yet")}
                footer={c.outstanding > 0 ? [{ label: t("Outstanding total"), value: `${fmt(c.outstanding)} SAR`, total: true, tone: "red" }] : null}
              />
            </RvSection>

            <RvSection title={t("Fund Activity")} meta={activity.length ? `${activity.length}` : undefined}>
              {(perms.can("clients", "edit") || perms.can("statements", "view")) && (
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
                  {perms.can("clients", "edit") && (
                    <button type="button" className="hms-dv-act" onClick={() => openForm(`/clients/${c.pk}/transfer/`)}>{t("Move Funds")}</button>
                  )}
                  {perms.can("clients", "edit") && (
                    <button type="button" className="hms-dv-act" onClick={() => openForm(`/clients/${c.pk}/refund/`)}>{t("Refund")}</button>
                  )}
                  {perms.can("statements", "view") && (
                    <a className="hms-dv-act" href={`/finance/clients/${c.pk}/statement/`}>{t("View statement")}</a>
                  )}
                </div>
              )}
              <DetailTable
                columns={[
                  { header: t("Date"), render: (r) => r.date || t("Not set") },
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
                  { header: t("Debit"), align: "right", render: (r) => (r.debit ? fmt(r.debit) : null) },
                  { header: t("Credit"), align: "right", render: (r) => (r.credit ? fmt(r.credit) : null) },
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
            </RvSection>

            <RvSection title={t("Confirmation Letters")} meta={cls.length ? `${cls.length}` : undefined}>
              <DetailTable
                columns={[
                  { header: "CL", strong: true, render: (cl) => <a href={`/cl/${cl.pk}/`}>{cl.confirmation_number}</a> },
                  { header: t("Guest"), render: (cl) => cl.guest_name || t("Not set") },
                  { header: t("Hotel"), render: (cl) => cl.hotel_name || t("Not set") },
                  { header: t("Check-in"), align: "right", render: (cl) => cl.check_in || t("Not set") },
                ]}
                rows={cls.slice(0, 8)}
                rowKey={(cl) => cl.pk}
                empty={t("No confirmation letters yet")}
              />
            </RvSection>

            {c.note ? (
              <RvSection title={t("Notes")}>
                <div className="hms-rv-railtext">{c.note}</div>
              </RvSection>
            ) : null}
          </RvCard>
        </div>

        <RvRail
          rows={[
            { k: t("Total Billed"), v: `${fmt(c.total_billed)} SAR` },
            c.saldo_dana !== 0 ? { k: t("Fund Balance"), v: `${fmt(c.saldo_dana)} SAR` } : null,
            { k: t("Client Score"), v: `${c.score}/100`, c: scoreColor },
            c.days_since_last_order != null
              ? { k: t("Last Order"), v: t("{n} days ago", { n: c.days_since_last_order }), c: c.days_since_last_order > 45 ? "var(--red)" : undefined }
              : null,
          ].filter(Boolean)}
        >
          <RvRailBlock label={t("Contact")}>
            <div style={{ fontSize: 13.5, fontWeight: 500, color: "var(--foreground)" }}>{c.pic || c.name}</div>
            {contactLines.length ? (
              contactLines.map((l, i) => (
                <div key={i} style={{ fontSize: 12.5, color: "var(--muted-foreground)", marginTop: 4 }}>{l}</div>
              ))
            ) : (
              <div style={{ fontSize: 12.5, color: "var(--muted-foreground)", marginTop: 4 }}>{t("No contact details on file yet.")}</div>
            )}
            {needsWaGroup(c) ? (
              <div style={{ color: "var(--red)", fontSize: 12.5, marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border)" }}>
                {t("Reminder is set to {target} but the WhatsApp Group is not set.", { target: c.reminder_target === "BOTH" ? t("PIC & Group") : t("Group") })}
              </div>
            ) : null}
          </RvRailBlock>
        </RvRail>
      </div>

      {confirmDialog}
    </div>
  );
}