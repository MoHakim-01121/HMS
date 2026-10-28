import { Fragment, useEffect, useRef, useState } from "react";
import { Link, router } from "@inertiajs/react";
import { cn } from "@/lib/utils";
import { useI18n } from "../../utils/i18n.jsx";
import Page from "../../components/shadcn/page.jsx";

// Calendar, as on the HMS Calendar v2 canvas ("Redesign"): a row per hotel
// (or per client), one bar per booking from midday of check-in to midday of
// check-out, coloured by where the stay stands today. Above the rows, a tile
// per day and a bar chart of check-ins; beside them an agenda of who comes in,
// moves hotel and leaves from the picked day on. The server sends real dates;
// all layout is here.

// Weekday initials indexed by Date#getUTCDay() (0 = Sunday). Indonesian needs
// three letters because Senin/Selasa/Sabtu all start with S.
const DOW = { en: ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"], id: ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"] };
const DOW3 = { en: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], id: DOW.id };
const DAYNAME = {
  en: ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
  id: ["Minggu", "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"],
};
const MONTH = {
  en: ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
  id: ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"],
};
const MON = {
  en: MONTH.en.map((m) => m.slice(0, 3)),
  id: ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"],
};

const ICON_BTN = "grid size-[34px] phone:size-11 flex-none cursor-pointer place-content-center rounded-full border border-border bg-card text-foreground hover:bg-secondary [&_svg]:size-4 [&_svg]:fill-none [&_svg]:stroke-current [&_svg]:stroke-[1.8]";
const SEG = "inline-flex gap-0.5 rounded-full bg-secondary p-[3px]";
const SEG_BTN = "h-[30px] phone:h-10 cursor-pointer rounded-full border-0 bg-transparent px-4 font-sans text-[13px] leading-[normal] font-medium text-muted-foreground";
const SEG_ON = "bg-card text-foreground shadow-pill";
const CARD = "overflow-clip rounded-[22px] border border-border bg-card";
const LABEL_COL = "grid-cols-[var(--label-w)_minmax(0,1fr)]";
const LINK = "underline decoration-border underline-offset-3 hover:decoration-current";
const ARROW = "M5 12h14M13 6l6 6-6 6";
const OUT_ICON = ["M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4", "M16 17l5-5-5-5", "M21 12H9"];
const IN_ICON = ["M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4", "M10 17l5-5-5-5", "M15 12H3"];

// Where a stay stands today: a tint, an edge on its left and the ink on it.
const STAY = {
  house: "bg-stay-house text-stay-house-ink before:bg-stay-house-edge",
  soon: "bg-stay-soon text-stay-soon-ink before:bg-stay-soon-edge",
  over: "bg-stay-over text-muted-foreground before:bg-stay-over-edge",
  tent: "bg-booking-tentative text-on-warning before:bg-tentative-text",
};
const SWATCH = {
  house: "bg-stay-house before:bg-stay-house-edge",
  soon: "bg-stay-soon before:bg-stay-soon-edge",
  over: "bg-stay-over before:bg-stay-over-edge",
  tent: "bg-booking-tentative before:bg-tentative-text",
};
const TAG = {
  In: "bg-stay-soon text-stay-soon-ink",
  Move: "bg-stay-house text-stay-house-ink",
  Out: "text-muted-foreground ring-1 ring-border ring-inset",
};
// Status ink in the popup: open invoice warns, tentative is yellow, settled is quiet.
const TONE = { wt: "text-warning-text", ty: "text-tentative-text" };
// The agenda shows five days with movement at a time, and up to six lines a
// day before a busy day folds the rest behind "+N more".
const PAGE = 5;
const PER_DAY = 6;

// Dates travel as day numbers (days since 1970-01-01, UTC) so the bar maths is
// plain subtraction with no time zone in it.
const DAY_MS = 86400000;
const dn = (iso) => { const [y, m, d] = iso.split("-").map(Number); return Date.UTC(y, m - 1, d) / DAY_MS; };
const asDate = (n) => new Date(n * DAY_MS);
const iso = (n) => asDate(n).toISOString().slice(0, 10);
const fmtSar = (v) => Math.round(v).toLocaleString("en-US");
const uniq = (xs) => [...new Set(xs)];

