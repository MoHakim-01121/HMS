import { useState } from "react";
import { cn } from "@/lib/utils";
import { DA, DC } from "../../components/shadcn/detail-a.jsx";
import { Link, router, usePage } from "@inertiajs/react";
import { Spark, LIcon, MONTHS, Pill, fmtN, Note, PageFrame, PageMain, Toolbar, MonthLabel, NavButton, MenuButton, Menu, MenuItem, MenuSep, MenuHint, Kpi, Empty } from "../../components/shadcn/list-a.jsx";
import { Popover, PopoverTrigger } from "../../components/shadcn/ui/popover.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import "../../styles/dashboard.css";

// Dashboards of the HMS Dashboard canvas, one per role (`variant`):
// - Manager (ManagerHomlu): the period's sales (booked value as the one accent
//   card, CL sold, room nights, cancellations, branch profit), CL sold per month
//   against last season, how much of what was billed is paid, today's to do,
//   this week's check-ins, the season's top clients and hotels, money now.
// - Administrator (Admin): the Manager's, with past due in the KPIs, the branch
//   table, and users and access in place of top hotels.
// - Finance (Finance): cash and bank as the accent card, received, paid out,
//   receivables and FX profit, money in and out per month, collected, the money
//   queue, payments to confirm, invoices to chase, accounts and what is owed to HQ.
// - Staff and Viewer (Staff): Staff sees the CLs they sold, their to do, the
//   payments they uploaded and their cash advance; Viewer the branch, read only.
// A block the user may not view arrives missing from the props and is not drawn.

const MON = MONTHS.map((m) => m.slice(0, 3));
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const GREEN = "var(--data)";
const ARC = 289; // length of the gauge's half circle (r = 92)

const iso = (s) => new Date(s + "T00:00:00");
const dDay = (s) => { const d = iso(s); return `${d.getDate()} ${MON[d.getMonth()]}`; };
const dWeek = (s) => { const d = iso(s); return `${DAYS[d.getDay()]} ${d.getDate()} ${MON[d.getMonth()]}`; };
const millions = (v) => `${(Math.round((v || 0) / 100000) / 10).toLocaleString("en-US")} M`;
const money = (v, ccy) => (ccy === "IDR" && Math.abs(v) >= 1e6 ? millions(v) : fmtN(v));
const pctOf = (cur, prev) => (prev ? Math.round(((cur - prev) * 100) / prev) : null);
const pastDueSub = (t, c, d) => (c === 1 ? t("1 client, {d} days late", { d }) : t("{c} clients, oldest {d} days", { c, d }));
const greeting = (t) => { const h = new Date().getHours(); return h < 11 ? t("Good morning") : h < 15 ? t("Good afternoon") : t("Good evening"); };

export default function Home(props) {
  const [loading, setLoading] = useState(false);
  const go = (params) => router.get("/dashboard/", params, {
    preserveScroll: true, replace: true, onStart: () => setLoading(true), onFinish: () => setLoading(false),
  });
  const Body = props.variant === "finance" ? FinanceHome : props.variant === "staff" || props.variant === "viewer" ? StaffHome : ManagerHome;
  return (
    <PageFrame className="db">
      <PageMain loading={loading} className={"db-v-" + props.variant}>
        <Body {...props} onGo={go} />
      </PageMain>
    </PageFrame>
  );
}

// Greeting, branch and what waits today; then the period bar.
function Head({ todo, readOnly, scopeNote, period, seasons, today, onGo }) {
  const { t } = useI18n();
  const { auth, branch } = usePage().props;
  const firstName = (auth?.user?.name || auth?.user?.username || "").split(" ")[0];
  const n = (todo || []).reduce((a, x) => a + x.count, 0);
  return (
    <>
      <div>
        <h1 className="db-hi">{greeting(t)}, {firstName}</h1>
        <div className="db-sub">
          {branch?.current ? `${branch.current.name} · ` : ""}
          {readOnly ? t("Read only.") : n ? t("{n} things wait for you today.", { n }) : t("Nothing waits for you today.")}
        </div>
      </div>
      <PeriodBar period={period} seasons={seasons} today={today} onGo={onGo} note={scopeNote} />
    </>
  );
}

function ManagerHome(props) {
  const { t } = useI18n();
  const { variant, period, sales, profit, sold_months: sm, collected: col, todo = [], checkins, top, money: mon, branches, receivable, people, seasons = [] } = props;
  const isSeason = period.kind === "season";
  const todoCount = todo.reduce((a, x) => a + x.count, 0);
  const admin = variant === "admin";
  // Nobody locked or idle: no card, rather than a card-sized empty state.
  const access = admin && people && (people.locked.length || people.idle.length) ? people : null;

  return (
    <>
        <Head todo={todo} period={period} seasons={seasons} today={props.today} onGo={props.onGo} />

        {sales && <KpiRow period={period} sales={sales} profit={profit} sm={sm} isSeason={isSeason} kind={admin ? "admin" : "manager"} receivable={receivable} />}

        {(sm || col) && (
          <div className={"db-g2" + (sm && col ? "" : " one")}>
            {sm && <SoldPerMonth sm={sm} sales={sales} period={period} isSeason={isSeason} />}
            {col && <Collected col={col} />}
          </div>
        )}

        {(todo.length > 0 || checkins) && (
          <div className={"db-g2b" + (todo.length && checkins ? "" : " one")}>
            {todo.length > 0 && <Todo items={todo} count={todoCount} />}
            {checkins && <Checkins data={checkins} />}
          </div>
        )}

        {branches?.length > 0 && <ByBranch rows={branches} period={period} />}

        {(top || mon || access) && (
          <div className={"db-g3" + ([top, admin ? access : top, mon].filter(Boolean).length === 3 ? "" : " two")}>
            {top && <TopClients top={top} />}
            {top && !admin && <Ranking title={t("Top hotels")} meta={`${top.season ? t("Season {s}", { s: top.season }) : t("12 months")}, ${t("room nights")}`}
              rows={top.hotels.map((r) => ({ ...r, href: `/hotels/${r.id}/`, sub: r.city, v: r.rn }))}
              empty={[t("No stays yet"), t("Hotels appear here after the first check-in.")]} hasPrev={top.has_prev} />}
            {mon && <MoneyNow m={mon} />}
            {access && <People p={access} />}
          </div>
        )}
    </>
  );
}

function TopClients({ top, title }) {
  const { t } = useI18n();
  return (
    <Ranking title={title || t("Top clients")} meta={`${top.season ? t("Season {s}", { s: top.season }) : t("12 months")}, SAR`}
      rows={top.clients.map((r) => ({ ...r, href: `/clients/${r.id}/`, sub: t("{n} CL", { n: r.cl }), v: r.val }))}
      empty={[t("No sales this season yet"), t("Clients appear here after their first CL.")]} hasPrev={top.has_prev} />
  );
}

