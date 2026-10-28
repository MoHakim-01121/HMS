import { useContext, useMemo, useState } from "react";
import { useForm } from "@inertiajs/react";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import SearchBox from "../../components/shadcn/search-box.jsx";
import { FormModalContext, StandaloneFormModal } from "../../components/shadcn/form-modal.jsx";
import { Icon } from "../../components/icons.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";
import AllocationTable, { EMPTY, allocKey, suggestAllocations } from "./AllocationTable.jsx";
import Page from "../../components/shadcn/page.jsx";
import { cn } from "@/lib/utils";

// Two panels like the CL and Invoice forms: the fields and the allocation
// list, and a 300px summary rail. Below 1100px the rail drops under the list
// and sticks to the bottom of the dialog, so the total and Save stay in view.
const LBL = "text-[11px] font-semibold tracking-[.06em] text-muted-foreground uppercase";
const NUM = "text-right whitespace-nowrap tabular-nums";
const ROW = "flex justify-between gap-3 text-muted-foreground [&>span:last-child]:font-medium [&>span:last-child]:text-foreground";
const TOOL = "h-9 cursor-pointer rounded-full border border-border bg-card px-3 font-[inherit] leading-[inherit] text-[12px] font-semibold text-foreground hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring";
const NOTE = {
  muted: "border border-border bg-card text-muted-foreground",
  warn: "border border-border bg-[color:color-mix(in_oklch,var(--muted)_55%,var(--card))] text-foreground",
  err: "border border-[color:color-mix(in_oklch,var(--red)_30%,var(--border))] bg-[color:color-mix(in_oklch,var(--red)_8%,var(--card))] text-red",
};


