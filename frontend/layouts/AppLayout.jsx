import { useEffect, useRef, useState, useMemo } from "react";
import axios from "axios";
import { Link, router, usePage } from "@inertiajs/react";
import { useTheme } from "./useTheme.js";
import { Icon } from "../components/icons.jsx";
import { getCsrf } from "../utils/csrf.js";
import { useI18n } from "../utils/i18n.jsx";
import SearchOverlay from "../components/shadcn/search-overlay.jsx";
import ShellSidebar from "../components/shell/ShellSidebar.jsx";
import TopbarSearch from "../components/shell/TopbarSearch.jsx";
import { NAV_TOP, NAV_GROUPS, NavIcon, allowed } from "../components/shell/nav.jsx";
import { usePresence } from "../components/shell/usePresence.js";
import DraftModal from "../components/shadcn/draft-modal.jsx";
import Toast, { showToast } from "../components/shadcn/toast.jsx";
import LanguageSwitcher from "../components/shell/LanguageSwitcher.jsx";
import { FormModalProvider } from "../components/shadcn/form-modal.jsx";
import { cn } from "@/lib/utils";

const NAV = {
  home: "/dashboard/",
  cl: "/cl/",
  invoice: "/invoice/",
  calendar: "/calendar/",
  account: "/account/profile/",
  logout: "/logout/",
};

const PAGE_TITLES = {
  home: "Home",
  cl: "CL",
  invoice: "Invoice",
  hotels: "Hotels",
  services: "Services",
  calendar: "Calendar",
  clients: "Clients",
  remittance: "Remittance",
  payments: "Payments",
  expenses: "Expenses",
  periods: "Financial Periods",
  statements: "Client Ledger",
  bank_accounts: "Bank and Cash",
  exchanges: "Transfer and Exchange",
  credit_notes: "Credit Notes",
  fund_flow: "Fund Flow",
  branch_report: "Branch report",
  ar_aging: "AR Aging",
  reconciliation: "Bank Reconciliation",
  penalties: "Penalties",
  journal: "Journal",
  trial_balance: "Trial Balance",
  users: "Users",
  roles: "Roles",
  account: "My Profile",
};

// Bottom nav: 5 core tabs — Home center, most-used operations flanking, More on right
const BNAV_TABS = [
  { key: "cl", label: "CL", icon: "cl" },
  { key: "invoice", label: "Invoice", icon: "invoice" },
  { key: "home", label: "Home", icon: "home" },
  { key: "calendar", label: "Calendar", icon: "calendar" },
  { key: "_more", label: "More", icon: "menu" },
];

function pageKeyFromUrl(url) {
  if (url === "/" || url === "") return "home";
  const map = [
    ["/hotels", "hotels"], ["/invoice", "invoice"],
    ["/calendar", "calendar"], ["/clients", "clients"],
    ["/remittance", "remittance"],
    ["/cl", "cl"], ["/users", "users"], ["/roles", "roles"], ["/account", "account"],
    ["/finance/payments", "payments"], ["/finance/expenses", "expenses"], ["/finance/periods", "periods"],
    ["/finance/journal", "journal"], ["/finance/trial-balance", "trial_balance"],
    ["/finance/statements", "statements"], ["/finance/clients", "statements"], ["/finance/exchanges", "exchanges"], ["/finance/credit-notes", "credit_notes"], ["/finance/invoices", "invoice"], ["/finance/fund-flow", "fund_flow"], ["/finance/branch-report", "branch_report"], ["/finance/ar-aging", "ar_aging"], ["/finance/bank-accounts", "bank_accounts"],
    ["/finance/reconciliation", "reconciliation"], ["/finance/penalties", "penalties"],
    ["/penalty", "penalties"],
  ];
  for (const [pre, key] of map) if (url.startsWith(pre)) return key;
  return "home";
}

function Csrf() {
  return <input type="hidden" name="csrfmiddlewaretoken" value={getCsrf()} />;
}

// No photo: a plain person glyph, never a monogram (initials avatars read as
// templated UI, 2026-10-22).
function UserGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="8" r="4" /><path d="M4 21c0-4.4 3.6-8 8-8s8 3.6 8 8" />
    </svg>
  );
}

