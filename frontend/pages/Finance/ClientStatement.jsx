import { useEffect, useMemo, useState } from "react";
import { router } from "@inertiajs/react";
import Pagination from "../../components/shadcn/pagination.jsx";
import PendingOutTable from "../../components/shadcn/pending-out-table.jsx";
import { DPage, DTop, DHead, DBanner, DBtn, DCard, DTabs, DIcon } from "../../components/shadcn/detail-a.jsx";
import { SearchTool, ExportMenu } from "../../components/shadcn/list-a.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Popover, PopoverContent, PopoverTrigger } from "../../components/shadcn/ui/popover.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { fmt, fmtDate, fmtDateShort } from "../../utils/format.js";

// The Client Ledger, from the "Client Ledger" artboards on the Record View HMS
// canvas (Past due, All time, custom range): the head card says where the
// client stands, money awaiting a second person sits in its own card, and the
// statement groups entries by month, each month foldable with its own totals.
// All time opens on the latest three months; a custom range labels the months
// it cuts.

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

const credit = (n) => (n < 0 ? { color: "var(--success-text)" } : undefined);
const invHref = (r) => (r.id ? `/invoice/${r.id}/` : null);
const lastDay = (key) => { const [y, m] = key.split("-").map(Number); return new Date(y, m, 0).getDate(); };

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

  const balance = isOpen ? total_open : closing_balance;
  const openInv = aging.invoices || [];
  const late = openInv.filter((i) => i.days_overdue > 0);
  const pastDue = late.reduce((s, i) => s + Number(i.amount || 0), 0);
  const fundHeld = Number(client.saldo_dana || 0);

  const badge = late.length ? { label: t("Past due"), tone: "red" }
    : balance > 0 ? { label: t("Owing"), tone: "amber" }
      : balance < 0 ? { label: t("In credit"), tone: "green" }
        : { label: t("Settled"), tone: "green" };

  const refunds = pending_out.filter((r) => r.kind === "refund").length;
  const transfers = pending_out.length - refunds;
  const waiting = [
    refunds ? t(refunds === 1 ? "1 refund" : "{n} refunds", { n: refunds }) : null,
    transfers ? t(transfers === 1 ? "1 transfer" : "{n} transfers", { n: transfers }) : null,
  ].filter(Boolean).join(", ") || t("None");

  const oldest = late[0];
  const facts = [
    { k: t("Balance"), v: `${fmt(balance)} SAR`, strong: true, tone: balance < 0 ? "success" : undefined },
    { k: t("Past due"), v: `${fmt(pastDue)} SAR`, tone: pastDue > 0 ? "danger" : undefined },
    { k: t("Open invoices"), v: openInv.length },
    { k: t("Deposit held"), v: `${fmt(fundHeld)} SAR` },
    {
      k: t("Oldest past due"),
      v: oldest ? (
        <>
          {invHref(oldest) ? <a className="da-mono" href={invHref(oldest)}>{oldest.invoice_number}</a> : <span className="da-mono">{oldest.invoice_number}</span>}{" "}
          <span style={{ color: "var(--danger-text)", fontWeight: 600 }}>{t("{n} days late", { n: oldest.days_overdue })}</span>
        </>
      ) : <span className="dim">{t("None")}</span>,
    },
    client.total_billed != null && { k: t("Total billed"), v: `${fmt(client.total_billed)} SAR` },
    client.avg_days_to_pay != null && { k: t("Avg days to pay"), v: t(Math.round(client.avg_days_to_pay) === 1 ? "1 day" : "{n} days", { n: Math.round(client.avg_days_to_pay) }) },
    { k: t("Awaiting approval"), v: waiting },
  ];

  // ── Period control ──
  const presetList = presets(seasons);
  const activePreset = presetList.find((p) => p.from === (date_from || "") && p.to === (date_to || ""));
  const periodLabel = isOpen
    ? (date_to ? t("As of {d}", { d: fmtDate(date_to) }) : t("Today"))
    : activePreset
      ? (activePreset.raw ? activePreset.label : t(activePreset.label))
      : t("{a} to {b}", { a: date_from ? fmtDate(date_from) : "…", b: date_to ? fmtDate(date_to) : t("today") });
  const qs = (pdfMode = isOpen ? "open" : "") => {
    const p = new URLSearchParams();
    if (date_from) p.set("from", date_from);
    if (date_to) p.set("to", date_to);
    if (pdfMode) p.set("mode", pdfMode);
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

  // Folded months. All time opens on the latest three; any narrower period
  // opens every month. A search shows every match.
  const allTime = !date_from && !date_to;
  const initialFolded = () => new Set(allTime && !q ? groups.slice(0, -3).map((g) => g.key) : []);
  const [folded, setFolded] = useState(initialFolded);
  useEffect(() => { setFolded(initialFolded()); }, [date_from, date_to, q, pagination?.number]); // eslint-disable-line react-hooks/exhaustive-deps
  const toggle = (key) => setFolded((s) => { const n = new Set(s); if (n.has(key)) n.delete(key); else n.add(key); return n; });
  const anyFolded = groups.some((g) => folded.has(g.key));

  const openRows = useMemo(
    () => [...open_items].sort((a, b) => (b.days_overdue || 0) - (a.days_overdue || 0)
      || (a.due_date || "").localeCompare(b.due_date || "")),
    [open_items],
  );

  const firstPage = !pagination || pagination.number === 1;
  const fromDay = date_from ? Number(date_from.slice(8, 10)) : 1;
  const openingLabel = date_from && fromDay !== 1
    ? t("Balance before {date}", { date: fmtDate(date_from) })
    : t("Opening balance");

  const monthNote = (g, i) => {
    const m = months[g.key] || {};
    const n = m.n ?? g.rows.length;
    const count = t(n === 1 ? "1 entry" : "{n} entries", { n });
    if (!q && m.n > g.rows.length) return t("{k} of {n} on this page", { k: g.rows.length, n: m.n });
    if (i === 0 && date_from && date_from.slice(0, 7) === g.key && fromDay !== 1) {
      return t("From {date}, {count}", { date: fmtDateShort(date_from), count });
    }
    if (i === groups.length - 1 && date_to && date_to.slice(0, 7) === g.key && Number(date_to.slice(8, 10)) !== lastDay(g.key)) {
      return t("Until {date}, {count}", { date: fmtDateShort(date_to), count });
    }
    return count;
  };

  const pdfBase = `/finance/clients/${client.id}/statement/pdf/`;
  const tools = (
    <>
      {!isOpen && groups.length > 1 ? (
        <button type="button" className="ghost" onClick={() => setFolded(anyFolded ? new Set() : new Set(groups.map((g) => g.key)))}>
          {anyFolded ? t("Expand all") : t("Fold all")}
        </button>
      ) : null}
      {!isOpen ? <SearchTool value={q} onSearch={(v) => go({ q: v })} placeholder={t("Search number")} /> : null}
      <PeriodPicker
        isOpen={isOpen} label={periodLabel} presets={presetList} active={activePreset?.key}
        dateFrom={date_from} dateTo={date_to} onApply={(from, to) => go({ from, to })} t={t}
      />
      {canExportPdf ? (
        <ExportMenu items={isOpen ? [
          { label: t("Open invoices"), hint: t("Unpaid invoices as of the date shown"), href: `${pdfBase}${qs()}`, external: true },
        ] : [
          { label: t("Client statement"), hint: t("Every entry with a running balance"), href: `${pdfBase}${qs()}`, external: true },
          { label: t("Client reservation statement"), hint: t("One line per reservation: billed, paid, balance"), href: `${pdfBase}${qs("byres")}`, external: true },
        ]} />
      ) : null}
    </>
  );

  return (
    <DPage>
      <style>{CSS}</style>
      <DTop href="/finance/statements/" />

      {canMoveMoney && (fundHeld > 0 || balance < 0) ? (
        <DBanner
          tone={fundHeld > 0 ? "warning" : "success"}
          actions={<DBtn primary onClick={() => openForm(`/finance/clients/${client.id}/deposit-transfer/`)}>{t("Deposit or refund")}</DBtn>}
        >
          {fundHeld > 0
            ? <><b>{fmt(fundHeld)} SAR</b> {t("deposit is held for this client.")}</>
            : <><b>{fmt(-balance)} SAR</b> {t("in credit, ours to refund or offset.")}</>}
        </DBanner>
      ) : null}

      <DHead
        title={client.name}
        badge={badge}
        menu={[perms.can("clients", "view") && { label: t("View client"), icon: "user", href: `/clients/${client.id}/` }]}
        facts={facts}
      />

      {pending_out.length > 0 ? (
        <DCard title={t("Awaiting approval")} count={pending_out.length}>
          <PendingOutTable rows={pending_out} plain />
        </DCard>
      ) : null}

      <section className="da-card">
        <DTabs
          tall
          label={t("Ledger view")}
          value={isOpen ? "open" : "st"}
          onChange={(k) => (k === "open" ? go({ mode: "open", q: "", from: "" }) : go({ mode: "", q: "" }))}
          tabs={[
            { key: "st", label: t("Statement") },
            { key: "open", label: t("Open invoices"), count: isOpen ? open_items.length : openInv.length },
          ]}
          tools={tools}
        />

        {!isOpen && (hidden_voided > 0 || show_voided) ? (
          <p className="da-notice">
            {show_voided
              ? t("Reversed entries are shown, struck through.")
              : t(hidden_voided === 1
                ? "1 reversed entry is hidden. It cancels its pair, so the balances stay the same."
                : "{n} reversed entries are hidden. Each cancels its pair, so the balances stay the same.", { n: hidden_voided })}
            <button type="button" className="da-lnk" onClick={() => go({ voided: show_voided ? "" : "1" })}>
              {show_voided ? t("Hide") : t("Show")}
            </button>
          </p>
        ) : null}

        <div className="da-scroll">
          {isOpen ? (
            <table className="da-t">
              <thead>
                <tr><th>{t("Invoice")}</th><th>{t("Due")}</th><th>{t("Late")}</th><th className="n w">{t("Billed")}</th><th className="n w">{t("Paid")}</th><th className="n w">{t("Open")}</th></tr>
              </thead>
              <tbody>
                {openRows.length ? openRows.map((r) => (
                  <tr key={r.invoice_number}>
                    <td>{invHref(r) ? <a className="mono" href={invHref(r)}>{r.invoice_number}</a> : <span className="mono">{r.invoice_number}</span>}</td>
                    <td className="nw" style={{ color: "var(--foreground)" }}>{r.due_date ? fmtDate(r.due_date) : t("Not set")}</td>
                    <td className={r.overdue ? "late" : "mut"}>{r.overdue ? t("{n} days", { n: r.days_overdue }) : t("Not yet due")}</td>
                    <td className="n">{fmt(r.billed)}</td>
                    <td className="n">{fmt(r.paid)}</td>
                    <td className="n bold">{fmt(r.remaining)}</td>
                  </tr>
                )) : <tr><td colSpan={6} className="empty">{t("No open invoices. Every charge on this client has been paid.")}</td></tr>}
              </tbody>
              {openRows.length ? (
                <tfoot><tr><td colSpan={5} className="fl" style={{ color: "var(--foreground)", fontWeight: 600 }}>{t("Total open")}</td><td className="n">{fmt(total_open)}</td></tr></tfoot>
              ) : null}
            </table>
          ) : (
            <table className="da-t">
              <thead>
                <tr><th className="d">{t("Date")}</th><th>{t("Description")}</th><th className="n w">{t("Charge")}</th><th className="n w">{t("Payment")}</th><th className="n w">{t("Balance")}</th></tr>
              </thead>
              {firstPage && !q ? (
                <tbody>
                  <tr className="last">
                    <td className="d">{date_from ? fmtDateShort(date_from) : ""}</td>
                    <td className="mut">{openingLabel}</td>
                    <td /><td />
                    <td className="n" style={credit(opening_balance)}>{fmt(opening_balance)}</td>
                  </tr>
                </tbody>
              ) : null}
              {groups.length ? groups.map((g, i) => {
                const m = months[g.key] || {};
                const isFolded = folded.has(g.key);
                return (
                  <tbody key={g.key}>
                    <tr className="grp ruled">
                      <th colSpan={2} scope="rowgroup">
                        <button type="button" className="da-mt" aria-expanded={!isFolded} onClick={() => toggle(g.key)}>
                          {DIcon.chev}<span style={{ textTransform: "capitalize" }}>{monthName(g.key)}</span><span className="cnt">{monthNote(g, i)}</span>
                        </button>
                      </th>
                      <td className="n">{Number(m.debit) ? fmt(m.debit) : ""}</td>
                      <td className="n">{Number(m.credit) ? fmt(m.credit) : ""}</td>
                      <td className="n" style={credit(m.closing)}>{m.closing != null ? fmt(m.closing) : ""}</td>
                    </tr>
                    {isFolded ? null : g.rows.map((r, j) => <LedgerRow key={`${r.entry_number}-${j}`} r={r} t={t} last={j === g.rows.length - 1} />)}
                  </tbody>
                );
              }) : (
                <tbody><tr><td colSpan={5} className="empty">{q ? t("No entries match “{q}”.", { q }) : t("No entries in this period.")}</td></tr></tbody>
              )}
              <tfoot>
                <tr>
                  <td colSpan={2} className="fl">{t("Total for period")}</td>
                  <td className="n">{fmt(total_debit)}</td>
                  <td className="n">{fmt(total_credit)}</td>
                  <td />
                </tr>
                <tr className="after">
                  <td colSpan={4} className="fl" style={{ paddingBottom: 18 }}>{date_to ? t("Closing balance on {date}", { date: fmtDate(date_to) }) : t("Closing balance")}</td>
                  <td className="n" style={{ paddingBottom: 18, fontSize: 14.5, ...credit(closing_balance) }}>{fmt(closing_balance)}</td>
                </tr>
              </tfoot>
            </table>
          )}
        </div>

        {!isOpen ? <Pagination pagination={pagination} unit="entries" onPage={(p) => go({ page: p })} /> : null}
      </section>
    </DPage>
  );
}