// "October ‹ ›  2026 ▾": months step back to any month and up to this one;
// the menu switches to the running season when there is one.
function PeriodBar({ period, seasons, today, onGo, note }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const isSeason = period.kind === "season";
  const start = iso(period.start);
  const thisMonth = today.slice(0, 7);
  const shift = (d) => {
    const dt = new Date(start.getFullYear(), start.getMonth() + d, 1);
    onGo({ month: `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}` });
  };
  const atNow = period.start.slice(0, 7) === thisMonth;
  return (
    <Toolbar left={<>
      <MonthLabel>{isSeason ? t("Whole season") : `${t(MONTHS[start.getMonth()])} ${start.getFullYear()}`}</MonthLabel>
      <NavButton aria-label={t("Previous month")} disabled={isSeason} onClick={() => shift(-1)}>{LIcon.prev}</NavButton>
      <NavButton aria-label={t("Next month")} disabled={isSeason || atNow} onClick={() => shift(1)}>{LIcon.next}</NavButton>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <MenuButton aria-haspopup="menu">{isSeason ? t("Season {s}", { s: period.label }) : t("Monthly")}{LIcon.chev}</MenuButton>
        </PopoverTrigger>
        <Menu align="start" sideOffset={6} className="w-[220px]">
          <MenuItem on={!isSeason} onClick={() => { setOpen(false); onGo({ month: thisMonth }); }}>{t("Month by month")}</MenuItem>
          {seasons.length > 0 && <MenuSep />}
          {seasons.slice(0, 1).map((s) => (
            <MenuItem key={s.name} on={isSeason} onClick={() => { setOpen(false); onGo({ season: 1 }); }}>
              <span>{t("Season {s}", { s: s.name })}<MenuHint>{dDay(s.start)} {s.start.slice(0, 4)} {t("to")} {dDay(s.end)} {s.end.slice(0, 4)}</MenuHint></span>
            </MenuItem>
          ))}
        </Menu>
      </Popover>
    </>}>
      {note && <Note>{note}</Note>}
    </Toolbar>
  );
}

// kind: "manager" (CL sold, room nights, cancelled, profit), "admin" (past due
// in place of cancelled), "staff" (the branch's CLs: sold, room nights,
// check-ins this week, not invoiced) or "viewer" (sold, room nights, check-ins, cancelled).
function KpiRow({ period, sales, profit, sm, isSeason, kind = "manager", receivable, checkins, uninvoiced }) {
  const { t } = useI18n();
  const mine = kind === "staff";
  const { cur, prev } = sales;
  const prevLabel = period.prev_label;
  const cmp = (v) => (prev ? `${prevLabel}: ${v}` : t("First season in HMS, nothing to compare"));
  const pct = (a, b) => { const p = prev ? pctOf(a, b) : null; return !p ? null : `${p > 0 ? "+" : "-"}${Math.abs(p)}%`; };

  // The accent card: the period's booked value, with its build-up as bars.
  let bars, axis;
  if (isSeason && sm) {
    const vals = sm.months.slice(0, sm.now + 1).map((m) => m.cur || 0);
    const mx = Math.max(1, ...vals);
    bars = vals.map((v) => ({ h: (v / mx) * 100, on: true }));
    axis = [MON[iso(sm.months[0].key).getMonth()], MON[iso(sm.months[sm.now].key).getMonth()]];
  } else {
    const mx = Math.max(1, ...cur.bars);
    bars = cur.bars.map((v, i) => ({ h: (v / mx) * 100, on: i === cur.bars.length - 1 }));
    axis = [dDay(period.start), period.running ? t("Today, {d}", { d: dDay(period.end) }) : dDay(period.end)];
  }
  const heroPct = pct(cur.value, prev?.value);
  const heroBad = heroPct && heroPct.startsWith("-");

  const kpis = [
    { label: t("CL sold"), v: fmtN(cur.cl), d: pct(cur.cl, prev?.cl), good: !prev || cur.cl >= prev.cl,
      foot: cmp(fmtN(prev?.cl)), spark: [cur.spark.cl, prev?.spark.cl], href: "/cl/" },
    { label: t("Room nights"), v: fmtN(cur.rn), d: pct(cur.rn, prev?.rn), good: !prev || cur.rn >= prev.rn,
      foot: cmp(fmtN(prev?.rn)), spark: [cur.spark.rn, prev?.spark.rn], href: "/calendar/" },
  ];
  const cancelled = { label: t("Cancelled"), v: fmtN(cur.cancelled), unit: "CL", d: pct(cur.cancelled, prev?.cancelled),
    good: !prev || cur.cancelled <= prev.cancelled,
    foot: `${t("{v} SAR lost", { v: fmtN(cur.lost) })}. ${prev ? `${prevLabel}: ${prev.cancelled}` : ""}`,
    spark: [cur.spark.cancelled, prev?.spark.cancelled], href: "/cl/" };
  if (kind === "staff" || kind === "viewer") {
    if (checkins) {
      const rooms = checkins.rows.reduce((a, r) => a + r.rooms, 0);
      kpis.push({ label: t("Check-ins this week"), v: fmtN(checkins.rows.length),
        foot: t("{n} rooms", { n: rooms }), href: "/calendar/" });
    }
    if (mine && uninvoiced) {
      const r = uninvoiced.rows?.[0];
      kpis.push({ label: t("CLs not invoiced"), v: fmtN(uninvoiced.count), warn: uninvoiced.count > 0,
        foot: r ? t("Nearest {d}", { d: dWeek(r.check_in) }) : t("All invoiced"), href: "/invoice/" });
    } else if (!mine) kpis.push(cancelled);
  } else if (kind === "admin" && receivable) {
    kpis.push({ label: t("Past due"), v: fmtN(receivable.past_due), unit: "SAR", warn: receivable.past_due > 0,
      foot: receivable.past_due ? pastDueSub(t, receivable.past_clients, receivable.oldest) : t("Nothing past due"),
      href: "/finance/ar-aging/" });
  } else kpis.push(cancelled);
  if (profit && kind !== "staff" && kind !== "viewer") {
    const p = profit.cur, q = profit.prev;
    kpis.push({
      label: t("Branch profit"), v: p.profit == null ? t("No FX gain yet") : millions(p.profit), unit: p.profit == null ? "" : "IDR", none: p.profit == null, loss: p.profit < 0,
      d: p.profit != null && q?.profit ? pct(p.profit, q.profit) : null, good: !q?.profit || p.profit >= q.profit,
      foot: t("FX {fx} − expenses {ex}", { fx: millions(p.fx), ex: millions(p.expenses) }), href: "/finance/fund-flow/",
    });
  }

  return (
    <div className={"db-kpis" + (kpis.length === 3 ? " k3" : "")}>
      <Link className={"db-hero" + (heroBad ? " bad" : "")} href="/cl/">
        <span className="l">{isSeason ? t("Booked value, season {s}", { s: period.label }) : t("Booked value, {m}", { m: t(period.label) })}
          {heroPct && <span className={"chip" + (heroBad ? " bad" : "")}>{heroPct}</span>}</span>
        <span className="v">{fmtN(cur.value)}<small>SAR</small></span>
        <span className="bars" role="img" aria-label={t("Booked value building up over the period")}>
          {bars.map((b, i) => <i key={i} className={b.on ? "on" : ""} style={{ height: `${Math.max(b.h, 4)}%` }} />)}
        </span>
        <span className="ax"><span>{axis[0]}</span><span>{axis[1]}</span></span>
        <span className="f">{prev ? `${prevLabel}: ${fmtN(prev.value)}` : t("First season in HMS, nothing to compare")}</span>
      </Link>
      {kpis.map((k) => (
        <Kpi key={k.label} href={k.href} label={k.label} value={k.v} unit={k.unit} foot={k.foot}
          delta={k.d && { text: k.d, good: k.good }}
          tone={k.none ? "none" : k.loss ? "loss" : k.warn ? "warn" : undefined}
          spark={k.spark && <Spark cur={k.spark[0]} prev={k.spark[1] || []} label={t("{k}, this period against the one before", { k: k.label })} />} />
      ))}
    </div>
  );
}

