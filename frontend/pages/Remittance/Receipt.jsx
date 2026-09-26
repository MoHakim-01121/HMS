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
import AllocationTable, { allocKey, suggestAllocations } from "./AllocationTable.jsx";
import { REM_TABLE_CSS, RECEIPT_CSS } from "./remittanceStyles.js";

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
    <div className="page rcp-form shadcn-root">
      <style>{REM_TABLE_CSS + RECEIPT_CSS}</style>
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

      <form method="post" onSubmit={submit}>
        <div className="rcp-card">
          <div className="rcp-main">
            {error && <div className="rcp-alert" role="alert"><Icon name="alert-circle" size={15} />{error}</div>}

            <div className="rcp-fields">
              {editing ? (
                <div className="rcp-fixed">
                  <span className="rcp-lbl">{t("Received")}</span>
                  <span className="rcp-fixed-v">{fmt(settlement.received_amount_sar)} SAR · {settlement.received_date}</span>
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
              <section className="rcp-alloc" aria-labelledby="rcp-alloc-title">
                <div className="rcp-alloc-h">
                  <div>
                    <h3 id="rcp-alloc-title" className="rcp-alloc-title">{t("Allocate to reservations")}</h3>
                    <p className="rcp-alloc-desc">{t("Paid in full first, then nearest check-in. Every amount can be changed.")}</p>
                  </div>
                  <div className="rcp-alloc-tools">
                    <SearchBox value={query} onChange={setQuery} placeholder="Search reservation, client, hotel" />
                    <button type="button" className="rcp-tool" onClick={autoFill}>{t("Auto-fill")}</button>
                    <button type="button" className="rcp-tool" onClick={() => setValues({})}>{t("Clear")}</button>
                  </div>
                </div>
                <AllocationTable
                  rows={shown} values={values} onChange={setValue}
                  emptyText={candidates.length ? t("No matching reservation.") : t("No client money waiting to be allocated.")}
                />
              </section>
            ) : (
              <p className="rcp-legacy">{t("Transfers without an IDR amount and rate are allocated when sent — nothing to allocate here.")}</p>
            )}
          </div>

          <aside className="rcp-rail" aria-label={t("Summary")}>
            <div className="rcp-rows">
              <div className="rcp-row rcp-row-full"><span>{t("Transfer")}</span><span className="rcp-num">{fmt(rem.basis_sar ?? 0)}</span></div>
              <div className="rcp-row rcp-row-full"><span>{t("Received before")}</span><span className="rcp-num">{fmt(rem.settled_sar - (editing ? settlement.received_amount_sar : 0))}</span></div>
              <div className="rcp-row"><span>{editing ? t("This receipt") : t("Received now")}</span><span className="rcp-num">{fmt(received)}</span></div>
              <div className="rcp-row rcp-row-total"><span>{t("Allocated")}</span><span className="rcp-num">{fmt(allocated)}</span></div>
              <div className="rcp-row"><span>{t("Left to allocate")}</span><span className="rcp-num">{fmt(Math.max(received - allocated, 0))}</span></div>
            </div>
            {railNote && <p className={`rcp-note is-${railNote.tone}`} role={railNote.tone === "err" ? "alert" : undefined}>{railNote.text}</p>}
            <div className="rcp-actions">
              <button type="submit" className="rcp-cta" disabled={!canSave}>
                {form.processing ? t("Saving…") : editing ? t("Save Allocation") : t("Save Receipt")}
              </button>
            </div>
          </aside>
        </div>
      </form>
    </div>
  );

  return inModal ? page : <StandaloneFormModal closeHref={closeHref}>{page}</StandaloneFormModal>;
}
