import { useState } from "react";
import { Link } from "@inertiajs/react";

// Day-count–dependent grid CSS (incl. mobile) injected per render, ported from calendar.html.
function gridCss(days) {
  return `
.cal-page { padding:24px 20px 64px; max-width:1140px; margin:0 auto; }
.cal-topbar { display:flex; align-items:center; justify-content:space-between; margin-bottom:16px; gap:12px; flex-wrap:wrap; }
.cal-topbar-left { display:flex; align-items:center; gap:16px; }
.cal-topbar-right { display:flex; align-items:center; gap:16px; flex-wrap:wrap; }
.cal-nav { display:flex; align-items:center; gap:4px; }
.cal-nav a { display:inline-flex; align-items:center; justify-content:center; width:30px; height:30px; border-radius:var(--r); border:1px solid var(--border); color:var(--text-2); text-decoration:none; transition:background .12s,color .12s,border-color .12s; }
.cal-nav a:hover { background:var(--surface-2); color:var(--text); border-color:var(--border-2); }
.cal-month { font-size:17px; font-weight:700; color:var(--text); min-width:148px; text-align:center; letter-spacing:-.2px; }
.cal-count { font-size:12px; color:var(--text-3); font-weight:500; }
.cal-legend { display:flex; gap:14px; align-items:center; }
.legend-item { display:flex; align-items:center; gap:5px; font-size:11px; color:var(--text-2); }
.legend-dot { width:8px; height:8px; border-radius:2px; flex-shrink:0; }
.cal-summary { display:flex; gap:6px; margin-bottom:14px; flex-wrap:wrap; }
.sum-pill { display:inline-flex; align-items:center; gap:5px; padding:4px 11px; border-radius:var(--r-full); font-size:11px; font-weight:500; background:var(--surface); border:1px solid var(--border); color:var(--text-2); }
.sum-pill .sum-val { font-weight:700; color:var(--text); }
.sum-pill.red { background:var(--red-muted); border-color:rgba(229,83,75,.3); color:var(--red); }
.sum-pill.green { background:var(--green-muted); border-color:rgba(38,194,129,.3); color:var(--green); }
.sum-pill.blue { background:var(--accent-muted); border-color:rgba(94,106,210,.3); color:var(--accent-2); }
.cal-card { background:var(--surface); border:1px solid var(--border-2); border-radius:var(--r-xl); overflow:hidden; box-shadow:var(--shadow-md); }
.cal-grid-template { display:grid; grid-template-columns:140px repeat(${days},1fr); width:100%; }
.cal-hotel-th { padding:8px 12px; font-size:10px; font-weight:600; color:var(--text-3); text-transform:uppercase; letter-spacing:.5px; border-right:1px solid var(--border); background:var(--surface); position:sticky; left:0; z-index:2; }
.cal-day-th { padding:8px 0; font-size:10px; font-weight:600; color:var(--text-2); text-align:center; border-right:1px solid var(--border); background:var(--surface); line-height:1; }
.cal-day-th.today { color:var(--accent-2); background:var(--accent-muted); font-weight:700; }
.cal-row { display:grid; grid-template-columns:140px repeat(${days},1fr); grid-template-rows:0 1fr; border-top:1px solid var(--border); background:var(--surface); width:100%; position:relative; }
.cal-hotel-name { grid-column:1; grid-row:1 / span 2; padding:0 12px; font-size:11px; font-weight:500; color:var(--text); display:flex; align-items:center; border-right:1px solid var(--border); position:sticky; left:0; background:var(--surface); z-index:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.cal-cell { border-right:1px solid var(--border); }
.cal-cell.today-col { background:rgba(94,106,210,.04); }
.cal-blocks { grid-column:2 / -1; display:grid; grid-template-columns:repeat(${days},1fr); align-items:center; padding:8px 0; position:relative; min-height:46px; }
.cal-block { grid-row:1; height:28px; border-radius:var(--r); display:flex; align-items:center; padding:0 7px; font-size:10px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; text-decoration:none; transition:filter .12s,transform .1s; margin:0 1px; min-width:0; }
.cal-block:hover { filter:brightness(1.15); transform:translateY(-1px); z-index:5; }
.block-blue { background:#7B87E8; color:#fff; } .block-yellow { background:#F0A420; color:#fff; }
.block-red { background:#E85555; color:#fff; } .block-green { background:#26C281; color:#fff; }
.cal-today-bg { grid-row:1; align-self:stretch; background:rgba(94,106,210,.07); pointer-events:none; z-index:0; margin:-8px 0; }
.cal-tooltip { position:fixed; background:var(--surface); border:1px solid var(--border-2); border-radius:var(--r-xl); z-index:var(--z-overlay); pointer-events:none; min-width:230px; max-width:290px; box-shadow:var(--shadow-xl); overflow:hidden; }
.tt-head { padding:12px 14px 10px; border-bottom:1px solid var(--border); }
.tt-guest { font-size:13px; font-weight:700; color:var(--text); line-height:1.3; }
.tt-body { padding:10px 14px 12px; display:grid; grid-template-columns:52px 1fr; gap:5px 8px; align-items:baseline; }
.tt-label { font-size:10px; color:var(--text-3); font-weight:600; text-transform:uppercase; letter-spacing:.4px; }
.tt-val { font-size:12px; color:var(--text); font-weight:500; }
.tt-inv-section { border-top:1px solid var(--border); padding:8px 14px 11px; display:grid; grid-template-columns:52px 1fr; gap:5px 8px; align-items:baseline; }
.tt-inv-link { font-size:12px; font-weight:600; color:var(--accent-2); text-decoration:none; }
.tt-sisa-val { font-size:12px; font-weight:700; }
@media (max-width:600px){
  .cal-page { padding:10px 0 80px; }
  .cal-topbar { padding:0 12px; flex-wrap:nowrap; margin-bottom:10px; }
  .cal-topbar-right { gap:8px; } .cal-legend, .cal-count { display:none; }
  .cal-month { font-size:15px; min-width:110px; } .sum-pill { font-size:10px; padding:3px 8px; }
  .cal-card { border-radius:0; border-left:none; border-right:none; }
  .cal-scroll-wrap { background:var(--surface); overflow-x:auto; -webkit-overflow-scrolling:touch; }
  .cal-grid-template { grid-template-columns:72px repeat(${days},minmax(30px,1fr)); min-width:calc(72px + ${days} * 30px); }
  .cal-row { grid-template-columns:72px repeat(${days},minmax(30px,1fr)); min-width:calc(72px + ${days} * 30px); }
  .cal-hotel-th { font-size:9px; padding:6px 8px; } .cal-hotel-name { font-size:10px; padding:0 6px; min-height:0; }
  .cal-day-th { padding:6px 0; font-size:9px; }
  .cal-blocks { grid-column:2 / -1; grid-template-columns:repeat(${days},minmax(30px,1fr)); min-height:38px; padding:6px 0; }
  .cal-block { font-size:9px; height:22px; padding:0 4px; border-radius:3px; }
  .cal-tooltip { position:fixed; bottom:80px; left:12px; right:12px; top:auto; max-width:100%; min-width:0; }
}`;
}