function SoldPerMonth({ sm, isSeason, title }) {
  const { t } = useI18n();
  const [hv, setHv] = useState(-1);
  const months = sm.months.map((m) => ({ ...m, d: iso(m.key) }));
  const pre = sm.before_hms || 0;
  const max = Math.max(3, ...months.map((m) => Math.max(m.cur || 0, sm.has_ly ? m.ly : 0)));
  const scale = Math.ceil(max / 3) * 3;
  const pick = isSeason ? sm.now : sm.selected ?? sm.now;
  const seasonSum = months.slice(0, sm.now + 1).reduce((a, m) => a + (m.cur || 0), 0);
  const lySum = months.slice(0, sm.now + 1).reduce((a, m) => a + m.ly, 0);
  const p = months[pick];
  const lyName = sm.prev_season ? t("Season {s}", { s: sm.prev_season }) : t("A year earlier");
  const note = isSeason
    ? (sm.has_ly ? t("sold so far this season, {n} at the same point last season", { n: lySum }) : t("sold so far this season"))
    : !sm.has_ly
      ? (pick === sm.now ? t("sold so far in {m}", { m: t(MONTHS[p.d.getMonth()]) }) : t("sold in {m}", { m: t(MONTHS[p.d.getMonth()]) }))
      : pick === sm.now
        ? t("sold so far in {m}, {n} in {m} last season", { m: t(MONTHS[p.d.getMonth()]), n: p.ly })
        : t("sold in {m}, {n} in {m} last season", { m: t(MONTHS[p.d.getMonth()]), n: p.ly });
  return (
    <section data-slot="card" className={cn(DA.card, DA.cardPad)}>
      <div data-slot="card-head" className={cn(DA.cardHead, "p-0 max-[600px]:p-0")}>
        <h2>{title || t("CL sold per month")}{sm.season && <span className={DA.count}>{t("Season {s}", { s: sm.season })}</span>}</h2>
        <span className="db-lg">
          <span><i style={{ background: GREEN }} />{isSeason ? t("This season") : t(MONTHS[p.d.getMonth()])}</span>
          <span><i style={{ background: "var(--chart-bar)" }} />{t("Other months")}</span>
          {sm.has_ly && <span><i className="ly" />{lyName}</span>}
        </span>
      </div>
      <div className="db-big"><b>{isSeason ? seasonSum : p.cur ?? 0} CL</b><span>{note}</span></div>
      <div className="bc" role="img" aria-label={t("CL sold per month: {list}.", { list: months.map((m, i) => (i < pre ? "-" : m.cur ?? "-")).join(", ") })}>
        <div className="gl" style={{ bottom: 0 }} />
        {pre > 0 && <span className="pre" style={{ width: `calc(${(pre / 12) * 100}% - 8px)` }}>{t("Not in HMS yet")}</span>}
        {months.map((m, i) => {
          const on = isSeason ? i <= sm.now : i === pick;
          const down = sm.has_ly && m.cur != null && m.cur < m.ly;
          return (
            i < pre ? <div key={m.key} className="col" /> :
            <div key={m.key} className={"col" + (on ? " on" : "") + (on && down ? " down" : "")}
              onMouseEnter={() => setHv(i)} onMouseLeave={() => setHv(-1)}>
              <span className="b" style={{ height: `${((m.cur || 0) / scale) * 100}%` }}>
                {m.cur > 0 && <span className="val">{m.cur}</span>}
              </span>
              {sm.has_ly && <span className="ly" style={{ bottom: `${(m.ly / scale) * 100}%` }} />}
              {hv === i && (
                <span className={"tip" + (i < 2 ? " l" : i > 8 ? " r" : "")}>
                  <span className="h">{t(MONTHS[m.d.getMonth()])} {m.d.getFullYear()}</span>
                  <span className="r2"><span>{m.cur == null ? t("Not yet") : i === sm.now ? t("Sold so far") : t("Sold")}</span><b>{m.cur == null ? "-" : `${m.cur} CL`}</b></span>
                  {sm.has_ly && <span className="r2"><span>{lyName}</span><b>{m.ly} CL</b></span>}
                </span>
              )}
            </div>
          );
        })}
      </div>
      <div className="bx">{months.map((m, i) => <span key={m.key} className={i < pre ? "pre" : (isSeason ? i <= sm.now : i === pick) || hv === i ? "on" : ""}>{MON[m.d.getMonth()]}</span>)}</div>
    </section>
  );
}

