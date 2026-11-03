import { useMemo, useState } from "react";
import SearchBox from "../../components/shadcn/search-box.jsx";
import { Icon } from "../../components/icons.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { TableCard, PRow, PBand, Tr, Th, Td, Empty, Primary } from "../../components/shadcn/list-a.jsx";
import { Checkbox } from "../../components/shadcn/ui/checkbox.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";
import { cn } from "@/lib/utils";

// Tab Tracking: uang klien di Surabaya yang belum dialokasikan, per reservasi,
// dalam satu tabel yang dikelompokkan menurut dekatnya check-in. Angka
// ringkasan membentuk hitungan yang bisa dicek (kolom 1 − kolom 2 − kolom 3 =
// kolom 4). Reservasi yang dicentang menjadi rencana transfer baru
// (RemittancePlanLine). Data dari _compute_tracking_data
// (hw/views/remittance_views.py).
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

const TABLE_COLS = [52, null, 120, 120, 170, 130, 44];

// What happened to a reservation's money, oldest first, under its row.
function History({ row, t, className }) {
  return (
    <ol className={cn("m-0 flex max-w-[560px] list-none flex-col gap-2 [&>li]:relative [&>li]:flex [&>li]:items-baseline [&>li]:gap-2 [&>li]:text-[13px]", className)}>
      <li><span className={cn(DOT, "border-foreground bg-foreground")} />{t("Paid by client")}<span className={AMT}>{fmt(row.paid_sar)}</span></li>
      {row.history.map((h, i) => (
        <li key={`${h.rmt_id}-${i}`}>
          <span className={cn(DOT, "border-foreground bg-foreground")} />
          {h.kind === "receipt" ? t("Received at HQ {date}", { date: h.date }) : t("Sent {date}", { date: h.date })}
          <a className="font-mono text-[12px] text-muted-foreground no-underline hover:text-foreground hover:underline" href={`/remittance/${h.rmt_id}/`}>{h.rmt_number}</a>
          <span className={AMT}>{fmt(h.amount_sar)}</span>
        </li>
      ))}
      {row.planned.map((p) => (
        <li key={`plan-${p.rmt_id}`} className="text-muted-foreground">
          <span className={DOT} />
          {t("Planned, not received yet")}
          <a className="font-mono text-[12px] text-muted-foreground no-underline hover:text-foreground hover:underline" href={`/remittance/${p.rmt_id}/`}>{p.rmt_number}</a>
          <span className={AMT}>{fmt(p.amount_sar)}</span>
        </li>
      ))}
      {row.to_send > 0 && (
        <li className="text-muted-foreground"><span className={DOT} />{t("Still to send")}<span className={AMT}>{fmt(row.to_send)}</span></li>
      )}
    </ol>
  );
}

function Row({ row, open, onToggle, checked, onCheck, canPlan, t }) {
  const partial = row.paid_sar < row.total_sar;
  const planned = row.planned.reduce((sum, p) => sum + p.amount_sar, 0);
  return (
    <>
      <Tr aria-expanded={open} onClick={onToggle} row={checked ? "on" : undefined}>
        <Td onClick={(e) => e.stopPropagation()}>
          {canPlan && row.to_send > 0 && (
            <Checkbox checked={checked} onCheckedChange={onCheck} aria-label={t("Plan {number}", { number: row.linked_number })} />
          )}
        </Td>
        <Td className="truncate">
          <span className="mr-2 font-mono text-[12px] font-bold">{row.linked_number}</span>{row.client_name}
          <span className="mt-0.5 block truncate text-[12px] font-normal text-muted-foreground">{row.hotel}</span>
        </Td>
        <Td>{row.check_in || "—"}</Td>
        <Td className="text-right">
          {fmt(row.paid_sar)}
          {partial && <span className="mt-0.5 block text-[12px] font-normal text-muted-foreground">{t("of {total}", { total: fmt(row.total_sar) })}</span>}
        </Td>
        <Td className="text-right">
          {planned ? fmt(planned) : <span className="text-muted-foreground">—</span>}
          {row.planned.length > 0 && <span className="mt-0.5 block truncate font-mono text-[11px] font-normal text-muted-foreground">{row.planned.map((p) => p.rmt_number).join(", ")}</span>}
        </Td>
        <Td className={cn("text-right font-semibold", row.to_send <= 0 && "font-medium text-muted-foreground")}>{fmt(row.to_send)}</Td>
        <Td><Icon name="chevron" size={14} className={cn("text-muted-foreground transition-[rotate] duration-150", open && "rotate-180")} /></Td>
      </Tr>
      {open && (
        <Tr row="static">
          <Td colSpan={TABLE_COLS.length} className="whitespace-normal">
            <History row={row} t={t} className="py-1 pl-[52px]" />
          </Td>
        </Tr>
      )}
    </>
  );
}

