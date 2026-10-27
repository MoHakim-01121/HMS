import { Fragment, useEffect, useRef, useState } from "react";
import { Link, router } from "@inertiajs/react";
import { cn } from "@/lib/utils";
import { useI18n } from "../../utils/i18n.jsx";
import Page from "../../components/shadcn/page.jsx";

// Calendar, as on the Record View HMS canvas ("Calendar (disetujui)"): every
// hotel with a booking in the range, grouped by city, one bar per booking from
// midday of check-in to midday of check-out. A bar opens a popup with the CL
// and its invoice; the panel beside the timeline lists who arrives, leaves and
// stays on the picked day. The server sends real dates; all layout is here.

// Weekday initials indexed by Date#getUTCDay() (0 = Sunday). Indonesian needs
// three letters because Senin/Selasa/Sabtu all start with S.
const DOW = { en: ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"], id: ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"] };
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
// Round icon button (week arrows, popup close).
const ICON_BTN = "grid size-9 flex-none cursor-pointer place-content-center rounded-full border-0 bg-transparent text-foreground hover:bg-secondary [&_svg]:size-4 [&_svg]:fill-none [&_svg]:stroke-current [&_svg]:stroke-[1.8]";
const SEG_BTN = "h-[30px] cursor-pointer rounded-full border-0 bg-transparent px-4 font-sans text-[13px] leading-[normal] font-medium text-muted-foreground";
const SEG_ON = "bg-card text-foreground shadow-pill";
const HOTEL_CELL = "sticky left-0 z-[2] flex min-w-0 items-center justify-between gap-2 border-r border-border bg-card pr-4 pl-5";
const CARD = "surface overflow-clip rounded-[20px] border border-border bg-card";
const LINK = "underline decoration-border underline-offset-3 hover:decoration-current";
// Status ink: open invoice warns, tentative is yellow, settled is quiet.
const TONE = { wt: "text-warning-text", ty: "text-tentative-text", mt: "text-muted-foreground" };

// Long In-house lists show the first eight; the rest open on request.
const CAP = 8;

// Dates travel as day numbers (days since 1970-01-01, UTC) so the bar maths is
// plain subtraction with no time zone in it.
const DAY_MS = 86400000;
const dn = (iso) => { const [y, m, d] = iso.split("-").map(Number); return Date.UTC(y, m - 1, d) / DAY_MS; };
const asDate = (n) => new Date(n * DAY_MS);
const iso = (n) => asDate(n).toISOString().slice(0, 10);
const fmtSar = (v) => Math.round(v).toLocaleString("en-US");