function Collected({ col, deposits }) {
  const { t } = useI18n();
  const pct = col.pct ?? 0;
  return (
    <section data-slot="card" className={cn(DA.card, DA.cardPad)}>
      <div data-slot="card-head" className={cn(DA.cardHead, "p-0 max-[600px]:p-0")}><h2>{t("Collected")}</h2><Link href="/finance/ar-aging/">{t("AR aging")}</Link></div>
      {col.billed > 0 ? (
        <>
          <div className="gauge">
            <svg width="220" height="124" viewBox="0 0 220 124" role="img" aria-label={t("{p} percent of billed is paid", { p: pct })}>
              <path d="M18 110 A92 92 0 0 1 202 110" fill="none" stroke="var(--chart-bar)" strokeWidth="16" strokeLinecap="round" />
              <path d="M18 110 A92 92 0 0 1 202 110" fill="none" strokeWidth="16" strokeLinecap="round"
                stroke={pct < 60 ? "oklch(0.72 0.16 62)" : GREEN} strokeDasharray={`${((ARC * pct) / 100).toFixed(1)} ${ARC}`} />
            </svg>
            <span className="gpct">{pct}%</span><span className="glab">{t("of billed is paid")}</span>
          </div>
          <div style={{ marginTop: 12 }}>
            <div className="kv"><span><i style={{ background: GREEN }} />{t("Paid")}</span><b>{fmtN(col.paid)}</b></div>
            <div className="kv"><span><i style={{ background: "var(--chart-bar)" }} />{t("Not due yet")}</span><b>{fmtN(col.not_due)}</b></div>
            <div className="kv"><span><i style={{ background: "var(--warning)" }} />{t("Past due")}</span><b style={{ color: col.past_due ? "var(--warning-text)" : undefined }}>{fmtN(col.past_due)}</b></div>
            <div className="kv tot"><span>{t("Billed")}</span><b>{fmtN(col.billed)}</b></div>
            {deposits?.total > 0 && <div className="kv"><span>{t("Client deposits, not applied")}</span><b>{fmtN(deposits.total)}</b></div>}
          </div>
        </>
      ) : (
        <Empty title={t("Nothing billed yet")} sub={t("Invoices issued in this period show here.")} />
      )}
    </section>
  );
}

function todoText(x, t) {
  switch (x.key) {
    case "checkin_today": return [t("Check-in today"), x.count > 1 ? t("{c} and {n} more", { c: x.first, n: x.count - 1 }) : x.first, ""];
    case "due_week": return [t("Invoices due this week"), t("Nearest {d}, {c}", { d: dWeek(x.nearest.date), c: x.nearest.client }), "w"];
    case "past_due": return [t("Invoices past due"), pastDueSub(t, x.clients, x.oldest), x.oldest > 30 ? "r" : "w"];
    case "no_dp": return [t("No DP, check-in within 14 days"), t("Nearest {d}, {c}", { d: dWeek(x.nearest.date), c: x.nearest.client }), "w"];
    case "tentative": return [t("Tentative, check-in within 14 days"), t("Confirm or release rooms, nearest {d}", { d: dWeek(x.nearest.date) }), "w"];
    case "uninvoiced": return [t("Confirmed, not invoiced"), t("Nearest {d}, {c}", { d: dWeek(x.nearest.date), c: x.nearest.client }), ""];
    case "expenses": return [t("Expenses to approve"), t("Submitted by {names}", { names: x.by.join(", ") }), ""];
    case "refunds": return [t("Refunds to approve"), x.first ? t("{n}, by {by}", { n: x.first.number, by: x.first.by }) : "", ""];
    case "payments": return [t("Payments to confirm"), t("Check the money arrived, oldest {d} days", { d: x.oldest ?? 0 }), x.oldest > 2 ? "w" : ""];
    case "to_pay": return [t("Expenses to pay"), t("Approved, not paid yet, oldest {d} days", { d: x.oldest ?? 0 }), ""];
    case "not_sent": return [t("Not sent to HQ"), x.last_sent ? t("Last sent {d}", { d: dDay(x.last_sent) }) : t("Nothing sent yet"), "w"];
    case "transit": return [t("Remittances in transit"), t("Sent to HQ, not received yet, since {d}", { d: dDay(x.since) }), ""];
    case "unreconciled": return [t("Bank lines to reconcile"), x.since ? t("{a}, since {d}", { a: x.account, d: dDay(x.since) }) : x.account, ""];
    case "staff_held": return [t("Staff cash held long"), x.first ? t("{n}, {d} days without spending", { n: x.first.name, d: x.first.days }) : "", "w"];
    case "period": return [t("Close {m}", { m: t(MONTHS[iso(x.month).getMonth()]) }), t("Ended {d} days ago", { d: x.days }), x.days > 10 ? "w" : ""];
    case "locked": return [t("Locked user account"), x.first ? t("{u}, {n} failed sign-ins", { u: x.first.username, n: x.first.failures }) : "", "r"];
    case "idle": return [t("Users idle 30 days or more"), t("Still active, may need to be turned off"), ""];
    default: return [x.key, "", ""];
  }
}