function Icon({ d, label }) {
  return (
    <svg viewBox="0 0 24 24" className="mt-0.5 size-[13px] fill-none stroke-current stroke-2 [stroke-linecap:round] [stroke-linejoin:round]"
      role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      {[].concat(d).map((p) => <path key={p} d={p} />)}
    </svg>
  );
}

export default function Calendar({ view, start, end, today, cities = [], hotels = [], bookings = [] }) {
  const { t, locale } = useI18n();
  const L = locale === "id" ? "id" : "en";
  const S = dn(start), E = dn(end), TODAY = dn(today);
  const W = E - S + 1;
  const month = view === "month";

  // The picked day and the open booking survive a trip to the server: a
  // navigation that wants them set leaves them in `carry`.
  const carry = useRef(null);
  const [day, setDay] = useState(TODAY >= S && TODAY <= E ? TODAY : S);
  const [sel, setSel] = useState(null);
  const [pages, setPages] = useState(1);
  const [openDays, setOpenDays] = useState([]);
  const [byClient, setByClient] = useState(false);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    const c = carry.current;
    carry.current = null;
    setDay(c?.day ?? (TODAY >= S && TODAY <= E ? TODAY : S));
    setSel(c?.sel ?? null);
    setPages(1);
    setOpenDays([]);
  }, [start, end, S, E, TODAY]);

  const go = (params, keep) => {
    carry.current = keep || null;
    router.get("/calendar/", params, {
      preserveState: true, preserveScroll: true, replace: true,
      onStart: () => setLoading(true), onFinish: () => setLoading(false),
    });
  };
  const viewParam = (v) => (v === "month" ? { view: "month" } : {});
  const pickDay = (n) => { setDay(n); setSel(null); setPages(1); setOpenDays([]); };

  const dateTxt = (n) => { const d = asDate(n); return `${d.getUTCDate()} ${MON[L][d.getUTCMonth()]}`; };
  const dowOf = (n) => asDate(n).getUTCDay();
  const plural = (n, one, many) => t(n === 1 ? one : many, { n });
  const rooms = (n) => plural(n, "{n} room", "{n} rooms");
  const nights = (n) => plural(n, "{n} night", "{n} nights");
  const invTxt = (b) => (!b.inv_number ? t("Not invoiced") : b.inv_open > 0 ? t("{amount} SAR open", { amount: fmtSar(b.inv_open) }) : t("Paid"));

  const hotelOf = Object.fromEntries(hotels.map((h) => [h.id, h]));
  const items = bookings.map((b) => ({ ...b, s: dn(b.check_in), e: dn(b.check_out), city: hotelOf[b.hotel]?.city }));
  const shown = items.filter((r) => r.e > S && r.s <= E);
  const status = (r) => (r.tentative ? "tent" : r.e <= TODAY ? "over" : r.s <= TODAY ? "house" : "soon");
  const cityLabel = Object.fromEntries(cities.map((c) => [c.value, t(c.label)]));

  // ── Check-ins: one client arriving at one hotel. The same client at two
  // hotels counts twice; two CLs of one client at one hotel count once.
  const arrivals = (n) => uniq(items.filter((r) => r.s === n).map((r) => `${r.client} · ${hotelOf[r.hotel].name}`)).sort();
  const days = Array.from({ length: W }, (_, i) => {
    const n = S + i;
    const who = arrivals(n);
    return { n, num: asDate(n).getUTCDate(), dow: DOW[L][dowOf(n)], who, count: who.length, aria: `${DAYNAME[L][dowOf(n)]} ${dateTxt(n)}` };
  });
  const peak = Math.max(...days.map((d) => d.count));
  const peakDays = days.filter((d) => peak && d.count === peak).map((d) => `${d.dow} ${d.num}`).join(", ");

  // ── Rows: by hotel (grouped by city) or by client (in the order their
  // first stay in the range begins). Each row stacks its CLs into lanes.
  const toRow = (key, name, mine, extra) => {
    const ends = [];
    const bars = [...mine].sort((a, b) => a.s - b.s || b.e - a.e).map((r) => {
      let lane = ends.findIndex((x) => r.s >= x);
      if (lane === -1) { lane = ends.length; ends.push(r.e); } else { ends[lane] = r.e; }
      return { ...r, lane: lane + 1 };
    });
    return { key, name, bars, ...extra };
  };
  const groups = byClient
    ? [{
        value: "clients", label: t("Clients"),
        rows: uniq([...shown].sort((a, b) => a.s - b.s).map((r) => r.client)).map((client) => {
          const mine = shown.filter((r) => r.client === client);
          // The route in order, a city repeated only when the client comes back to it.
          const route = [...mine].sort((a, b) => a.s - b.s).map((r) => cityLabel[r.city]).filter((c, i, xs) => c !== xs[i - 1]);
          return toRow(client, client, mine, { cls: plural(mine.length, "{n} CL", "{n} CLs"), route });
        }),
      }]
    : cities
        .map((c) => ({
          value: c.value, label: t(c.label),
          rows: hotels.filter((h) => h.city === c.value)
            .map((h) => toRow(h.id, h.name, shown.filter((r) => r.hotel === h.id), { url: h.url }))
            .filter((h) => h.bars.length),
        }))
        .filter((g) => g.rows.length);
  const allRows = groups.flatMap((g) => g.rows);
  const counted = (g) => (byClient ? plural(g.rows.length, "{n} client", "{n} clients") : plural(g.rows.length, "{n} hotel", "{n} hotels"));

  // Grid column of a booking's edges: day i's midday sits on line 2i + 2.
  const edges = (r) => [Math.max(1, 2 * (r.s - S) + 2), Math.min(2 * W + 1, 2 * (r.e - S) + 2)];
  const BAR_H = month ? 30 : 40, GAP = 6, PAD = 8;
  const popStyle = (r, rowIdx) => {
    const [a, b] = edges(r);
    // Under the bar; bars in the right part of the window hang it from their end.
    const right = (a - 1) / (2 * W) > 0.55;
    // The bottom two rows open it above the bar so the card edge does not cut it off.
    const above = allRows.length > 2 && rowIdx >= allRows.length - 2;
    const top = PAD + (r.lane - 1) * (BAR_H + GAP);
    return {
      ...(above ? { bottom: `calc(100% - ${top - 6}px)` } : { top: top + BAR_H + 6 }),
      ...(right ? { right: `${((2 * W + 1 - b) / (2 * W)) * 100}%` } : { left: `${((a - 1) / (2 * W)) * 100}%` }),
    };
  };

  useEffect(() => {
    if (!sel) return undefined;
    const onKey = (e) => { if (e.key === "Escape") setSel(null); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [sel]);

  // ── Agenda from the picked day to the end of the range: who comes in and goes
  // out, one line per client. Leaving one of our hotels and entering another the
  // same day is one Move. Who stays is left to the timeline.
  const perClient = (xs) => uniq(xs.map((r) => r.client)).sort().map((client) => {
    const mine = xs.filter((r) => r.client === client);
    return { client, ids: mine.map((r) => r.id), hotels: uniq(mine.map((r) => hotelOf[r.hotel].name)).join(", "), n: mine.reduce((s, r) => s + r.rooms, 0), e: Math.max(...mine.map((r) => r.e)) };
  });
  const agenda = [];
  let next = day;
  for (; agenda.length < PAGE * pages && next <= E; next++) {
    const inn = perClient(items.filter((r) => r.s === next)), out = perClient(items.filter((r) => r.e === next));
    const moving = new Set(inn.filter((g) => out.some((o) => o.client === g.client)).map((g) => g.client));
    const list = [
      ...inn.filter((g) => !moving.has(g.client)).map((g) => ({ kind: "In", g, sub: `${g.hotels} · ${t("until {date}", { date: dateTxt(g.e) })}` })),
      ...inn.filter((g) => moving.has(g.client)).map((g) => ({ kind: "Move", g, from: out.find((o) => o.client === g.client).hotels })),
      ...out.filter((g) => !moving.has(g.client)).map((g) => ({ kind: "Out", g, sub: g.hotels })),
    ];
    if (list.length) agenda.push({ n: next, list });
  }
  const hasMore = items.some((r) => (r.s >= next && r.s <= E) || (r.e >= next && r.e <= E));
  const tonight = items.filter((r) => r.s <= day && day < r.e).reduce((s, r) => s + r.rooms, 0);
  // A line in the agenda opens its booking on the timeline.
  const pickClient = (ids) => setSel(ids.find((id) => shown.some((r) => r.id === id)) ?? null);

  // ── Navigation: two weeks move a week at a time, a month a month.
  const move = (step) => {
    if (month) {
      const d = asDate(S);
      const first = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + step, 1) / DAY_MS;
      go({ view: "month", start: iso(first) }, { day: TODAY >= first && asDate(TODAY).getUTCMonth() === asDate(first).getUTCMonth() ? TODAY : first });
      return;
    }
    const s = S + step;
    go({ start: iso(s) }, { day: TODAY >= s && TODAY <= s + W - 1 ? TODAY : s });
  };
  const goToday = () => {
    if (TODAY >= S && TODAY <= E) { pickDay(TODAY); return; }
    go(viewParam(view), { day: TODAY });
  };
  const setView = (v) => { if (v !== view) go({ ...viewParam(v), start: iso(day) }, { day }); };

  const first = asDate(S), last = asDate(E);
  const title = first.getUTCMonth() === last.getUTCMonth()
    ? `${MONTH[L][first.getUTCMonth()]} ${first.getUTCFullYear()}`
    : `${MON[L][first.getUTCMonth()]} – ${MON[L][last.getUTCMonth()]} ${last.getUTCFullYear()}`;
  const at = (x) => `calc(var(--label-w) + (100% - var(--label-w)) * ${x} / ${W})`;
  const legend = [["house", "In-house"], ["soon", "Arriving"], ["over", "Checked out"]]
    .concat(shown.some((r) => r.tentative) ? [["tent", "Tentative"]] : []);

  return (
    <Page className="max-w-[1440px]">
      <div className={cn(
        "text-[14px] leading-[1.5] text-foreground",
        "[&_:is(button,a):focus-visible]:outline-2 [&_:is(button,a):focus-visible]:outline-offset-2 [&_:is(button,a):focus-visible]:outline-ring [&_:is(button,a):focus-visible]:outline-solid",
        loading && "opacity-60 transition-opacity duration-150",
      )}>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="m-0 text-[30px] leading-[1.1] font-semibold tracking-[-0.025em] tabular-nums phone:text-[26px]">{title}</h1>
            <div className="flex items-center gap-1">
              <button type="button" className={ICON_BTN} aria-label={t(month ? "Previous month" : "Previous week")} onClick={() => move(month ? -1 : -7)}>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M15 18l-6-6 6-6" /></svg>
              </button>
              <button type="button" className={ICON_BTN} aria-label={t(month ? "Next month" : "Next week")} onClick={() => move(month ? 1 : 7)}>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M9 6l6 6-6 6" /></svg>
              </button>
              <button type="button" onClick={goToday}
                className={cn(
                  "ml-1 h-[34px] phone:h-11 cursor-pointer rounded-full px-4 font-sans text-[13px] leading-[normal] font-semibold",
                  day === TODAY ? "border border-border bg-card text-muted-foreground" : "border-0 bg-primary text-primary-foreground",
                )}>
                {t("Today")}
              </button>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <ul className="m-0 flex list-none flex-wrap items-center gap-3.5 p-0 text-[12px]" aria-label={t("Legend")}>
              {legend.map(([k, label]) => (
                <li key={k} className="inline-flex items-center gap-1.5">
                  <span aria-hidden="true" className={cn("relative h-3 w-[18px] overflow-hidden rounded-[4px] before:absolute before:inset-y-0 before:left-0 before:w-[3px]", SWATCH[k])} />
                  {t(label)}
                </li>
              ))}
            </ul>
            <div className={SEG} role="group" aria-label={t("Rows")}>
              <button type="button" className={cn(SEG_BTN, !byClient && SEG_ON)} aria-pressed={!byClient} onClick={() => { setByClient(false); setSel(null); }}>{t("By hotel")}</button>
              <button type="button" className={cn(SEG_BTN, byClient && SEG_ON)} aria-pressed={byClient} onClick={() => { setByClient(true); setSel(null); }}>{t("By client")}</button>
            </div>
            <div className={SEG} role="group" aria-label={t("Range")}>
              <button type="button" className={cn(SEG_BTN, !month && SEG_ON)} aria-pressed={!month} onClick={() => setView("weeks")}>{t("2 weeks")}</button>
              <button type="button" className={cn(SEG_BTN, month && SEG_ON)} aria-pressed={month} onClick={() => setView("month")}>{t("Month")}</button>
            </div>
          </div>
        </div>

        {/* A month needs the full width, so its agenda moves under the timeline. */}
        <div className="mt-5 flex flex-wrap items-start gap-5">
          <section className={cn(CARD, "min-w-0", month ? "basis-full" : "flex-[999_1_760px]")} aria-label={t("Timeline")}>
            {/* Many hotels or a long month scroll inside the card, so the dates and
                the check-in chart stay on top and the row names stay on the left. */}
            <div className="max-h-[calc(100dvh-180px)] overflow-auto overscroll-contain [scrollbar-width:thin]">
              {/* The row-name column: narrower on a phone so more days show. */}
              <div className={cn("relative [--label-w:190px] phone:[--label-w:112px]", month ? "min-w-[1080px]" : "min-w-[960px] phone:min-w-[728px]")}>
                {sel && <div className="absolute inset-0 z-[5]" aria-hidden="true" onClick={() => setSel(null)} />}

                <div className={cn("sticky top-0 z-[4] grid border-b border-border bg-card", LABEL_COL)}>
                  <div className="sticky left-0 z-[5] flex flex-col justify-end gap-0.5 bg-card px-5 pb-4 phone:px-3">
                    <span className="text-[13px] font-semibold">{t("Check-ins")}</span>
                    <span className="text-[12px] text-muted-foreground phone:hidden">{t("Client per hotel, a day")}</span>
                    {peak > 0 && <span className="text-[12px] text-muted-foreground tabular-nums">{t("Peak {n}: {days}", { n: peak, days: peakDays })}</span>}
                  </div>
                  <div className={cn("grid gap-y-2.5 pt-3.5 pb-3", month ? "gap-x-[3px] px-1.5" : "gap-x-1.5 px-2.5")}
                    style={{ gridTemplateColumns: `repeat(${W}, minmax(0, 1fr))` }}>
                    {days.map((d) => {
                      const picked = d.n === day, isToday = d.n === TODAY;
                      return (
                        <button type="button" key={d.n} aria-pressed={picked} aria-label={d.aria} onClick={() => pickDay(d.n)}
                          className={cn(
                            "flex min-w-0 cursor-pointer flex-col items-center gap-0.5 border-0 [font:inherit]",
                            month ? "rounded-[10px] py-1.5" : "rounded-[14px] py-2",
                            picked ? "bg-primary text-primary-foreground"
                              : cn("bg-cal-tile hover:bg-secondary", isToday && "ring-[1.5px] ring-primary ring-inset", d.n < TODAY ? "text-muted-foreground" : "text-foreground"),
                          )}>
                          <span className={cn("font-medium", month ? "text-[10px]" : "text-[11px]", picked ? "opacity-80" : "text-muted-foreground")}>{d.dow}</span>
                          <span className={cn("leading-[1.1] font-semibold tabular-nums", month ? "text-[14px]" : "text-[20px]")}>{d.num}</span>
                        </button>
                      );
                    })}
                    {days.map((d) => {
                      const picked = d.n === day, top = d.count && d.count === peak;
                      return (
                        <button type="button" key={`c${d.n}`} onClick={() => pickDay(d.n)}
                          title={d.count ? d.who.join("\n") : t("No check-ins")}
                          aria-label={`${d.aria}, ${plural(d.count, "{n} check-in", "{n} check-ins")}`}
                          className="flex h-[52px] cursor-pointer flex-col items-center justify-end gap-1 border-0 bg-transparent p-0 [font:inherit]">
                          <span className={cn("text-[13px] leading-none tabular-nums", top ? "font-bold" : "font-semibold", picked || top ? "text-foreground" : "text-muted-foreground")}>{d.count || ""}</span>
                          <span className={cn("block w-[44%] max-w-[30px] rounded-t-[5px] rounded-b-[2px]", picked ? "bg-primary" : "bg-chart-bar")}
                            style={{ height: d.count ? Math.max(3, Math.round((28 * d.count) / peak)) : 0 }} />
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="relative">
                  {day >= S && day <= E && (
                    <div className="pointer-events-none absolute inset-y-0 bg-primary/6" aria-hidden="true"
                      style={{ left: at(day - S), width: `calc((100% - var(--label-w)) / ${W})` }} />
                  )}
                  {TODAY >= S && TODAY <= E && (
                    <div className="pointer-events-none absolute inset-y-0 z-0 -ml-px w-0.5 bg-primary" aria-hidden="true" style={{ left: at(TODAY - S + 0.5) }}>
                      <span className="absolute top-1.5 left-1/2 -translate-x-1/2 rounded-full bg-primary px-2 py-px text-[10px] font-bold tracking-[0.02em] whitespace-nowrap text-primary-foreground">{t("Today")}</span>
                    </div>
                  )}

                  {groups.map((g, gi) => (
                    <Fragment key={g.value}>
                      <div className={cn("bg-cal-tile pt-3.5 pb-2.5", gi > 0 && "border-t border-border")}>
                        <div className="sticky left-0 z-[3] flex w-max items-center gap-2 px-5 phone:px-3">
                          <span className="text-[13px] font-semibold">{g.label}</span>
                          <span className="rounded-full bg-card px-2 py-px text-[11px] font-semibold text-muted-foreground ring-1 ring-border ring-inset">{counted(g)}</span>
                        </div>
                      </div>
                      {g.rows.map((h) => {
                        const hit = h.bars.find((r) => r.id === sel);
                        return (
                          <div className={cn("grid border-t border-hairline", LABEL_COL)} key={h.key}>
                            <div className="sticky left-0 z-[3] flex min-w-0 flex-col justify-center border-r border-hairline bg-card px-5 phone:px-3">
                              {h.url ? (
                                <Link href={h.url} title={h.name}
                                  className="min-w-0 overflow-hidden text-[13px] font-medium text-ellipsis whitespace-nowrap text-foreground no-underline hover:underline hover:underline-offset-3 phone:-my-3 phone:py-3">
                                  {h.name}
                                </Link>
                              ) : (
                                <span title={h.name} className="min-w-0 overflow-hidden text-[13px] font-semibold text-ellipsis whitespace-nowrap">{h.name}</span>
                              )}
                              {h.route && (
                                <span className="flex flex-wrap items-center gap-x-1 text-[12px] text-muted-foreground">
                                  <span>{h.cls} ·</span>
                                  {h.route.map((c, i) => (
                                    <Fragment key={i}>
                                      {i > 0 && <span className="[&_svg]:mt-0 [&_svg]:size-3"><Icon d={ARROW} label={t("then")} /></span>}
                                      <span>{c}</span>
                                    </Fragment>
                                  ))}
                                </span>
                              )}
                            </div>
                            <div className="relative min-w-0">
                              <div className={cn("grid items-center gap-y-1.5 py-2", month ? "auto-rows-[30px]" : "auto-rows-[40px]")}
                                style={{ gridTemplateColumns: `repeat(${2 * W}, minmax(0, 1fr))` }}>
                                {h.bars.map((r) => {
                                  const [a, b] = edges(r);
                                  const name = byClient ? hotelOf[r.hotel].name : r.client;
                                  const aria = `${r.ref}, ${r.client}, ${hotelOf[r.hotel].name}, ${dateTxt(r.s)} ${t("to")} ${dateTxt(r.e)}, ${rooms(r.rooms)}${r.tentative ? ", " + t("tentative") : ""}`;
                                  return (
                                    <button type="button" key={r.id} title={aria} aria-label={aria} aria-expanded={sel === r.id}
                                      onClick={() => setSel(sel === r.id ? null : r.id)}
                                      className={cn(
                                        "relative z-1 box-border flex min-w-0 cursor-pointer flex-col justify-center overflow-hidden border-0 text-left whitespace-nowrap [font:inherit]",
                                        "before:absolute before:inset-y-0 before:left-0 before:w-[3px]",
                                        month ? "mx-px h-[30px] rounded-[7px] pr-1.5 pl-[9px]" : "mx-[3px] h-10 rounded-[9px] pr-2.5 pl-3",
                                        STAY[status(r)],
                                        sel === r.id && "outline-2 outline-offset-1 outline-foreground outline-solid",
                                      )}
                                      style={{ gridColumn: `${a} / ${b}`, gridRow: r.lane }}>
                                      <span className="block overflow-hidden text-[12px] leading-[1.3] font-semibold text-ellipsis">{name}</span>
                                      {!month && <span className="block overflow-hidden text-[11px] leading-[1.3] text-ellipsis tabular-nums opacity-80">{`CL ${r.ref} · ${rooms(r.rooms)}`}</span>}
                                    </button>
                                  );
                                })}
                              </div>
                              {hit && (
                                <div className="surface absolute z-[6] w-[280px] rounded-[14px] border border-border bg-popover text-left text-[13px] shadow-popover"
                                  role="dialog" aria-label={hit.ref} style={popStyle(hit, allRows.indexOf(h))}>
                                  <div className="flex items-start justify-between gap-3 pt-4 pr-3 pb-3 pl-4">
                                    <div><b className="block text-[14px] leading-[1.3] font-semibold">{hit.client}</b></div>
                                    <button type="button" className={cn(ICON_BTN, "size-8 border-0 bg-transparent")} aria-label={t("Close")} autoFocus onClick={() => setSel(null)}>
                                      <svg viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" d="M6 6l12 12M18 6L6 18" /></svg>
                                    </button>
                                  </div>
                                  <dl className="m-0 grid grid-cols-[64px_1fr] gap-x-3 gap-y-2 px-4 pt-0.5 pb-4 text-[13px] tabular-nums [&_dd]:m-0 [&_dd]:font-medium [&_dt]:text-muted-foreground">
                                    <dt>{t("CL No")}</dt><dd><Link className={cn("font-semibold text-foreground", LINK)} href={hit.url}>{hit.ref}</Link></dd>
                                    <dt>{t("Hotel")}</dt><dd>{hotelOf[hit.hotel].name}</dd>
                                    <dt>{t("Status")}</dt><dd><span className={hit.tentative ? TONE.ty : undefined}>{t(hit.tentative ? "Tentative" : "Definite")}</span></dd>
                                    <dt>{t("Stay")}</dt><dd>{`${dateTxt(hit.s)} ${t("to")} ${dateTxt(hit.e)}, ${nights(hit.e - hit.s)}`}</dd>
                                    <dt>{t("Rooms")}</dt><dd>{(hit.room_types ? hit.room_types + ", " : "") + rooms(hit.rooms)}</dd>
                                    <dt>{t("Invoice")}</dt>
                                    <dd>
                                      {hit.inv_number && <><Link className={cn("font-semibold text-foreground", LINK)} href={hit.inv_url}>{hit.inv_number}</Link>, </>}
                                      <span className={!hit.inv_number || hit.inv_open > 0 ? TONE.wt : undefined}>{invTxt(hit)}</span>
                                    </dd>
                                  </dl>
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </Fragment>
                  ))}
                  {!groups.length && <div className="px-6 py-14 text-center text-[13px] text-muted-foreground">{t("No bookings in these dates")}</div>}
                </div>
              </div>
            </div>
          </section>

          {/* Phones read the agenda first, then the timeline. */}
          <aside className={cn(CARD, "box-border max-w-full p-5 phone:order-first phone:p-4", month ? "basis-full" : "flex-[1_1_380px]")} aria-label={t("Agenda")}>
            <div className="flex items-baseline justify-between gap-2">
              <h2 className="m-0 text-[17px] leading-[1.3] font-semibold tracking-[-0.01em]">{t("Agenda")}</h2>
              <span className="text-[12px] text-muted-foreground tabular-nums">{t("{rooms} that night", { rooms: rooms(tonight) })}</span>
            </div>
            <p className="m-0 text-[12px] text-muted-foreground">
              {day === TODAY ? t("From today") : t("From {date}", { date: `${DAYNAME[L][dowOf(day)]} ${dateTxt(day)}` })}
            </p>
            {/* Beside the timeline there is room for one column; under it the days sit side by side. */}
            <div className="mt-3.5 grid grid-cols-[repeat(auto-fill,minmax(min(100%,320px),1fr))] items-start gap-2.5">
              {agenda.map((a) => {
                const on = a.n === day;
                const open = openDays.includes(a.n);
                const lines = open ? a.list : a.list.slice(0, PER_DAY);
                const hidden = a.list.length - PER_DAY;
                return (
                  <div key={a.n} className={cn("flex gap-3 rounded-2xl border py-3 pr-3 pl-2.5", on ? "border-border bg-cal-tile" : "border-hairline")}>
                    <div className={cn("flex h-12 w-11 flex-none flex-col items-center justify-center rounded-xl", on ? "bg-primary text-primary-foreground" : "bg-cal-tile")}>
                      <span className="text-[11px] font-medium">{DOW3[L][dowOf(a.n)]}</span>
                      <span className="text-[17px] leading-[1.1] font-semibold tabular-nums">{asDate(a.n).getUTCDate()}</span>
                    </div>
                    <div className="flex min-w-0 flex-1 flex-col gap-2.5">
                      {lines.map((i) => (
                        <button type="button" key={i.kind + i.g.client} onClick={() => pickClient(i.g.ids)}
                          className="grid cursor-pointer grid-cols-[46px_minmax(0,1fr)_auto] items-baseline gap-x-2.5 border-0 bg-transparent p-0 text-left text-inherit [font:inherit]">
                          <span className={cn("box-border w-[46px] rounded-full py-0.5 text-center text-[11px] font-semibold whitespace-nowrap", TAG[i.kind])}>{t(i.kind)}</span>
                          <span className="min-w-0">
                            <span className="block text-[13px] leading-[1.35] font-semibold">{i.g.client}</span>
                            {i.kind === "Move" ? (
                              <span className="mt-0.5 grid grid-cols-[14px_minmax(0,1fr)] gap-x-1.5 gap-y-0.5 text-[12px] leading-[1.4] text-muted-foreground">
                                <Icon d={OUT_ICON} label={t("from")} />
                                <span>{i.from}</span>
                                <Icon d={IN_ICON} label={t("moves to")} />
                                <span>{`${i.g.hotels} · ${t("until {date}", { date: dateTxt(i.g.e) })}`}</span>
                              </span>
                            ) : (
                              <span className="block text-[12px] leading-[1.4] text-muted-foreground">{i.sub}</span>
                            )}
                          </span>
                          <span className="text-[12px] whitespace-nowrap text-muted-foreground tabular-nums">{rooms(i.g.n)}</span>
                        </button>
                      ))}
                      {hidden > 0 && (
                        <button type="button" aria-expanded={open}
                          onClick={() => setOpenDays(open ? openDays.filter((x) => x !== a.n) : [...openDays, a.n])}
                          className={cn("cursor-pointer self-start border-0 bg-transparent p-0 font-sans text-[12px] leading-[normal] font-semibold text-foreground", LINK)}>
                          {open ? t("Show less") : t("+{n} more", { n: hidden })}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="flex flex-col items-center gap-2.5 pt-3.5 pb-1 text-center">
              {!hasMore && <span className="text-[12px] text-muted-foreground">{t("No more check-ins or check-outs until {date}", { date: dateTxt(E) })}</span>}
              <div className="flex justify-center gap-2">
                {hasMore && (
                  <button type="button" onClick={() => setPages(pages + 1)}
                    className="h-8 cursor-pointer rounded-full border border-border bg-transparent px-3.5 font-sans text-[13px] leading-[normal] font-medium text-foreground hover:bg-secondary">
                    {t("Show more")}
                  </button>
                )}
                {pages > 1 && (
                  <button type="button" onClick={() => setPages(1)}
                    className="h-8 cursor-pointer rounded-full border border-border bg-transparent px-3.5 font-sans text-[13px] leading-[normal] font-medium text-foreground hover:bg-secondary">
                    {t("Show less")}
                  </button>
                )}
              </div>
            </div>
          </aside>
        </div>
      </div>
    </Page>
  );
}