export default function TrackingPanel({ tracking, canPlan }) {
  const { t } = useI18n();
  const openForm = useFormModal();
  const perms = usePerms();
  const [query, setQuery] = useState("");
  const [client, setClient] = useState("");
  const [openKey, setOpenKey] = useState(null);
  const [picked, setPicked] = useState(() => new Set());

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
  const selectable = visible.filter((r) => r.to_send > 0);
  const chosen = reservations.filter((r) => picked.has(r.invoice_line_id) && r.to_send > 0);
  const chosenSar = chosen.reduce((sum, r) => sum + r.to_send, 0);
  const setMany = (rows, on) => setPicked((prev) => {
    const next = new Set(prev);
    rows.forEach((r) => (on ? next.add(r.invoice_line_id) : next.delete(r.invoice_line_id)));
    return next;
  });
  const stateOf = (rows) => {
    const n = rows.filter((r) => picked.has(r.invoice_line_id)).length;
    return n === 0 ? false : n === rows.length ? true : "indeterminate";
  };
  const planQuery = `plan=${chosen.map((r) => `${r.invoice_line_id}:${r.to_send}`).join(",")}`;
  const planUrl = `/remittance/new/?${planQuery}`;

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

      <div className="mb-3.5 flex flex-wrap items-start gap-2.5 phone:items-center phone:gap-2">
        <SearchBox value={query} onChange={setQuery} placeholder="Search reservation, client, hotel" />
        <div className="flex items-center gap-2 phone:w-full phone:flex-[1_1_100%]">
          <select className="h-9 min-w-[130px] flex-none appearance-none rounded-full border border-input bg-card px-3 font-[inherit] text-[12.5px] text-foreground phone:block phone:h-10 phone:w-full" value={client} onChange={(e) => setClient(e.target.value)} aria-label={t("Client")}>
            <option value="">{t("All clients")}</option>
            {clients.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        {canPlan && chosen.length > 0 && (
          <div className="ml-auto flex items-center gap-3 phone:ml-0 phone:w-full phone:justify-between">
            <span className="text-[13px] text-muted-foreground tabular-nums">{t("{n} chosen · {sar} SAR", { n: chosen.length, sar: fmt(chosenSar) })}</span>
            <Button asChild variant="outline">
              <a href={`/remittance/draft/pdf/?${planQuery}`} target="_blank" rel="noreferrer"><Icon name="file-text" size={15} />{t("Print draft")}</a>
            </Button>
            <Primary label={t("Create remittance")} onClick={() => openForm(planUrl)} />
          </div>
        )}
      </div>

      <TableCard cols={TABLE_COLS}
        phone={BUCKETS.map((b) => {
          const rows = visible.filter((r) => r.bucket === b.key);
          if (!rows.length) return null;
          const open = rows.filter((r) => r.to_send > 0);
          return [
            <PBand key={b.key} label={t(b.label)} count={rows.length} end={fmt(rows.reduce((sum, r) => sum + r.to_send, 0))}
              lead={canPlan && open.length > 0 && <Checkbox checked={stateOf(open)} onCheckedChange={(v) => setMany(open, v === true)} aria-label={t("Choose {group}", { group: t(b.label) })} />} />,
            ...rows.map((row) => {
              const key = `${row.linked_number}|${row.invoice_id}`;
              const checked = picked.has(row.invoice_line_id);
              return (
                <PRow key={key} mono no={row.linked_number} on={checked}
                  lead={canPlan && row.to_send > 0 && <Checkbox checked={checked} onCheckedChange={(v) => setMany([row], v === true)} aria-label={t("Plan {number}", { number: row.linked_number })} />}
                  end={fmt(row.to_send)} amountTone={row.to_send <= 0 ? "font-medium text-muted-foreground" : undefined}
                  title={row.client_name}
                  meta={[row.check_in, row.hotel].filter(Boolean).join(" · ")}
                  note={row.paid_sar < row.total_sar ? t("{paid} of {total}", { paid: fmt(row.paid_sar), total: fmt(row.total_sar) }) : null}
                  onClick={() => setOpenKey(openKey === key ? null : key)}>
                  {openKey === key && <History row={row} t={t} className="pt-0 pr-4 pb-3.5 pl-11" />}
                </PRow>
              );
            }),
          ];
        })}
        empty={visible.length ? null : (
        <Empty title={query || client ? t("No matching reservation.") : t("All client money has been allocated.")} />
      )}>
        <thead>
          <tr>
            <Th>
              {canPlan && selectable.length > 0 && (
                <Checkbox checked={stateOf(selectable)} onCheckedChange={(v) => setMany(selectable, v === true)} aria-label={t("Choose all")} />
              )}
            </Th>
            <Th>{t("Reservation")}</Th>
            <Th>{t("Check-in")}</Th>
            <Th className="text-right">{t("Paid by client")}</Th>
            <Th className="text-right">{t("Planned")}</Th>
            <Th className="text-right">{t("Still to send")}</Th>
            <Th />
          </tr>
        </thead>
        <tbody>
          {BUCKETS.map((b) => {
            const rows = visible.filter((r) => r.bucket === b.key);
            if (!rows.length) return null;
            const open = rows.filter((r) => r.to_send > 0);
            return [
              <Tr key={b.key} row="band">
                <Td>
                  {canPlan && open.length > 0 && (
                    <Checkbox checked={stateOf(open)} onCheckedChange={(v) => setMany(open, v === true)} aria-label={t("Choose {group}", { group: t(b.label) })} />
                  )}
                </Td>
                <Td colSpan={4}>{t(b.label)} <span className="ml-1 font-normal text-muted-foreground">{rows.length}</span></Td>
                <Td className="text-right">{fmt(rows.reduce((sum, r) => sum + r.to_send, 0))}</Td>
                <Td />
              </Tr>,
              ...rows.map((row) => {
                const key = `${row.linked_number}|${row.invoice_id}`;
                return (
                  <Row key={key} row={row} t={t} canPlan={canPlan}
                    open={openKey === key} onToggle={() => setOpenKey(openKey === key ? null : key)}
                    checked={picked.has(row.invoice_line_id)} onCheck={(v) => setMany([row], v === true)} />
                );
              }),
            ];
          })}
        </tbody>
      </TableCard>
    </div>
  );
}