function Todo({ items, count }) {
  const { t } = useI18n();
  return (
    <section data-slot="card" className={DA.card}>
      <div data-slot="card-head" className={DA.cardHead}><h2>{t("To do")}{count > 0 && <span className={DA.count}>{count}</span>}</h2><span className={DA.meta}>{t("Today, most urgent first")}</span></div>
      {items.length ? (
        <div className="dt dt-todo" role="table" aria-label={t("To do")}>
          <div className="dt-h" role="row"><span role="columnheader">{t("What")}</span><span className="n" role="columnheader">{t("Count")}</span><span className="n" role="columnheader">{t("Amount")}</span><span /></div>
          {items.map((x) => {
            const [title, sub, tone] = todoText(x, t);
            return (
              <Link key={x.key} className="dt-r" role="row" href={x.url}>
                <span role="cell" style={{ minWidth: 0 }}><span className="strong">{title}</span><span className="sub ell">{sub}</span></span>
                <span className="n" role="cell"><span className={"cnt" + (tone === "r" ? " r" : "")}>{x.count}</span></span>
                <span className="n" role="cell">{x.amount != null && <><span className="bold">{money(x.amount, x.ccy)}</span><span className="mut">{x.ccy}</span></>}</span>
                <span className="go" aria-hidden="true">{LIcon.next}</span>
              </Link>
            );
          })}
        </div>
      ) : (
        <Empty lead={<div className="db-ok"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10" /></svg></div>}
          title={t("Nothing waits for you")} sub={t("Past-due invoices, missing DPs and approvals show up here.")} />
      )}
    </section>
  );
}

const CI_PILL = { paid: ["green", "Paid"], partial: ["amber-o", "Partial"], no_dp: ["amber", "No DP"], uninvoiced: ["amber", "Not invoiced"], tentative: ["outline", "Tentative"] };

function Checkins({ data, title }) {
  const { t } = useI18n();
  const rows = data.rows;
  const rooms = rows.reduce((a, r) => a + r.rooms, 0);
  return (
    <section data-slot="card" className={DA.card}>
      <div data-slot="card-head" className={DA.cardHead}><h2>{title || t("Check-ins this week")}{rows.length > 0 && <span className={DA.count}>{rows.length}</span>}</h2><Link href="/calendar/">{t("Calendar")}</Link></div>
      {rows.length ? (
        <>
          <div className="dt dt-ci" role="table" aria-label={t("Check-ins this week")}>
            <div className="dt-h" role="row"><span role="columnheader">{t("Date")}</span><span role="columnheader">{t("Client")}</span><span className="n" role="columnheader">{t("Rooms")}</span><span role="columnheader">{t("Status")}</span></div>
            {rows.map((r) => {
              const [tone, label] = CI_PILL[r.state] || ["gray", r.state];
              const d = iso(r.check_in);
              return (
                <Link key={r.id} className="dt-r" role="row" href={`/cl/${r.id}/`}>
                  <span className="d" role="cell">{r.in_days === 0 ? t("Today") : `${t(DAYS[d.getDay()])} ${d.getDate()}`}</span>
                  <span role="cell" style={{ minWidth: 0 }}><span className="strong ell">{r.client}</span><span className="sub ell">{r.hotel}</span></span>
                  <span className="n" role="cell">{r.rooms}</span>
                  <span role="cell"><Pill tone={tone} sm>{t(label)}</Pill></span>
                </Link>
              );
            })}
          </div>
          <div data-slot="card-foot" className={DA.cardFoot}><span className={DA.footLabel}>{t("{n} rooms arriving this week", { n: rooms })}</span><Link href="/calendar/" style={{ marginLeft: "auto" }}>{t("See all in Calendar")}</Link></div>
        </>
      ) : (
        <Empty title={t("No check-ins this week")} sub={t("Arrivals of the next 7 days show here.")} />
      )}
    </section>
  );
}

function ByBranch({ rows, period }) {
  const { t } = useI18n();
  const sum = (k) => rows.reduce((a, r) => a + (r[k] || 0), 0);
  return (
    <section data-slot="card" className={DA.card}>
      <div data-slot="card-head" className={DA.cardHead}><h2>{t("By branch")}<span className={DA.count}>{rows.length}</span></h2><span className={DA.meta}>{period.kind === "season" ? t("Season {s}", { s: period.label }) : t(period.label)}, {t("SAR unless noted")}</span></div>
      <div className={DA.scroll}>
        <table data-slot="detail-table" className={DA.table}>
          <thead><tr><th>{t("Branch")}</th><th className={DC.n}>{t("CL sold")}</th><th className={DC.n}>{t("Booked value")}</th><th className={DC.n}>{t("Past due")}</th><th className={DC.n}>{t("Not sent to HQ")}</th><th className={DC.n}>{t("Profit")}</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.code} className={DA.rowMid}>
                <td><span className={DC.strong}>{r.name}</span></td>
                <td className={DC.n}>{fmtN(r.cl)}</td>
                <td className={cn(DC.n, DC.bold)}>{fmtN(r.value)}</td>
                <td className={cn(DC.n, r.past_due && DC.late)}>{r.past_due == null ? "–" : fmtN(r.past_due)}</td>
                <td className={DC.n}>{r.not_sent == null ? "–" : `${millions(r.not_sent)} IDR`}</td>
                <td className={cn(DC.n, DC.bold)}>{r.profit == null ? "–" : `${millions(r.profit)} IDR`}</td>
              </tr>
            ))}
          </tbody>
          {rows.length > 1 && (
            <tfoot><tr><td>{t("All branches")}</td><td className={DC.n}>{fmtN(sum("cl"))}</td><td className={DC.n}>{fmtN(sum("value"))}</td><td className={DC.n}>{fmtN(sum("past_due"))}</td><td className={DC.n}>{`${millions(sum("not_sent"))} IDR`}</td><td className={DC.n}>{`${millions(sum("profit"))} IDR`}</td></tr></tfoot>
          )}
        </table>
      </div>
    </section>
  );
}

function Ranking({ title, meta, rows, empty, hasPrev }) {
  const { t } = useI18n();
  const max = Math.max(1, ...rows.map((r) => r.v));
  const chg = (r) => (r.new ? (hasPrev ? [t("New"), "nw"] : ["", ""]) : r.chg == null ? ["", ""] : [`${r.chg >= 0 ? "+" : "−"}${Math.abs(r.chg)}%`, r.chg >= 0 ? "up" : "dn"]);
  return (
    <section data-slot="card" className={DA.card}>
      <div data-slot="card-head" className={DA.cardHead}><h2>{title}</h2><span className={DA.meta}>{meta}</span></div>
      {rows.length ? (
        <div className="rk">
          {rows.map((r, i) => {
            const [c, tone] = chg(r);
            return (
              <Link key={r.id} className="rk-r" href={r.href}>
                <span className="no">{i + 1}</span>
                <span className="nm">{r.name}<small>{r.sub}</small></span>
                <span className={"chg " + tone}>{c}</span>
                <b>{fmtN(r.v)}</b>
                <span className="bar"><i style={{ width: `${(r.v / max) * 100}%` }} /></span>
              </Link>
            );
          })}
        </div>
      ) : (
        <Empty title={empty[0]} sub={empty[1]} />
      )}
    </section>
  );
}

function MoneyNow({ m }) {
  const { t } = useI18n();
  const rows = [
    { label: t("Bank and Cash"), sub: t("{n} accounts, today's rate", { n: m.cash.accounts }), v: fmtN(m.cash.sar), unit: "SAR", href: "/finance/bank-accounts/", zero: !m.cash.sar },
    { label: t("Staff cash held"), sub: m.staff.people ? t("{n} staff, oldest {d} days", { n: m.staff.people, d: m.staff.oldest ?? 0 }) : t("None"), v: fmtN(m.staff.sar), unit: "SAR", href: "/finance/bank-accounts/", warn: (m.staff.oldest || 0) > 14, zero: !m.staff.sar },
    { label: t("Waiting for Finance"), sub: m.pending.count ? t("{v} SAR, oldest {d} days", { v: fmtN(m.pending.sar), d: m.pending.oldest ?? 0 }) : t("Nothing pending"), v: fmtN(m.pending.count), unit: t("payments"), href: "/finance/payments/", warn: (m.pending.oldest || 0) > 3, zero: !m.pending.count },
  ];
  if (m.not_sent) rows.push({ label: t("Not sent to HQ"), sub: m.not_sent.last_sent ? t("Last sent {d}", { d: dDay(m.not_sent.last_sent) }) : t("Nothing sent yet"), v: millions(m.not_sent.idr), unit: "IDR", href: "/remittance/", warn: m.not_sent.idr > 0, zero: !m.not_sent.idr });
  return (
    <section data-slot="card" className={DA.card}>
      <div data-slot="card-head" className={DA.cardHead}><h2>{t("Money now")}</h2><Link href="/finance/bank-accounts/">{t("Bank and Cash")}</Link></div>
      <div className="mn">
        {rows.map((r) => (
          <Link key={r.label} className="mn-r" href={r.href}>
            <span>{r.label}<small>{r.sub}</small></span>
            <b className={r.warn ? "warn" : r.zero ? "zero" : ""}>{r.v}<small>{r.unit}</small></b>
          </Link>
        ))}
      </div>
    </section>
  );
}