// ── Mobile More page (full-screen module grid) ─────────────────────────
function MobileMore({ page, perms, onClose }) {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const inputRef = useRef(null);

  useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 100);
  }, []);

  const groups = useMemo(() => {
    const ok = allowed(perms);
    const match = (it) => !query || t(it.label).toLowerCase().includes(query.toLowerCase());
    // Home is already in the bottom nav.
    const top = { id: "top", heading: "Overview", items: NAV_TOP.filter((it) => it.key !== "home") };
    return [top, ...NAV_GROUPS]
      .map((g) => ({ ...g, items: g.items.filter((it) => ok(it) && match(it)) }))
      .filter((g) => g.items.length);
  }, [query, perms, t]);

  return (
    <div className="fixed top-[calc(48px_+_env(safe-area-inset-top))] right-0 bottom-[calc(56px_+_env(safe-area-inset-bottom))] left-0 z-[calc(var(--z-sticky,200)_+_1)] hidden animate-rise-in flex-col bg-background max-[600px]:flex">
      <div className="flex-shrink-0 px-4 pt-3 pb-0">
        <div className="flex h-10 items-center gap-2 rounded-[12px] border border-border bg-secondary px-3 text-muted-foreground">
          <Icon name="search" size={16} strokeWidth={1.8} />
          <input
            ref={inputRef}
            type="text"
            placeholder={t("Search modules...")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="h-full w-auto min-w-0 flex-1 rounded-none border-0 bg-transparent p-0 font-[family-name:inherit] text-[15px] text-foreground shadow-none outline-none placeholder:text-muted-foreground"
          />
          {query && (
            <button type="button" onClick={() => setQuery("")}
              className="flex size-5 flex-shrink-0 cursor-pointer items-center justify-center rounded-full border-0 bg-transparent text-muted-foreground">
              <Icon name="close" size={14} />
            </button>
          )}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-4 pt-2 pb-5">
        {groups.map((g) => (
          <div key={g.id} className="pb-1.5">
            <div className="px-1 pt-3.5 pb-2 text-[11px] font-semibold tracking-[0.13em] text-muted-foreground uppercase">{t(g.heading)}</div>
            <div className="overflow-hidden rounded-card border border-border bg-card">
              {g.items.map((item) => (
                <div key={item.key}>
                  <Link
                    href={item.href}
                    className={cn(
                      "flex h-12 items-center gap-3 px-[15px] text-[13.5px] font-medium text-foreground no-underline transition-[background-color] duration-[120ms] ease-[ease] active:bg-secondary",
                      "[&>svg:first-child]:flex-none [&>svg:first-child]:text-muted-foreground",
                      page === item.key && "font-semibold [&>svg:first-child]:text-foreground",
                    )}
                    onClick={onClose}
                  >
                    <NavIcon name={item.icon || item.key} />
                    <span className="flex-1">{t(item.label)}</span>
                    <Icon name="chevron" size={15} strokeWidth={1.8} className="flex-none text-muted-foreground" />
                  </Link>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Desktop topbar: floats over a blurred strip of the page, its title and icons
// lined up with the page's own edges (--page-max wide, 1320px on list pages,
// centred in what the sidebar leaves).
const TOPBAR = cn(
  "canvas fixed top-0 right-0 z-[var(--z-sticky,200)] hidden h-(--topbar-h) items-center justify-between gap-4 min-[601px]:flex",
  "pt-(--shell-gap) pr-[calc(var(--tb-x)_-_4px)] pb-0 pl-(--tb-x) [body:has([data-slot=list-main])_&]:[--page-max:1320px]",
  "border-b border-b-transparent bg-background/86 backdrop-blur-[20px] backdrop-saturate-[1.4]",
  "transition-[left,border-color] duration-[300ms,200ms] ease-[cubic-bezier(.32,.72,0,1),ease] in-data-[scroll-locked]:right-[var(--removed-body-scroll-bar-size,0px)]",
);
const TOPBAR_X = "[--tb-x:max(20px,calc((100vw_-_var(--sidebar-w)_-_var(--page-max,1040px))_/_2_+_20px))]";
const TOPBAR_X_MINI = "[--tb-x:max(20px,calc((100vw_-_var(--sidebar-w-collapsed)_-_var(--page-max,1040px))_/_2_+_20px))]";
const PRESS = "transition-[background-color,scale] duration-[160ms,120ms] ease-[ease] active:scale-[.94] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid";
const ICON_BTN = cn(PRESS, "relative grid size-10 flex-none cursor-pointer place-content-center rounded-[12px] border-0 bg-transparent text-muted-foreground hover:bg-card hover:text-foreground aria-expanded:bg-card aria-expanded:text-foreground");
// Topbar menus (notifications, account) drop from the right.
const MENU = "surface absolute top-[50px] right-0 z-40 origin-top-right animate-menu-in rounded-[16px] border border-border bg-popover shadow-menu";
const MENU_CLOSING = "pointer-events-none animate-menu-out";
const MENU_GROUP = "px-2.5 pt-3 pb-1 text-[11.5px] font-medium text-muted-foreground";
const MENU_ROW = cn(
  "box-border flex w-full cursor-pointer items-center gap-2.5 rounded-[8px] border-0 bg-transparent px-2.5 py-[9px] text-left font-sans text-[13px] leading-[normal] font-medium text-foreground no-underline",
  "transition-[background-color,color] duration-[160ms] ease-[ease] hover:bg-secondary [:where(&)_svg]:flex-none [:where(&)_svg]:text-muted-foreground",
);
const MENU_META = "ml-auto text-[12px] text-muted-foreground";
const ACCT_LINE = "overflow-hidden text-[12px] text-ellipsis whitespace-nowrap text-muted-foreground";

// Phone chrome (600px and below): top bar, bottom nav, More page and the
// account / notification bottom sheets.
const M_BTN = "relative flex size-11 cursor-pointer appearance-none items-center justify-center rounded-[10px] border-0 bg-transparent text-foreground transition-[background-color] duration-[120ms] ease-[ease] active:bg-secondary";
const SCRIM = "fixed inset-0 z-[calc(var(--z-sticky,200)_+_4)] hidden animate-fade-in bg-scrim-soft max-[600px]:block";
const SHEET = "fixed right-0 bottom-0 left-0 z-[calc(var(--z-sticky,200)_+_5)] hidden translate-y-full flex-col rounded-t-[20px] bg-card pt-3.5 pb-[calc(18px_+_env(safe-area-inset-bottom))] transition-[translate] duration-[240ms] ease-drawer max-[600px]:flex";
const GRAB = "mx-auto mt-0 mb-3.5 h-1 w-[38px] rounded-full bg-border";
const SHEET_ROW = "flex h-[52px] w-full cursor-pointer items-center gap-3 border-0 bg-transparent px-[18px] font-[family-name:inherit] text-[13.5px] font-medium text-foreground no-underline active:bg-secondary [&_svg]:flex-none [&_svg]:text-muted-foreground";
const SHEET_CLOSE = "mx-[18px] mt-3.5 mb-0 h-12 cursor-pointer rounded-full border border-input bg-card font-[family-name:inherit] text-[13px] font-semibold text-foreground";

const READ_KEY = "hms.notif.read";
const MINI_KEY = "hms.sidebar.mini";
const TOAST_KEY = "hms.branch.toast";

const fmtSar = (v) => new Intl.NumberFormat("en-US").format(Math.round(v || 0));
const notifKey = (n) => `${n.type}:${n.ref}:${n.days}`;
function readSet(key) {
  try { return new Set(JSON.parse(window.localStorage.getItem(key) || "[]")); } catch { return new Set(); }
}
function readMini() {
  try { return window.localStorage.getItem(MINI_KEY) === "1"; } catch { return false; }
}

export default function AppLayout({ children }) {
  const { props, url } = usePage();
  const { t, locale } = useI18n();
  const user = props.auth?.user;
  const branch = props.branch || {};
  const dueNotifs = props.due_soon_notifs || [];
  const { theme, toggle } = useTheme();
  const page = pageKeyFromUrl(url);
  const isMap = url.split("?")[0].includes("/map/");

  const [search, setSearch] = useState(false);
  const [notif, setNotif] = useState(false);
  const [mNotif, setMNotif] = useState(false); // phones: the old sheet
  const [account, setAccount] = useState(false);
  const [mAccount, setMAccount] = useState(false);
  const [mMore, setMMore] = useState(false);
  const [collapsed, setCollapsed] = useState(readMini);
  const [lift, setLift] = useState(false);
  const [readKeys, setReadKeys] = useState(() => readSet(READ_KEY));
  const [confirmTo, setConfirmTo] = useState(null);
  const [toast, setToast] = useState("");
  const [switching, setSwitching] = useState(false);
  const accountWrap = useRef(null);
  const notifWrap = useRef(null);
  const searchRef = useRef(null);
  const dirty = useRef(null);
  const main = useRef(null);

  // The browser tab names the page: its heading ("INV-090", "Journal
  // Entries"), Home on the dashboard, so tabs and history can be told apart.
  useEffect(() => {
    const id = requestAnimationFrame(() => {
      const h1 = ["/", "/dashboard/"].includes(url.split("?")[0]) ? "" : main.current?.querySelector("h1")?.textContent?.trim();
      document.title = `${h1 || t(PAGE_TITLES[page] || "Home")} — Konoz United`;
    });
    return () => cancelAnimationFrame(id);
  }, [url, page, t]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") { setSearch(false); setNotif(false); setMNotif(false); setAccount(false); setMAccount(false); setMMore(false); setConfirmTo(null); }
      const tag = document.activeElement?.tagName;
      if (e.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA") {
        e.preventDefault();
        if (window.matchMedia("(min-width: 601px)").matches && searchRef.current) searchRef.current.focus();
        else setSearch(true);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // The mouse wheel over a focused number field steps its value: scrolling
  // the page past a capacity or coordinate field silently changed it. Drop
  // focus first, so the wheel scrolls the page and the value stays.
  useEffect(() => {
    const onWheel = (e) => {
      const el = document.activeElement;
      if (el?.type === "number" && el === e.target) el.blur();
    };
    document.addEventListener("wheel", onWheel, { passive: true });
    return () => document.removeEventListener("wheel", onWheel);
  }, []);

  // An upload larger than nginx's client_max_body_size (3 MB) is rejected
  // upstream with a plain 413 HTML page — a non-Inertia response. Without this,
  // Inertia surfaces its raw error-modal. Convert that one case into a toast.
  useEffect(() => {
    return router.on("invalid", (event) => {
      if (event.detail.response?.status === 413) {
        event.preventDefault();
        showToast(t("File too large. Maximum upload size is 3 MB."), "error");
      }
    });
  }, [t]);

  // Unsaved changes: typing in any form marks the page dirty (with the form's
  // title when it has one); a visit clears it. Switching branch asks first.
  useEffect(() => {
    const onInput = (e) => {
      const f = e.target.closest?.("form");
      if (!f) return;
      const scope = f.closest('[role="dialog"]') || main.current;
      const title = scope?.querySelector("h1, h2, [data-slot=dialog-title], .htitle")?.textContent?.trim();
      dirty.current = title || t("this page");
    };
    document.addEventListener("input", onInput, true);
    const off = router.on("navigate", () => { dirty.current = null; });
    // A form dismissed without saving (discarded) is no longer unsaved work.
    const onClean = () => { dirty.current = null; };
    window.addEventListener("hms:clean", onClean);
    // Reload or closing the tab with unsaved input: the browser asks first.
    const onUnload = (e) => { if (dirty.current) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", onUnload);
    return () => { document.removeEventListener("input", onInput, true); off(); window.removeEventListener("hms:clean", onClean); window.removeEventListener("beforeunload", onUnload); };
  }, [t]);

  useEffect(() => {
    let name = "";
    try { name = window.sessionStorage.getItem(TOAST_KEY) || ""; window.sessionStorage.removeItem(TOAST_KEY); } catch { /* storage blocked */ }
    if (!name) return;
    setToast(name);
    const id = setTimeout(() => setToast(""), 3200);
    return () => clearTimeout(id);
  }, []);

  useEffect(() => {
    const onDoc = (e) => {
      if (accountWrap.current && !accountWrap.current.contains(e.target)) setAccount(false);
      if (notifWrap.current && !notifWrap.current.contains(e.target)) setNotif(false);
      setMAccount(false);
      setMNotif(false);
    };
    if (account || notif || mAccount || mNotif) {
      document.addEventListener("click", onDoc);
      return () => document.removeEventListener("click", onDoc);
    }
  }, [account, notif, mAccount, mNotif]);

  // Collapsing re-lays the page once, then slides the content from where it
  // was (FLIP) on the sidebar's own curve: a transform, not a padding
  // transition that re-lays every table on every frame.
  // toggleMini reads the left edge before the padding changes, this effect
  // after.
  const shellLeft = useRef(null);
  useEffect(() => {
    const shell = main.current;
    const before = shellLeft.current;
    shellLeft.current = null;
    if (!shell || before == null || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const dx = before - shell.getBoundingClientRect().left;
    if (dx) shell.animate([{ transform: `translateX(${dx}px)` }, { transform: "none" }], { duration: 300, easing: "cubic-bezier(.32,.72,0,1)" });
  }, [collapsed]);

  // The topbar stays put; once the page scrolls under it, a hairline shows.
  useEffect(() => {
    const onScroll = () => setLift(window.scrollY > 4);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    document.body.classList.toggle("map-fullscreen", isMap);
    return () => document.body.classList.remove("map-fullscreen");
  }, [isMap]);

  // Lock body scroll when More page is open
  useEffect(() => {
    if (mMore) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [mMore]);

  const toggleMini = () => {
    const m = !collapsed;
    shellLeft.current = main.current?.getBoundingClientRect().left ?? null;
    try { window.localStorage.setItem(MINI_KEY, m ? "1" : "0"); } catch { /* storage blocked */ }
    setCollapsed(m);
  };

  const doSwitch = (b) => {
    setConfirmTo(null);
    dirty.current = null;
    try { window.sessionStorage.setItem(TOAST_KEY, b.name); } catch { /* storage blocked */ }
    setSwitching(true);
    const form = document.createElement("form");
    form.method = "post";
    form.action = "/account/branch/";
    for (const [k, v] of [["csrfmiddlewaretoken", getCsrf()], ["branch", b.code], ["next", window.location.pathname + window.location.search]]) {
      const i = document.createElement("input");
      i.type = "hidden"; i.name = k; i.value = v;
      form.appendChild(i);
    }
    document.body.appendChild(form);
    form.submit();
  };
  const pickBranch = (b) => (dirty.current ? setConfirmTo(b) : doSwitch(b));

  const setLanguage = async (value) => {
    try {
      await axios.post("/account/language/", new URLSearchParams({ language: value }));
      router.reload();
    } catch { /* keep current language */ }
  };

  const notifLabel = (n) => {
    const kind = n.type === "check_in" ? "Check-in" : n.type === "check_out" ? "Check-out" : "Due";
    if (n.days === 0) return t(`${kind} today`);
    if (n.days === 1) return t(`${kind} tomorrow`);
    return t(`${kind} in {n} days`, { n: n.days });
  };
  const fresh = dueNotifs.filter((n) => !readKeys.has(notifKey(n)));
  const earlier = dueNotifs.filter((n) => readKeys.has(notifKey(n)));
  const unread = fresh.length;
  const markRead = () => {
    const next = new Set([...readKeys, ...dueNotifs.map(notifKey)]);
    setReadKeys(next);
    try { window.localStorage.setItem(READ_KEY, JSON.stringify([...next])); } catch { /* storage blocked */ }
  };

  const [notifShown, notifClosing] = usePresence(notif);
  const [acctShown, acctClosing] = usePresence(account);
  const pageTitle = t(PAGE_TITLES[page] || "Home");
  // The desktop topbar names the day on every page; the page names itself
  // in its own heading. The phone's top bar keeps the page title.
  const dayLabel = (() => {
    const d = new Date(), loc = locale === "id" ? "id-ID" : "en-GB";
    return `${d.toLocaleDateString(loc, { weekday: "long" })}, ${d.toLocaleDateString(loc, { day: "numeric", month: "long", year: "numeric" })}`;
  })();
  // `branch_report` is not a server module: the report needs statements and
  // a branch on HMS to report on (head office alone has none).
  const perms = { ...(user?.perms || {}), branch_report: user?.report_branches ? (user?.perms?.statements || []) : [] };
  const displayName = user ? (user.name || user.username) : "";
  const roleBranch = [user?.role_label, branch.current?.name].filter(Boolean).join(", ");
  const avatar = (lg, className) => (
    <span className={cn("grid size-9 flex-none place-content-center overflow-hidden rounded-full bg-info-tint text-[12.5px] font-bold tracking-[.02em] text-info-text", lg && "size-10 text-[13.5px]", className)}>
      {user.avatar ? <img className="block size-full object-cover" src={user.avatar} alt="" /> : <UserGlyph />}
    </span>
  );
  const notifGroup = (title, rows) => rows.length > 0 && (
    <div role="group" aria-label={title}>
      <div className={MENU_GROUP}>{title}</div>
      {rows.map((n, i) => (
        <Link key={i} href={n.url} onClick={() => setNotif(false)}
          className="grid min-h-10 grid-cols-[92px_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-px rounded-[8px] px-2.5 py-1.5 text-[13.5px] whitespace-nowrap text-foreground no-underline transition-[background-color,color] duration-[160ms] ease-[ease] hover:bg-secondary">
          <span className="overflow-hidden font-mono text-[12.5px] font-medium text-ellipsis text-muted-foreground">{n.ref}</span>
          <span className="overflow-hidden font-medium text-ellipsis">{n.title}</span>
          <span className={cn("text-right text-[12.5px] text-muted-foreground", n.days <= 1 && "font-medium text-warning-text")}>{notifLabel(n)}</span>
          {n.type === "invoice_due" && <span className="col-start-3 text-right text-[12.5px] font-semibold tabular-nums">{fmtSar(n.remaining)} SAR</span>}
        </Link>
      ))}
    </div>
  );

  return (
    <FormModalProvider>
      <div data-page={page} className={cn(!isMap && "min-[601px]:pt-(--topbar-h)", !isMap && (collapsed ? "min-[601px]:pl-(--sidebar-w-collapsed)" : "min-[601px]:pl-(--sidebar-w)"))}>
      <a href="#main"
        className="fixed top-2 left-2 z-[1000] -translate-y-[200%] rounded-full bg-primary px-4 py-2 font-sans text-[13px] leading-[normal] font-semibold text-primary-foreground no-underline transition-[translate] duration-150 ease-[ease] focus:translate-y-0 focus:outline-2 focus:outline-offset-2 focus:outline-ring focus:outline-solid">
        {t("Skip to content")}
      </a>
      {user && (
        <>
          {!isMap && <ShellSidebar page={page} perms={perms} theme={theme} branch={branch} mini={collapsed} onPickBranch={pickBranch} onToggleMini={toggleMini} />}

          {!isMap && (
          <header className={cn(TOPBAR, collapsed ? TOPBAR_X_MINI : TOPBAR_X, collapsed ? "left-(--sidebar-w-collapsed)" : "left-(--sidebar-w)", lift && "border-b-[color:color-mix(in_oklch,var(--border)_80%,transparent)]")}>
            <div className="flex min-w-0 items-center gap-1">
              <span className="overflow-hidden text-[13px] font-medium text-ellipsis whitespace-nowrap text-muted-foreground tabular-nums">{dayLabel}</span>
            </div>
            <div className="flex min-w-0 items-center gap-1">
              <TopbarSearch ref={searchRef} perms={perms} branchName={branch.current?.name} />

              <div className="relative" ref={notifWrap}>
                <button type="button" className={ICON_BTN} aria-label={unread ? t("Notifications, {n} unread", { n: unread }) : t("Notifications")}
                  aria-haspopup="true" aria-expanded={notif}
                  onClick={() => { setNotif((v) => !v); setAccount(false); }}>
                  <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 16v-5a6 6 0 0112 0v5l2 2H4zM10 21h4" /></svg>
                  {unread > 0 && (
                    <span className="absolute top-[3px] right-[3px] box-border grid h-[18px] min-w-[18px] place-content-center rounded-full border-2 border-background bg-primary px-[5px] text-[10.5px] font-semibold text-primary-foreground tabular-nums">
                      {unread > 9 ? "9+" : unread}
                    </span>
                  )}
                </button>
                {notifShown && (
                  <div className={cn(MENU, "flex max-h-[min(480px,calc(100vh_-_96px))] w-[420px] flex-col px-1.5 pt-0 pb-1.5", notifClosing && MENU_CLOSING)}>
                    <div className="-mx-1.5 flex h-12 flex-none items-center justify-between border-b border-hairline px-4 text-[14px] font-semibold">
                      {t("Notifications")}
                      {unread > 0 && (
                        <button type="button" onClick={markRead}
                          className="-mr-2 h-7 cursor-pointer rounded-[8px] border-0 bg-transparent px-2 font-sans text-[12.5px] leading-[normal] font-medium text-muted-foreground hover:bg-secondary hover:text-foreground">
                          {t("Mark all as read")}
                        </button>
                      )}
                    </div>
                    <div className="scrollbar-quiet min-h-0 flex-1 overflow-y-auto overscroll-contain pb-0.5">
                      {dueNotifs.length === 0 && <div className="px-2.5 pt-3.5 pb-[18px] text-[13px] text-muted-foreground">{t("No notifications")}</div>}
                      {notifGroup(t("New"), fresh)}
                      {notifGroup(t("Earlier"), earlier)}
                    </div>
                  </div>
                )}
              </div>

              <span className="mx-1.5 h-[22px] w-px bg-border" aria-hidden="true" />
              <div className="relative" ref={accountWrap}>
                <button type="button" aria-label={t("Account, {name}", { name: displayName })} title={displayName}
                  aria-haspopup="menu" aria-expanded={account}
                  className={cn(PRESS, "group/acct grid size-11 cursor-pointer place-content-center rounded-full border-0 bg-transparent p-0")}
                  onClick={() => { setAccount((v) => !v); setNotif(false); }}>
                  {avatar(false, "ring-1 ring-border ring-offset-2 ring-offset-card transition-shadow duration-150 ease-[ease] group-hover/acct:ring-2 group-hover/acct:ring-input group-aria-expanded/acct:ring-2 group-aria-expanded/acct:ring-input")}
                </button>
                {acctShown && (
                  <div className={cn(MENU, "w-[260px] p-1.5", acctClosing && MENU_CLOSING)} role="menu">
                    <div className="mb-1 flex items-center gap-2.5 border-b border-hairline px-2.5 pt-2.5 pb-3">
                      {avatar(true)}
                      <span className="flex min-w-0 flex-col leading-[1.3]">
                        <b className="text-[13.5px]">{displayName}</b>
                        <span className={ACCT_LINE}>{roleBranch}</span>
                        <span className={ACCT_LINE}>{user.username}</span>
                      </span>
                    </div>
                    <Link className={MENU_ROW} href={NAV.account} role="menuitem" onClick={() => setAccount(false)}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4" /><path d="M4 20c1.5-4 4.5-6 8-6s6.5 2 8 6" /></svg>{t("My Profile")}
                    </Link>
                    <button type="button" className={MENU_ROW} role="menuitem" onClick={toggle}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>{t("Theme")}<span className={MENU_META}>{theme === "light" ? t("Light") : t("Dark")}</span>
                    </button>
                    <button type="button" className={MENU_ROW} role="menuitem" onClick={() => setLanguage(locale === "en" ? "id" : "en")}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.5 3.8 5.5 3.8 9s-1.3 6.5-3.8 9c-2.5-2.5-3.8-5.5-3.8-9S9.5 5.5 12 3z" /></svg>{t("Language")}<span className={MENU_META}>{locale === "en" ? "English" : "Indonesia"}</span>
                    </button>
                    <div className="my-1 h-px bg-hairline" />
                    <form method="post" action={NAV.logout} className="m-0">
                      <Csrf />
                      <button type="submit" className={cn(MENU_ROW, "text-danger-text [&_svg]:text-danger-text")} role="menuitem">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10" /></svg>{t("Log out")}
                      </button>
                    </form>
                  </div>
                )}
              </div>
            </div>
          </header>
          )}
        </>
      )}

      {user && (
        <>
          {/* ── Mobile top bar ── */}
          {!isMap && (
          <header id="m-top-bar"
            className="fixed top-0 right-0 left-0 z-[var(--z-sticky,200)] flex h-[calc(48px_+_env(safe-area-inset-top))] items-center justify-between gap-3 border-b border-border bg-card px-4 pt-[env(safe-area-inset-top)] min-[601px]:hidden">
            <div className="flex min-w-0 flex-1 items-center gap-2.5">
              <span className="overflow-hidden text-[17px] font-semibold tracking-[-0.01em] text-ellipsis whitespace-nowrap text-foreground">{pageTitle}</span>
            </div>
            <div className="flex flex-shrink-0 items-center gap-2">
              <button type="button" className={M_BTN} aria-label="Search"
                onClick={(e) => { e.stopPropagation(); setSearch(true); }}>
                <Icon name="search" size={19} strokeWidth={1.8} />
              </button>
              <button type="button" className={M_BTN} aria-label="Notifications"
                aria-haspopup="true" aria-expanded={mNotif}
                onClick={(e) => { e.stopPropagation(); setMNotif((v) => !v); setMAccount(false); setMMore(false); }}>
                <Icon name="bell" size={19} strokeWidth={1.8} />
                {dueNotifs.length > 0 && (
                  <span className="pointer-events-none absolute top-1.5 right-1.5 flex h-3.5 min-w-3.5 items-center justify-center rounded-full border-[1.5px] border-card bg-destructive px-[3px] text-[9px] font-semibold text-destructive-foreground">
                    {dueNotifs.length}
                  </span>
                )}
              </button>
              <button type="button" className={M_BTN} aria-label="Account"
                aria-haspopup="true" aria-expanded={mAccount}
                onClick={(e) => { e.stopPropagation(); setMAccount((v) => !v); setMNotif(false); setMMore(false); }}>
                <span className="size-[30px] flex-shrink-0 overflow-hidden rounded-full">
                  {user.avatar
                    ? <img className="block size-full object-cover" src={user.avatar} alt={user.username} />
                    : <span className="flex size-full items-center justify-center bg-foreground text-[11px] font-semibold text-background"><UserGlyph /></span>}
                </span>
              </button>
            </div>
          </header>
          )}

          {/* ── Mobile bottom nav ── */}
          {!isMap && (
          <nav id="m-bottom-nav"
            className="fixed right-0 bottom-0 left-0 z-[var(--z-sticky,200)] grid h-[calc(64px_+_env(safe-area-inset-bottom))] grid-cols-5 items-center border-t border-border bg-card px-1.5 pt-0 pb-[env(safe-area-inset-bottom)] min-[601px]:hidden">
            {BNAV_TABS.map((tab) => {
              const isMore = tab.key === "_more";
              const isActive = isMore ? mMore : page === tab.key;
              const inner = (
                <>
                  <span className="relative flex size-6 items-center justify-center [&_svg]:size-[22px]"><Icon name={tab.icon} strokeWidth={isActive ? 2 : 1.8} /></span>
                  <span className={cn("text-[10px] leading-none font-medium tracking-[0.01em]", isActive && "font-semibold")}>{t(tab.label)}</span>
                </>
              );
              const cls = cn(
                "flex h-[52px] cursor-pointer appearance-none flex-col items-center justify-center gap-1 rounded-[12px] border-0 bg-transparent font-[family-name:inherit] text-muted-foreground no-underline transition-[color] duration-[120ms] ease-[ease] active:opacity-70",
                isActive && "text-foreground",
              );
              return isMore ? (
                <button key={tab.key} type="button" className={cls}
                  onClick={() => { setMMore((v) => !v); setMNotif(false); setMAccount(false); }}>
                  {inner}
                </button>
              ) : (
                <Link key={tab.key} href={NAV[tab.key]} className={cls}>{inner}</Link>
              );
            })}
          </nav>
          )}

          {/* ── Mobile More page (full-screen module grid) ── */}
          {mMore && (
            <MobileMore page={page} perms={perms} onClose={() => setMMore(false)} />
          )}

          {/* ── Mobile account sheet (v2.1 bottom sheet) ── */}
          {mAccount && <div className={SCRIM} onClick={() => setMAccount(false)} />}
          <div className={cn(SHEET, mAccount && "translate-y-0")} onClick={(e) => e.stopPropagation()}
            ref={(el) => { if (el) el.inert = !mAccount; }} role={mAccount ? "dialog" : undefined} aria-hidden={!mAccount} aria-label={t("Account")}>
            <span className={GRAB} aria-hidden="true" />
            <div className="flex items-center gap-[11px] border-b border-hairline px-[18px] pt-0 pb-3.5">
              <span className="flex size-10 flex-none items-center justify-center overflow-hidden rounded-full bg-foreground text-[13px] font-semibold text-background">
                {user.avatar ? <img className="size-full object-cover" src={user.avatar} alt={user.username} /> : <UserGlyph />}
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="text-[14px] font-semibold text-foreground">{user.username}</span>
                <span className="overflow-hidden text-[12px] text-ellipsis whitespace-nowrap text-muted-foreground">{user.name && user.name !== user.username ? user.name : user.role_label}</span>
              </span>
              <span>{user.role_label || (user.is_superuser ? t("Admin") : user.is_staff ? t("Staff") : t("Member"))}</span>
            </div>
            {/* Rows divide only where a hairline reads as a break: above Language. */}
            <a href={NAV.account} className={SHEET_ROW}><Icon name="user" size={18} /><span className="flex-1 text-left">{t("My Profile")}</span></a>
            <button type="button" className={SHEET_ROW} onClick={toggle}>
              <Icon name={theme === "light" ? "sun" : "moon"} size={18} /><span className="flex-1 text-left">{t("Theme")}</span>
              <span>{theme === "light" ? t("Light") : t("Dark")}</span>
            </button>
            <div className={cn(SHEET_ROW, "cursor-default border-t border-hairline")}>
              <Icon name="globe" size={18} /><span className="flex-1 text-left">{t("Language")}</span>
              <LanguageSwitcher variant="mini" />
            </div>
            <form method="post" action={NAV.logout} className="m-0">
              <Csrf />
              <button type="submit" className={cn(SHEET_ROW, "text-danger-ink [&_svg]:text-current")}><Icon name="logout" size={18} /><span className="flex-1 text-left">{t("Log out")}</span></button>
            </form>
            <button type="button" className={SHEET_CLOSE} onClick={() => setMAccount(false)}>{t("Close")}</button>
          </div>

          {/* ── Mobile notification sheet: the account sheet's frame, the desktop list's groups ── */}
          {mNotif && <div className={SCRIM} onClick={() => setMNotif(false)} />}
          <div className={cn(SHEET, "max-h-[80dvh]", mNotif && "translate-y-0")} onClick={(e) => e.stopPropagation()}
            ref={(el) => { if (el) el.inert = !mNotif; }} role={mNotif ? "dialog" : undefined} aria-hidden={!mNotif} aria-label={t("Notifications")}>
            <span className={GRAB} aria-hidden="true" />
            <div className="flex flex-none items-center justify-between border-b border-hairline px-[18px] pt-0 pb-3 text-[15px] font-semibold text-foreground">
              <span>{t("Notifications")}</span>
              {unread > 0 && (
                <button type="button" onClick={markRead}
                  className="-mr-2 h-8 cursor-pointer rounded-[8px] border-0 bg-transparent px-2 font-sans text-[13px] leading-[normal] font-medium text-muted-foreground active:bg-secondary">
                  {t("Mark all as read")}
                </button>
              )}
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 py-0">
              {dueNotifs.length === 0 && <div className="px-2.5 py-5 text-[13px] text-muted-foreground">{t("No notifications")}</div>}
              {[[t("New"), fresh], [t("Earlier"), earlier]].map(([title, rows]) => rows.length > 0 && (
                <div key={title} role="group" aria-label={title}>
                  <div className="px-2.5 pt-3.5 pb-1 text-[12px] font-medium text-muted-foreground">{title}</div>
                  {rows.map((n, i) => (
                    <Link key={i} href={n.url} onClick={() => setMNotif(false)}
                      className="grid min-h-14 grid-cols-[minmax(0,1fr)_auto] content-center gap-x-3 gap-y-0.5 rounded-[10px] px-2.5 py-[9px] text-foreground no-underline active:bg-secondary">
                      <span className="overflow-hidden text-[14px] font-medium text-ellipsis whitespace-nowrap">{n.title}</span>
                      <span className={cn("text-right text-[12.5px] whitespace-nowrap text-muted-foreground", n.days <= 1 && "font-medium text-warning-text")}>{notifLabel(n)}</span>
                      <span className="col-start-1 font-mono text-[12px] text-muted-foreground">{n.ref}</span>
                      {n.type === "invoice_due" && <span className="col-start-2 text-right text-[12.5px] font-semibold tabular-nums">{fmtSar(n.remaining)} SAR</span>}
                    </Link>
                  ))}
                </div>
              ))}
            </div>
            <button type="button" className={SHEET_CLOSE} onClick={() => setMNotif(false)}>{t("Close")}</button>
          </div>
        </>
      )}

      {/* v2.1 is a flat solid canvas — no ambient blobs, gradients, or texture. */}
      <div ref={main} id="main" tabIndex={-1} className={cn("canvas transition-opacity duration-200 ease-[ease] focus:outline-none", switching && "opacity-35")}>{children}</div>

      {confirmTo && (
        <div className="fixed inset-0 z-[80] box-border flex animate-fade-in items-start justify-center bg-scrim px-6 pt-[120px] pb-6"
          onMouseDown={(e) => { if (e.target === e.currentTarget) setConfirmTo(null); }}>
          <div role="alertdialog" aria-modal="true" aria-labelledby="ks-cdt"
            className="surface box-border w-full max-w-[420px] animate-panel-in rounded-[20px] border border-border bg-popover px-[22px] pt-[22px] pb-[18px] shadow-palette">
            <h2 id="ks-cdt" className="m-0 text-[16px] font-semibold tracking-[-0.01em]">{t("Switch to {name}?", { name: confirmTo.name })}</h2>
            <p className="mt-2 mb-0 text-[13.5px] leading-[1.6] text-pretty text-muted-foreground">
              {t("You have unsaved changes in")} <b>{dirty.current}</b>. {t("Switching branch reloads the page and these changes will be lost.")}
            </p>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <button type="button" autoFocus onClick={() => setConfirmTo(null)}
                className="h-[38px] cursor-pointer rounded-full border border-input bg-card px-4 font-sans text-[13px] leading-[normal] font-semibold text-foreground hover:border-foreground">
                {t("Stay on {name}", { name: branch.current?.name || "" })}
              </button>
              <button type="button" onClick={() => doSwitch(confirmTo)}
                className="h-[38px] cursor-pointer rounded-full border-0 bg-destructive px-4 font-sans text-[13px] leading-[normal] font-semibold text-destructive-foreground">
                {t("Discard and switch")}
              </button>
            </div>
          </div>
        </div>
      )}
      {toast && (
        <div role="status"
          className="fixed bottom-7 left-1/2 z-[90] flex h-[42px] -translate-x-1/2 animate-rise-in items-center gap-[9px] rounded-full bg-foreground pr-[18px] pl-3.5 font-sans text-[13.5px] leading-[normal] font-medium text-background shadow-popover">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10" /></svg>
          <span>{t("Now showing")} <b className="font-semibold">{toast}</b></span>
        </div>
      )}
      <Toast />
      {user && <SearchOverlay open={search} onClose={() => setSearch(false)} />}
      {user && <DraftModal />}
      </div>
    </FormModalProvider>
  );
}
