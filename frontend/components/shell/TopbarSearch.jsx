import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { useI18n } from "../../utils/i18n.jsx";
import { navPages } from "./nav.jsx";
import { usePresence } from "./usePresence.js";

const RECENT_KEY = "hms.search.recent";

const TYPES = [
  ["CL", "Confirmation letters", "/cl/"],
  ["INV", "Invoices", "/invoice/"],
  ["PAY", "Payments", "/finance/payments/"],
  ["CLIENT", "Clients", "/clients/"],
  ["HOTEL", "Hotels", "/hotels/"],
];

// One search request. A dropped connection (the dev server reloading, a
// network blip) is retried once; a reply that is not JSON means the session
// ended and the server answered with the sign-in page.
async function searchOnce(query) {
  const url = "/search/?q=" + encodeURIComponent(query);
  for (let attempt = 0; ; attempt++) {
    let res;
    try {
      res = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
    } catch (e) {
      if (attempt === 0) { await new Promise((r) => setTimeout(r, 600)); continue; }
      throw Object.assign(new Error("network"), { reason: "network" });
    }
    const type = res.headers.get("content-type") || "";
    if (res.redirected || (res.ok && !type.includes("json"))) throw Object.assign(new Error("signed out"), { reason: "auth" });
    if (!res.ok) throw Object.assign(new Error(`HTTP ${res.status}`), { reason: "http", status: res.status });
    return res.json();
  }
}

function readRecent() {
  try {
    const v = JSON.parse(window.localStorage.getItem(RECENT_KEY) || "[]");
    return Array.isArray(v) ? v : [];
  } catch { return []; }
}

function remember(row) {
  if (!row.url || row.kind === "page") return;
  const keep = readRecent().filter((r) => r.url !== row.url);
  const next = [{ num: row.num || "", name: row.name, url: row.url, at: Date.now() }, ...keep].slice(0, 3);
  try { window.localStorage.setItem(RECENT_KEY, JSON.stringify(next)); } catch { /* storage blocked */ }
}

function ago(at, t) {
  const s = Math.floor((Date.now() - at) / 1000);
  if (s < 3600) return t("{m} min ago", { m: Math.max(1, Math.floor(s / 60)) });
  const d = new Date(at), now = new Date();
  if (d.toDateString() === now.toDateString()) return t("Today");
  const y = new Date(now); y.setDate(now.getDate() - 1);
  if (d.toDateString() === y.toDateString()) return t("Yesterday");
  return t("{d} days ago", { d: Math.max(2, Math.floor(s / 86400)) });
}

// Split `text` around the first match of `q` for a <mark>.
function Hit({ text, q }) {
  const s = text || "";
  const i = q ? s.toLowerCase().indexOf(q.toLowerCase()) : -1;
  if (i < 0) return s;
  return <>{s.slice(0, i)}<mark>{s.slice(i, i + q.length)}</mark>{s.slice(i + q.length)}</>;
}

