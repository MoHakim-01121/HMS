import Attachments from "../../components/ui/Attachments.jsx";
import DetailCard from "../../components/shadcn/detail-card.jsx";
import DetailGrid from "../../components/shadcn/detail-grid.jsx";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import Section from "../../components/shadcn/section.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import FooterSummary, { FooterTotal } from "../../components/shadcn/footer-summary.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtDec } from "../../utils/format.js";

const fmtPrice = (n) => fmtDec(n);

function heroPill(s) {
  if (s === "DEFINITE") return { label: "Definite", tone: "green" };
  if (s === "CANCELLED") return { label: "Cancelled", tone: "red" };
  return { label: "Tentative", tone: "yellow" };
}

function PenaltySection({ cl, penalty }) {
  const openForm = useFormModal();
  const perms = usePerms();
  const { t } = useI18n();
  return (
    <Section
      label={t("Cancellation Penalty")}
      icon="alert-circle"
      action={
        penalty ? (
          <>
            <a className="hms-dv-act" href={`/penalty/${penalty.pk}/pdf/`} target="_blank" rel="noreferrer">PDF</a>
            {perms.can("penalty", "edit") && (
              <button type="button" className="hms-dv-act" onClick={() => openForm(`/penalty/${penalty.pk}/edit/`)}>{t("Edit")}</button>
            )}
          </>
        ) : perms.can("penalty", "create") ? (
          <button type="button" className="hms-dv-act" onClick={() => openForm(`/cl/${cl.pk}/penalty/new/`)}>{t("+ Create penalty document")}</button>
        ) : null
      }
    >
      <DetailTable
        columns={[
          { header: t("Document"), strong: true, render: (p) => <a href={`/penalty/${p.pk}/`}>{p.penalty_number}</a> },
          { header: t("Cancelled"), render: (p) => p.cancellation_date || "—" },
          { header: t("Status"), render: (p) => <StatusPill small label={t(p.is_paid ? "Paid" : "Unpaid")} tone={p.is_paid ? "green" : "red"} /> },
          { header: t("Penalty"), align: "right", strong: true, render: (p) => `${fmt(p.penalty_amount)} ${p.penalty_currency}` },
        ]}
        rows={penalty ? [penalty] : []}
        rowKey={(p) => p.pk}
        empty={t("No penalty document for this CL yet.")}
      />
    </Section>
  );
}

export default function Detail({ cl, rooms, penalty, attachments }) {
  const openForm = useFormModal();
  const perms = usePerms();
  const { t } = useI18n();

  // guest_name pada CL adalah nama client, jadi judul kartu sudah mewakili
  // client-nya: baris "Client" di grid hanya muncul kalau namanya memang beda.
  const sameName = (a, b) => (a || "").trim().toLowerCase() === (b || "").trim().toLowerCase();
  const clientRow = cl.client && !sameName(cl.client.name, cl.guest_name);
  const totalRooms = rooms.reduce((s, r) => s + (r.quantity || 0), 0);
  const cancelled = cl.reservation_status === "CANCELLED";
  const hero = heroPill(cl.reservation_status);

  return (
    <div className="page dv-page hms-dv-page shadcn-root">
      <PageBack href="/cl/" />

      <DetailCard
        crumbs={[{ label: t("Confirmation Letters"), href: "/cl/" }]}
        kicker={cl.confirmation_number}
        title={cl.guest_name}
        sub={cl.hotel_name}
        pill={{ ...hero, label: t(hero.label) }}
        actions={
          <>
            {cl.client ? (
              <a className="hms-dv-act" href={`/clients/${cl.client.pk}/`}>{t("Client")}</a>
            ) : null}
            <a className="hms-dv-act" href={`/cl/${cl.pk}/pdf/`} target="_blank" rel="noreferrer">PDF</a>
            {perms.can("cl", "edit") && (
              <button type="button" className="hms-dv-act" onClick={() => openForm(`/cl/${cl.pk}/edit/`)}>{t("Edit")}</button>
            )}
          </>
        }
      >
        {/* Fakta booking dulu (kapan, berapa orang), lalu tautan ke dokumen
            terkait, lalu catatan. Nomor CL tidak diulang di sini — sudah jadi
            breadcrumb — dan total harga tetap di footer kartu. */}
        <DetailGrid
          rows={[
            {
              label: t("Stay"),
              icon: "calendar",
              value: (
                <>
                  {cl.check_in || "?"} - {cl.check_out || "?"}
                  <span className="hms-dv-mval-sub" style={{ marginLeft: 6 }}>
                    ({cl.num_nights} {t(cl.num_nights === 1 ? "night" : "nights")})
                  </span>
                </>
              ),
            },
            { label: t("Guests"), value: `${cl.num_guests} pax`, icon: "users" },
            clientRow && {
              label: t("Client"),
              icon: "clients",
              value: <a href={`/clients/${cl.client.pk}/`}>{cl.client.name}</a>,
            },
            {
              label: t("Invoice"),
              icon: "invoice",
              value: cl.invoice ? (
                <a href={`/invoice/${cl.invoice.pk}/`}>{cl.invoice.invoice_number}</a>
              ) : (
                <span className="hms-dv-mval-sub">{t("Not invoiced yet")}</span>
              ),
            },
            cl.guest_phone && { label: t("Phone"), value: cl.guest_phone, icon: "message" },
            cl.note && { label: t("Notes"), value: cl.note, icon: "file-text", span2: true, pre: true },
          ]}
        />

        <Attachments targetType="cl" targetId={cl.pk} initial={attachments} />

        {cancelled ? <PenaltySection cl={cl} penalty={penalty} /> : null}

        <Section label={t("Rooms")} icon="hotels" count={totalRooms || null}>
          <DetailTable
            columns={[
              { header: t("Room type"), strong: true, render: (r) => r.room_type },
              { header: t("Meal"), render: (r) => r.meals || "—" },
              { header: t("Qty"), render: (r) => r.quantity },
              { header: t("Rate"), render: (r) => `${fmtPrice(r.price)} / ${t("night")}` },
              { header: t("Subtotal"), align: "right", strong: true, render: (r) => fmt(r.subtotal) },
            ]}
            rows={rooms}
            empty={t("No room data")}
          />
        </Section>

        <FooterSummary right={<FooterTotal label={t("Total Price")} value={fmt(cl.total_price)} currency="SAR" />} />
      </DetailCard>
    </div>
  );
}
