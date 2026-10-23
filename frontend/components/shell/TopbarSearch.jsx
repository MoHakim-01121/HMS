import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { router } from "@inertiajs/react";
import { cn } from "@/lib/utils";
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
    } catch {
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
  return <>{s.slice(0, i)}<mark className="bg-transparent font-bold text-foreground">{s.slice(i, i + q.length)}</mark>{s.slice(i + q.length)}</>;
}

const NOTE = "p-5 text-center text-[13px] text-muted-foreground";

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
    <div ref={wrap} className={cn("relative mr-0.5 w-10 transition-[width,margin] duration-300 ease-drawer", open && "mr-1.5 w-[380px] max-[1100px]:w-[300px]")}>
      <label title={open ? undefined : t("Search")}
        className={cn(
          "box-border flex h-10 cursor-pointer items-center gap-[9px] overflow-hidden rounded-full border border-transparent bg-transparent pr-[5px] pl-[11px]",
          "transition-[border-color,background-color,box-shadow] duration-[250ms,250ms,300ms] ease-[ease] [&>svg]:flex-none [&>svg]:text-muted-foreground [&>svg]:transition-colors [&>svg]:duration-200",
          open ? "cursor-text border-foreground bg-card ring-4 ring-foreground/8" : "hover:bg-card",
        )}>
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
        <input ref={input} type="text" placeholder={t("Search CL, invoice, client, hotel")} aria-label={t("Search")}
          autoComplete="off" value={q} role="combobox" aria-expanded={open} aria-controls="ks-sres"
          className={cn(
            "h-full min-h-0 min-w-0 flex-1 rounded-none border-0 bg-transparent p-0 font-sans text-[14px] leading-[normal] font-medium text-foreground shadow-none outline-none",
            "transition-opacity ease-[ease] placeholder:font-normal placeholder:text-muted-foreground",
            open ? "opacity-100 delay-[80ms] duration-[180ms]" : "pointer-events-none opacity-0 duration-[160ms]",
          )}
          onFocus={() => setOpen(true)} onClick={() => setOpen(true)}
          onChange={(e) => { setQ(e.target.value); setAct(-1); setOpen(true); }} onKeyDown={onKey} />
        {q && (
          <button type="button" aria-label={t("Clear search")} onClick={() => { setQ(""); setAct(-1); input.current?.focus(); }}
            className={cn(
              "grid size-7 flex-none cursor-pointer place-content-center rounded-full border-0 bg-transparent text-muted-foreground transition-[opacity,background-color] duration-[200ms,120ms] ease-[ease] hover:bg-secondary hover:text-foreground",
              !open && "pointer-events-none opacity-0",
            )}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        )}
      </label>
      {panelShown && (
        <div role="dialog" aria-label={t("Search results")}
          className={cn(
            "surface absolute top-12 right-0 left-0 z-50 flex max-h-[calc(100vh_-_80px)] origin-top flex-col overflow-hidden rounded-[16px] border border-border bg-popover shadow-popover",
            panelClosing ? "pointer-events-none animate-menu-out" : "animate-panel-in",
          )}>
          <div id="ks-sres" role="listbox" aria-label={t("Results")}
            className="min-h-0 flex-1 animate-fade-in overflow-y-auto px-1.5 pt-1 pb-2 [animation-delay:50ms] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {noHits && (
              <div className="px-5 pt-7 pb-[30px] text-center">
                <b className="text-[14px] font-semibold">{t("No match for “{q}” in {branch}", { q: query, branch: branchName || "" })}</b>
                <p className="mx-auto mt-1.5 mb-0 max-w-[380px] text-[13px] leading-[1.6] text-pretty text-muted-foreground">{t("Search looks at CL, invoices, payments, clients, hotels and pages of this branch. Check the spelling, or switch branch to search another.")}</p>
              </div>
            )}
            {state.kind === "loading" && !groups.length && <div className={NOTE}>{t("Searching…")}</div>}
            {state.kind === "error" && (
              <div className={NOTE} role="alert">
                {state.reason === "auth" ? <>{t("Your session has ended.")} <a href="/login/">{t("Sign in again")}</a></>
                  : state.reason === "network" ? t("Can't reach the server. Check the connection and try again.")
                  : t("Search failed (error {code}). Try again.", { code: state.status || "?" })}
              </div>
            )}
            {groups.map((g) => (
              <div role="group" aria-label={g.title} key={g.title}>
                <div className="px-2.5 pt-3 pb-1 text-[11.5px] font-medium text-muted-foreground">{g.title}</div>
                {g.rows.map((r) => {
                  const me = idx++;
                  const numHit = !!(query && r.num && r.num.toLowerCase().includes(query.toLowerCase()));
                  return (
                    <a key={r.url + me} href={r.url} role="option" aria-selected={me === act}
                      className={cn(
                        "box-border flex h-[38px] w-full cursor-pointer items-center justify-between gap-4 rounded-[8px] border-0 bg-transparent px-2.5 text-left text-foreground no-underline [font:inherit]",
                        "transition-[background-color,color] duration-[160ms] ease-[ease] hover:bg-secondary",
                        me === act && "bg-secondary",
                      )}
                      onClick={(e) => { e.preventDefault(); go(r); }} onMouseEnter={() => setAct(me)}>
                      <span className="flex min-w-0 items-baseline gap-2.5 text-[13.5px] whitespace-nowrap">
                        {r.num && <span className="flex-none font-mono text-[12.5px] font-medium text-muted-foreground"><Hit text={r.num} q={numHit ? query : ""} /></span>}
                        <span className="overflow-hidden text-ellipsis"><Hit text={r.name} q={numHit ? "" : query} /></span>
                      </span>
                      <span className="flex-none text-[12.5px] whitespace-nowrap text-muted-foreground tabular-nums">{r.meta}</span>
                    </a>
                  );
                })}
                {g.more && (
                  <button type="button" onClick={() => { close(); router.visit(g.more.url); }}
                    className="block h-8 w-full cursor-pointer rounded-[8px] border-0 bg-transparent px-2.5 text-left font-sans text-[12.5px] leading-[normal] font-medium text-muted-foreground hover:bg-secondary hover:text-foreground">
                    {g.more.label}
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
});

export default TopbarSearch;