function countdown(checkin) {
  const ci = new Date(checkin);
  const now = new Date(); now.setHours(0, 0, 0, 0);
  const diff = Math.round((ci - now) / 86400000);
  if (diff === 0) return { text: "Hari ini", color: "var(--green)" };
  if (diff > 0) return { text: `${diff} hari lagi`, color: diff <= 3 ? "var(--yellow)" : "" };
  return { text: `${Math.abs(diff)} hari lalu`, color: "var(--text-3)" };
}

export default function Calendar(props) {
  const { year, month, month_name, days, today_day, hotels, prev_year, prev_month, next_year, next_month,
    total_reservations, checkins_today, checkouts_today, tentative_count, active_today } = props;
  const [tip, setTip] = useState(null); // { res, x, y }

  const show = (e, res) => setTip({ res, x: e.clientX, y: e.clientY });
  const move = (e) => setTip((t) => (t ? { ...t, x: e.clientX, y: e.clientY } : t));
  const hide = () => setTip(null);

  let tx = 0, ty = 0;
  if (tip) {
    tx = tip.x + 14; ty = tip.y + 14;
    if (tx + 200 > window.innerWidth) tx = tip.x - 210;
    if (ty + 140 > window.innerHeight) ty = tip.y - 150;
  }
  const cd = tip?.res.check_in ? countdown(tip.res.check_in) : null;

  return (
    <div className="cal-page">
      <style dangerouslySetInnerHTML={{ __html: gridCss(days.length) }} />

      <Link href="/" className="page-back">
        <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2.2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>Kembali
      </Link>

      <div className="cal-topbar">
        <div className="cal-topbar-left">
          <div className="cal-nav">
            <Link href={`/calendar/?year=${prev_year}&month=${prev_month}`} title="Bulan sebelumnya">
              <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
            </Link>
            <span className="cal-month">{month_name} {year}</span>
            <Link href={`/calendar/?year=${next_year}&month=${next_month}`} title="Bulan berikutnya">
              <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
            </Link>
          </div>
          <span className="cal-count">{total_reservations} reservasi</span>
        </div>
        <div className="cal-topbar-right">
          {today_day && active_today > 0 && <div className="sum-pill blue">Aktif <span className="sum-val">{active_today}</span></div>}
          {today_day && checkins_today > 0 && <div className="sum-pill green">CI <span className="sum-val">{checkins_today}</span></div>}
          {today_day && checkouts_today > 0 && <div className="sum-pill">CO <span className="sum-val">{checkouts_today}</span></div>}
          {today_day && tentative_count > 0 && <div className="sum-pill red">Tentative <span className="sum-val">{tentative_count}</span></div>}
          <div className="cal-legend">
            <div className="legend-item"><div className="legend-dot" style={{ background: "var(--accent-2)" }}></div>Definite</div>
            <div className="legend-item"><div className="legend-dot" style={{ background: "var(--yellow)" }}></div>Tentative</div>
            <div className="legend-item"><div className="legend-dot" style={{ background: "var(--red)" }}></div>Cancelled</div>
          </div>
        </div>
      </div>

      {hotels.length ? (
        <div className="cal-card">
          <div className="cal-scroll-wrap">
            <div className="cal-grid-template" style={{ borderBottom: "1px solid var(--border)" }}>
              <div className="cal-hotel-th">Hotel</div>
              {days.map((d) => <div key={d} className={"cal-day-th" + (d === today_day ? " today" : "")}>{d}</div>)}
            </div>

            {hotels.map((hotel, hi) => (
              <div className="cal-row" key={hi}>
                <div className="cal-hotel-name" title={hotel.name}>{hotel.name}</div>
                {days.map((d) => <div key={d} className={"cal-cell" + (d === today_day ? " today-col" : "")}></div>)}
                <div className="cal-blocks">
                  {today_day && <div className="cal-today-bg" style={{ gridColumn: `${today_day} / ${today_day + 1}` }}></div>}
                  {hotel.reservations.map((res, ri) => (
                    <a key={ri} href={res.url} className={`cal-block block-${res.color}`}
                      style={{ gridColumn: `${res.start} / ${res.end + 1}` }}
                      onMouseEnter={(e) => show(e, res)} onMouseMove={move} onMouseLeave={hide}>
                      {res.guest}
                    </a>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="card" style={{ marginTop: 0 }}>
          <div className="empty">
            <svg width="36" height="36" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24" className="empty-icon"><path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" /></svg>
            <div className="empty-title">Tidak ada reservasi</div>
            <div className="empty-sub">{month_name} {year}</div>
          </div>
        </div>
      )}

      {tip && (
        <div className="cal-tooltip" style={{ display: "block", left: tx, top: ty }}>
          <div className="tt-head"><div className="tt-guest">{tip.res.guest}</div></div>
          <div className="tt-body">
            <span className="tt-label">Status</span><span className="tt-val">{tip.res.status}</span>
            <span className="tt-label">CL No</span><span className="tt-val">{tip.res.ref}</span>
            <span className="tt-label">CI/CO</span><span className="tt-val">{tip.res.start} – {tip.res.end}</span>
            <span className="tt-label">Check-in</span><span className="tt-val" style={{ color: cd?.color }}>{cd?.text}</span>
            <span className="tt-label">Malam</span><span className="tt-val">{tip.res.nights} malam</span>
            <span className="tt-label">Total</span><span className="tt-val">{tip.res.total}</span>
          </div>
          {tip.res.inv_number && (
            <div className="tt-inv-section">
              <span className="tt-label">Invoice</span><a className="tt-inv-link" href={tip.res.inv_url || "#"}>{tip.res.inv_number}</a>
              <span className="tt-label">Sisa</span>
              <span className="tt-sisa-val" style={{ color: (tip.res.inv_remaining && tip.res.inv_remaining !== "0 SAR") ? "var(--red)" : "var(--green)" }}>{tip.res.inv_remaining || "—"}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
