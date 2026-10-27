import { useMemo, useState } from "react";
import SearchBox from "../../components/shadcn/search-box.jsx";
import { Icon } from "../../components/icons.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";
import { cn } from "@/lib/utils";

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

const TINT = "bg-[color:color-mix(in_oklch,var(--muted)_45%,var(--card))]";
const COLS = { 4: "grid-cols-4", 5: "grid-cols-5" };
const AMT = "ml-auto font-medium tabular-nums";
const DOT = "absolute top-[5px] -left-4 size-2 rounded-full border-[1.5px] border-muted-foreground";

function Row({ row, open, onToggle, t }) {
  const partial = row.paid_sar < row.total_sar;
  return (
    <li className="border-border not-first:border-t">
      <button type="button" aria-expanded={open} onClick={onToggle}
        className="flex w-full cursor-pointer items-center gap-3 border-0 bg-transparent px-4 py-3 text-left [font:inherit] text-inherit hover:bg-[color:color-mix(in_oklch,var(--muted)_45%,transparent)] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring">
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="truncate text-[13px] font-medium"><span className="mr-2 font-mono text-[12px] font-bold">{row.linked_number}</span>{row.client_name}</span>
          <span className="truncate text-[12px] text-muted-foreground">
            {[row.hotel, row.check_in ? t("in {date}", { date: row.check_in }) : null].filter(Boolean).join(" · ")}
            {partial ? ` · ${t("paid {paid} of {total}", { paid: fmt(row.paid_sar), total: fmt(row.total_sar) })}` : ""}
          </span>
        </span>
        <span className={cn("flex-none text-[14px] font-semibold tabular-nums", row.unallocated <= 0 && "font-medium text-muted-foreground")}>{fmt(row.unallocated)}</span>
        <Icon name="chevron" size={14} className={cn("flex-none text-muted-foreground transition-[rotate] duration-150", open && "rotate-180")} />
      </button>
      {open && (
        <ol className="m-0 flex list-none flex-col gap-2 pt-0.5 pr-4 pb-3.5 pl-9 [&>li]:relative [&>li]:flex [&>li]:items-baseline [&>li]:gap-2 [&>li]:text-[13px]">
          <li><span className={cn(DOT, "border-foreground bg-foreground")} />{t("Paid by client")}<span className={AMT}>{fmt(row.paid_sar)}</span></li>
          {row.history.map((h, i) => (
            <li key={`${h.rmt_id}-${i}`}>
              <span className={cn(DOT, "border-foreground bg-foreground")} />
              {h.kind === "receipt" ? t("Received at HQ {date}", { date: h.date }) : t("Sent {date}", { date: h.date })}
              <a className="font-mono text-[12px] text-muted-foreground no-underline hover:text-foreground hover:underline" href={`/remittance/${h.rmt_id}/`}>{h.rmt_number}</a>
              <span className={AMT}>{fmt(h.amount_sar)}</span>
            </li>
          ))}
          {row.unallocated > 0 && (
            <li className="text-muted-foreground"><span className={DOT} />{t("Not allocated yet")}<span className={AMT}>{fmt(row.unallocated)}</span></li>
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
    <div>
      <dl className={cn("m-0 mb-3.5 grid overflow-hidden rounded-[18px] border border-border bg-card max-[760px]:grid-cols-2", COLS[figures.length])}>
        {figures.map((f) => (
          <div key={f.label} className={cn(
            "min-w-0 border-l border-border px-4 py-3.5 first:border-l-0",
            "max-[760px]:border-t max-[760px]:border-l-0 max-[760px]:even:border-l max-[760px]:nth-[-n+2]:border-t-0",
            f.strong && cn(TINT, "max-[760px]:odd:col-span-full"),
          )}>
            <dt className="truncate text-[12px] text-muted-foreground">{f.op ? <span className="inline-block w-3.5 font-semibold text-foreground" aria-hidden="true">{f.op}</span> : null}{f.label}</dt>
            <dd className="m-0 mt-1.5 text-[18px] font-semibold tracking-[-.02em] tabular-nums max-[760px]:text-[16px]">{fmt(f.value)}<span className="ml-[5px] text-[12px] font-semibold tracking-normal text-muted-foreground">SAR</span></dd>
          </div>
        ))}
      </dl>

      {pending.map((p) => (
        <div key={p.settlement_id} role="status" className="mb-2.5 flex items-center gap-2 rounded-xl border border-border bg-[color:color-mix(in_oklch,var(--muted)_55%,var(--card))] px-3 py-2.5 text-[13px]">
          <Icon name="alert-circle" size={15} className="flex-none text-yellow" />
          <span className="min-w-0 flex-1">{t("{number}: {n} SAR received {date} but not allocated", { number: p.remittance_number, n: fmt(p.amount_sar), date: p.received_date })}</span>
          {perms.can("remittance", "edit") && perms.headOffice && (
            <button type="button" className="inline-flex cursor-pointer items-center gap-1 border-0 bg-transparent p-0 [font:inherit] text-[13px] font-semibold whitespace-nowrap text-foreground hover:underline" onClick={() => openForm(allocationUrl(p))}>
              {t("Allocate")}<Icon name="arrow-right" size={13} />
            </button>
          )}
        </div>
      ))}

      <div className="mb-3.5 flex flex-wrap items-start gap-2.5 max-[600px]:items-center max-[600px]:gap-2">
        <SearchBox value={query} onChange={setQuery} placeholder="Search reservation, client, hotel" />
        <div className="flex items-center gap-2 max-[600px]:w-full max-[600px]:flex-[1_1_100%]">
          <select className="h-9 min-w-[130px] flex-none appearance-none rounded-full border border-input bg-card px-3 font-[inherit] text-[12.5px] text-foreground max-[600px]:block max-[600px]:h-10 max-[600px]:w-full" value={client} onChange={(e) => setClient(e.target.value)} aria-label={t("Client")}>
            <option value="">{t("All clients")}</option>
            {clients.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      </div>

      {visible.length ? BUCKETS.map((b) => {
        const rows = visible.filter((r) => r.bucket === b.key);
        if (!rows.length) return null;
        return (
          <section key={b.key} className="mt-[18px]" aria-labelledby={`tq-${b.key}`}>
            <h3 id={`tq-${b.key}`} className="mx-1 mt-0 mb-2 flex justify-between gap-3 text-[11px] font-semibold tracking-[.07em] text-muted-foreground uppercase">
              <span>{t(b.label)} · {rows.length}</span>
              <span className="tracking-normal text-foreground tabular-nums">{fmt(rows.reduce((sum, r) => sum + r.unallocated, 0))}</span>
            </h3>
            <ul className="m-0 list-none overflow-hidden rounded-2xl border border-border bg-card p-0">
              {rows.map((row) => {
                const key = `${row.linked_number}|${row.invoice_id}`;
                return <Row key={key} row={row} t={t} open={openKey === key} onToggle={() => setOpenKey(openKey === key ? null : key)} />;
              })}
            </ul>
          </section>
        );
      }) : (
        <div className="mt-4 rounded-2xl border border-dashed border-border p-7 text-center text-[13px] text-muted-foreground">
          {query || client ? t("No matching reservation.") : t("All client money has been allocated.")}
        </div>
      )}
    </div>
  );
}

