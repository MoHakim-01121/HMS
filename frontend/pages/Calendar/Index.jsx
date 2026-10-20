import { Fragment, useEffect, useRef, useState } from "react";
import { Link, router } from "@inertiajs/react";
import { useI18n } from "../../utils/i18n.jsx";
import "../../styles/calendar.css";

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
  }, [start, end]);

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
      wCls: "w" + (monthMark && isWk ? " mn" : ""),
      aria: `${DAYNAME[L][d.getUTCDay()]} ${dateTxt(n)}`,
      cls: "cal-dh" + (isWk ? "" : " mo") + (n === TODAY ? " today" : n < TODAY ? " past" : "") + (n === day ? " pick" : ""),
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
    <div className="page shadcn-root">
      <div className={"cal-main" + (loading ? " cal-loading" : "")}>
        <h1>{t("Calendar")}</h1>

        <div className="cal-top">
          <div className="cal-nv">
            <span className="cal-rng">{rangeLabel}</span>
            {isWk && (
              <>
                <button type="button" className="cal-ib" aria-label={t("Previous week")} onClick={() => move(-7)}>
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M15 18l-6-6 6-6" /></svg>
                </button>
                <button type="button" className="cal-ib" aria-label={t("Next week")} onClick={() => move(7)}>
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M9 6l6 6-6 6" /></svg>
                </button>
              </>
            )}
            <button type="button" className="cal-txt" onClick={goToday}>{t("Today")}</button>
          </div>
          <div className="cal-seg" role="group" aria-label={t("Range")}>
            <button type="button" className={isWk ? "on" : ""} aria-pressed={isWk} onClick={() => setView("weeks")}>{t("2 weeks")}</button>
            <button type="button" className={isWk ? "" : "on"} aria-pressed={!isWk} onClick={() => setView("month")}>{t("Month")}</button>
          </div>
        </div>

        <div className={"cal-lay" + (isWk ? "" : " mo")}>
          <section className="cal-card" aria-label={t("Timeline")}>
            <div className={"cal-tl" + (isWk ? "" : " mo")}>
              <div className={"cal-occ" + (isWk ? "" : " mo")}>
                {sel && <div className="cal-scrim" aria-hidden="true" onClick={() => setSel(null)} />}
                {day >= S && day <= E && <div className="cal-col" style={colStyle} aria-hidden="true" />}
                <div className="cal-row head">
                  <div className="cal-hc"><span className="c">{t("Hotel")}</span></div>
                  <div className="cal-days" style={{ gridTemplateColumns: `repeat(${W}, minmax(0, 1fr))` }}>
                    {days.map((d) => (
                      <button type="button" key={d.n} className={d.cls} aria-pressed={d.n === day} aria-label={d.aria}
                        onClick={() => { setDay(d.n); setSel(null); setAll(false); }}>
                        <span className={d.wCls}>{d.dow}</span><span className="d">{d.num}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {groups.map((g) => (
                  <Fragment key={g.value}>
                    <div className="cal-city">{t(g.label)}</div>
                    {g.rows.map((h) => {
                      const hit = h.shown.find((r) => r.id === sel);
                      return (
                        <div className="cal-row ht" key={h.id}>
                          <div className="cal-hc"><Link href={h.url} title={h.name}>{h.name}</Link></div>
                          <div className="cal-lw">
                            <div className="cal-lanes" style={{ gridTemplateColumns: `repeat(${2 * W}, minmax(0, 1fr))` }}>
                              {h.shown.map((r) => {
                                const [a, b] = edges(r);
                                return (
                                  <button type="button" key={r.id}
                                    className={"cal-bar " + (r.tentative ? "ten" : "def") + (r.e <= TODAY ? " past" : "") + (isWk ? "" : " mo") + (sel === r.id ? " on" : "")}
                                    style={{ gridColumn: `${a} / ${b}`, gridRow: r.lane }}
                                    aria-expanded={sel === r.id}
                                    aria-label={`${r.ref}, ${r.client}, ${dateTxt(r.s)} ${t("to")} ${dateTxt(r.e)}, ${rooms(r.rooms)}${r.tentative ? ", " + t("tentative") : ""}`}
                                    onClick={() => setSel(sel === r.id ? null : r.id)}>
                                    <span className="t">{r.client}</span><span className="k">{r.rooms}</span>
                                  </button>
                                );
                              })}
                            </div>
                            {hit && (
                              <div className="cal-pop" role="dialog" aria-label={hit.ref} style={popStyle(hit, hotelIdx(h))}>
                                <div className="cal-pop-h">
                                  <div><b>{hit.client}</b></div>
                                  <button type="button" className="cal-ib" style={{ width: 32, height: 32 }} aria-label={t("Close")} autoFocus onClick={() => setSel(null)}>
                                    <svg viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" d="M6 6l12 12M18 6L6 18" /></svg>
                                  </button>
                                </div>
                                <dl>
                                  <dt>{t("CL No")}</dt><dd><Link className="lk" href={hit.url}>{hit.ref}</Link></dd>
                                  <dt>{t("Status")}</dt><dd><span className={hit.tentative ? "ty" : ""}>{t(hit.tentative ? "Tentative" : "Definite")}</span></dd>
                                  <dt>{t("Stay")}</dt><dd>{`${dateTxt(hit.s)} ${t("to")} ${dateTxt(hit.e)}, ${nights(hit.e - hit.s)}`}</dd>
                                  <dt>{t("Rooms")}</dt><dd>{(hit.room_types ? hit.room_types + ", " : "") + rooms(hit.rooms)}</dd>
                                  <dt>{t("Invoice")}</dt>
                                  <dd>
                                    {hit.inv_number && <><Link className="lk" href={hit.inv_url}>{hit.inv_number}</Link>, </>}
                                    <span className={!hit.inv_number || hit.inv_open > 0 ? "wt" : ""}>{invTxt(hit)}</span>
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
                {!groups.length && <div className="cal-empty">{t("No bookings in these dates")}</div>}
              </div>
            </div>
          </section>

          <aside className="cal-pn cal-card" aria-label={t("Selected day")}>
            <div className="cal-pin">
              <div className="cal-ph">
                <h2>{`${DAYNAME[L][dowOf(day)]}, ${dateTxt(day)}`}</h2>
                <p>{t("{when}, {rooms} tonight", { when: rel, rooms: rooms(tonight) })}</p>
              </div>
              <div className="cal-pb">
                {sections.map((s) => (
                  <div className="cal-sec" key={s.kind}>
                    <h3 className={s.count ? "" : "empty"}>{t(s.label)}<span>{s.count}</span></h3>
                    {s.list.map((r) => {
                      const open = !r.tentative && !(r.inv_number && !(r.inv_open > 0));
                      return (
                        <button type="button" key={r.id} className={"cal-it" + (sel === r.id ? " on" : "")} onClick={() => pickRow(r)}
                          aria-label={`${r.client}, ${hotelOf[r.hotel].name}, ${rooms(r.rooms)}, ${r.tentative ? t("tentative") : invTxt(r)}`}>
                          <span style={{ minWidth: 0 }}><span className="nm">{r.client}</span><span className="sb">{sub(r, s.kind)}</span></span>
                          <span>
                            <span className="rm">{rooms(r.rooms)}</span>
                            <span className={"st " + (r.tentative ? "ty" : open ? "wt" : "mt")}>{r.tentative ? t("Tentative") : open ? invTxt(r) : ""}</span>
                          </span>
                        </button>
                      );
                    })}
                    {s.more && (
                      <button type="button" className="cal-more" onClick={() => setAll(!all)}>
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
    </div>
  );
}