function LedgerRow({ r, t, last }) {
  const kind = t(LINE_KIND[r.entry_type] || r.entry_type_display || "");
  // The journal description usually restates the kind and number ("Charge
  // INV-009"); keep it only when it adds something (a payment reference).
  const restates = !r.description
    || r.description.startsWith(kind)
    || (r.invoice_number && r.description.trim().split(/\s+/).length <= 2 && r.description.includes(r.invoice_number));
  const cls = [r.is_voided ? "void" : "", last ? "last" : ""].filter(Boolean).join(" ") || undefined;
  return (
    <tr className={cls}>
      <td className="d">{r.date ? fmtDateShort(r.date) : ""}</td>
      <td className="desc">
        <span className="kind">{kind}</span>
        {r.invoice_number ? <span className="mono">{r.invoice_number}</span> : null}
        {restates ? null : <span className="sub">{r.description}</span>}
      </td>
      <td className="n">{r.amount_sar > 0 ? fmt(r.amount_sar) : ""}</td>
      <td className="n">{r.amount_sar < 0 ? fmt(-r.amount_sar) : ""}</td>
      <td className="n" style={credit(r.balance)}>{fmt(r.balance)}</td>
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
        <button type="button" className="la-tool cl-period" aria-haspopup="dialog">
          {DIcon.calendar}
          <span className="cl-period-label">{label}</span>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="cl-pop">
        {!isOpen ? (
          <div className="cl-presets" role="group" aria-label={t("Period")}>
            {presets.map((p) => (
              <button key={p.key} type="button" className={`cl-preset${active === p.key ? " is-on" : ""}`} aria-pressed={active === p.key} onClick={() => apply(p.from, p.to)}>
                {p.raw ? p.label : t(p.label)}
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
                <span style={{ color: "var(--muted-foreground)" }}>–</span>
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
.cl-period { max-width: 260px; }
.cl-period-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-variant-numeric: tabular-nums; }
.cl-pop { width: 340px; padding: 8px !important; }
.cl-presets { display: flex; flex-direction: column; gap: 2px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.cl-preset { display: flex; align-items: center; height: 36px; padding: 0 10px; border: none; border-radius: 6px; background: transparent; font: inherit; font-size: 13px; color: var(--foreground); cursor: pointer; text-align: start; }
.cl-preset:hover, .cl-preset.is-on { background: var(--secondary); }
.cl-preset.is-on { font-weight: 600; }
.cl-custom { padding: 12px 4px 4px; }
.cl-custom-lbl { font-size: 12px; font-weight: 500; color: var(--muted-foreground); margin-bottom: 8px; }
.cl-custom-row { display: flex; align-items: center; gap: 8px; }
.cl-custom-row input { min-width: 0; }
.cl-custom-act { margin-top: 12px; display: flex; justify-content: flex-end; gap: 8px; }
.da-main .hms-pag { border-top: 1px solid var(--border); }
@media (max-width: 600px) {
  .cl-period-label { display: none; }
  .cl-pop input { font-size: 16px !important; }
}
`;
