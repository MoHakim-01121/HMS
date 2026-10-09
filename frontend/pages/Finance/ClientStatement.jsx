import { useMemo, useState } from "react";
import { Link, router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import Pagination from "../../components/shadcn/pagination.jsx";
import PendingOutTable from "../../components/shadcn/pending-out-table.jsx";
import SearchBox from "../../components/shadcn/search-box.jsx";
import { RvBack } from "../../components/shadcn/record-view.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Popover, PopoverContent, PopoverTrigger } from "../../components/shadcn/ui/popover.jsx";
import useDebouncedSearch from "../../hooks/useDebouncedSearch.js";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { fmt, fmtDate, fmtDateShort } from "../../utils/format.js";

// The client ledger, built around what a bookkeeper opens it for:
//   1. where the client stands — one sentence under the name;
//   2. checking lines — the table is the page, with its own opening row and
//      period totals, so no figure lives outside it;
//   3. sending the statement — PDF sits beside the period it prints;
//   4. moving deposit money — offered only when there is money to move.
// Colour is spent on exceptions only: red for past-due, green for credit.

const LINE_KIND = {
  charge: "Invoice issued",
  payment: "Payment received",
  allocate: "Payment allocated",
  credit_note: "Credit note",
  refund: "Refund",
  transfer: "Deposit movement",
  penalty: "Cancellation penalty",
  reversal: "Reversal",
  remittance: "Remittance",
  remittance_diff: "Remittance difference",
  expense: "Expense",
  adjustment: "Adjustment",
};

const iso = (d) => {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
};
// Calendar presets, matching the backend's default (three calendar months),
// then the umrah seasons (named by the user, so not translated).
const presets = (seasons = []) => {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth();
  return [
    { key: "month", label: "This month", from: iso(new Date(y, m, 1)), to: "" },
    { key: "3m", label: "Last 3 months", from: iso(new Date(y, m - 2, 1)), to: "" },
    { key: "year", label: "This year", from: iso(new Date(y, 0, 1)), to: "" },
    { key: "all", label: "All time", from: "", to: "" },
    ...seasons.map((s) => ({ key: `season-${s.id}`, label: s.name, raw: true, from: s.date_from, to: s.date_to })),
  ];
};

const balanceTone = (n) => (n < 0 ? "is-credit" : "");

export default function ClientStatement({
  client = {}, statement = {}, aging = {}, pagination = null,
  mode = "balance", date_from, date_to, seasons = [], pending_out = [],
}) {
  const { t, locale } = useI18n();
  const perms = usePerms();
  const canExportPdf = perms.can("statements", "export");
  const canMoveMoney = perms.can("payments", "edit");
  const openForm = useFormModal();
  const {
    transactions = [], open_items = [],
    total_open = 0, closing_balance = 0,
    total_debit = 0, total_credit = 0, opening_balance = 0,
    months = {}, hidden_voided = 0, show_voided = false, q = "",
  } = statement;
  const isOpen = mode === "open";

  const go = (params = {}) => router.get(
    `/finance/clients/${client.id}/statement/`,
    {
      mode: isOpen ? "open" : "",
      from: date_from || "",
      to: date_to || "",
      q: q || "",
      voided: show_voided ? "1" : "",
      page: "",
      ...params,
    },
    { preserveScroll: true, preserveState: true },
  );
  const { query, setQuery } = useDebouncedSearch(q, (qq) => go({ q: qq }));

  const balance = isOpen ? total_open : closing_balance;
  const late = (aging.invoices || []).filter((i) => i.days_overdue > 0);
  const fundHeld = Number(client.saldo_dana || 0);
  const showMoneyAction = canMoveMoney && (fundHeld > 0 || balance < 0);

  // ── Summary: one sentence, colour only on the part that needs action ──
  let summary;
  if (balance > 0) {
    summary = (
      <>
        <strong>{fmt(balance)} SAR</strong> {t("owed")}
        <span className="cl-sep">·</span>
        {late.length ? (
          <span className="cl-late-text">
            {t("{n} past due, the oldest {inv} by {d} days", {
              n: late.length, inv: late[0].invoice_number, d: late[0].days_overdue,
            })}
            {!isOpen ? (
              <button type="button" className="cl-inline-link" onClick={() => go({ mode: "open", q: "" })}>
                {t("See open invoices")}
              </button>
            ) : null}
          </span>
        ) : (
          t("nothing past due")
        )}
      </>
    );
  } else if (balance < 0) {
    summary = <><strong className="cl-credit">{fmt(-balance)} SAR</strong> {t("in credit — ours to refund or offset")}</>;
  } else {
    summary = <>{t("Settled — nothing owed.")}</>;
  }

  // ── Period control ──
  const presetList = presets(seasons);
  const activePreset = presetList.find((p) => p.from === (date_from || "") && p.to === (date_to || ""));
  const periodLabel = isOpen
    ? (date_to ? t("As of {d}", { d: fmtDate(date_to) }) : t("Today"))
    : activePreset
      ? (activePreset.raw ? activePreset.label : t(activePreset.label))
      : `${date_from ? fmtDate(date_from) : "…"} – ${date_to ? fmtDate(date_to) : t("today")}`;
  const qs = () => {
    const p = new URLSearchParams();
    if (date_from) p.set("from", date_from);
    if (date_to) p.set("to", date_to);
    if (isOpen) p.set("mode", "open");
    const s = p.toString();
    return s ? `?${s}` : "";
  };

  const monthName = (key) => {
    const [y, m] = key.split("-").map(Number);
    return new Date(y, m - 1, 1).toLocaleString(locale === "id" ? "id-ID" : "en-US", { month: "long", year: "numeric" });
  };
  const groups = useMemo(() => {
    const out = [];
    transactions.forEach((r) => {
      const key = (r.date || "").slice(0, 7);
      if (!out.length || out[out.length - 1].key !== key) out.push({ key, rows: [] });
      out[out.length - 1].rows.push(r);
    });
    return out;
  }, [transactions]);

  const openRows = useMemo(
    () => [...open_items].sort((a, b) => (b.days_overdue || 0) - (a.days_overdue || 0)
      || (a.due_date || "").localeCompare(b.due_date || "")),
    [open_items],
  );

  const firstPage = !pagination || pagination.number === 1;

  return (
    <div className="page shadcn-root cl-page">
      <style>{CSS}</style>
      <RvBack href="/finance/statements/" label={t("Back to Client Ledger")} />

      <header className="cl-head">
        <div className="cl-head-main">
          <h1 className="cl-h1">
            <Link href={`/clients/${client.id}/`} className="cl-h1-link">{client.name}</Link>
          </h1>
          <p className="cl-summary">{summary}</p>
        </div>
        {showMoneyAction ? (
          <div className="cl-head-act">
            {fundHeld > 0 ? <span className="cl-held">{t("{a} SAR held", { a: fmt(fundHeld) })}</span> : null}
            <Button type="button" variant="outline" size="lg" onClick={() => openForm(`/finance/clients/${client.id}/deposit-transfer/`)}>
              {t("Deposit / Refund")}
            </Button>
          </div>
        ) : null}
      </header>

      {pending_out.length > 0 && (
        <section className="cl-card cl-pending">
          <h2 className="cl-h2">{t("Awaiting Approval")} <span className="cl-dim">{pending_out.length}</span></h2>
          <PendingOutTable rows={pending_out} />
        </section>
      )}

      <section className="cl-card">
        <div className="cl-toolbar">
          <div className="cl-modes" role="tablist" aria-label={t("Statement view")}>
            <button type="button" role="tab" aria-selected={!isOpen} className={!isOpen ? "is-active" : undefined} onClick={() => go({ mode: "", q: "" })}>
              {t("Statement")}
            </button>
            <button type="button" role="tab" aria-selected={isOpen} className={isOpen ? "is-active" : undefined} onClick={() => go({ mode: "open", q: "", from: "" })}>
              {t("Open Invoices")}
              {(isOpen ? open_items.length : aging.invoices?.length) ? (
                <span className="cl-modes-n">{isOpen ? open_items.length : aging.invoices.length}</span>
              ) : null}
            </button>
          </div>
          <div className="cl-tools">
            {!isOpen ? (
              <div className="cl-search">
                <SearchBox value={query} onChange={setQuery} placeholder={t("Search number")} />
              </div>
            ) : null}
            <PeriodPicker
              isOpen={isOpen} label={periodLabel} presets={presetList} active={activePreset?.key}
              dateFrom={date_from} dateTo={date_to} onApply={(from, to) => go({ from, to })} t={t}
            />
            {canExportPdf ? (
              <Button asChild variant="outline" size="lg" className="cl-icon-btn">
                <a href={`/finance/clients/${client.id}/statement/pdf/${qs()}`} target="_blank" rel="noreferrer" aria-label={t("Statement PDF")} title={t("Statement PDF")}>
                  <Icon name="download" size={16} />
                </a>
              </Button>
            ) : null}
          </div>
        </div>

        {!isOpen && (hidden_voided > 0 || show_voided) ? (
          <p className="cl-notice">
            {show_voided
              ? t("Reversed entries are shown, struck through.")
              : t("{n} reversed entries hidden — each cancels its pair, so balances are unchanged.", { n: hidden_voided })}
            <button type="button" className="cl-inline-link" onClick={() => go({ voided: show_voided ? "" : "1" })}>
              {show_voided ? t("Hide") : t("Show")}
            </button>
          </p>
        ) : null}

        {isOpen ? (
          <table className="cl-table cl-open">
            <thead>
              <tr>
                <th>{t("Invoice")}</th>
                <th>{t("Due")}</th>
                <th>{t("Late")}</th>
                <th className="num">{t("Billed")}</th>
                <th className="num">{t("Paid")}</th>
                <th className="num">{t("Open")}</th>
              </tr>
            </thead>
            <tbody>
              {openRows.length ? openRows.map((r) => (
                <tr key={r.invoice_number} className="cl-row">
                  <td className="cl-c-main mono">{r.invoice_number}</td>
                  <td className="cl-c-date">{r.due_date ? fmtDate(r.due_date) : "—"}</td>
                  <td className={`cl-c-late${r.overdue ? " is-late" : ""}`}>
                    {r.overdue ? t("{n} days", { n: r.days_overdue }) : t("Not yet due")}
                  </td>
                  <td className="num mono" data-label={t("Billed")}>{fmt(r.billed)}</td>
                  <td className="num mono" data-label={t("Paid")}>{fmt(r.paid)}</td>
                  <td className="num mono cl-c-amt" data-label={t("Open")}>{fmt(r.remaining)}</td>
                </tr>
              )) : (
                <tr><td colSpan={6} className="cl-empty">{t("No open invoices — every charge on this client has been paid.")}</td></tr>
              )}
            </tbody>
            {openRows.length ? (
              <tfoot>
                <tr>
                  <td colSpan={5} className="cl-foot-lbl">{t("Total open")}</td>
                  <td className="num mono">{fmt(total_open)}</td>
                </tr>
              </tfoot>
            ) : null}
          </table>
        ) : (
          <table className="cl-table">
            <thead>
              <tr>
                <th className="cl-c-date">{t("Date")}</th>
                <th>{t("Description")}</th>
                <th className="num">{t("Charge")}</th>
                <th className="num">{t("Payment")}</th>
                <th className="num">{t("Balance")}</th>
              </tr>
            </thead>
            {firstPage && !q ? (
              <tbody>
                <tr className="cl-row cl-opening">
                  <td className="cl-c-date">{date_from ? fmtDateShort(date_from) : ""}</td>
                  <td className="cl-c-main">{t("Opening balance")}</td>
                  <td className="num" /><td className="num" />
                  <td className={`num mono cl-c-bal ${balanceTone(opening_balance)}`} data-label={t("Balance")}>{fmt(opening_balance)}</td>
                </tr>
              </tbody>
            ) : null}
            {groups.length ? groups.map((g) => {
              const m = months[g.key] || {};
              const partial = !q && m.n > g.rows.length;
              return (
                <tbody key={g.key}>
                  <tr className="cl-month">
                    <th colSpan={2} scope="rowgroup">
                      {monthName(g.key)}
                      {partial ? <span className="cl-dim cl-month-n">{t("{k} of {n} on this page", { k: g.rows.length, n: m.n })}</span> : null}
                    </th>
                    <td className="num mono" data-label={t("Charge")}>{Number(m.debit) ? fmt(m.debit) : ""}</td>
                    <td className="num mono" data-label={t("Payment")}>{Number(m.credit) ? fmt(m.credit) : ""}</td>
                    <td className={`num mono ${balanceTone(m.closing)}`} data-label={t("Balance")}>{fmt(m.closing)}</td>
                  </tr>
                  {g.rows.map((r, i) => <LedgerRow key={`${r.entry_number}-${i}`} r={r} t={t} />)}
                </tbody>
              );
            }) : (
              <tbody>
                <tr><td colSpan={5} className="cl-empty">{q ? t("No entries match “{q}”.", { q }) : t("No entries in this period.")}</td></tr>
              </tbody>
            )}
            <tfoot>
              <tr>
                <td colSpan={2} className="cl-foot-lbl">{t("Total for period")}</td>
                <td className="num mono" data-label={t("Charge")}>{fmt(total_debit)}</td>
                <td className="num mono" data-label={t("Payment")}>{fmt(total_credit)}</td>
                <td className="num" />
              </tr>
              <tr className="cl-closing">
                <td colSpan={4} className="cl-foot-lbl">{t("Closing balance")}</td>
                <td className={`num mono ${balanceTone(closing_balance)}`}>{fmt(closing_balance)}</td>
              </tr>
            </tfoot>
          </table>
        )}

        {!isOpen ? <Pagination pagination={pagination} unit="entries" onPage={(p) => go({ page: p })} /> : null}
      </section>
    </div>
  );
}

function LedgerRow({ r, t }) {
  const kind = t(LINE_KIND[r.entry_type] || r.entry_type_display || "");
  // The journal description usually restates the kind and number ("Charge
  // INV-009"); keep it only when it adds something (a payment reference).
  const restates = !r.description
    || r.description.startsWith(kind)
    || (r.invoice_number && r.description.trim().split(/\s+/).length <= 2 && r.description.includes(r.invoice_number));
  return (
    <tr className={`cl-row${r.is_voided ? " is-void" : ""}`}>
      <td className="cl-c-date">{r.date ? fmtDateShort(r.date) : "—"}</td>
      <td className="cl-c-main">
        {kind}
        {r.invoice_number ? <> · <span className="mono">{r.invoice_number}</span></> : null}
        {restates ? null : <span className="cl-note">{r.description}</span>}
      </td>
      <td className="num mono" data-label={t("Charge")}>{r.amount_sar > 0 ? fmt(r.amount_sar) : ""}</td>
      <td className="num mono" data-label={t("Payment")}>{r.amount_sar < 0 ? fmt(-r.amount_sar) : ""}</td>
      <td className={`num mono cl-c-bal ${balanceTone(r.balance)}`} data-label={t("Balance")}>{fmt(r.balance)}</td>
    </tr>
  );
}

function PeriodPicker({ isOpen, label, presets, active, dateFrom, dateTo, onApply, t }) {
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState(dateFrom || "");
  const [to, setTo] = useState(dateTo || "");
  const apply = (f, tt) => { setOpen(false); onApply(f, tt); };
  const onOpenChange = (v) => {
    setOpen(v);
    if (v) { setFrom(dateFrom || ""); setTo(dateTo || ""); }
  };
  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" size="lg" className="group cl-period-btn hover:border-input data-[state=open]:bg-muted focus-visible:border-input focus-visible:ring-foreground/15">
          <Icon name="calendar" size={15} />
          <span className="cl-period-label">{label}</span>
          <Icon name="chevron" size={14} className="cl-chev" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="cl-pop">
        {!isOpen ? (
          <div className="cl-presets" role="group" aria-label={t("Period")}>
            {presets.map((p) => (
              <button key={p.key} type="button" className={`cl-preset${active === p.key ? " is-on" : ""}`} aria-pressed={active === p.key} onClick={() => apply(p.from, p.to)}>
                {p.raw ? p.label : t(p.label)}
                {active === p.key ? <Icon name="check" size={14} /> : null}
              </button>
            ))}
          </div>
        ) : null}
        <form className="cl-custom" onSubmit={(e) => { e.preventDefault(); apply(isOpen ? "" : from, to); }}>
          <div className="cl-custom-lbl">{isOpen ? t("As of") : t("Custom range")}</div>
          <div className="cl-custom-row">
            {!isOpen ? (
              <>
                <Input type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} aria-label={t("From")} />
                <span className="cl-dim">–</span>
              </>
            ) : null}
            <Input type="date" value={to} min={(!isOpen && from) || undefined} onChange={(e) => setTo(e.target.value)} aria-label={t("To")} />
          </div>
          <div className="cl-custom-act">
            {isOpen && dateTo ? (
              <Button type="button" variant="ghost" size="lg" onClick={() => apply("", "")}>{t("Today")}</Button>
            ) : null}
            <Button type="submit" size="lg">{t("Apply")}</Button>
          </div>
        </form>
      </PopoverContent>
    </Popover>
  );
}