// ── Administrator: users and access ──────────────────────────────────────
function People({ p }) {
  const { t } = useI18n();
  const rows = [
    ...p.locked.map((u) => ({ key: `l-${u.username}`, name: u.username, sub: t("Locked after {n} failed sign-ins, until {t}", { n: u.failures, t: u.until }), tone: "red", pill: t("Locked"), href: "/users/" })),
    ...p.idle.slice(0, 6).map((u) => ({ key: `i-${u.id}`, name: u.name, sub: u.never ? t("Never signed in") : t("Last seen {d} days ago", { d: u.days }), tone: "gray", pill: t("Idle"), href: `/users/${u.id}/edit/` })),
  ];
  return (
    <section data-slot="card" className={DA.card}>
      <div data-slot="card-head" className={DA.cardHead}><h2>{t("Users and access")}</h2><Link href="/users/">{t("Users")}</Link></div>
      {rows.length ? (
        <div className="mn">
          {rows.map((r) => (
            <Link key={r.key} className="mn-r" href={r.href}>
              <span>{r.name}<small>{r.sub}</small></span>
              <Pill tone={r.tone} sm>{r.pill}</Pill>
            </Link>
          ))}
        </div>
      ) : (
        <Empty title={t("Everyone can sign in")} sub={t("Locked and idle accounts show here.")} />
      )}
    </section>
  );
}

// ── Staff and Viewer ─────────────────────────────────────────────────────
const PAY_PILL = { pending: ["amber", "Waiting for Finance"], confirmed: ["green", "Confirmed"], rejected: ["red", "Sent back"], reversed: ["gray", "Reversed"], voided: ["gray", "Voided"] };

function StaffHome(props) {
  const { t } = useI18n();
  const { variant, period, sales, sold_months: sm, checkins, top, todo = [], uninvoiced, my_payments: pays, advance, seasons = [] } = props;
  const staff = variant === "staff";
  const isSeason = period.kind === "season";
  // Nothing waiting: no To do card, the greeting line already says so.
  const work = staff && todo.length > 0;
  return (
    <>
      <Head todo={todo} readOnly={!staff} period={period} seasons={seasons} today={props.today} onGo={props.onGo}
        scopeNote={staff ? null : t("Read only")} />
      {sales && <KpiRow period={period} sales={sales} sm={sm} isSeason={isSeason} kind={variant} checkins={checkins} uninvoiced={uninvoiced} />}
      {(sm || top) && (
        <div className={"db-g2 db-charts" + (sm && top ? "" : " one")}>
          {sm && <SoldPerMonth sm={sm} sales={sales} period={period} isSeason={isSeason} />}
          {top && <TopClients top={top} />}
        </div>
      )}
      {(work || checkins) && (
        <div className={"db-g2b db-work" + (work && checkins ? "" : " one")}>
          {work && <Todo items={todo} count={todo.reduce((a, x) => a + x.count, 0)} />}
          {checkins && <Checkins data={checkins} />}
        </div>
      )}
      {staff && (pays || advance) && (
        <div className={"db-g2b db-mine" + (pays && advance ? "" : " one")}>
          {pays && <MyPayments rows={pays} />}
          {advance && <MyAdvance rows={advance} />}
        </div>
      )}
    </>
  );
}

function MyPayments({ rows }) {
  const { t } = useI18n();
  return (
    <section data-slot="card" className={DA.card}>
      <div data-slot="card-head" className={DA.cardHead}><h2>{t("Payments I uploaded")}</h2><Link href="/finance/payments/">{t("Payment List")}</Link></div>
      {rows.length ? (
        <div className="dt dt-mypay" role="table" aria-label={t("Payments I uploaded")}>
          <div className="dt-h" role="row"><span role="columnheader">{t("Client")}</span><span className="n" role="columnheader">{t("Amount")}</span><span role="columnheader">{t("Status")}</span></div>
          {rows.map((p) => {
            const [tone, label] = PAY_PILL[p.status] || ["gray", p.status];
            return (
              <Link key={p.id} className="dt-r" role="row" href={`/finance/payments/${p.id}/`}>
                <span role="cell" style={{ minWidth: 0 }}><span className="strong ell">{p.client}</span><span className="sub ell">{[p.account, t("uploaded {d}", { d: dDay(p.uploaded) })].filter(Boolean).join(", ")}</span></span>
                <span className="n" role="cell"><span className="bold">{money(p.amount, p.ccy)}</span><span className="mut">{p.ccy}</span></span>
                <span role="cell"><Pill tone={tone} sm>{t(label)}</Pill></span>
              </Link>
            );
          })}
        </div>
      ) : (
        <Empty title={t("No payments uploaded yet")} sub={t("Client payments you record show here until Finance confirms them.")} />
      )}
    </section>
  );
}

function MyAdvance({ rows }) {
  const { t } = useI18n();
  return (
    <section data-slot="card" className={DA.card}>
      <div data-slot="card-head" className={DA.cardHead}><h2>{t("My cash advance")}</h2></div>
      <div className="mn">
        {rows.map((a) => (
          <div key={a.id} className="mn-r">
            <span>{a.held < 0 ? t("The office owes you") : t("Holding now")}<small>{a.given_on ? t("Last given {d}, {b}", { d: dDay(a.given_on), b: a.branch }) : a.branch}</small></span>
            <b className={a.held < 0 ? "warn" : ""}>{fmtN(Math.abs(a.held))}<small>{a.ccy}</small></b>
          </div>
        ))}
      </div>
      <div data-slot="card-foot" className={DA.cardFoot}><span className={DA.footLabel}>{t("Return what is left to the office cash when done.")}</span></div>
    </section>
  );
}

// ── Finance ──────────────────────────────────────────────────────────────
function FinanceHome(props) {
  const { period, todo = [], cash, received, flow, receivable, profit, collected: col, deposits, pay, chase, owed, to_pay: toPay, seasons = [] } = props;
  return (
    <>
      <Head todo={todo} period={period} seasons={seasons} today={props.today} onGo={props.onGo} />
      <FinanceKpis period={period} cash={cash} received={received} flow={flow} receivable={receivable} profit={profit} />
      {(flow || col) && (
        <div className={"db-g2" + (flow && col ? "" : " one")}>
          {flow && <MoneyInOut flow={flow} />}
          {col && <Collected col={col} deposits={deposits} />}
        </div>
      )}
      <div className={"db-g2b" + (pay || chase ? "" : " one")}>
        <Todo items={todo} count={todo.reduce((a, x) => a + x.count, 0)} />
        {(pay || chase) && (
          <div className="db-stack">
            {pay && <ToConfirm pay={pay} />}
            {chase && <ToChase chase={chase} />}
          </div>
        )}
      </div>
      {(profit || cash || owed) && (
        <div className={"db-g3" + ([profit, cash, owed].filter(Boolean).length === 3 ? "" : " two")}>
          {profit && <ProfitCard profit={profit} toPay={toPay} />}
          {cash && <Accounts cash={cash} />}
          {owed && <OwedHq owed={owed} deposits={deposits} />}
        </div>
      )}
    </>
  );
}