// Inline topbar search of Shell A: the field widens on focus and the results
// open under it — recent records before typing, then
// matches grouped by kind (three each) plus pages of the app.
const TopbarSearch = forwardRef(function TopbarSearch({ perms, branchName }, ref) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [act, setAct] = useState(-1);
  const [state, setState] = useState({ kind: "idle" });
  const wrap = useRef(null);
  const input = useRef(null);
  const timer = useRef(null);

  useImperativeHandle(ref, () => ({ focus: () => { input.current?.focus(); setOpen(true); } }), []);

  // The query clears after the panel has faded out, so its content does not
  // swap to "Recent" mid-animation.
  const clearLater = () => setTimeout(() => setQ(""), 160);
  const close = () => { setOpen(false); setAct(-1); input.current?.blur(); clearLater(); };

  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => { if (wrap.current && !wrap.current.contains(e.target)) { setOpen(false); setAct(-1); clearLater(); } };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const query = q.trim();
  useEffect(() => {
    clearTimeout(timer.current);
    if (query.length < 2) { setState({ kind: "idle" }); return; }
    setState((s) => (s.kind === "results" ? s : { kind: "loading" }));
    timer.current = setTimeout(async () => {
      try {
        const data = await searchOnce(query);
        setState({ kind: "results", q: query, data: data.results || [] });
      } catch (e) {
        setState({ kind: "error", reason: e.reason, status: e.status });
      }
    }, 200);
    return () => clearTimeout(timer.current);
  }, [query]);

  const groups = useMemo(() => {
    if (!query) {
      const recent = readRecent().map((r) => ({ ...r, kind: "recent", meta: ago(r.at, t) }));
      return recent.length ? [{ title: t("Recent"), rows: recent }] : [];
    }
    if (state.kind !== "results") return [];
    const out = [];
    for (const [type, title, list] of TYPES) {
      const hits = state.data.filter((r) => r.type === type);
      if (!hits.length) continue;
      out.push({
        title: t(title),
        more: hits.length > 3 ? { label: t("See all {kind}", { kind: t(title).toLowerCase() }), url: `${list}?q=${encodeURIComponent(query)}` } : null,
        rows: hits.slice(0, 3).map((r) => ({ kind: type, num: r.num || "", name: r.name || r.sub || r.label, meta: r.meta || "", url: r.url })),
      });
    }
    const pages = navPages(perms).filter((p) => t(p.label).toLowerCase().includes(query.toLowerCase()));
    if (pages.length) out.push({ title: t("Pages"), rows: pages.slice(0, 3).map((p) => ({ kind: "page", num: "", name: t(p.label), meta: "", url: p.href })) });
    return out;
  }, [query, state, perms, t]);

  const flat = groups.flatMap((g) => g.rows);
  const go = (row) => { remember(row); close(); router.visit(row.url); };

  const onKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setAct(flat.length ? (act + 1) % flat.length : -1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setAct(flat.length ? (act <= 0 ? flat.length - 1 : act - 1) : -1); }
    else if (e.key === "Enter") { e.preventDefault(); const row = flat[act < 0 ? 0 : act]; if (row) go(row); }
    else if (e.key === "Escape") { e.preventDefault(); close(); }
  };

  const noHits = query.length >= 2 && state.kind === "results" && groups.length === 0;
  const hasPanel = open && (groups.length > 0 || noHits || (query.length >= 2 && state.kind !== "results"));
  const [panelShown, panelClosing] = usePresence(hasPanel);
  let idx = 0;

  return (
    <div className={"ks-ts" + (open ? " open" : "")} ref={wrap}>
      <label className="ks-tsi" title={open ? undefined : t("Search")}>
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
        <input ref={input} type="text" placeholder={t("Search CL, invoice, client, hotel")} aria-label={t("Search")}
          autoComplete="off" value={q} role="combobox" aria-expanded={open} aria-controls="ks-sres"
          onFocus={() => setOpen(true)} onClick={() => setOpen(true)}
          onChange={(e) => { setQ(e.target.value); setAct(-1); setOpen(true); }} onKeyDown={onKey} />
        {q && (
          <button type="button" className="ks-sx" aria-label={t("Clear search")} onClick={() => { setQ(""); setAct(-1); input.current?.focus(); }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        )}
      </label>
      {panelShown && (
        <div className={"ks-sp" + (panelClosing ? " is-closing" : "")} role="dialog" aria-label={t("Search results")}>
          <div className="ks-sbody" id="ks-sres" role="listbox" aria-label={t("Results")}>
            {noHits && (
              <div className="ks-sempty">
                <b>{t("No match for “{q}” in {branch}", { q: query, branch: branchName || "" })}</b>
                <p>{t("Search looks at CL, invoices, payments, clients, hotels and pages of this branch. Check the spelling, or switch branch to search another.")}</p>
              </div>
            )}
            {state.kind === "loading" && !groups.length && <div className="ks-sload">{t("Searching…")}</div>}
            {state.kind === "error" && (
              <div className="ks-sload" role="alert">
                {state.reason === "auth" ? <>{t("Your session has ended.")} <a href="/login/">{t("Sign in again")}</a></>
                  : state.reason === "network" ? t("Can't reach the server. Check the connection and try again.")
                  : t("Search failed (error {code}). Try again.", { code: state.status || "?" })}
              </div>
            )}
            {groups.map((g) => (
              <div role="group" aria-label={g.title} key={g.title}>
                <div className="ks-sg">{g.title}</div>
                {g.rows.map((r) => {
                  const me = idx++;
                  const numHit = !!(query && r.num && r.num.toLowerCase().includes(query.toLowerCase()));
                  return (
                    <a key={r.url + me} href={r.url} className={"ks-sr" + (me === act ? " on" : "")} role="option" aria-selected={me === act}
                      onClick={(e) => { e.preventDefault(); go(r); }} onMouseEnter={() => setAct(me)}>
                      <span className="ks-st1">
                        {r.num && <span className="mono"><Hit text={r.num} q={numHit ? query : ""} /></span>}
                        <span className="nm"><Hit text={r.name} q={numHit ? "" : query} /></span>
                      </span>
                      <span className="ks-smeta">{r.meta}</span>
                    </a>
                  );
                })}
                {g.more && <button type="button" className="ks-smore" onClick={() => { close(); router.visit(g.more.url); }}>{g.more.label}</button>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
});

export default TopbarSearch;