const CSS = `
/* Type follows the Homlu scale (spec §0d): detail title 24/600, table header
   11.5/500, table body 13, labels 12–12.5. Spacing uses 4·8·12·16·24 only. */
.cl-page { --cl-ease: cubic-bezier(0.2,0,0,1); }
.cl-dim { color:var(--muted-foreground); font-weight:500; }
.cl-sep { margin:0 8px; color:var(--muted-foreground); }

/* Header: name and the one-sentence answer, aligned to the card's edge */
.cl-head { margin-top:16px; display:flex; align-items:flex-end; justify-content:space-between; gap:16px; flex-wrap:wrap; }
.cl-head-main { min-width:0; }
.cl-h1 { margin:0; font-size:24px; font-weight:600; letter-spacing:-.02em; line-height:1.1; text-wrap:balance; }
.cl-h1-link { color:var(--foreground); text-decoration:none; }
.cl-h1-link:hover { text-decoration:underline; text-underline-offset:4px; text-decoration-thickness:1px; }
.cl-summary { margin:8px 0 0; font-size:13px; line-height:1.5; color:var(--muted-foreground); text-wrap:pretty; }
.cl-summary strong { font-weight:600; color:var(--foreground); font-variant-numeric:tabular-nums; }
.cl-summary .cl-credit { color:var(--green); }
.cl-late-text { color:var(--red); font-weight:500; }
.cl-head-act { display:flex; align-items:center; gap:12px; }
.cl-held { font-size:12.5px; color:var(--muted-foreground); font-variant-numeric:tabular-nums; white-space:nowrap; }

/* One card per job; radius 20, hairline, no shadow (spec §0e) */
.cl-card { margin-top:24px; background:var(--card); border:1px solid var(--border); border-radius:20px; }
.cl-card + .cl-card { margin-top:16px; }
.cl-pending { padding:16px 22px; }
.cl-h2 { margin:0 0 8px; font-size:14.5px; font-weight:600; letter-spacing:-.01em; }

/* Toolbar */
.cl-toolbar { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; padding:12px 16px 12px 22px; border-bottom:1px solid var(--border); }
.cl-tools { display:flex; align-items:center; gap:8px; }
.cl-modes { display:inline-flex; padding:3px; gap:3px; background:var(--muted); border-radius:9999px; }
.cl-modes button { position:relative; height:34px; padding:0 14px; border:none; background:transparent; border-radius:9999px; font:inherit; font-size:13px; font-weight:600; color:var(--muted-foreground); cursor:pointer; display:inline-flex; align-items:center; gap:8px; white-space:nowrap; transition-property:color, background-color, box-shadow, scale; transition-duration:120ms; transition-timing-function:var(--cl-ease); }
.cl-modes button:hover { color:var(--foreground); }
.cl-modes button.is-active { background:var(--card); color:var(--foreground); box-shadow:0 1px 2px rgb(0 0 0 / .06), 0 0 0 1px rgb(0 0 0 / .04); }
.cl-modes-n { font-size:11px; font-weight:600; padding:1px 6px; border-radius:9999px; background:var(--border); color:var(--foreground); font-variant-numeric:tabular-nums; }
.cl-search { width:240px; }
.cl-search .search-wrap { height:40px; }
.cl-period-btn { max-width:260px; }
.cl-period-label { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-variant-numeric:tabular-nums; }
.cl-chev { color:var(--muted-foreground); transition-property:rotate; transition-duration:200ms; transition-timing-function:var(--cl-ease); }
.group[data-state="open"] .cl-chev { rotate:180deg; }
.cl-icon-btn { width:40px; padding:0 !important; }

/* Period popover */
.cl-pop { width:340px; padding:8px !important; }
.cl-presets { display:flex; flex-direction:column; gap:2px; padding-bottom:8px; border-bottom:1px solid var(--border); }
.cl-preset { position:relative; display:flex; align-items:center; justify-content:space-between; height:36px; padding:0 10px; border:none; border-radius:6px; background:transparent; font:inherit; font-size:13px; color:var(--foreground); cursor:pointer; text-align:start; transition-property:background-color, scale; transition-duration:120ms; }
.cl-preset:hover, .cl-preset.is-on { background:var(--muted); }
.cl-preset.is-on { font-weight:600; }
.cl-custom { padding:12px 4px 4px; }
.cl-custom-lbl { font-size:12px; font-weight:500; color:var(--muted-foreground); margin-bottom:8px; }
.cl-custom-row { display:flex; align-items:center; gap:8px; }
.cl-custom-row input { min-width:0; }
.cl-custom-act { margin-top:12px; display:flex; justify-content:flex-end; gap:8px; }

.cl-notice { margin:0; padding:12px 22px; border-bottom:1px solid var(--border); font-size:12.5px; line-height:1.5; color:var(--muted-foreground); text-wrap:pretty; }
.cl-inline-link { position:relative; margin-left:8px; padding:0; border:none; background:none; font:inherit; font-weight:600; color:var(--foreground); cursor:pointer; text-decoration:underline; text-underline-offset:3px; text-decoration-thickness:1px; text-decoration-color:var(--input); transition-property:text-decoration-color, scale; transition-duration:120ms; }
.cl-inline-link:hover { text-decoration-color:currentColor; }
.cl-late-text .cl-inline-link { color:inherit; }

/* Table: hairlines only, no fills, numbers right and tabular (spec §0e) */
.cl-table { width:100%; border-collapse:separate; border-spacing:0; font-size:13px; }
.cl-table th, .cl-table td { padding:12px; text-align:start; vertical-align:top; }
.cl-table th:first-child, .cl-table td:first-child { padding-inline-start:22px; }
.cl-table th:last-child, .cl-table td:last-child { padding-inline-end:22px; }
.cl-table thead th { position:sticky; top:var(--topbar-h, 0px); z-index:2; background:var(--card); padding-block:10px; font-size:11.5px; font-weight:500; color:var(--muted-foreground); white-space:nowrap; box-shadow:inset 0 -1px 0 var(--border); }
.cl-table .num { text-align:end; white-space:nowrap; font-variant-numeric:tabular-nums; }
.cl-table thead th.num { width:120px; }
.cl-c-date { width:88px; white-space:nowrap; color:var(--muted-foreground); font-variant-numeric:tabular-nums; }
.cl-c-main { color:var(--foreground); overflow-wrap:anywhere; }
.cl-note { display:block; margin-top:2px; font-size:12px; color:var(--muted-foreground); }
.cl-row td { border-bottom:1px solid var(--border); }
.cl-row:hover td { background:var(--surface-2, var(--muted)); }
.cl-opening td { color:var(--muted-foreground); }
.cl-opening .num { color:var(--foreground); }
.cl-month th, .cl-month td { padding-top:24px; padding-bottom:8px; font-size:13px; font-weight:600; color:var(--foreground); border-bottom:1px solid var(--border); }
.cl-month th { text-transform:capitalize; }
.cl-month td { color:var(--muted-foreground); font-weight:500; }
.cl-month-n { margin-inline-start:8px; font-size:12px; text-transform:none; }
.cl-row.is-void td { color:var(--muted-foreground); }
.cl-row.is-void .cl-c-main, .cl-row.is-void .num { text-decoration:line-through; text-decoration-thickness:1px; }
.cl-table .is-credit { color:var(--green); }
.cl-empty { text-align:center !important; color:var(--muted-foreground); padding:32px 22px !important; }
/* design.css gives every tfoot cell a card fill and its own top rule; here
   only the first footer row opens with a rule, and the fill would square off
   the card's rounded bottom corners. */
.cl-table tfoot td { padding-block:12px; font-weight:600; color:var(--foreground); background:none; border-top:none; font-size:13px; }
.cl-table tfoot tr:first-child td { border-top:1px solid var(--input); }
.cl-foot-lbl { text-align:end !important; color:var(--muted-foreground) !important; font-weight:500 !important; }
.cl-closing td { padding-top:0 !important; }
.cl-closing .num { font-size:14.5px; }

/* Open invoices */
.cl-c-late { white-space:nowrap; color:var(--muted-foreground); font-variant-numeric:tabular-nums; }
.cl-c-late.is-late { color:var(--red); font-weight:600; }
.cl-open .cl-c-main { font-weight:600; }
.cl-c-amt { font-weight:600; }

.cl-page .hms-pag { border-top:1px solid var(--border); border-radius:0 0 20px 20px; }

/* Press feedback + 40px hit areas (44px on touch) for hand-rolled controls */
.cl-modes button:active, .cl-preset:active, .cl-inline-link:active { scale:.96; }
.cl-inline-link::before { content:""; position:absolute; inset-inline:-4px; top:50%; height:40px; translate:0 -50%; }
.cl-modes button::before { content:""; position:absolute; inset-inline:-1px; top:50%; height:40px; translate:0 -50%; }
@media (pointer:coarse) {
  .cl-inline-link::before, .cl-modes button::before { height:44px; }
}
@media (prefers-reduced-motion: reduce) {
  .cl-page *, .cl-pop * { transition-duration:0ms !important; }
  .cl-modes button:active, .cl-preset:active, .cl-inline-link:active { scale:none; }
}

@media (max-width:860px) {
  .cl-toolbar { padding-inline:16px; }
  .cl-search { width:auto; flex:1 1 auto; }
  .cl-tools { width:100%; }
}

/* Phone: the table becomes a two-line list; month rows take over as the
   sticky context because column headers are gone. */
@media (max-width:600px) {
  .cl-head { align-items:stretch; }
  .cl-head-act { width:100%; justify-content:space-between; }
  .cl-card { border-radius:14px; margin-top:16px; }
  .cl-toolbar { padding:12px; }
  .cl-modes { width:100%; }
  .cl-modes button { flex:1 1 0; justify-content:center; }
  .cl-period-btn { min-width:0; flex:0 1 auto; }
  .cl-period-label { display:none; }
  .cl-notice { padding:12px 16px; }
  .cl-pop input { font-size:16px !important; }

  .cl-table thead { display:none; }
  .cl-table, .cl-table tbody, .cl-table tfoot, .cl-table tr { display:block; }
  .cl-table td, .cl-table th { padding:0 !important; border:none !important; }
  .cl-table .cl-row { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:4px 12px; padding:12px 16px; border-bottom:1px solid var(--border); }
  .cl-row .cl-c-main { grid-column:1; grid-row:1; }
  .cl-row .cl-c-date { grid-column:1; grid-row:2; width:auto; font-size:12px; }
  .cl-row td.num:empty { display:none; }
  .cl-row td.num:not(.cl-c-bal) { grid-column:2; grid-row:1; font-weight:600; }
  .cl-row td.cl-c-bal { grid-column:2; grid-row:2; font-size:12px; color:var(--muted-foreground); }
  .cl-row td.cl-c-bal::before { content:attr(data-label) " "; }
  .cl-opening td.cl-c-date { display:none; }
  .cl-opening td.cl-c-bal { grid-row:1; font-size:13px; color:var(--foreground); }
  .cl-opening td.cl-c-bal::before { content:none; }

  .cl-table .cl-month { display:flex; flex-wrap:wrap; align-items:baseline; justify-content:space-between; gap:4px 12px; padding:16px 16px 8px; position:sticky; top:calc(48px + env(safe-area-inset-top, 0px)); z-index:2; background:var(--card); border-bottom:1px solid var(--border); }
  .cl-month td:not(:last-child) { display:none; }
  .cl-month td:last-child::before { content:attr(data-label) " "; font-weight:400; }

  .cl-open .cl-row .cl-c-main { grid-row:1; }
  .cl-open .cl-row .cl-c-date { grid-row:2; }
  .cl-open .cl-row .cl-c-late { grid-column:1; grid-row:3; font-size:12px; }
  .cl-open .cl-row td.num:not(.cl-c-amt) { display:none; }
  .cl-open .cl-row td.cl-c-amt { grid-column:2; grid-row:1; }

  .cl-table tfoot tr { display:flex; justify-content:space-between; gap:12px; padding:8px 16px; }
  .cl-table tfoot tr:first-child { border-top:1px solid var(--input); padding-top:12px; }
  .cl-table tfoot td.num:empty { display:none; }
  .cl-table tfoot tr:first-child td.num::before { content:attr(data-label) " "; color:var(--muted-foreground); font-weight:400; }
  .cl-foot-lbl { text-align:start !important; }
  .cl-closing { padding-bottom:16px !important; }
}
`;
