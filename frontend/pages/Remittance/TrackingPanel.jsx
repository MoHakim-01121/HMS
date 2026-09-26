import { useMemo, useState } from "react";
import SearchBox from "../../components/shadcn/search-box.jsx";
import { Icon } from "../../components/icons.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

// Tab Tracking: uang klien di Surabaya yang belum dialokasikan, per reservasi,
// dikelompokkan menurut dekatnya check-in. Angka ringkasan membentuk hitungan
// yang bisa dicek (kolom 1 − kolom 2 − kolom 3 = kolom 4). Data dari
// _compute_tracking_data (hw/views/remittance_views.py).
const BUCKETS = [
  { key: "past", label: "Check-in passed" },
  { key: "week", label: "Next 7 days" },
  { key: "month", label: "8–30 days" },
  { key: "later", label: "Later" },
];

function Row({ row, open, onToggle, t }) {
  const partial = row.paid_sar < row.total_sar;
  return (
    <li className={open ? "tq-row is-open" : "tq-row"}>
      <button type="button" className="tq-row-btn" aria-expanded={open} onClick={onToggle}>
        <span className="tq-row-main">
          <span className="tq-row-t"><span className="tq-no">{row.linked_number}</span>{row.client_name}</span>
          <span className="tq-row-sub">
            {[row.hotel, row.check_in ? t("in {date}", { date: row.check_in }) : null].filter(Boolean).join(" · ")}
            {partial ? ` · ${t("paid {paid} of {total}", { paid: fmt(row.paid_sar), total: fmt(row.total_sar) })}` : ""}
          </span>
        </span>
        <span className={row.unallocated > 0 ? "tq-amt" : "tq-amt is-zero"}>{fmt(row.unallocated)}</span>
        <Icon name="chevron" size={14} className="tq-chev" />
      </button>
      {open && (
        <ol className="tq-timeline">
          <li><span className="tq-dot is-done" />{t("Paid by client")}<span className="tq-tl-amt">{fmt(row.paid_sar)}</span></li>
          {row.history.map((h, i) => (
            <li key={`${h.rmt_id}-${i}`}>
              <span className="tq-dot is-done" />
              {h.kind === "receipt" ? t("Received at HQ {date}", { date: h.date }) : t("Sent {date}", { date: h.date })}
              <a className="tq-rmt" href={`/remittance/${h.rmt_id}/`}>{h.rmt_number}</a>
              <span className="tq-tl-amt">{fmt(h.amount_sar)}</span>
            </li>
          ))}
          {row.unallocated > 0 && (
            <li className="is-todo"><span className="tq-dot" />{t("Not allocated yet")}<span className="tq-tl-amt">{fmt(row.unallocated)}</span></li>
          )}
        </ol>
      )}
    </li>
  );
}

