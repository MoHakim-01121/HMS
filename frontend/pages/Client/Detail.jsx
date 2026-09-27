import { router } from "@inertiajs/react";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import KebabMenu from "../../components/shadcn/kebab-menu.jsx";
import { RvBack, RvHero, RvCard, RvSection, RvRail, RvRailBlock } from "../../components/shadcn/record-view.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

const needsWaGroup = (c) => c.reminder_target !== "PIC" && !c.wa_group;

// Client is information only: identity, contact, and its CLs. Money for this
// client (invoices, balances, fund activity, refunds) lives under Finance.
export default function Detail({ client, cls }) {
  const { t } = useI18n();
  const c = client;
  const openForm = useFormModal();
  const perms = usePerms();
  const [confirm, confirmDialog] = useConfirm();
  const del = () => confirm({ title: t("Delete client"), message: t("Delete client \"{name}\"?", { name: c.name }), onConfirm: () => router.post(`/clients/${c.pk}/delete/`) });

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
        badge={c.is_active ? { label: t("Active"), tone: "green" } : { label: t("Inactive"), tone: "gray" }}
        title={c.name}
        facts={[
          c.brand ? { k: t("Brand"), v: c.brand } : null,
          locationLine ? { k: t("Location"), v: locationLine } : null,
        ].filter(Boolean)}
        actions={
          <>
            {c.wa ? <a className="hms-rv-btn" href={`https://wa.me/${c.wa}`} target="_blank" rel="noreferrer">{t("WhatsApp")}</a> : null}
            {perms.can("clients", "edit") && (
              <button type="button" className="hms-rv-btn primary" onClick={() => openForm(`/cl/new/?client=${c.pk}`)}>
                {t("Create CL")}
              </button>
            )}
            {perms.can("statements", "view") && (
              <a className="hms-rv-btn" href={`/finance/clients/${c.pk}/statement/`}>{t("Client Finance")}</a>
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
            c.days_since_last_order != null
              ? { k: t("Last Order"), v: t("{n} days ago", { n: c.days_since_last_order }) }
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