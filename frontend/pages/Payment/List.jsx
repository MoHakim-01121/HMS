import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import { Icon } from "../../components/icons.jsx";
import ListCard from "../../components/shadcn/list-card.jsx";
import SearchBox from "../../components/shadcn/search-box.jsx";
import FilterPanel from "../../components/shadcn/filter-panel.jsx";
import FilterChips from "../../components/shadcn/filter-chips.jsx";
import useDebouncedSearch from "../../hooks/useDebouncedSearch.js";
import RowActions from "../../components/shadcn/row-actions.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import KpiCard from "../../components/shadcn/kpi-card.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import {
  Dialog, DialogCloseButton, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import Combobox from "../../components/shadcn/combobox.jsx";
import { showToast } from "../../components/shadcn/toast.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmtDMY } from "../../utils/format.js";
import { usePerms } from "../../utils/perms.js";

// Keep in sync with nginx `client_max_body_size` on the VPS. A larger file is
// rejected upstream with a 413 before it ever reaches Django, so catch it here.
const MAX_PROOF_BYTES = 3 * 1024 * 1024;

// Only the unapplied status hint needs bespoke styles —
// every field uses the shared FormField/.fg-* system, and the file input
// picks up the standard [data-slot="input"][type="file"] treatment.
const CSS = `
.pay-dialog .pay-warn { font-size: 12px; color: var(--yellow); margin-top: 4px; }


/* Pinned action strip — same treatment as the shared modal's sticky
   .hms-form-actions (tailwind.css), as a plain footer since this dialog
   doesn't render the actions inside the scrolling body. */
.pay-dialog .pay-footer {
  padding: 14px 20px;
  border-top: 1px solid var(--border);
  background: var(--background);
  flex-shrink: 0;
}
`;

// Props a filter/sort/page change needs back -- see `go` below.
const LIST_PROPS = [
  "payments", "pagination", "total_count", "q", "status_list", "date_from", "date_to",
  "sort", "sort_label", "sort_labels", "active_filters", "status_groups",
];

// Django reads ?status=a&status=b (repeated), so build the query string by hand
// -- same shape as the CL list.
function buildQuery({ q, status, date_from, date_to, sort, page }, base = "/finance/payments/") {
  const p = new URLSearchParams();
  if (q) p.append("q", q);
  (status || []).forEach((s) => p.append("status", s));
  if (date_from) p.append("date_from", date_from);
  if (date_to) p.append("date_to", date_to);
  if (sort) p.append("sort", sort);
  if (page) p.append("page", page);
  const qs = p.toString();
  return qs ? `${base}?${qs}` : base;
}

// Same list the Penalty form offers.
const CURRENCIES = ["SAR", "IDR", "USD"];

export default function List({ payments = [], invoice_choices = [], client_choices = [], account_choices = [], stats = {}, pagination = null,
  q = "", status_list = [], date_from = "", date_to = "", sort = "-created_at", sort_label = "", sort_labels = {},
  active_filters = 0, status_groups = [] }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canCreate = perms.can("payments", "create");
  const canEdit = perms.can("payments", "edit");
  // Pencatat tidak mengonfirmasi pembayarannya sendiri (kecuali admin).
  const canConfirm = (p) => canEdit && (perms.isAdmin || p.created_by !== perms.user?.username);
  const canExport = perms.can("payments", "export");
  const [panelOpen, setPanelOpen] = useState(false);
  const [sortOpen, setSortOpen] = useState(false);
  const [sel, setSel] = useState(status_list);
  const [from, setFrom] = useState(date_from);
  const [to, setTo] = useState(date_to);
  const { query, setQuery } = useDebouncedSearch(q, (qq) => go({ q: qq }));
  const [askConfirm, askConfirmUi] = useConfirm();
  const [confirmDialog, setConfirmDialog] = useState(null);
  const [rejectDialog, setRejectDialog] = useState(null);
  const [recordDialog, setRecordDialog] = useState(false);
  const [recordForm, setRecordForm] = useState({
    invoice_id: "",
    client_id: "",
    client_name: "",
    payment_date: new Date().toISOString().split("T")[0],
    amount: "",
    currency: "SAR",
    exchange_rate: "1",
    method: "",
    account: account_choices.find((a) => a.currency === "SAR")?.value || "",
    reference: "",
    note: "",
  });

  // When invoice changes, populate reservations
  const selectedInvoice = invoice_choices.find((inv) => String(inv.id) === String(recordForm.invoice_id));
  // Client-first: when a client is picked, shorten the invoice list to that
  // client's invoices only; with no client yet, every invoice stays on offer.
  const invoiceOptions = recordForm.client_id && !recordForm.invoice_id
    ? invoice_choices.filter((inv) => String(inv.client_id) === String(recordForm.client_id))
    : invoice_choices;

  // Filtering is server-side (keeps pagination consistent). Any filter change
  // drops `page`, so the result set always restarts at page 1.
  //
  // Partial reload: only the list props come back. The dialog dropdowns and
  // KPI stats are lazy on the server (payment_list), so a search keystroke no
  // longer rebuilds ~300 queries of invoice choices it never shows.
  const go = (extra = {}) =>
    router.get(buildQuery({ q: query, status: status_list, date_from, date_to, sort, ...extra }), {}, {
      preserveState: true, preserveScroll: true, replace: true, only: LIST_PROPS,
    });

  const toggleStatus = (val) => setSel((prev) => prev.includes(val) ? prev.filter((s) => s !== val) : [...prev, val]);
  const applyFilters = () => { setPanelOpen(false); go({ status: sel, date_from: from, date_to: to }); };
  const resetAll = () => { setSel([]); setFrom(""); setTo(""); setPanelOpen(false); go({ q: "", status: [], date_from: "", date_to: "" }); setQuery(""); };
  const dirty = sel.slice().sort().join() !== status_list.slice().sort().join() || from !== date_from || to !== date_to;

  const groupLabel = Object.fromEntries(status_groups.map((g) => [g.key, g.label]));
  const chips = [
    ...(q ? [{ key: "q", label: t('Keyword "{q}"', { q }), onRemove: () => { setQuery(""); go({ q: "" }); } }] : []),
    ...((date_from || date_to) ? [{ key: "date", label: t("Payment date {from} to {to}", { from: date_from || "…", to: date_to || "…" }), onRemove: () => { setFrom(""); setTo(""); go({ date_from: "", date_to: "" }); } }] : []),
    ...status_list.map((val) => ({
      key: "status-" + val,
      label: t("Status {status}", { status: t(groupLabel[val] || val) }),
      onRemove: () => { const next = status_list.filter((s) => s !== val); setSel(next); go({ status: next }); },
    })),
  ];
  const hasFilter = !!q || active_filters > 0;
  const exportHref = buildQuery({ q, status: status_list, date_from, date_to, sort }, "/finance/payments/export/csv/");

  // Parse a numeric input that may carry thousands separators -- either
  // "48,000,000" (en-US) or "48.000.000" (id-ID). Amounts, rates and
  // allocations here are practical integers, so both separators are
  // stripped before parsing (a lone "." stays a float for sub-1 rates).
  const parseNum = (v) => {
    if (v == null || v === "") return 0;
    const cleaned = String(v).replace(/[^\d.,-]/g, "");
    const n = parseFloat(cleaned.replace(/,/g, "").replace(/\.(?=\d{3}\b)/g, ""));
    return isNaN(n) ? 0 : n;
  };

  // Reset amount when invoice changes; the invoice carries its client, so a
  // picked invoice also fills the client field (backend derives client from it).
  // "__none__" is the explicit "back to deposit" choice — client is kept so a
  // deposit stays valid without retyping.
  const onInvoiceChange = (v) => {
    if (v === "__none__") {
      setRecordForm((prev) => ({ ...prev, invoice_id: "", amount: "" }));
      return;
    }
    const inv = invoice_choices.find((i) => String(i.id) === String(v));
    setRecordForm((prev) => ({
      ...prev,
      invoice_id: v,
      amount: "",
      client_id: inv ? String(inv.client_id) : prev.client_id,
      client_name: inv ? inv.client_name : prev.client_name,
    }));
  };

  // Picking a client narrows the invoice list to that client only; switching
  // to a client that owns a different invoice clears the stale invoice.
  const onClientSelect = (o) => {
    setRecordForm((prev) => {
      const prevInv = prev.invoice_id
        ? invoice_choices.find((i) => String(i.id) === String(prev.invoice_id))
        : null;
      const keepInvoice = prevInv && String(prevInv.client_id) === String(o.id);
      return {
        ...prev,
        client_id: String(o.id),
        client_name: o.name,
        invoice_id: keepInvoice ? prev.invoice_id : "",
        amount: keepInvoice ? prev.amount : "",
      };
    });
  };

  // Free-typed text without a pick means no client yet — drop the id so a
  // deposit can't be saved against a client that was only half-typed.
  const onClientText = (v) => {
    setRecordForm((prev) => ({ ...prev, client_name: v, client_id: "" }));
  };

  // Back to SAR means the rate is definitionally 1 — don't leave a stale
  // foreign rate behind for the next non-SAR payment to inherit.
  const onCurrencyChange = (v) => {
    // Money lands in an account of its own currency: re-pick when it changes.
    const still = account_choices.find((a) => a.value === recordForm.account && a.currency === v);
    setRecordForm({
      ...recordForm, currency: v, exchange_rate: v === "SAR" ? "1" : recordForm.exchange_rate,
      account: still ? still.value : (account_choices.find((a) => a.currency === v)?.value || ""),
    });
  };

  // Live SAR equivalent, mirroring the backend's convert_to_sar
  // (hw/utils.py): IDR divides by the rate, every other non-SAR currency
  // multiplies. Keeping this in lockstep with the backend is what prevents
  // the preview from disagreeing with the stored amount_sar.
  const payAmount = parseNum(recordForm.amount);
  const payRate = parseNum(recordForm.exchange_rate);
  let sarEquiv = null;
  if (recordForm.currency !== "SAR" && payAmount > 0 && payRate > 0) {
    const sar =
      recordForm.currency === "IDR"
        ? payAmount / payRate
        : payAmount * payRate;
    sarEquiv = Math.round(sar).toLocaleString("en-US");
  }


  const confirmPayment = (payment) => {
    router.post(`/finance/payments/${payment.id}/confirm/`);
    setConfirmDialog(null);
  };

  const rejectPayment = () => {
    router.post(`/finance/payments/${rejectDialog.id}/reject/`, { reason: rejectDialog.reason });
    setRejectDialog(null);
  };

  // Reverse and Void both write to the ledger, so each states its consequence
  // in writing before it runs -- same wording the detail page used to carry.
  const reversePayment = (p) => {
    askConfirm({
      title: t("Reverse Payment"),
      message: t("Are you sure you want to reverse this payment? This will create a reversing journal entry."),
      confirmLabel: "Reverse",
      icon: "swap",
      danger: true,
      onConfirm: () => router.post(`/finance/payments/${p.id}/reverse/`),
    });
  };

  const voidPayment = (p) => {
    askConfirm({
      title: t("Void Payment"),
      message: t("Void payment {number}? This posts a reversal journal entry and marks it voided.", {
        number: p.payment_number,
      }),
      confirmLabel: "Void",
      icon: "close",
      danger: true,
      onConfirm: () => router.post(`/finance/payments/${p.id}/void/`),
    });
  };

  const submitRecord = () => {
    if (recordForm.proof && recordForm.proof.size > MAX_PROOF_BYTES) {
      showToast(t("File too large. Maximum upload size is 3 MB."), "error");
      return;
    }
    if (!recordForm.proof) {
      showToast(t("Proof is required. Attach an image or PDF."), "error");
      return;
    }
    if (!recordForm.invoice_id && !recordForm.client_id) {
      showToast(t("Pick a client to record a payment without an invoice (a deposit)."), "error");
      return;
    }
    // Strip thousands separators so the backend's _to_float (which removes
    // ",") receives a clean integer and never mis-reads "4,800" as "4.8".
    const cleanNum = (v) => (v == null || v === "" ? v : String(v).replace(/,/g, ""));
    const derivedClientId = recordForm.invoice_id
      ? (selectedInvoice?.client_id ?? recordForm.client_id)
      : recordForm.client_id;
    const payload = {
      ...recordForm,
      client_id: derivedClientId,
      amount: cleanNum(recordForm.amount),
      exchange_rate: cleanNum(recordForm.exchange_rate),
    };
    const fd = new FormData();
    Object.entries(payload).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") fd.append(k, v);
    });
    fd.append("proof", recordForm.proof);
    router.post("/finance/payments/record/", fd, {
      onSuccess: () => setRecordDialog(false),
    });
  };

  // Single truncating class for the two free-text columns so long client /
  // method values ellipsize instead of stretching the auto-width table into
  // a horizontal scroll (the table itself stays w-full inside the card).
  const ellipsis = { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" };

  const columns = [
    {
      header: t("Payment #"),
      className: "col-m-primary",
      render: (p) => <span className="col-bold col-nowrap">{p.payment_number}</span>,
    },
    {
      header: t("Status"),
      className: "col-m-badge",
      // Grouped label (5 meanings) so the pill reads the same as the filter;
      // the raw status stays on the tooltip for finance staff.
      render: (p) => <span title={p.status_display}><StatusPill tone={p.status_group_tone || "gray"} label={t(p.status_group_label || p.status_display)} /></span>,
    },
    {
      header: t("Client"),
      className: "col-m-secondary",
      style: { ...ellipsis, maxWidth: 220, minWidth: 120 },
      render: (p) => p.client_name || "—",
    },
    {
      header: t("Date"),
      className: "col-m-meta col-nowrap",
      render: (p) => fmtDMY(p.payment_date) || "—",
    },
    {
      header: t("Payment for"),
      className: "col-m-meta",
      style: ellipsis,
      // An invoice payment names its invoice; one recorded without an invoice
      // is a client deposit waiting to be applied.
      render: (p) => p.invoice_number || <span style={{ color: "var(--muted-foreground)" }}>{t("Deposit")}</span>,
    },
    {
      header: t("Method"),
      className: "col-m-meta",
      style: ellipsis,
      render: (p) => p.method || "—",
    },
    {
      header: t("Amount"),
      className: "col-m-amount",
      style: { textAlign: "right" },
      render: (p) => (
        <>
          <span className="col-nowrap">
            {p.amount_sar?.toLocaleString("en-US")} SAR
          </span>
          {p.unallocated_sar > 0 && (
            <span className="pay-warn" style={{ display: "block", marginTop: 2, fontSize: 11, fontWeight: 600, whiteSpace: "nowrap" }}>
              {t("{n} SAR unallocated", { n: p.unallocated_sar?.toLocaleString("en-US") })}
            </span>
          )}
        </>
      ),
    },
    {
      header: "",
      className: "col-m-actions",
      render: (p) => (
        <RowActions
          actions={[
            canConfirm(p) && p.status === "pending"
              && { icon: "check", label: t("Confirm"), onClick: () => setConfirmDialog(p) },
            canEdit && p.status === "pending"
              && { icon: "close", label: t("Reject"), variant: "red", onClick: () => setRejectDialog({ ...p, reason: "" }) },
            canEdit && ["received", "partially_applied"].includes(p.status)
              && { icon: "arrow-right", label: t("Apply"), href: `/finance/payments/${p.id}/` },
            canEdit && ["confirmed", "allocated", "applied"].includes(p.status)
              && { icon: "swap", label: t("Reverse"), variant: "red", onClick: () => reversePayment(p) },
            canEdit && ["received", "partially_applied", "applied"].includes(p.status)
              && { icon: "trash", label: t("Void"), variant: "red", onClick: () => voidPayment(p) },
          ]}
        />
      ),
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />

      <PageHeader
        title={t("Payments")}
        sub={t("Track all payment records and their status.")}
        actions={
          <>
            {canExport && (
              <Button asChild variant="outline" size="lg">
                <a href={exportHref} target="_blank" rel="noreferrer">{t("Export CSV")}</a>
              </Button>
            )}
            {canCreate && (
              <Button size="lg" onClick={() => setRecordDialog(true)}>+ {t("Record Payment")}</Button>
            )}
          </>
        }
      />

      {/* KPI Row */}
      <div className="hms-kpi-row">
        <KpiCard label={t("Total Payments")} value={stats.total || 0} icon="wallet" />
        <KpiCard label={t("Allocated")} value={stats.allocated || 0} icon="check" tone="green" />
        <KpiCard label={t("Partially allocated")} value={stats.partially_applied || 0} icon="clock" tone="yellow" />
        {/* The warning lives in this card, not a separate banner: one number,
            one place. Yellow + the foot only appear when something is left. */}
        <KpiCard
          label={t("Unapplied")}
          value={(stats.unapplied_total ?? 0).toLocaleString("en-US")}
          unit="SAR"
          tone={(stats.unapplied_total ?? 0) > 0 ? "yellow" : undefined}
          foot={(stats.unapplied_count ?? 0) > 0
            ? t("{c} payment(s) to assign to reservations", { c: stats.unapplied_count })
            : t("All assigned")}
        />
      </div>

      {/* Filter Bar */}
      <div className="filter-bar">
        <SearchBox value={query} onChange={setQuery} placeholder="Search payment #, client, invoice, reference…" />

        <div className="fbar-actions">
          <div className="sort-wrap" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="fbar-btn" onClick={() => { setSortOpen((v) => !v); setPanelOpen(false); }}>
              <Icon name="sort" size={13} /> {sort_label}
            </button>
            {sortOpen && (
              <div className="sort-menu open">
                {Object.entries(sort_labels).map(([val, label]) => (
                  <a key={val} className={"sort-opt" + (sort === val ? " active" : "")} onClick={() => { setSortOpen(false); go({ sort: val }); }}>{label}</a>
                ))}
              </div>
            )}
          </div>

          <FilterPanel
            count={active_filters}
            open={panelOpen}
            onToggle={() => { setPanelOpen((v) => !v); setSortOpen(false); }}
            dirty={dirty}
            onApply={applyFilters}
            onResetAll={resetAll}
          >
            <div className="fp-section">
              <div className="fp-section-head">
                <span className="fp-section-label">{t("Payment date")}</span>
                <button type="button" className="fp-reset" onClick={() => { setFrom(""); setTo(""); }}>{t("Reset")}</button>
              </div>
              <div className="fp-date-row">
                <div className="fp-date-field"><label>{t("From")}</label><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></div>
                <div className="fp-date-field"><label>{t("To")}</label><input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></div>
              </div>
            </div>
            <div className="fp-section">
              <div className="fp-section-head">
                <span className="fp-section-label">{t("Status")}</span>
                <button type="button" className="fp-reset" onClick={() => setSel([])}>{t("Reset")}</button>
              </div>
              <div className="fp-status-group" data-multi role="group" aria-label={t("Status")}>
                {status_groups.map(({ key: val, label, count }) => (
                  <div key={val} className={"fp-status-opt" + (sel.includes(val) ? " selected" : "")}
                    role="checkbox" aria-checked={sel.includes(val)} tabIndex={0}
                    onClick={() => toggleStatus(val)}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleStatus(val); } }}>
                    <span className="fp-status-dot"></span>
                    <span className="fp-status-opt-label">{t(label)}</span>
                    <span className="fp-status-count">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          </FilterPanel>
        </div>
      </div>

      <FilterChips chips={chips} onClearAll={resetAll} />

      <ListCard
        columns={columns}
        rows={payments}
        rowKey={(p) => p.id}
        onRowClick={(p) => router.visit(`/finance/payments/${p.id}/`)}
        empty={{
          icon: "wallet",
          title: "No payments yet",
          sub: "Use the Record Payment button in the top right",
          filteredTitle: "No results",
          filteredSub: "Try adjusting your search filters",
        }}
        hasFilter={hasFilter}
        pagination={pagination}
        unit={t("payments")}
        onPage={(p) => go({ page: p })}
      />

      {/* Record Payment Dialog */}
      {recordDialog && (
        <Dialog open onOpenChange={(v) => { if (!v) setRecordDialog(false); }}>
          <DialogContent className="sm:max-w-3xl form-modal-content pay-dialog" showCloseButton={false}>
            <style>{CSS}</style>
            <div className="hms-modal-head">
              <div style={{ minWidth: 0 }}>
                <DialogTitle className="hms-modal-title">{t("Record Payment")}</DialogTitle>
              </div>
              <DialogCloseButton />
            </div>

            <div className="hms-modal-body">
              <form
                onSubmit={(e) => { e.preventDefault(); submitRecord(); }}
                style={{ display: "flex", flexDirection: "column", gap: 24 }}
              >
                <FormSection label={t("Payment Details")}>
                  <FormField label={t("Client")} name="client_id">
                    <Combobox
                      name="client_id"
                      value={recordForm.client_name}
                      onTextChange={onClientText}
                      onSelect={onClientSelect}
                      options={client_choices}
                      getLabel={(o) => o.name}
                      getSub={(o) => o.city}
                      placeholder={t("Search client...")}
                    />
                  </FormField>
                  <FormField
                    label={t("Invoice")}
                    name="invoice_id"
                    hint={t("Leave blank to record as a deposit.")}
                  >
                    <Select value={recordForm.invoice_id} onValueChange={onInvoiceChange}>
                      <SelectTrigger className="w-full"><SelectValue placeholder={t("Select invoice...")} /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">{t("Deposit (no invoice)")}</SelectItem>
                        {invoiceOptions.map((inv) => (
                          <SelectItem key={inv.id} value={String(inv.id)}>
                            {inv.label} ({inv.remaining?.toLocaleString("en-US")} SAR remaining)
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FormField>

                  {/* fg-3 collapses to a 2-col grid inside .hms-modal-body
                      (tailwind.css). Ordered so both states pack cleanly:
                      SAR → Date|Amount / Currency|Received / Method|Reference;
                      non-SAR → Currency pairs with its Rate. */}
                  <div className="fg-3">
                    <FormField label={t("Date")} name="payment_date" type="date" required
                      value={recordForm.payment_date}
                      onChange={(v) => setRecordForm({ ...recordForm, payment_date: v })} />
                    <FormField label={t("Amount")} name="amount" type="number" required
                      value={recordForm.amount} placeholder="0"
                      onChange={(v) => setRecordForm({ ...recordForm, amount: v })} />
                    <FormField label={t("Currency")} name="currency">
                      <Select value={recordForm.currency} onValueChange={onCurrencyChange}>
                        <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </FormField>
                    {recordForm.currency !== "SAR" && (
                      <FormField label={t("Exchange Rate")} name="exchange_rate" type="number" step="0.0001" required
                        value={recordForm.exchange_rate}
                        onChange={(v) => setRecordForm({ ...recordForm, exchange_rate: v })}
                        hint={sarEquiv ? `≈ ${sarEquiv} SAR` : undefined} />
                    )}
                    <FormField label={t("Received Into")} name="account" required>
                      {/* Radix fires onValueChange("") when the filtered options drop the
                          current value; ignore it so the auto-picked account sticks. */}
                      <Select value={recordForm.account} onValueChange={(v) => v && setRecordForm((prev) => ({ ...prev, account: v }))}>
                        <SelectTrigger className="w-full"><SelectValue placeholder={t("Select account...")} /></SelectTrigger>
                        <SelectContent>
                          {account_choices.filter((a) => a.currency === recordForm.currency).map((a) => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </FormField>
                    <FormField label={t("Method")} name="method">
                      <Select value={recordForm.method} onValueChange={(v) => setRecordForm({ ...recordForm, method: v })}>
                        <SelectTrigger className="w-full"><SelectValue placeholder={t("Select...")} /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="Cash">{t("Cash")}</SelectItem>
                          <SelectItem value="Transfer">{t("Transfer")}</SelectItem>
                          <SelectItem value="Card">{t("Card")}</SelectItem>
                        </SelectContent>
                      </Select>
                    </FormField>
                    <FormField label={t("Reference")} name="reference"
                      value={recordForm.reference} placeholder={t("TRX #, check #, etc.")}
                      onChange={(v) => setRecordForm({ ...recordForm, reference: v })} />
                  </div>

                  <FormField label={t("Note")} name="note">
                    <Textarea rows={2} value={recordForm.note}
                      onChange={(e) => setRecordForm({ ...recordForm, note: e.target.value })} />
                  </FormField>
                </FormSection>

                <FormSection label={t("Proof (required)")}>
                  <FormField name="proof" hint={t("Image or PDF — required for every payment")} required>
                    <Input type="file" accept="image/*,.pdf"
                      onChange={(e) => {
                        const f = e.target.files[0];
                        if (f && f.size > MAX_PROOF_BYTES) {
                          showToast(t("File too large. Maximum upload size is 3 MB."), "error");
                          e.target.value = "";
                          setRecordForm({ ...recordForm, proof: undefined });
                          return;
                        }
                        setRecordForm({ ...recordForm, proof: f });
                      }} />
                  </FormField>
                </FormSection>
              </form>
            </div>

            <DialogFooter className="pay-footer">
              <Button variant="outline" onClick={() => setRecordDialog(false)}>{t("Cancel")}</Button>
              <Button onClick={submitRecord} disabled={!recordForm.amount || !recordForm.proof || (!recordForm.invoice_id && !recordForm.client_id)}>
                {t("Record Payment")}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {/* Confirm Dialog */}
      {askConfirmUi}

      {confirmDialog && (
        <Dialog open onOpenChange={(v) => { if (!v) setConfirmDialog(null); }}>
          <DialogContent className="hms-dialog">
            <DialogHeader>
              <DialogTitle>{t("Confirm Payment")}</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-muted-foreground">
              {t("Confirm payment {number} for {amount} SAR?", {
                number: confirmDialog.payment_number,
                amount: confirmDialog.amount_sar?.toLocaleString("en-US"),
              })}
            </p>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirmDialog(null)}>{t("Cancel")}</Button>
              <Button onClick={() => confirmPayment(confirmDialog)}>{t("Confirm")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {/* Reject Dialog */}
      {rejectDialog && (
        <Dialog open onOpenChange={(v) => { if (!v) setRejectDialog(null); }}>
          <DialogContent className="hms-dialog">
            <DialogHeader>
              <DialogTitle>{t("Reject Payment")}</DialogTitle>
            </DialogHeader>
            <FormField label={t("Reason")} name="reject_reason">
              <Textarea
                rows={3}
                placeholder={t("Reason for rejection...")}
                value={rejectDialog.reason}
                onChange={(e) => setRejectDialog({ ...rejectDialog, reason: e.target.value })}
              />
            </FormField>
            <DialogFooter>
              <Button variant="outline" onClick={() => setRejectDialog(null)}>{t("Cancel")}</Button>
              <Button variant="destructive" onClick={rejectPayment}>{t("Reject")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