export default function TrackingPanel({ tracking }) {
  const { t } = useI18n();
  const openForm = useFormModal();
  const perms = usePerms();
  const [query, setQuery] = useState("");
  const [client, setClient] = useState("");
  const [openKey, setOpenKey] = useState(null);

  const { summary, pending_allocations: pending = [], reservations = [] } = tracking || {};
  const clients = useMemo(() => [...new Set(reservations.map((r) => r.client_name))].sort(), [reservations]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return reservations.filter((r) => {
      if (client && r.client_name !== client) return false;
      // Tanpa kata kunci hanya yang masih punya uang belum dialokasikan;
      // pencarian ikut menemukan reservasi yang sudah habis dialokasikan.
      if (!q) return r.unallocated > 0;
      return [r.linked_number, r.client_name, r.hotel, r.invoice_number].some((v) => (v || "").toLowerCase().includes(q));
    });
  }, [reservations, query, client]);

  if (!summary) return null;

  const figures = [
    { label: t("Client money not allocated"), value: summary.client_unallocated },
    { op: "−", label: t("In transit, not allocated"), value: summary.in_transit },
    { op: "−", label: t("Received, not allocated"), value: summary.received_unallocated },
    ...(summary.fee ? [{ op: "−", label: t("Fee/difference"), value: summary.fee }] : []),
    { op: "=", label: t("Still in Surabaya"), value: summary.still_sby, strong: true },
  ];
  const allocationUrl = (p) => `/remittance/${p.remittance_id}/receipt/${p.settlement_id}/allocation/?next=${encodeURIComponent("/remittance/?tab=tracking")}`;

  return (
    <div className="tq">
      <style>{CSS}</style>
      <dl className="tq-bridge" style={{ "--tq-cols": figures.length }}>
        {figures.map((f) => (
          <div key={f.label} className={f.strong ? "tq-fig is-strong" : "tq-fig"}>
            <dt>{f.op ? <span className="tq-op" aria-hidden="true">{f.op}</span> : null}{f.label}</dt>
            <dd>{fmt(f.value)}<span className="tq-cur">SAR</span></dd>
          </div>
        ))}
      </dl>

      {pending.map((p) => (
        <div className="tq-callout" key={p.settlement_id} role="status">
          <Icon name="alert-circle" size={15} />
          <span>{t("{number}: {n} SAR received {date} but not allocated", { number: p.remittance_number, n: fmt(p.amount_sar), date: p.received_date })}</span>
          {perms.can("remittance", "edit") && (
            <button type="button" className="tq-callout-act" onClick={() => openForm(allocationUrl(p))}>
              {t("Allocate")}<Icon name="arrow-right" size={13} />
            </button>
          )}
        </div>
      ))}

      <div className="filter-bar">
        <SearchBox value={query} onChange={setQuery} placeholder="Search reservation, client, hotel" />
        <div className="fbar-actions">
          <select className="tq-select" value={client} onChange={(e) => setClient(e.target.value)} aria-label={t("Client")}>
            <option value="">{t("All clients")}</option>
            {clients.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      </div>

      {visible.length ? BUCKETS.map((b) => {
        const rows = visible.filter((r) => r.bucket === b.key);
        if (!rows.length) return null;
        return (
          <section key={b.key} className="tq-group" aria-labelledby={`tq-${b.key}`}>
            <h3 id={`tq-${b.key}`} className="tq-group-h">
              <span>{t(b.label)} · {rows.length}</span>
              <span className="tq-group-sum">{fmt(rows.reduce((sum, r) => sum + r.unallocated, 0))}</span>
            </h3>
            <ul className="tq-list">
              {rows.map((row) => {
                const key = `${row.linked_number}|${row.invoice_id}`;
                return <Row key={key} row={row} t={t} open={openKey === key} onToggle={() => setOpenKey(openKey === key ? null : key)} />;
              })}
            </ul>
          </section>
        );
      }) : (
        <div className="tq-empty">
          {query || client ? t("No matching reservation.") : t("All client money has been allocated.")}
        </div>
      )}
    </div>
  );
}