// Catat penerimaan Pusat + alokasikan uangnya ke reservasi (satu langkah),
// atau ubah alokasi satu penerimaan (`settlement` terisi). Backend:
// hw/views/settlement_views.py, aturan di hw/finance/remittance_allocation.py.
export default function Receipt({ rem, settlement, candidates = [], form: initial, error, next }) {
  const { t } = useI18n();
  const editing = !!settlement;
  const closeHref = next || `/remittance/${rem.id}/`;
  const inModal = useContext(FormModalContext)?.inModal;

  const form = useForm({
    received_amount_sar: String(initial?.received_amount_sar ?? ""),
    received_date: initial?.received_date || "",
    reference: initial?.reference || "",
  });
  const [values, setValues] = useState(() => (
    initial?.allocations
      ? Object.fromEntries(initial.allocations.map((a) => [allocKey(a), String(a.amount_sar)]))
      : suggestAllocations(candidates, Math.min(Number(initial?.received_amount_sar) || 0, rem.remaining_to_allocate))
  ));
  const [query, setQuery] = useState("");

  const received = Number(form.data.received_amount_sar) || 0;
  const allocated = Object.values(values).reduce((sum, v) => sum + (Number(v) || 0), 0);
  const overRow = candidates.some((row) => (Number(values[allocKey(row)]) || 0) > row.available);
  const overTransfer = allocated > rem.remaining_to_allocate;
  const canSave = !form.processing && !overRow && !overTransfer && (editing || received > 0);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return candidates;
    return candidates.filter((r) => [r.linked_number, r.customer_name, r.hotel, r.invoice_number]
      .some((v) => (v || "").toLowerCase().includes(q)));
  }, [candidates, query]);

  const setValue = (key, v) => setValues((prev) => ({ ...prev, [key]: v }));
  const autoFill = () => setValues(suggestAllocations(candidates, Math.min(received, rem.remaining_to_allocate)));

  const submit = (e) => {
    e.preventDefault();
    const allocations = candidates
      .map((row) => ({ linked_number: row.linked_number, invoice_id: row.invoice_id, amount_sar: Number(values[allocKey(row)]) || 0 }))
      .filter((a) => a.amount_sar > 0);
    form.transform((d) => ({ ...d, allocations, next: closeHref }));
    form.post(editing ? `/remittance/${rem.id}/receipt/${settlement.id}/allocation/` : `/remittance/${rem.id}/receipt/`);
  };

  let railNote = null;
  if (overTransfer) {
    railNote = { tone: "err", text: t("Exceeds what is left of this transfer ({n} SAR).", { n: fmt(rem.remaining_to_allocate) }) };
  } else if (allocated > received) {
    railNote = { tone: "warn", text: t("{n} SAR more than received. Normal on the last receipt: the difference becomes a fee when closed.", { n: fmt(allocated - received) }) };
  } else if (allocated < received) {
    railNote = { tone: "muted", text: t("{n} SAR not allocated yet — you can allocate it later.", { n: fmt(received - allocated) }) };
  }

  const page = (
    <Page data-modal-width="wider">
      <PageBack href={closeHref} label={t("Back")} />
      <FormHeader
        kicker={t("Remittance")}
        title={editing
          ? t("Change Allocation · {number}", { number: rem.remittance_number })
          : t("Record Receipt · {number}", { number: rem.remittance_number })}
        sub={rem.amount_idr != null
          ? t("Transfer {date} · {idr} IDR @ {rate}", { date: rem.date, idr: fmt(rem.amount_idr), rate: fmt(rem.exchange_rate) })
          : t("Transfer {date}", { date: rem.date })}
      />

      <form method="post" onSubmit={submit} className="mt-[22px] in-data-[slot=modal-body]:mt-0">
        <div className="flex items-stretch rounded-card border border-border bg-card max-[1099px]:flex-col in-data-[slot=modal-body]:-mx-5 in-data-[slot=modal-body]:-my-6 in-data-[slot=modal-body]:rounded-none in-data-[slot=modal-body]:border-0">
          <div className="flex min-w-0 flex-1 flex-col gap-[22px] px-7 py-6 max-[1099px]:p-5">
            {error && <div className="flex items-center gap-2 rounded-xl border border-[color:color-mix(in_oklch,var(--red)_30%,var(--border))] bg-[color:color-mix(in_oklch,var(--red)_8%,var(--card))] text-red px-3 py-2.5 text-[13px]" role="alert"><Icon name="alert-circle" size={15} />{error}</div>}

            <div className="grid grid-cols-3 gap-3 max-[700px]:grid-cols-1 [&_[data-slot=form-field]_label]:text-[11px] [&_[data-slot=form-field]_label]:font-semibold [&_[data-slot=form-field]_label]:tracking-[.06em] [&_[data-slot=form-field]_label]:text-muted-foreground [&_[data-slot=form-field]_label]:uppercase">
              {editing ? (
                <div className="col-span-full flex flex-col gap-1.5">
                  <span className={LBL}>{t("Received")}</span>
                  <span className="text-[14px] font-semibold tabular-nums">{fmt(settlement.received_amount_sar)} SAR · {settlement.received_date}</span>
                </div>
              ) : (
                <>
                  <FormField label={t("Received amount (SAR)")} name="received_amount_sar" type="number" min="1" required autoFocus
                    value={form.data.received_amount_sar} onChange={(v) => form.setData("received_amount_sar", v)} />
                  <FormField label={t("Received date")} name="received_date" type="date" required
                    value={form.data.received_date} onChange={(v) => form.setData("received_date", v)} />
                  <FormField label={t("Bank reference")} name="reference"
                    value={form.data.reference} onChange={(v) => form.setData("reference", v)} />
                </>
              )}
            </div>

            {rem.can_allocate ? (
              <section className="flex flex-col gap-3" aria-labelledby="rcp-alloc-title">
                <div className="flex flex-wrap items-end justify-between gap-3">
                  <div>
                    <h3 id="rcp-alloc-title" className="m-0 text-[13px] font-semibold text-foreground">{t("Allocate to reservations")}</h3>
                    <p className="mt-[3px] mb-0 text-[12px] text-muted-foreground">{t("Paid in full first, then nearest check-in. Every amount can be changed.")}</p>
                  </div>
                  <div className="flex items-center gap-1.5 max-[700px]:w-full">
                    <SearchBox value={query} onChange={setQuery} placeholder="Search reservation, client, hotel"
                      className="h-9 w-[250px] phone:h-9 max-[700px]:w-auto max-[700px]:min-w-0" />
                    <button type="button" className={TOOL} onClick={autoFill}>{t("Auto-fill")}</button>
                    <button type="button" className={TOOL} onClick={() => setValues({})}>{t("Clear")}</button>
                  </div>
                </div>
                <AllocationTable
                  rows={shown} values={values} onChange={setValue}
                  emptyText={candidates.length ? t("No matching reservation.") : t("No client money waiting to be allocated.")}
                />
              </section>
            ) : (
              <p className={EMPTY}>{t("Transfers without an IDR amount and rate are allocated when sent — nothing to allocate here.")}</p>
            )}
          </div>

          <aside className="flex w-[300px] flex-none flex-col gap-4 border-l border-border bg-[color:color-mix(in_oklch,var(--muted)_38%,var(--card))] p-6 max-[1099px]:sticky max-[1099px]:bottom-0 max-[1099px]:z-2 max-[1099px]:w-auto max-[1099px]:gap-2.5 max-[1099px]:border-t max-[1099px]:border-l-0 max-[1099px]:px-5 max-[1099px]:py-3.5 max-[700px]:gap-2 max-[700px]:px-4 max-[700px]:py-3" aria-label={t("Summary")}>
            <div className="sticky top-0 flex flex-col gap-[9px] text-[13px] max-[1099px]:static">
              <div className={cn(ROW, "max-[1099px]:hidden")}><span>{t("Transfer")}</span><span className={NUM}>{fmt(rem.basis_sar ?? 0)}</span></div>
              <div className={cn(ROW, "max-[1099px]:hidden")}><span>{t("Received before")}</span><span className={NUM}>{fmt(rem.settled_sar - (editing ? settlement.received_amount_sar : 0))}</span></div>
              <div className={cn(ROW, "max-[700px]:hidden")}><span>{editing ? t("This receipt") : t("Received now")}</span><span className={NUM}>{fmt(received)}</span></div>
              <div className={cn(ROW, "border-t border-border pt-[9px] font-semibold text-foreground max-[1099px]:border-t-0 max-[1099px]:pt-0 [&>span:last-child]:text-[20px] [&>span:last-child]:font-semibold [&>span:last-child]:tracking-[-.02em] max-[1099px]:[&>span:last-child]:text-[17px]")}><span>{t("Allocated")}</span><span className={NUM}>{fmt(allocated)}</span></div>
              <div className={cn(ROW, "max-[700px]:hidden")}><span>{t("Left to allocate")}</span><span className={NUM}>{fmt(Math.max(received - allocated, 0))}</span></div>
            </div>
            {railNote && <p className={cn("m-0 rounded-[10px] px-[11px] py-[9px] text-[12px] leading-normal", NOTE[railNote.tone])} role={railNote.tone === "err" ? "alert" : undefined}>{railNote.text}</p>}
            <div className="sticky bottom-0 -mx-6 mt-auto -mb-6 bg-[color:color-mix(in_oklch,var(--muted)_38%,var(--card))] px-6 pt-4 pb-6 max-[1099px]:static max-[1099px]:m-0 max-[1099px]:bg-transparent max-[1099px]:p-0">
              <button type="submit" className="h-[42px] w-full cursor-pointer rounded-[12px] border-0 bg-primary font-[inherit] leading-[inherit] text-[13px] font-semibold text-primary-foreground hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-55 max-[700px]:h-10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solid focus-visible:outline-ring" disabled={!canSave}>
                {form.processing ? t("Saving…") : editing ? t("Save Allocation") : t("Save Receipt")}
              </button>
            </div>
          </aside>
        </div>
      </form>
    </Page>
  );

  return inModal ? page : <StandaloneFormModal closeHref={closeHref}>{page}</StandaloneFormModal>;
}