function FinanceKpis({ period, cash, received, flow, receivable, profit }) {
  const { t } = useI18n();
  const prevLabel = period.prev_label;
  const pct = (a, b) => { const p = b ? pctOf(a, b) : null; return !p ? null : `${p > 0 ? "+" : "-"}${Math.abs(p)}%`; };
  const kpis = [];
  if (received) {
    const c = received.cur, p = received.prev;
    kpis.push({ label: t("Received"), v: fmtN(c.sar), unit: "SAR", d: pct(c.sar, p?.sar), good: !p || c.sar >= p.sar,
      foot: p ? `${prevLabel}: ${fmtN(p.sar)}` : t("{n} payments confirmed", { n: c.count }), spark: [c.spark, p?.spark], href: "/finance/payments/" });
  }
  if (flow) {
    const c = flow.cur, p = flow.prev;
    kpis.push({ label: t("Paid out"), v: millions(c.out), unit: "IDR", d: pct(c.out, p?.out), good: !p || c.out <= p.out,
      foot: t("Hotels, expenses, refunds and money sent to HQ"), href: "/finance/fund-flow/" });
  }
  if (receivable) {
    kpis.push({ label: t("Receivables"), v: fmtN(receivable.total), unit: "SAR", warn: receivable.past_due > 0,
      foot: receivable.past_due ? t("{v} of it past due", { v: fmtN(receivable.past_due) }) : t("Nothing past due"), href: "/finance/ar-aging/" });
  }
  if (profit) {
    kpis.push({ label: t("Branch profit"), v: profit.cur == null ? t("No FX gain yet") : millions(profit.cur), unit: profit.cur == null ? "" : "IDR",
      none: profit.cur == null, loss: profit.cur < 0, d: profit.cur != null && profit.prev ? pct(profit.cur, profit.prev) : null, good: !profit.prev || profit.cur >= profit.prev,
      foot: t("FX gain on rupiah sent to HQ"), href: "/finance/fund-flow/" });
  }
  const ccy = (cash?.currencies || []).filter((c) => c.native);
  return (
    <div className={"db-kpis" + (cash ? (kpis.length === 3 ? " k3" : "") : " nohero")}>
      {cash && (
        <Link className="db-hero" href="/finance/bank-accounts/">
          <span className="l">{t("Bank and Cash")}</span>
          <span className="v">{fmtN(cash.sar)}<small>SAR</small></span>
          <span className="lines">
            {ccy.map((c) => <span key={c.ccy}><span>{c.ccy}</span><b>{money(c.native, c.ccy)}</b></span>)}
          </span>
          <span className="f">{t("{n} accounts, today's rate", { n: cash.accounts.length })}</span>
        </Link>
      )}
      {kpis.map((k) => (
        <Kpi key={k.label} href={k.href} label={k.label} value={k.v} unit={k.unit} foot={k.foot}
          delta={k.d && { text: k.d, good: k.good }}
          tone={k.none ? "none" : k.loss ? "loss" : k.warn ? "warn" : undefined}
          spark={k.spark && <Spark cur={k.spark[0]} prev={k.spark[1] || []} label={t("{k}, this period against the one before", { k: k.label })} />} />
      ))}
    </div>
  );
}

// Received and paid out per month, the last six months, rupiah in millions.
function MoneyInOut({ flow }) {
  const { t } = useI18n();
  const [hv, setHv] = useState(-1);
  const months = flow.months.map((m) => ({ ...m, d: iso(m.key) }));
  const top = Math.max(1, ...months.map((m) => Math.max(m.in, m.out))) / 1e6;
  const step = Math.max(1, Math.ceil(top / 3 / 50) * 50);
  const scale = step * 3;
  const last = months.length - 1;
  const net = flow.cur.in - flow.cur.out;
  return (
    <section data-slot="card" className={cn(DA.card, DA.cardPad)}>
      <div data-slot="card-head" className={cn(DA.cardHead, "p-0 max-[600px]:p-0")}>
        <h2>{t("Money in and out")}<span className={DA.count}>{t("per month, M IDR")}</span></h2>
        <span className="db-lg"><span><i style={{ background: GREEN }} />{t("Received")}</span><span><i style={{ background: "var(--foreground)" }} />{t("Paid out")}</span></span>
      </div>
      <div className="db-big"><b>{net >= 0 ? "+" : "−"}{millions(Math.abs(net))} IDR</b><span>{t("net in the branch accounts this period")}</span></div>
      <div className="fc" role="img" aria-label={t("Received and paid out per month: {list}.", { list: months.map((m) => `${MON[m.d.getMonth()]} ${millions(m.in)} / ${millions(m.out)}`).join(", ") })}>
        {[1, 2 / 3, 1 / 3, 0].map((f) => (
          <div key={f} className="gl" style={{ bottom: `${f * 100}%` }}><span>{Math.round(scale * f)}</span></div>
        ))}
        {months.map((m, i) => (
          <div key={m.key} className={"fcol" + (i === last ? " on" : "")} onMouseEnter={() => setHv(i)} onMouseLeave={() => setHv(-1)}>
            <span className="fin" style={{ height: `${Math.min(100, (m.in / 1e6 / scale) * 100)}%` }} />
            <span className="fout" style={{ height: `${Math.min(100, (m.out / 1e6 / scale) * 100)}%` }} />
            {hv === i && (
              <span className={"tip" + (i > 3 ? " r" : "")}>
                <span className="h">{t(MONTHS[m.d.getMonth()])} {m.d.getFullYear()}</span>
                <span className="r2"><span>{t("Received")}</span><b>{millions(m.in)}</b></span>
                <span className="r2"><span>{t("Paid out")}</span><b>{millions(m.out)}</b></span>
                <span className="r2"><span>{t("Net")}</span><b>{m.in >= m.out ? "+" : "−"}{millions(Math.abs(m.in - m.out))}</b></span>
              </span>
            )}
          </div>
        ))}
      </div>
      <div className="fx">{months.map((m, i) => <span key={m.key} className={i === last || hv === i ? "on" : ""}>{MON[m.d.getMonth()]}</span>)}</div>
    </section>
  );
}