const CSS = `
.tq-bridge {
  display: grid; grid-template-columns: repeat(var(--tq-cols), minmax(0, 1fr)); margin: 0 0 14px;
  border: 1px solid var(--border); border-radius: 18px; background: var(--card); overflow: hidden;
}
.tq-fig { padding: 14px 16px; border-left: 1px solid var(--border); min-width: 0; }
.tq-fig:first-child { border-left: none; }
.tq-fig dt { font-size: 12px; color: var(--muted-foreground); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tq-fig dd { margin: 6px 0 0; font-size: 18px; font-weight: 600; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.tq-fig.is-strong { background: color-mix(in oklch, var(--muted) 45%, var(--card)); }
.tq-op { display: inline-block; width: 14px; font-weight: 600; color: var(--foreground); }
.tq-cur { margin-left: 5px; font-size: 10.5px; font-weight: 600; color: var(--muted-foreground); letter-spacing: 0; }

.tq-callout {
  display: flex; align-items: center; gap: 8px; margin-bottom: 10px; padding: 10px 12px;
  border-radius: 12px; font-size: 12.5px;
  background: color-mix(in oklch, var(--muted) 55%, var(--card)); border: 1px solid var(--border);
}
.tq-callout > svg { flex: none; color: var(--yellow); }
.tq-callout > span { flex: 1; min-width: 0; }
.tq-callout-act {
  display: inline-flex; align-items: center; gap: 4px; border: none; background: none; padding: 0;
  font: inherit; font-size: 12.5px; font-weight: 600; color: var(--foreground); cursor: pointer; white-space: nowrap;
}
.tq-callout-act:hover { text-decoration: underline; }

.tq-select {
  height: 36px; padding: 0 12px; border-radius: 999px; border: 1px solid var(--input);
  background: var(--card); font: inherit; font-size: 13px; color: var(--foreground);
}
.tq-group { margin-top: 18px; }
.tq-group-h {
  display: flex; justify-content: space-between; gap: 12px; margin: 0 4px 8px;
  font-size: 11px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--muted-foreground);
}
.tq-group-sum { font-variant-numeric: tabular-nums; letter-spacing: 0; color: var(--foreground); }
.tq-list { list-style: none; margin: 0; padding: 0; border: 1px solid var(--border); border-radius: 16px; background: var(--card); overflow: hidden; }
.tq-row + .tq-row { border-top: 1px solid var(--border); }
.tq-row-btn {
  display: flex; align-items: center; gap: 12px; width: 100%; padding: 12px 16px;
  border: none; background: none; font: inherit; text-align: left; cursor: pointer; color: inherit;
}
.tq-row-btn:hover { background: color-mix(in oklch, var(--muted) 45%, transparent); }
.tq-row-btn:focus-visible { outline: 2px solid var(--ring); outline-offset: -2px; }
.tq-row-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.tq-row-t { font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tq-no { font-family: var(--font-mono); font-size: 12px; font-weight: 700; margin-right: 8px; }
.tq-row-sub { font-size: 11.5px; color: var(--muted-foreground); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tq-amt { flex: none; font-size: 13.5px; font-weight: 600; font-variant-numeric: tabular-nums; }
.tq-amt.is-zero { color: var(--muted-foreground); font-weight: 500; }
.tq-chev { flex: none; color: var(--muted-foreground); transition: transform .15s; }
.tq-row.is-open .tq-chev { transform: rotate(180deg); }

.tq-timeline { list-style: none; margin: 0; padding: 2px 16px 14px 36px; display: flex; flex-direction: column; gap: 8px; }
.tq-timeline li { position: relative; display: flex; align-items: baseline; gap: 8px; font-size: 12.5px; }
.tq-timeline li.is-todo { color: var(--muted-foreground); }
.tq-dot { position: absolute; left: -16px; top: 5px; width: 8px; height: 8px; border-radius: 50%; border: 1.5px solid var(--muted-foreground); }
.tq-dot.is-done { background: var(--foreground); border-color: var(--foreground); }
.tq-rmt { font-family: var(--font-mono); font-size: 11.5px; color: var(--muted-foreground); text-decoration: none; }
.tq-rmt:hover { color: var(--foreground); text-decoration: underline; }
.tq-tl-amt { margin-left: auto; font-variant-numeric: tabular-nums; font-weight: 500; }
.tq-empty { margin-top: 16px; padding: 28px; text-align: center; font-size: 13px; color: var(--muted-foreground); border: 1px dashed var(--border); border-radius: 16px; }

@media (max-width: 760px) {
  .tq-bridge { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .tq-fig { border-left: none; border-top: 1px solid var(--border); }
  .tq-fig:nth-child(-n+2) { border-top: none; }
  .tq-fig:nth-child(even) { border-left: 1px solid var(--border); }
  .tq-fig.is-strong:nth-child(odd) { grid-column: 1 / -1; }
  .tq-fig dd { font-size: 16px; }
}
@media (max-width: 600px) {
  .shadcn-root .tq .filter-bar { flex-wrap: wrap; }
  .shadcn-root .tq .filter-bar .fbar-actions { flex: 1 1 100%; width: 100%; }
  /* aturan lama (.filter-bar select { display:none !important }) menyembunyikan
     semua select di filter-bar mobile; dropdown client ini tetap dibutuhkan */
  .shadcn-root .tq .filter-bar select.tq-select { display: block !important; width: 100%; height: 40px; }
}
`;
