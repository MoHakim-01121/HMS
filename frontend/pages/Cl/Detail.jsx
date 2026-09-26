import { useState } from "react";
import { router } from "@inertiajs/react";
import Attachments from "../../components/ui/Attachments.jsx";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import KebabMenu from "../../components/shadcn/kebab-menu.jsx";
import { RvBack } from "../../components/shadcn/record-view.jsx";
import { Icon } from "../../components/icons.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtDate, fmtStay } from "../../utils/format.js";

// CL detail, from the Claude Design file "CL Detail.dc.html" (project
// 7cf7c6a1…): the hero carries identity + actions in its top row, the facts
// as a grid and one status sentence closing the card; the content card holds
// Penalty (cancelled only), Rooms, History and a related-documents footer;
// the rail keeps Client / Phone / Invoice, Attachments and Notes. Edit lives in
// the overflow menu so "Create invoice" is the only filled action.

const fmtRate = (n) =>
  Number(n || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const STATUS = {
  DEFINITE: { label: "Definite", tone: "green", title: "Confirmed.", text: "This reservation is confirmed." },
  // Tentative = the hotel already confirmed the rooms; it turns Definite once
  // a payment comes in (30% down payment or full settlement).
  TENTATIVE: {
    label: "Tentative",
    tone: "yellow",
    title: "Awaiting payment.",
    text: "Rooms are confirmed. This becomes Definite once a payment is received: a 30% down payment or full settlement.",
  },
  CANCELLED: { label: "Cancelled", tone: "red", title: "Cancelled.", text: "This confirmation letter was cancelled." },
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

// Only the rooms that differ, one entry per room:
//   { type, kind: "added"|"removed"|"changed", a, b }   (a/b = { qty, price })
// Same-type rows are paired in order, since the log carries no row id.
function roomChanges(before, after) {
  const a = parseRooms(before);
  const b = parseRooms(after);
  if (!a || !b) return null;
  const types = [...new Set([...a, ...b].map((r) => r.type))];
  const out = [];
  for (const type of types) {
    const xs = a.filter((r) => r.type === type);
    const ys = b.filter((r) => r.type === type);
    for (let i = 0; i < Math.max(xs.length, ys.length); i++) {
      const x = xs[i];
      const y = ys[i];
      if (!x) out.push({ type, kind: "added", b: y });
      else if (!y) out.push({ type, kind: "removed", a: x });
      else if (x.qty !== y.qty || x.price !== y.price) out.push({ type, kind: "changed", a: x, b: y });
    }
  }
  return out;
}

const isRoomsChange = (c) => c.field === "Rooms" || c.label === "Rooms";

// Before → after, the old value struck through; an empty side reads "empty".
function Delta({ t, before, after }) {
  const empty = (v) => v == null || v === "" || v === "—";
  return (
    <>
      {empty(before) ? <span className="none">{t("empty")}</span> : <s>{before}</s>}
      <Icon name="arrow-right" size={13} strokeWidth={1.8} className="arr" aria-hidden="true" />
      {empty(after) ? <span className="none">{t("empty")}</span> : <b>{after}</b>}
    </>
  );
}

// Field values as the reader knows them: status labels, dates as "05 Oct 2026".
function prettyValue(t, label, v) {
  if (v == null || v === "") return v;
  if (label === "Status" && STATUS[v]) return t(STATUS[v].label);
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return fmtDate(v);
  return v;
}

// Every change in one log entry, as label | value rows (no box around them).
function ChangeRows({ t, changes }) {
  const rows = [];
  changes.forEach((c, ci) => {
    const rc = isRoomsChange(c) ? roomChanges(c.before, c.after) : null;
    if (rc) {
      if (!rc.length) rows.push(<div key={ci} className="hms-cl-chg-row"><span className="k">{t("Rooms")}</span><span className="v">{t("Rooms updated")}</span></div>);
      rc.forEach((r, ri) => {
        const rooms = (n) => `${n} ${t(n === 1 ? "room" : "rooms")}`;
        let v;
        if (r.kind === "added") {
          v = <><span className="tag add">{t("Added")}</span><b>{rooms(r.b.qty)}</b><span className="dim">@ {fmtRate(r.b.price)} / {t("night")}</span></>;
        } else if (r.kind === "removed") {
          v = <><span className="tag del">{t("Removed")}</span><s>{rooms(r.a.qty)} @ {fmtRate(r.a.price)}</s></>;
        } else {
          const qtyChanged = r.a.qty !== r.b.qty;
          const rateChanged = r.a.price !== r.b.price;
          v = (
            <>
              {qtyChanged
                ? <span className="grp"><Delta t={t} before={r.a.qty} after={rooms(r.b.qty)} /></span>
                : <span className="dim">{rooms(r.b.qty)}</span>}
              {rateChanged
                ? <span className="grp">@ <Delta t={t} before={fmtRate(r.a.price)} after={`${fmtRate(r.b.price)} / ${t("night")}`} /></span>
                : <span className="dim">@ {fmtRate(r.b.price)} / {t("night")}</span>}
            </>
          );
        }
        rows.push(
          <div key={`${ci}-${ri}`} className="hms-cl-chg-row">
            <span className="k strong">{r.type}</span>
            <span className="v">{v}</span>
          </div>
        );
      });
      return;
    }
    rows.push(
      <div key={ci} className="hms-cl-chg-row">
        <span className="k">{t(c.label)}</span>
        <span className="v">
          <Delta t={t} before={prettyValue(t, c.label, c.before)} after={prettyValue(t, c.label, c.after)} />
        </span>
      </div>
    );
  });
  return <div className="hms-cl-chg">{rows}</div>;
}

function HistoryEntry({ t, log }) {
  return (
    <div className="hms-cl-hentry">
      <div className="hms-cl-histrow">
        <span className="txt">{log.action}</span>
        <span className="when">{[log.timestamp, log.by].filter(Boolean).join(" · ")}</span>
      </div>
      {log.changes?.length ? <ChangeRows t={t} changes={log.changes} /> : null}
    </div>
  );
}

export default function Detail({ cl, rooms, penalty, attachments, logs = [] }) {
  const openForm = useFormModal();
  const perms = usePerms();
  const { t } = useI18n();
  const [confirm, confirmDialog] = useConfirm();
  const [attCount, setAttCount] = useState(attachments.length);
  const [showAllLogs, setShowAllLogs] = useState(false);

  const totalRooms = rooms.reduce((s, r) => s + (r.quantity || 0), 0);
  const roomTypeCount = new Set(rooms.map((r) => r.room_type).filter(Boolean)).size;
  const cancelled = cl.reservation_status === "CANCELLED";
  const st = STATUS[cl.reservation_status] || STATUS.TENTATIVE;
  const nightsLabel = cl.num_nights != null ? `${cl.num_nights} ${t(cl.num_nights === 1 ? "night" : "nights")}` : null;
  const roomWord = t(totalRooms === 1 ? "room" : "rooms");
  const stay = fmtStay(cl.check_in, cl.check_out);

  const noteText = cancelled && penalty
    ? t("This confirmation letter was cancelled. A penalty document is issued.")
    : t(st.text);

  const facts = [
    cl.hotel_name ? { k: t("Hotel"), v: cl.hotel_name } : null,
    stay ? { k: t("Stay"), v: stay, nowrap: true } : null,
    nightsLabel ? { k: t("Nights"), v: nightsLabel } : null,
    totalRooms
      ? {
          k: t("Rooms"),
          v: roomTypeCount > 1
            ? `${totalRooms} ${roomWord}, ${roomTypeCount} ${t(roomTypeCount === 1 ? "type" : "types")}`
            : `${totalRooms} ${roomWord}`,
        }
      : null,
  ].filter(Boolean);

  const canCreateInvoice = !cl.invoice && !cancelled && perms.can("invoice", "create");

  const menuItems = [
    perms.can("cl", "edit") && { label: t("Edit"), icon: "edit", onClick: () => openForm(`/cl/${cl.pk}/edit/`) },
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

  const related = [
    cl.invoice ? { href: `/invoice/${cl.invoice.pk}/`, no: cl.invoice.invoice_number, kind: t("invoice") } : null,
    penalty ? { href: `/penalty/${penalty.pk}/`, no: penalty.penalty_number, kind: t("penalty") } : null,
  ].filter(Boolean);

  const lastLog = logs[0];

  return (
    <div className="page shadcn-root hms-rv-page hms-cl">
      <RvBack href="/cl/" label={t("Back")} stamp={cl.created_at ? t("Created {date}", { date: cl.created_at }) : undefined} />

      <header className="hms-cl-hero">
        <div className="hms-cl-hero-top">
          <div className="hms-cl-hero-id">
            <div className="hms-rv-hero-kicker">
              <span className="hms-rv-kicker">{cl.confirmation_number}</span>
              <span className={`hms-dv-pill hms-cl-badge tone-${st.tone}`}>{t(st.label)}</span>
            </div>
            <h1 className="hms-cl-h1">
              {cl.num_guests != null ? `${cl.guest_name}, ${cl.num_guests} ${t("pax")}` : cl.guest_name}
            </h1>
          </div>

          <div className="hms-cl-actions">
            {canCreateInvoice && (
              <button type="button" className="hms-rv-btn primary" onClick={() => openForm(`/invoice/new/?cl=${cl.pk}`)}>
                {t("Create invoice")}
              </button>
            )}
            <a className="hms-rv-btn" href={`/cl/${cl.pk}/pdf/`} target="_blank" rel="noreferrer">
              <Icon name="download" size={14} strokeWidth={1.6} />
              PDF
            </a>
            <KebabMenu items={menuItems} />
          </div>
        </div>

        {facts.length ? (
          <dl className="hms-cl-facts">
            {facts.map((f) => (
              <div key={f.k}>
                <dt className="hms-rv-lbl">{f.k}</dt>
                <dd className={f.nowrap ? "nowrap" : undefined}>{f.v}</dd>
              </div>
            ))}
          </dl>
        ) : null}

        <div className="hms-cl-note">
          <span className={`hms-cl-note-ico tone-${st.tone}`}>
            {cl.reservation_status === "DEFINITE" ? <Icon name="check" size={11} strokeWidth={2.2} /> : "!"}
          </span>
          <p>
            <strong>{t(st.title)}</strong> {noteText}
          </p>
        </div>
      </header>

      <div className="hms-cl-grid">
        <main className="hms-cl-main">
          {cancelled ? (
            <section className="hms-cl-sec">
              <div className="hms-cl-sech">
                <h2>{t("Cancellation penalty")}</h2>
                {penalty ? (
                  <div className="hms-cl-sech-acts">
                    <a className="hms-dv-act" href={`/penalty/${penalty.pk}/pdf/`} target="_blank" rel="noreferrer">PDF</a>
                    {perms.can("penalty", "edit") && (
                      <button type="button" className="hms-dv-act" onClick={() => openForm(`/penalty/${penalty.pk}/edit/`)}>{t("Edit")}</button>
                    )}
                  </div>
                ) : null}
              </div>
              {penalty ? (
                <DetailTable
                  columns={[
                    { header: t("Document"), render: (p) => <a className="mono" href={`/penalty/${p.pk}/`}>{p.penalty_number}</a> },
                    { header: t("Cancelled"), className: "tab", render: (p) => (p.cancellation_date ? fmtDate(p.cancellation_date) : t("Not set")) },
                    {
                      header: t("Status"),
                      render: (p) => (
                        <span className="hms-cl-dot">
                          <span style={{ background: p.is_paid ? "var(--green)" : "var(--red)" }} />
                          {t(p.is_paid ? "Paid" : "Unpaid")}
                        </span>
                      ),
                    },
                    { header: t("Penalty"), align: "right", className: "semi", render: (p) => `${fmt(p.penalty_amount)} ${p.penalty_currency}` },
                  ]}
                  rows={[penalty]}
                  rowKey={(p) => p.pk}
                />
              ) : (
                <div className="hms-cl-nopen">
                  <span>{t("No penalty document for this CL yet.")}</span>
                  {perms.can("penalty", "create") && (
                    <button type="button" className="hms-cl-smbtn" onClick={() => openForm(`/cl/${cl.pk}/penalty/new/`)}>
                      {t("+ Create penalty document")}
                    </button>
                  )}
                </div>
              )}
            </section>
          ) : null}

          <section className="hms-cl-sec">
            <div className="hms-cl-sech">
              <h2>{t("Rooms")}</h2>
              <span className="meta">{t("Rates in SAR, per room-night")}</span>
            </div>
            <DetailTable
              columns={[
                { header: t("Room type"), className: "semi", render: (r) => r.room_type },
                { header: t("Meal"), className: "dim", render: (r) => r.meals || t("Not set") },
                { header: t("Qty"), align: "right", render: (r) => r.quantity },
                { header: t("Rate"), align: "right", render: (r) => fmtRate(r.price) },
                { header: t("Subtotal"), align: "right", strong: true, render: (r) => fmt(r.subtotal) },
              ]}
              rows={rooms}
              empty={t("No room data")}
              footer={
                rooms.length
                  ? [{
                      label: nightsLabel ? `${t("Total")} · ${nightsLabel}` : t("Total"),
                      value: `${fmt(cl.total_price)} SAR`,
                      total: true,
                    }]
                  : null
              }
            />
          </section>

          {lastLog ? (
            <section className="hms-cl-sec hms-cl-history">
              <div className="hms-cl-sech flush">
                <h2>{t("History")}</h2>
                {logs.length > 1 ? (
                  <button type="button" className="hms-cl-histcount" onClick={() => setShowAllLogs((v) => !v)} aria-expanded={showAllLogs}>
                    <Icon name="clock" size={14} strokeWidth={1.6} />
                    {showAllLogs ? t("Latest only") : t("{n} changes", { n: logs.length })}
                  </button>
                ) : null}
              </div>
              {(showAllLogs ? logs : [lastLog]).map((log, i) => (
                <HistoryEntry key={i} t={t} log={log} />
              ))}
            </section>
          ) : null}

          {related.length ? (
            <footer className="hms-cl-related">
              <span className="hms-rv-lbl">{t("Related documents")}</span>
              {related.map((d) => (
                <a key={d.href} className="hms-rv-linkchip" href={d.href}>
                  <span className="mono">{d.no}</span>
                  <span className="s">{d.kind}</span>
                </a>
              ))}
            </footer>
          ) : null}
        </main>

        <aside className="hms-cl-rail">
          <dl className="hms-cl-raillist">
            {cl.client ? (
              <div>
                <dt>{t("Client")}</dt>
                <dd>
                  <a href={`/clients/${cl.client.pk}/`}>
                    {cl.client.name}
                    <Icon name="arrow-up-right" size={13} strokeWidth={1.8} aria-hidden="true" />
                  </a>
                </dd>
              </div>
            ) : null}
            {cl.guest_phone ? (
              <div>
                <dt>{t("Phone")}</dt>
                <dd className="tab">{cl.guest_phone}</dd>
              </div>
            ) : null}
            <div>
              <dt>{t("Invoice")}</dt>
              <dd>
                {cl.invoice
                  ? (
                    <a href={`/invoice/${cl.invoice.pk}/`}>
                      <span className="mono">{cl.invoice.invoice_number}</span>
                      <Icon name="arrow-up-right" size={13} strokeWidth={1.8} aria-hidden="true" />
                    </a>
                  )
                  : <span className="none">{t("Not invoiced yet")}</span>}
              </dd>
            </div>
          </dl>

          <div className="hms-cl-railblock">
            <div className="hms-cl-railblock-h">
              <span className="hms-rv-lbl">{t("Attachments")}</span>
              <span className="count">{attCount || null}</span>
            </div>
            <Attachments targetType="cl" targetId={cl.pk} initial={attachments} compact dashedAdd onCountChange={setAttCount} />
          </div>

          {cl.note ? (
            <div className="hms-cl-railblock">
              <span className="hms-rv-lbl">{t("Notes")}</span>
              <p className="hms-cl-notes">{cl.note}</p>
            </div>
          ) : null}
        </aside>
      </div>

      {confirmDialog}
    </div>
  );
}