function ToConfirm({ pay }) {
  const { t } = useI18n();
  return (
    <section data-slot="card" className={DA.card}>
      <div data-slot="card-head" className={DA.cardHead}><h2>{t("Payments to confirm")}{pay.count > 0 && <span className={DA.count}>{pay.count}</span>}</h2><span className={DA.meta}>{t("Check the money arrived, then confirm")}</span></div>
      {pay.rows.length ? (
        <div className="dt dt-pay" role="table" aria-label={t("Payments to confirm")}>
          <div className="dt-h" role="row"><span role="columnheader">{t("Client")}</span><span className="n" role="columnheader">{t("Amount")}</span><span /></div>
          {pay.rows.map((p) => (
            <Link key={p.id} className="dt-r" role="row" href={`/finance/payments/${p.id}/`}>
              <span role="cell" style={{ minWidth: 0 }}><span className="strong ell">{p.client}</span><span className="sub ell">{t("Into {a}, waiting {d} days", { a: p.account, d: p.waiting })}</span></span>
              <span className="n" role="cell"><span className="bold">{money(p.amount, p.ccy)}</span><span className="mut">{p.ccy}</span></span>
              <span className="go" aria-hidden="true">{LIcon.next}</span>
            </Link>
          ))}
        </div>
      ) : (
        <Empty title={t("No payments to confirm")} sub={t("Payments recorded by staff wait here for you.")} />
      )}
    </section>
  );
}

function ToChase({ chase }) {
  const { t } = useI18n();
  return (
    <section data-slot="card" className={cn(DA.card, "flex-1")}>
      <div data-slot="card-head" className={DA.cardHead}><h2>{t("Invoices to chase")}{chase.clients > 0 && <span className={DA.count}>{chase.clients}</span>}</h2><Link href="/finance/ar-aging/">{t("AR aging")}</Link></div>
      {chase.rows.length ? (
        <>
          <div className="dt dt-pd" role="table" aria-label={t("Invoices past due")}>
            <div className="dt-h" role="row"><span role="columnheader">{t("Client and invoice")}</span><span className="n" role="columnheader">{t("Late")}</span><span role="columnheader">{t("Reminded")}</span><span className="n" role="columnheader">SAR</span></div>
            {chase.rows.map((r) => (
              <Link key={r.client_id} className="dt-r" role="row" href={`/invoice/${r.invoice.id}/`}>
                <span role="cell" style={{ minWidth: 0 }}><span className="strong ell">{r.client}</span><span className="sub ell">{t("{n}, due {d}", { n: r.invoice.number, d: dDay(r.due_date) })}</span></span>
                <span className="n late-n" role="cell">{t("{d} d", { d: r.late })}</span>
                <span className="d" role="cell">{r.reminded ? dDay(r.reminded) : t("Never")}</span>
                <span className="n bold" role="cell">{fmtN(r.open)}</span>
              </Link>
            ))}
          </div>
          <div data-slot="card-foot" className={DA.cardFoot}><span className={DA.footLabel}>{t("{v} SAR past due", { v: fmtN(chase.total) })}</span></div>
        </>
      ) : (
        <Empty title={t("Nothing past due")} sub={t("Invoices past their due date show here.")} />
      )}
    </section>
  );
}

function ProfitCard({ profit, toPay }) {
  const { t } = useI18n();
  return (
    <section data-slot="card" className={DA.card}>
      <div data-slot="card-head" className={DA.cardHead}><h2>{t("Branch profit and expenses")}</h2><Link href="/finance/fund-flow/">{t("Fund Flow")}</Link></div>
      <div className="mn">
        <Link className="mn-r" href="/finance/fund-flow/"><span>{t("Branch profit, FX gain")}<small>{t("On rupiah sent to HQ this period")}</small></span><b className={profit.cur < 0 ? "warn" : ""}>{profit.cur == null ? "–" : millions(profit.cur)}<small>IDR</small></b></Link>
        <Link className="mn-r" href="/finance/expenses/"><span>{t("Expenses paid")}<small>{t("From branch cash, claimed back from Pusat")}</small></span><b>{millions(profit.expenses)}<small>IDR</small></b></Link>
        {toPay && <Link className="mn-r" href="/finance/expenses/?status=approved"><span>{t("Expenses to pay")}<small>{toPay.count ? t("{n} approved, not paid yet", { n: toPay.count }) : t("None")}</small></span><b className={toPay.count ? "warn" : ""}>{millions(toPay.total)}<small>IDR</small></b></Link>}
      </div>
    </section>
  );
}

function Accounts({ cash }) {
  const { t } = useI18n();
  const st = cash.staff;
  return (
    <section data-slot="card" className={DA.card}>
      <div data-slot="card-head" className={DA.cardHead}><h2>{t("Accounts")}</h2><Link href="/finance/bank-accounts/">{t("Bank and Cash")}</Link></div>
      <div className="mn">
        {cash.accounts.map((a) => (
          <Link key={a.id} className="mn-r" href="/finance/bank-accounts/">
            <span className="ell">{a.name}<small>{a.kind === "cash" ? t("Cash in the office") : t("Bank, {c}", { c: a.ccy })}</small></span>
            <b className={a.native < 0 ? "warn" : ""}>{money(a.native, a.ccy)}<small>{a.ccy}</small></b>
          </Link>
        ))}
        <Link className="mn-r" href="/finance/bank-accounts/">
          <span>{t("Held by staff")}<small>{st.people ? t("{n} staff, oldest {d} days", { n: st.people, d: st.oldest ?? 0 }) : t("None")}</small></span>
          <b className={(st.oldest || 0) > 14 ? "warn" : ""}>{fmtN(st.sar)}<small>SAR</small></b>
        </Link>
      </div>
    </section>
  );
}

function OwedHq({ owed, deposits }) {
  const { t } = useI18n();
  const tr = owed.transit;
  return (
    <section data-slot="card" className={DA.card}>
      <div data-slot="card-head" className={DA.cardHead}><h2>{t("Owed to HQ")}</h2><Link href="/remittance/">{t("Remittance")}</Link></div>
      <div className="mn">
        <Link className="mn-r" href="/remittance/"><span>{t("Not sent yet")}<small>{owed.last_sent ? t("Last sent {d}", { d: dDay(owed.last_sent) }) : t("Nothing sent yet")}</small></span><b className={owed.not_sent > 0 ? "warn" : ""}>{millions(owed.not_sent)}<small>IDR</small></b></Link>
        <Link className="mn-r" href="/remittance/"><span>{t("In transit")}<small>{tr.count ? t("Sent to HQ, not received yet, since {d}", { d: dDay(tr.first.date) }) : t("Nothing in transit")}</small></span><b>{fmtN(tr.count)}<small>{t("remittances")}</small></b></Link>
        {deposits && <Link className="mn-r" href="/finance/statements/"><span>{t("Client deposits")}<small>{t("Paid ahead, not applied yet")}</small></span><b>{fmtN(deposits.total)}<small>SAR</small></b></Link>}
      </div>
    </section>
  );
}
