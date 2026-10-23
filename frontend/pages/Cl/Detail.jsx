import { useState } from "react";
import { cn } from "@/lib/utils";
import { router } from "@inertiajs/react";
import Attachments from "../../components/ui/Attachments.jsx";
import { DPage, DTop, DHead, DCard, DTabs, DLog, DBtn, DPill, dayMonth, DA, DC, dBtnClass } from "../../components/shadcn/detail-a.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtDate, fmtStay } from "../../utils/format.js";

// CL detail, the approved "CL Detail" artboard on the Record View HMS canvas:
// the head card names the CL and its status with the facts under it, Rooms
// is the one table, and Notes / Attachments / History share a tabbed card.

const fmtRate = (n) =>
  Number(n || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const STATUS = {
  DEFINITE: { label: "Definite", tone: "green" },
  TENTATIVE: { label: "Tentative", tone: "amber" },
  CANCELLED: { label: "Cancelled", tone: "red" },
};

// The room log stores whole lists ("Quad x2 @ 560.00 | Double x1 @ 480.00",
// "—" when empty — see cl_views._rooms_summary). Returns null when a string
// doesn't match, so the caller falls back to the plain before/after sentence.
function parseRooms(s) {
  if (!s || s === "—") return [];
  const out = [];
  for (const part of s.split(" | ")) {
    const m = /^(.*) x(\d+) @ (.+)$/.exec(part.trim());
    if (!m) return null;
    out.push({ type: m[1], qty: Number(m[2]), price: Number(m[3]) });
  }
  return out;
}

// Rooms that differ, one phrase each: "Double added", "Quad 2 → 4 rooms".
// Same-type rows are paired in order, since the log carries no row id.
function roomPhrases(t, before, after) {
  const a = parseRooms(before);
  const b = parseRooms(after);
  if (!a || !b) return null;
  const rooms = (n) => `${n} ${t(n === 1 ? "room" : "rooms")}`;
  const out = [];
  for (const type of [...new Set([...a, ...b].map((r) => r.type))]) {
    const xs = a.filter((r) => r.type === type);
    const ys = b.filter((r) => r.type === type);
    for (let i = 0; i < Math.max(xs.length, ys.length); i++) {
      const x = xs[i];
      const y = ys[i];
      if (!x) out.push(t("{type} added", { type }));
      else if (!y) out.push(t("{type} removed", { type }));
      else if (x.qty !== y.qty) out.push(`${type} ${rooms(x.qty)} → ${rooms(y.qty)}`);
      else if (x.price !== y.price) out.push(`${type} ${fmtRate(x.price)} → ${fmtRate(y.price)} / ${t("night")}`);
    }
  }
  return out;
}

// Field values as the reader knows them: status labels, dates as "05 Oct 2026".
function pretty(t, label, v) {
  if (v == null || v === "" || v === "—") return t("(empty)");
  if (label === "Status" && STATUS[v]) return t(STATUS[v].label);
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return fmtDate(v);
  return v;
}

// One history line: "Status changed from Tentative to Definite".
function logBody(t, log) {
  if (!log.changes?.length) return log.action;
  return log.changes.map((c, i) => {
    const sep = i ? "; " : "";
    if (c.field === "Rooms" || c.label === "Rooms") {
      const ph = roomPhrases(t, c.before, c.after);
      return <span key={i}>{sep}{t("Rooms updated")}{ph && ph.length ? `: ${ph.join(", ")}` : ""}</span>;
    }
    return (
      <span key={i}>
        {sep}{t("{field} changed from {a} to {b}", { field: t(c.label), a: pretty(t, c.label, c.before), b: pretty(t, c.label, c.after) })}
      </span>
    );
  });
}

export default function Detail({ cl, rooms, penalty, attachments, logs = [] }) {
  const openForm = useFormModal();
  const perms = usePerms();
  const { t } = useI18n();
  const [confirm, confirmDialog] = useConfirm();
  const [attCount, setAttCount] = useState(attachments.length);
  const [tab, setTab] = useState("notes");

  const totalRooms = rooms.reduce((s, r) => s + (r.quantity || 0), 0);
  const roomTypeCount = new Set(rooms.map((r) => r.room_type).filter(Boolean)).size;
  const cancelled = cl.reservation_status === "CANCELLED";
  const st = STATUS[cl.reservation_status] || STATUS.TENTATIVE;
  const roomWord = t(totalRooms === 1 ? "room" : "rooms");
  const canCreateInvoice = !cl.invoice && !cancelled && perms.can("invoice", "create");

  const menu = [
    canCreateInvoice && { label: t("Create invoice"), icon: "plus", onClick: () => openForm(`/invoice/new/?cl=${cl.pk}`) },
    perms.can("cl", "edit") && { label: t("Edit"), icon: "edit", onClick: () => openForm(`/cl/${cl.pk}/edit/`) },
    { label: t("Download PDF"), icon: "pdf", href: `/cl/${cl.pk}/pdf/`, external: true },
    perms.can("cl", "delete") && {
      label: t("Delete CL…"),
      icon: "trash",
      danger: true,
      separator: true,
      onClick: () =>
        confirm({
          title: t("Delete {number}?", { number: cl.confirmation_number }),
          message: t("The reservation for {guest} at {hotel} will be removed permanently. This can't be undone.", {
            guest: cl.guest_name,
            hotel: cl.hotel_name || "-",
          }),
          danger: true,
          onConfirm: () => router.post(`/cl/${cl.pk}/delete/`),
        }),
    },
  ];

  const facts = [
    { k: t("Hotel"), v: cl.hotel_name || t("Not set") },
    { k: t("Stay"), v: fmtStay(cl.check_in, cl.check_out) || t("Not set") },
    cl.num_nights != null && { k: t("Nights"), v: `${cl.num_nights} ${t(cl.num_nights === 1 ? "night" : "nights")}` },
    totalRooms > 0 && {
      k: t("Rooms"),
      v: roomTypeCount > 1
        ? `${totalRooms} ${roomWord}, ${roomTypeCount} ${t(roomTypeCount === 1 ? "type" : "types")}`
        : `${totalRooms} ${roomWord}`,
    },
    { k: t("Client"), v: cl.client ? <a href={`/clients/${cl.client.pk}/`}>{cl.client.name}</a> : cl.guest_name || t("Not set") },
    cl.client && cl.guest_name && cl.guest_name !== cl.client.name && { k: t("Guest"), v: cl.guest_name },
    cl.num_guests != null && { k: t("Pax"), v: cl.num_guests },
    { k: t("Invoice"), v: cl.invoice ? <a href={`/invoice/${cl.invoice.pk}/`}>{cl.invoice.invoice_number}</a> : <span className="font-normal text-muted-foreground">{t("Not invoiced yet")}</span> },
    cl.guest_phone && { k: t("Phone"), v: cl.guest_phone },
  ];

  const related = [
    cl.invoice && { href: `/invoice/${cl.invoice.pk}/`, no: cl.invoice.invoice_number, kind: t("invoice") },
    penalty && { href: `/penalty/${penalty.pk}/`, no: penalty.penalty_number, kind: t("penalty") },
  ].filter(Boolean);

  const history = logs.map((l, i) => ({ key: i, when: dayMonth(l.timestamp), body: logBody(t, l), by: l.by }));

  return (
    <DPage>
      <DTop href="/cl/" stamp={cl.created_at ? t("Created {date}", { date: cl.created_at }) : undefined} />

      <DHead title={cl.confirmation_number} badge={{ label: t(st.label), tone: st.tone }} menu={menu} facts={facts} />

      {cancelled ? (
        <DCard
          title={t("Cancellation penalty")}
          actions={penalty ? (
            <>
              <a href={`/penalty/${penalty.pk}/pdf/`} target="_blank" rel="noreferrer">PDF</a>
              {perms.can("penalty", "edit") && <button type="button" onClick={() => openForm(`/penalty/${penalty.pk}/edit/`)}>{t("Edit")}</button>}
            </>
          ) : null}
        >
          {penalty ? (
            <div className={DA.scroll}>
              <table data-slot="detail-table" className={DA.table}>
                <thead><tr><th>{t("Document")}</th><th>{t("Cancelled")}</th><th>{t("Status")}</th><th className={DC.n}>{t("Penalty")}</th></tr></thead>
                <tbody>
                  <tr>
                    <td><a className={DC.mono} href={`/penalty/${penalty.pk}/`}>{penalty.penalty_number}</a></td>
                    <td className={DC.nw}>{penalty.cancellation_date ? fmtDate(penalty.cancellation_date) : t("Not set")}</td>
                    <td><DPill sm tone={penalty.is_paid ? "green" : "red"}>{t(penalty.is_paid ? "Paid" : "Unpaid")}</DPill></td>
                    <td className={cn(DC.n, DC.bold)}>{fmt(penalty.penalty_amount)} {penalty.penalty_currency}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          ) : (
            <div data-slot="card-foot" className={cn(DA.cardFoot, "justify-between border-t-0")}>
              <span className={DA.footLabel}>{t("No penalty document for this CL yet.")}</span>
              {perms.can("penalty", "create") && (
                <DBtn className={dBtnClass({ soft: true })} onClick={() => openForm(`/cl/${cl.pk}/penalty/new/`)}>{t("+ Create penalty document")}</DBtn>
              )}
            </div>
          )}
        </DCard>
      ) : null}

      <DCard title={t("Rooms")} meta={t("Rates in SAR, per room-night")}>
        <div className={DA.scroll}>
          <table data-slot="detail-table" className={DA.table}>
            <thead><tr><th>{t("Room type")}</th><th>{t("Meal")}</th><th className={DC.n}>{t("Qty")}</th><th className={DC.n}>{t("Rate")}</th><th className={DC.n}>{t("Subtotal")}</th></tr></thead>
            <tbody>
              {rooms.length ? rooms.map((r, i) => (
                <tr key={i}>
                  <td className={DC.strong}>{r.room_type}</td>
                  <td className={DC.mut}>{r.meals || t("Not set")}</td>
                  <td className={DC.n}>{r.quantity}</td>
                  <td className={DC.n}>{fmtRate(r.price)} / {t("night")}</td>
                  <td className={cn(DC.n, DC.strong)}>{fmt(r.subtotal)}</td>
                </tr>
              )) : <tr><td colSpan={5} className={DC.empty}>{t("No room data")}</td></tr>}
            </tbody>
            {rooms.length ? <tfoot><tr><td colSpan={4}>{t("Total")}</td><td className={DC.n}>{fmt(cl.total_price)} SAR</td></tr></tfoot> : null}
          </table>
        </div>
        {related.length ? (
          <div data-slot="card-foot" className={DA.cardFoot}>
            <span className={DA.footLabel}>{t("Related documents")}</span>
            {related.map((d) => (
              <a key={d.href} className={DA.tag} href={d.href}>{d.no} <span className={DA.tagSub}>{d.kind}</span></a>
            ))}
          </div>
        ) : null}
      </DCard>

      <section data-slot="card" className={DA.card}>
        <DTabs
          value={tab}
          onChange={setTab}
          tabs={[
            { key: "notes", label: t("Notes") },
            { key: "files", label: t("Attachments"), count: attCount },
            { key: "history", label: t("History"), count: logs.length },
          ]}
        />
        <div role="tabpanel" hidden={tab !== "notes"} className={cn(DA.panel, "py-5")}>
          {cl.note
            ? <p className={cn(DA.text, "m-0 max-w-[640px]")}>{cl.note}</p>
            : <span className="mut" style={{ fontSize: 13, color: "var(--muted-foreground)" }}>{t("No notes.")}</span>}
        </div>
        <div role="tabpanel" hidden={tab !== "files"} className={DA.files}>
          <Attachments targetType="cl" targetId={cl.pk} initial={attachments} onCountChange={setAttCount} />
        </div>
        <div role="tabpanel" hidden={tab !== "history"}>
          <DLog rows={history} empty={t("No changes recorded yet.")} />
        </div>
      </section>

      {confirmDialog}
    </DPage>
  );
}