export default function Calendar({ view, start, end, today, cities = [], hotels = [], bookings = [] }) {
  const { t, locale } = useI18n();
  const L = locale === "id" ? "id" : "en";
  const S = dn(start), E = dn(end), TODAY = dn(today);
  const W = E - S + 1;
  const isWk = view !== "month";

  // The picked day and the open booking survive a trip to the server: a
  // navigation that wants them set leaves them in `carry`.
  const carry = useRef(null);
  const [day, setDay] = useState(TODAY >= S && TODAY <= E ? TODAY : S);
  const [sel, setSel] = useState(null);
  const [all, setAll] = useState(false);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    const c = carry.current;
    carry.current = null;
    setDay(c?.day ?? (TODAY >= S && TODAY <= E ? TODAY : S));
    setSel(c?.sel ?? null);
    setAll(false);
  }, [start, end, S, E, TODAY]);

  const go = (params, keep) => {
    carry.current = keep || null;
    router.get("/calendar/", params, {
      preserveState: true, preserveScroll: true, replace: true,
      onStart: () => setLoading(true), onFinish: () => setLoading(false),
    });
  };
  const viewParam = (v) => (v === "month" ? { view: "month" } : {});

  const dateTxt = (n) => { const d = asDate(n); return `${d.getUTCDate()} ${MON[L][d.getUTCMonth()]}`; };
  const dowOf = (n) => asDate(n).getUTCDay();
  const plural = (n, one, many) => t(n === 1 ? one : many, { n });
  const rooms = (n) => plural(n, "{n} room", "{n} rooms");
  const nights = (n) => plural(n, "{n} night", "{n} nights");
  const invTxt = (b) => (!b.inv_number ? t("Not invoiced") : b.inv_open > 0 ? t("{amount} SAR open", { amount: fmtSar(b.inv_open) }) : t("Paid"));

  const items = bookings.map((b) => ({ ...b, s: dn(b.check_in), e: dn(b.check_out) }));
  const hotelOf = Object.fromEntries(hotels.map((h) => [h.id, h]));

  // ── Timeline ──
  const days = [];
  for (let i = 0; i < W; i++) {
    const n = S + i;
    const d = asDate(n);
    // The first day of a month (and the window's first day) shows the month's name in place of the weekday.
    const monthMark = d.getUTCDate() === 1 || i === 0;
    days.push({
      n, num: d.getUTCDate(),
      dow: monthMark && isWk ? MON[L][d.getUTCMonth()] : DOW[L][d.getUTCDay()],
      mark: monthMark && isWk,
      aria: `${DAYNAME[L][d.getUTCDay()]} ${dateTxt(n)}`,
    });
  }

  // Grid column of a booking's edges: day i's midday sits on line 2i + 2.
  const edges = (r) => [Math.max(1, 2 * (r.s - S) + 2), Math.min(2 * W + 1, 2 * (r.e - S) + 2)];
  const rows = hotels.map((h) => {
    const shown = items.filter((r) => r.hotel === h.id && r.e > S && r.s <= E);
    const ends = [];
    shown.forEach((r) => {
      let lane = ends.findIndex((x) => r.s >= x);
      if (lane === -1) { lane = ends.length; ends.push(r.e); } else { ends[lane] = r.e; }
      r.lane = lane + 1;
    });
    return { ...h, shown };
  });
  const groups = cities
    .map((c) => ({ ...c, rows: rows.filter((h) => h.city === c.value && h.shown.length) }))
    .filter((g) => g.rows.length);
  const visibleRows = groups.flatMap((g) => g.rows);

  const popStyle = (r, hotelIdx) => {
    const [a, b] = edges(r);
    // Under the bar; bars in the right part of the window hang it from their end.
    const right = (a - 1) / (2 * W) > 0.55;
    // The bottom two hotels open it above the bar so the card edge does not cut it off.
    const above = visibleRows.length > 2 && hotelIdx >= visibleRows.length - 2;
    return {
      ...(above ? { bottom: `calc(100% - ${9 + (r.lane - 1) * 34 - 8}px)` } : { top: r.lane * 34 + 10 }),
      ...(right ? { right: `${((2 * W + 1 - b) / (2 * W)) * 100}%` } : { left: `${((a - 1) / (2 * W)) * 100}%` }),
    };
  };

  useEffect(() => {
    if (!sel) return undefined;
    const onKey = (e) => { if (e.key === "Escape") setSel(null); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [sel]);

  // ── Panel: the picked day ──
  const byName = (a, b) => a.client.localeCompare(b.client) || hotelOf[a.hotel].name.localeCompare(hotelOf[b.hotel].name);
  const ins = items.filter((r) => r.s === day).sort(byName);
  const outs = items.filter((r) => r.e === day).sort(byName);
  const house = items.filter((r) => r.s < day && day < r.e).sort(byName);
  const tonight = items.filter((r) => r.s <= day && day < r.e).reduce((n, r) => n + r.rooms, 0);
  const k = day - TODAY;
  const rel = k === 0 ? t("Today") : k === 1 ? t("Tomorrow") : k === -1 ? t("Yesterday")
    : k > 0 ? t("In {n} days", { n: k }) : t("{n} days ago", { n: -k });

  // A row opens its bar's popup; when the bar is outside the dates shown, move to the two weeks it starts in.
  const pickRow = (r) => {
    if (sel === r.id) { setSel(null); return; }
    if (!isWk || (r.e > S && r.s <= E)) { setSel(r.id); return; }
    go({ start: iso(r.s) }, { day, sel: r.id });
  };
  const sections = [
    ["Arriving", ins, "in"], ["Leaving", outs, "out"], ["In-house", house, "house"],
  ].map(([label, list, kind]) => {
    const capped = kind === "house";
    const cut = capped && !all && list.length > CAP;
    return { label, list: cut ? list.slice(0, CAP) : list, count: list.length, kind, more: capped && list.length > CAP, cut };
  });
  const sub = (r, kind) => `${hotelOf[r.hotel].name}, ${kind === "in" ? nights(r.e - r.s)
    : kind === "house" ? t("night {i} of {n}", { i: day - r.s + 1, n: r.e - r.s }) : t("checks out")}`;

  // ── Navigation ──
  // Moving a week takes the picked day along: today if it is in that week, else the week's first day.
  const move = (step) => {
    const s = S + step;
    go({ start: iso(s) }, { day: TODAY >= s && TODAY <= s + W - 1 ? TODAY : s });
  };
  const goToday = () => {
    if (TODAY >= S && TODAY <= E && (!isWk || TODAY - S < 7)) { setDay(TODAY); setSel(null); return; }
    go(viewParam(view), { day: TODAY });
  };
  const setView = (v) => { if (v !== view) go({ ...viewParam(v), start: iso(day) }, { day }); };
  const first = asDate(S);
  const rangeLabel = isWk ? `${dateTxt(S)} ${t("to")} ${dateTxt(E)}` : `${MONTH[L][first.getUTCMonth()]} ${first.getUTCFullYear()}`;
  const colStyle = { left: `calc(184px + (100% - 184px) * ${day - S} / ${W})`, width: `calc((100% - 184px) / ${W})` };

  const hotelIdx = (h) => visibleRows.indexOf(h);

  return (
    <Page>
      <div className={cn(
        "mx-auto max-w-[1440px] text-[14px] leading-[1.5] text-foreground",
        "[&_:is(button,a):focus-visible]:outline-2 [&_:is(button,a):focus-visible]:outline-offset-2 [&_:is(button,a):focus-visible]:outline-ring [&_:is(button,a):focus-visible]:outline-solid",
        loading && "opacity-60 transition-opacity duration-150",
      )}>
        <h1 className="m-0 text-[24px] leading-[1.15] font-semibold tracking-[-0.02em]">{t("Calendar")}</h1>

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-1">
            <span className="mr-2 min-w-[160px] text-[16px] font-semibold tracking-[-0.01em] tabular-nums">{rangeLabel}</span>
            {isWk && (
              <>
                <button type="button" className={ICON_BTN} aria-label={t("Previous week")} onClick={() => move(-7)}>
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M15 18l-6-6 6-6" /></svg>
                </button>
                <button type="button" className={ICON_BTN} aria-label={t("Next week")} onClick={() => move(7)}>
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M9 6l6 6-6 6" /></svg>
                </button>
              </>
            )}
            <button type="button" onClick={goToday}
              className="ml-1 h-9 cursor-pointer rounded-full border-0 bg-transparent px-3 font-sans text-[13px] leading-[normal] font-medium text-foreground hover:bg-secondary">
              {t("Today")}
            </button>
          </div>
          <div className="inline-flex gap-0.5 rounded-full bg-secondary p-[3px]" role="group" aria-label={t("Range")}>
            <button type="button" className={cn(SEG_BTN, isWk && SEG_ON)} aria-pressed={isWk} onClick={() => setView("weeks")}>{t("2 weeks")}</button>
            <button type="button" className={cn(SEG_BTN, !isWk && SEG_ON)} aria-pressed={!isWk} onClick={() => setView("month")}>{t("Month")}</button>
          </div>
        </div>

        {/* The panel sits beside the timeline from 1280px (1800px for a month,
            which needs ~24px a day), under it below that. */}
        <div className={cn("mt-4 grid grid-cols-[minmax(0,1fr)_320px] items-stretch gap-6 max-[1279px]:grid-cols-[minmax(0,1fr)]", !isWk && "max-[1799px]:grid-cols-[minmax(0,1fr)]")}>
          <section className={CARD} aria-label={t("Timeline")}>
            <div className={cn("overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden", isWk && "min-[1280px]:overflow-visible")}>
              <div className={cn("relative", isWk ? "min-w-[760px] min-[1280px]:min-w-0" : "min-w-[940px]")}>
                {sel && <div className="absolute inset-0 z-[5]" aria-hidden="true" onClick={() => setSel(null)} />}
                {day >= S && day <= E && <div className="pointer-events-none absolute top-0 bottom-0 bg-foreground/4" style={colStyle} aria-hidden="true" />}
                <div className="sticky top-0 z-[5] grid grid-cols-[184px_minmax(0,1fr)] border-b border-border bg-card">
                  <div className={HOTEL_CELL}><span className="flex-none text-[12px] text-muted-foreground tabular-nums">{t("Hotel")}</span></div>
                  <div className="grid" style={{ gridTemplateColumns: `repeat(${W}, minmax(0, 1fr))` }}>
                    {days.map((d) => {
                      const today = d.n === TODAY, past = d.n < TODAY;
                      return (
                        <button type="button" key={d.n} aria-pressed={d.n === day} aria-label={d.aria}
                          className="group/dh flex cursor-pointer flex-col items-center gap-0.5 border-0 bg-transparent pt-3 pb-2 text-foreground [font:inherit]"
                          onClick={() => { setDay(d.n); setSel(null); setAll(false); }}>
                          <span className={cn("text-[12px] text-muted-foreground", (d.mark || d.n === day) && "font-semibold text-foreground")}>{d.dow}</span>
                          <span className={cn(
                            "grid h-7 min-w-7 place-content-center rounded-full text-[13px] font-semibold tabular-nums group-hover/dh:bg-secondary",
                            !isWk && "h-[22px] min-w-[22px] text-[12px]",
                            past && "font-medium text-muted-foreground",
                            today && "bg-primary text-primary-foreground group-hover/dh:bg-primary",
                          )}>{d.num}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {groups.map((g, gi) => (
                  <Fragment key={g.value}>
                    <div className={cn("border-t border-border px-5 pt-4 pb-2 text-[12px] font-semibold text-muted-foreground", gi === 0 && "border-t-0")}>{t(g.label)}</div>
                    {g.rows.map((h, hi) => {
                      const hit = h.shown.find((r) => r.id === sel);
                      return (
                        <div className={cn("grid grid-cols-[184px_minmax(0,1fr)]", hi > 0 && "border-t border-hairline")} key={h.id}>
                          <div className={HOTEL_CELL}>
                            <Link href={h.url} title={h.name}
                              className="min-w-0 overflow-hidden text-[13px] font-medium text-ellipsis whitespace-nowrap text-foreground no-underline hover:underline hover:underline-offset-3">
                              {h.name}
                            </Link>
                          </div>
                          <div className="relative min-w-0">
                            <div className="box-border grid min-h-[46px] auto-rows-[28px] items-center gap-y-2 py-2" style={{ gridTemplateColumns: `repeat(${2 * W}, minmax(0, 1fr))` }}>
                              {h.shown.map((r) => {
                                const [a, b] = edges(r);
                                return (
                                  <button type="button" key={r.id}
                                    className={cn(
                                      "mx-0.5 box-border flex h-7 min-w-0 cursor-pointer items-center gap-2 overflow-hidden rounded-[7px] border-0 px-3 text-left font-sans text-[12px] leading-[normal] font-medium whitespace-nowrap",
                                      r.tentative ? "bg-booking-tentative text-on-warning hover:bg-booking-tentative-hover"
                                        : r.e <= TODAY ? "bg-secondary text-muted-foreground"
                                        : "bg-booking-definite text-white hover:bg-booking-definite-hover",
                                      sel === r.id && "outline-2 outline-offset-1 outline-foreground outline-solid",
                                    )}
                                    style={{ gridColumn: `${a} / ${b}`, gridRow: r.lane }}
                                    aria-expanded={sel === r.id}
                                    aria-label={`${r.ref}, ${r.client}, ${dateTxt(r.s)} ${t("to")} ${dateTxt(r.e)}, ${rooms(r.rooms)}${r.tentative ? ", " + t("tentative") : ""}`}
                                    onClick={() => setSel(sel === r.id ? null : r.id)}>
                                    <span className="min-w-0 overflow-hidden text-ellipsis">{r.client}</span>
                                    <span className={cn("ml-auto flex-none tabular-nums opacity-70", !isWk && "hidden")}>{r.rooms}</span>
                                  </button>
                                );
                              })}
                            </div>
                            {hit && (
                              <div className="surface absolute z-[6] w-[280px] rounded-[14px] border border-border bg-popover text-left text-[13px] shadow-popover"
                                role="dialog" aria-label={hit.ref} style={popStyle(hit, hotelIdx(h))}>
                                <div className="flex items-start justify-between gap-3 pt-4 pr-3 pb-3 pl-4">
                                  <div><b className="block text-[14px] leading-[1.3] font-semibold">{hit.client}</b></div>
                                  <button type="button" className={cn(ICON_BTN, "size-8")} aria-label={t("Close")} autoFocus onClick={() => setSel(null)}>
                                    <svg viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" d="M6 6l12 12M18 6L6 18" /></svg>
                                  </button>
                                </div>
                                <dl className="m-0 grid grid-cols-[64px_1fr] gap-x-3 gap-y-2 px-4 pt-0.5 pb-4 text-[13px] tabular-nums [&_dd]:m-0 [&_dd]:font-medium [&_dt]:text-muted-foreground">
                                  <dt>{t("CL No")}</dt><dd><Link className={cn("font-semibold text-foreground", LINK)} href={hit.url}>{hit.ref}</Link></dd>
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
          </section>

          {/* The panel takes the timeline's height exactly: its inner box is laid
              over the grid cell, so a long list never makes the row taller. The
              list scrolls with no scrollbar; a fade at the foot says there is more. */}
          <aside className={cn(CARD, "relative min-h-[320px] max-[1279px]:min-h-0", !isWk && "max-[1799px]:min-h-0")} aria-label={t("Selected day")}>
            <div className={cn("absolute inset-0 flex flex-col max-[1279px]:static", !isWk && "max-[1799px]:static")}>
              <div className="px-6 pt-6 pb-2">
                <h2 className="m-0 text-[20px] leading-[1.2] font-semibold tracking-[-0.02em]">{`${DAYNAME[L][dowOf(day)]}, ${dateTxt(day)}`}</h2>
                <p className="mt-1 mb-0 text-[13px] text-muted-foreground tabular-nums">{t("{when}, {rooms} tonight", { when: rel, rooms: rooms(tonight) })}</p>
              </div>
              <div className={cn("min-h-0 flex-1 overflow-y-auto pb-7 mask-b-from-[calc(100%-28px)] [scrollbar-width:none] max-[1279px]:mask-none [&::-webkit-scrollbar]:hidden", !isWk && "max-[1799px]:mask-none")}>
                {sections.map((s, si) => (
                  <div className={cn("pt-4 pb-1", si > 0 && "border-t border-hairline")} key={s.kind}>
                    <h3 className={cn("m-0 flex justify-between px-6 pt-0 pb-2 text-[13px] font-semibold", !s.count && "font-medium text-muted-foreground")}>
                      {t(s.label)}<span className="font-normal text-muted-foreground tabular-nums">{s.count}</span>
                    </h3>
                    {s.list.map((r) => {
                      const open = !r.tentative && !(r.inv_number && !(r.inv_open > 0));
                      return (
                        <button type="button" key={r.id} onClick={() => pickRow(r)}
                          className={cn(
                            "box-border grid w-full cursor-pointer grid-cols-[minmax(0,1fr)_auto] gap-x-3 border-0 bg-transparent px-6 py-2 text-left text-inherit [font:inherit]",
                            "hover:bg-[color:color-mix(in_oklch,var(--foreground)_3.5%,var(--card))]",
                            sel === r.id && "bg-[color:color-mix(in_oklch,var(--foreground)_3.5%,var(--card))]",
                          )}
                          aria-label={`${r.client}, ${hotelOf[r.hotel].name}, ${rooms(r.rooms)}, ${r.tentative ? t("tentative") : invTxt(r)}`}>
                          <span className="min-w-0">
                            <span className="block overflow-hidden text-[14px] font-medium text-ellipsis whitespace-nowrap">{r.client}</span>
                            <span className="block overflow-hidden text-[12px] text-ellipsis whitespace-nowrap text-muted-foreground">{sub(r, s.kind)}</span>
                          </span>
                          <span>
                            <span className="block text-right text-[13px] font-semibold tabular-nums">{rooms(r.rooms)}</span>
                            <span className={cn("block text-right text-[12px] font-medium whitespace-nowrap", TONE[r.tentative ? "ty" : open ? "wt" : "mt"])}>{r.tentative ? t("Tentative") : open ? invTxt(r) : ""}</span>
                          </span>
                        </button>
                      );
                    })}
                    {s.more && (
                      <button type="button" onClick={() => setAll(!all)}
                        className={cn("mt-0.5 mb-1 w-full cursor-pointer border-0 bg-transparent px-6 py-2 text-left font-sans text-[13px] leading-[normal] font-medium text-foreground", LINK)}>
                        {s.cut ? t("Show all {n}", { n: s.count }) : t("Show fewer")}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </aside>
        </div>
      </div>
    </Page>
  );
}
