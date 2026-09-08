import { router } from "@inertiajs/react";
import Attachments from "../../components/ui/Attachments.jsx";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import KebabMenu from "../../components/shadcn/kebab-menu.jsx";
import { RvBack, RvHero, RvCard, RvSection, RvRail, RvRailBlock, RvLinks } from "../../components/shadcn/record-view.jsx";
import { Icon } from "../../components/icons.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtDec } from "../../utils/format.js";

const fmtPrice = (n) => fmtDec(n);

function heroPill(s) {
  if (s === "DEFINITE") return { label: "Definite", tone: "green" };
  if (s === "CANCELLED") return { label: "Cancelled", tone: "red" };
  return { label: "Tentative", tone: "yellow" };
}

function formatChange(t, c) {
  return t("{field} changed from {before} to {after}", {
    field: c.label,
    before: c.before || t("(empty)"),
    after: c.after || t("(empty)"),
  });
}

export default function Detail({ cl, rooms, penalty, attachments, logs = [] }) {
  const openForm = useFormModal();
  const perms = usePerms();
  const { t } = useI18n();
  const [confirm, confirmDialog] = useConfirm();

  const totalRooms = rooms.reduce((s, r) => s + (r.quantity || 0), 0);
  const roomTypeCount = new Set(rooms.map((r) => r.room_type).filter(Boolean)).size;
  const cancelled = cl.reservation_status === "CANCELLED";
  const hero = heroPill(cl.reservation_status);
  const nightsLabel = `${cl.num_nights} ${t(cl.num_nights === 1 ? "night" : "nights")}`;
  const roomWord = t(totalRooms === 1 ? "room" : "rooms");

  const note =
    cancelled
      ? {
          icon: <Icon name="alert-circle" size={13} strokeWidth={2} />,
          iconBg: "var(--red)",
          title: t("Cancelled"),
          text: penalty
            ? t("This confirmation letter was cancelled. A penalty document is issued.")
            : t("This confirmation letter was cancelled."),
        }
      : cl.reservation_status === "DEFINITE"
        ? {
            icon: <Icon name="check" size={12} strokeWidth={2.4} />,
            iconBg: "var(--green)",
            title: t("Definite"),
            text: t("This reservation is confirmed."),
          }
        : {
            icon: <Icon name="alert-circle" size={13} strokeWidth={2} />,
            iconBg: "var(--yellow)",
            title: t("Tentative"),
            text: t("This reservation is not confirmed yet."),
          };

  const sections = [];
  if (cancelled) {
    sections.push({
      title: t("Cancellation Penalty"),
      meta: penalty ? (
        <div style={{ display: "flex", gap: 10 }}>
          <a className="hms-dv-act" href={`/penalty/${penalty.pk}/pdf/`} target="_blank" rel="noreferrer">PDF</a>
          {perms.can("penalty", "edit") && (
            <button type="button" className="hms-dv-act" onClick={() => openForm(`/penalty/${penalty.pk}/edit/`)}>{t("Edit")}</button>
          )}
        </div>
      ) : null,
      body: penalty ? (
        <DetailTable
          columns={[
            { header: t("Document"), strong: true, render: (p) => <a href={`/penalty/${p.pk}/`}>{p.penalty_number}</a> },
            { header: t("Cancelled"), render: (p) => p.cancellation_date || t("Not set") },
            { header: t("Status"), render: (p) => <StatusPill small label={t(p.is_paid ? "Paid" : "Unpaid")} tone={p.is_paid ? "green" : "red"} /> },
            { header: t("Penalty"), align: "right", strong: true, render: (p) => `${fmt(p.penalty_amount)} ${p.penalty_currency}` },
          ]}
          rows={[penalty]}
          rowKey={(p) => p.pk}
        />
      ) : (
        <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
          <div className="hms-dv-empty" style={{ flex: "1 1 240px" }}>{t("No penalty document for this CL yet.")}</div>
          {perms.can("penalty", "create") && (
            <button type="button" className="hms-dv-act primary" onClick={() => openForm(`/cl/${cl.pk}/penalty/new/`)}>
              {t("+ Create penalty document")}
            </button>
          )}
        </div>
      ),
    });
  }
  const roomsMeta = totalRooms
    ? [
        `${totalRooms} ${roomWord}`,
        roomTypeCount > 1 ? `${roomTypeCount} ${t(roomTypeCount === 1 ? "type" : "types")}` : null,
        nightsLabel,
      ].filter(Boolean).join(", ")
    : undefined;

  sections.push({
    title: t("Rooms"),
    meta: roomsMeta,
    body: (
      <>
        <DetailTable
          columns={[
            { header: t("Room type"), strong: true, render: (r) => r.room_type },
            { header: t("Meal"), render: (r) => r.meals || t("Not set") },
            { header: t("Qty"), align: "right", render: (r) => r.quantity },
            { header: t("Rate"), align: "right", render: (r) => `${fmtPrice(r.price)} / ${t("night")}` },
            { header: t("Subtotal"), align: "right", strong: true, render: (r) => fmt(r.subtotal) },
          ]}
          rows={rooms}
          empty={t("No room data")}
          footer={
            rooms.length
              ? [{ label: t("Total"), value: `${fmt(cl.total_price)} SAR`, total: true }]
              : null
          }
        />
        <RvLinks
          label={t("Related documents")}
          items={[
            cl.invoice ? { href: `/invoice/${cl.invoice.pk}/`, label: cl.invoice.invoice_number, sub: t("invoice") } : null,
            penalty ? { href: `/penalty/${penalty.pk}/`, label: penalty.penalty_number, sub: t("penalty") } : null,
          ]}
        />
      </>
    ),
  });
  const stayRange = [cl.check_in, cl.check_out].filter(Boolean).join(" – ");

  const canEdit = perms.can("cl", "edit");
  const canCreateInvoice = !cl.invoice && !cancelled && perms.can("invoice", "create");

  const menuItems = [
    perms.can("cl", "delete") && {
      label: t("Delete"),
      danger: true,
      onClick: () =>
        confirm({
          title: t("Delete CL"),
          message: t("Delete CL {number}?", { number: cl.confirmation_number }),
          danger: true,
          onConfirm: () => router.post(`/cl/${cl.pk}/delete/`),
        }),
    },
  ];

  return (
    <div className="page shadcn-root hms-rv-page">
      <RvBack href="/cl/" label={t("Back")} stamp={cl.created_at ? t("Created {date}", { date: cl.created_at }) : undefined} />

      <RvHero
        kicker={cl.confirmation_number}
        badge={{ label: t(hero.label), tone: hero.tone }}
        title={cl.num_guests != null ? `${cl.guest_name}, ${cl.num_guests} ${t("pax")}` : cl.guest_name}
        facts={[
          cl.hotel_name ? { k: t("Hotel"), v: cl.hotel_name } : null,
          stayRange ? { k: t("Stay"), v: stayRange, } : null,
          cl.num_nights != null ? { k: t("Nights"), v: nightsLabel } : null,
          totalRooms
            ? {
                k: t("Rooms"),
                v: roomTypeCount > 1
                  ? `${totalRooms} ${roomWord}, ${roomTypeCount} ${t(roomTypeCount === 1 ? "type" : "types")}`
                  : `${totalRooms} ${roomWord}`,
              }
            : null,
        ].filter(Boolean)}
        note={note}
        actions={
          <>
            {canCreateInvoice && (
              <button type="button" className="hms-rv-btn primary" onClick={() => openForm(`/invoice/new/?cl=${cl.pk}`)}>
                {t("Create Invoice")}
              </button>
            )}
            <a className="hms-rv-btn" href={`/cl/${cl.pk}/pdf/`} target="_blank" rel="noreferrer">PDF</a>
            {canEdit && (
              <button type="button" className={canCreateInvoice ? "hms-rv-btn" : "hms-rv-btn primary"} onClick={() => openForm(`/cl/${cl.pk}/edit/`)}>
                {t("Edit")}
              </button>
            )}
            <KebabMenu items={menuItems} />
          </>
        }
      />

      <div className="hms-rv-grid">
        <div className="hms-rv-col">
          <RvCard>
            {sections.map((s, i) => (
              <RvSection key={s.title} title={s.title} meta={s.meta} first={i === 0}>
                {s.body}
              </RvSection>
            ))}
          </RvCard>
        </div>

        <RvRail
          rows={[
            { k: `${t("Rooms")} × ${t("nights")}`, v: `${totalRooms} × ${cl.num_nights}` },
            cl.invoice
              ? { k: t("Invoice"), v: <a href={`/invoice/${cl.invoice.pk}/`}>{cl.invoice.invoice_number}</a> }
              : { k: t("Invoice"), v: t("Not invoiced yet") },
            cl.client ? { k: t("Client"), v: <a href={`/clients/${cl.client.pk}/`}>{cl.client.name}</a> } : null,
            cl.guest_phone
              ? { k: t("Phone"), v: <span style={{ fontVariantNumeric: "tabular-nums" }}>{cl.guest_phone}</span> }
              : null,
          ].filter(Boolean)}
        >
          <RvRailBlock label={t("Attachments")} action={<span className="hms-rv-lbl">{attachments.length || null}</span>}>
            <Attachments targetType="cl" targetId={cl.pk} initial={attachments} compact />
          </RvRailBlock>
          {cl.note ? (
            <RvRailBlock label={t("Notes")}>
              <div className="hms-rv-railtext">{cl.note}</div>
            </RvRailBlock>
          ) : null}
          {logs.length ? (
            <RvRailBlock label={t("History")} pin>
              <div className="hms-rv-railtext">
                {logs[0].changes?.length
                  ? formatChange(t, logs[0].changes[0])
                  : t("{action} by {by}", { action: logs[0].action, by: logs[0].by })}
              </div>
              {logs.length > 1 ? (
                <span className="hms-rv-raillink">{t("{n} changes", { n: logs.length })}</span>
              ) : null}
            </RvRailBlock>
          ) : null}
        </RvRail>
      </div>

      {confirmDialog}
    </div>
  );
}