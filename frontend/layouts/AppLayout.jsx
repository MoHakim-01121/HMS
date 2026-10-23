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
import "../styles/shell.css";
import DraftModal from "../components/shadcn/draft-modal.jsx";
import Toast, { showToast } from "../components/shadcn/toast.jsx";
import LanguageSwitcher from "../components/shell/LanguageSwitcher.jsx";
import { FormModalProvider } from "../components/shadcn/form-modal.jsx";

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
    <div className="m-more">
      <div className="m-more-head">
        <div className="m-more-search">
          <Icon name="search" size={16} strokeWidth={1.8} />
          <input
            ref={inputRef}
            type="text"
            placeholder={t("Search modules...")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && (
            <button type="button" className="m-more-clear" onClick={() => setQuery("")}>
              <Icon name="close" size={14} />
            </button>
          )}
        </div>
      </div>
      <div className="m-more-body">
        {groups.map((g) => (
          <div key={g.id} className="m-more-group">
            <div className="m-more-heading">{t(g.heading)}</div>
            <div className="m-more-card">
              {g.items.map((item) => (
                <div key={item.key}>
                  <Link
                    href={item.href}
                    className={"m-more-item" + (page === item.key ? " active" : "")}
                    onClick={onClose}
                  >
                    <NavIcon name={item.icon || item.key} />
                    <span className="m-more-label">{t(item.label)}</span>
                    <Icon name="chevron" size={15} strokeWidth={1.8} className="m-more-chev" />
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
  const accountWrap = useRef(null);
  const notifWrap = useRef(null);
  const searchRef = useRef(null);
  const dirty = useRef(null);

  // The browser tab names the page: its heading ("INV-090", "Journal
  // Entries"), Home on the dashboard, so tabs and history can be told apart.
  useEffect(() => {
    const id = requestAnimationFrame(() => {
      const h1 = ["/", "/dashboard/"].includes(url.split("?")[0]) ? "" : document.querySelector(".page-shell h1")?.textContent?.trim();
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
      const scope = f.closest('[role="dialog"]') || document.querySelector(".page-shell");
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
  const collapseMounted = useRef(false);
  useEffect(() => {
    const shell = document.querySelector(".page-shell");
    const before = shell?.getBoundingClientRect().left;
    document.body.classList.toggle("sidebar-collapsed", collapsed);
    if (!collapseMounted.current) { collapseMounted.current = true; return; }
    if (!shell || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const dx = before - shell.getBoundingClientRect().left;
    if (dx) shell.animate([{ transform: `translateX(${dx}px)` }, { transform: "none" }], { duration: 300, easing: "cubic-bezier(.32,.72,0,1)" });
  }, [collapsed]);
  useEffect(() => () => document.body.classList.remove("sidebar-collapsed"), []);

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
    try { window.localStorage.setItem(MINI_KEY, m ? "1" : "0"); } catch { /* storage blocked */ }
    setCollapsed(m);
  };

  const doSwitch = (b) => {
    setConfirmTo(null);
    dirty.current = null;
    try { window.sessionStorage.setItem(TOAST_KEY, b.name); } catch { /* storage blocked */ }
    document.body.classList.add("ks-switching");
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
  const avatar = (lg) => (
    <span className={"ks-av" + (lg ? " lg" : "")}>
      {user.avatar ? <img src={user.avatar} alt="" /> : <UserGlyph />}
    </span>
  );
  const notifGroup = (title, rows) => rows.length > 0 && (
    <div role="group" aria-label={title}>
      <div className="ks-sg">{title}</div>
      {rows.map((n, i) => (
        <Link key={i} className="ks-nr" href={n.url} onClick={() => setNotif(false)}>
          <span className="mono">{n.ref}</span><span className="nm">{n.title}</span>
          <span className={"smeta" + (n.days <= 1 ? " hot" : "")}>{notifLabel(n)}</span>
          {n.type === "invoice_due" && <span className="amt">{fmtSar(n.remaining)} SAR</span>}
        </Link>
      ))}
    </div>
  );

  return (
    <FormModalProvider>
      <div data-page={page}>
      <a className="skip-link" href="#main">{t("Skip to content")}</a>
      {user && (
        <>
          {!isMap && <ShellSidebar page={page} perms={perms} theme={theme} branch={branch} mini={collapsed} onPickBranch={pickBranch} onToggleMini={toggleMini} />}

          <header className={"hms-topbar ks-tb" + (lift ? " lift" : "")}>
            <div className="ks-tl">
              <span className="ks-pt day">{dayLabel}</span>
            </div>
            <div className="ks-tr">
              <TopbarSearch ref={searchRef} perms={perms} branchName={branch.current?.name} />

              <div className="ks-anchor" ref={notifWrap}>
                <button type="button" className="ks-ib" aria-label={unread ? t("Notifications, {n} unread", { n: unread }) : t("Notifications")}
                  aria-haspopup="true" aria-expanded={notif}
                  onClick={() => { setNotif((v) => !v); setAccount(false); }}>
                  <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 16v-5a6 6 0 0112 0v5l2 2H4zM10 21h4" /></svg>
                  {unread > 0 && <span className="ks-nb">{unread > 9 ? "9+" : unread}</span>}
                </button>
                {notifShown && (
                  <div className={"ks-dd ks-ndd" + (notifClosing ? " is-closing" : "")}>
                    <div className="ks-nh">{t("Notifications")}{unread > 0 && <button type="button" className="ks-nlink" onClick={markRead}>{t("Mark all as read")}</button>}</div>
                    <div className="ks-nbody">
                      {dueNotifs.length === 0 && <div className="ks-nempty">{t("No notifications")}</div>}
                      {notifGroup(t("New"), fresh)}
                      {notifGroup(t("Earlier"), earlier)}
                    </div>
                  </div>
                )}
              </div>

              <span className="ks-div" aria-hidden="true" />
              <div className="ks-anchor" ref={accountWrap}>
                <button type="button" className="ks-acct" aria-label={t("Account, {name}", { name: displayName })} title={displayName}
                  aria-haspopup="menu" aria-expanded={account}
                  onClick={() => { setAccount((v) => !v); setNotif(false); }}>
                  {avatar(false)}
                </button>
                {acctShown && (
                  <div className={"ks-dd" + (acctClosing ? " is-closing" : "")} role="menu" style={{ width: 260 }}>
                    <div className="ks-ah">{avatar(true)}<span className="an"><b>{displayName}</b><span>{roleBranch}</span><span>{user.username}</span></span></div>
                    <Link className="ks-ar" href={NAV.account} role="menuitem" onClick={() => setAccount(false)}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4" /><path d="M4 20c1.5-4 4.5-6 8-6s6.5 2 8 6" /></svg>{t("My Profile")}
                    </Link>
                    <button type="button" className="ks-ar" role="menuitem" onClick={toggle}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>{t("Theme")}<span className="am">{theme === "light" ? t("Light") : t("Dark")}</span>
                    </button>
                    <button type="button" className="ks-ar" role="menuitem" onClick={() => setLanguage(locale === "en" ? "id" : "en")}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.5 3.8 5.5 3.8 9s-1.3 6.5-3.8 9c-2.5-2.5-3.8-5.5-3.8-9S9.5 5.5 12 3z" /></svg>{t("Language")}<span className="am">{locale === "en" ? "English" : "Indonesia"}</span>
                    </button>
                    <div className="ks-sep" />
                    <form method="post" action={NAV.logout} style={{ margin: 0 }}>
                      <Csrf />
                      <button type="submit" className="ks-ar danger" role="menuitem">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10" /></svg>{t("Log out")}
                      </button>
                    </form>
                  </div>
                )}
              </div>
            </div>
          </header>
        </>
      )}

      {user && (
        <>
          {/* ── Mobile top bar ── */}
          <header className="m-top-bar" id="m-top-bar">
            <div className="m-top-bar-left">
              <span className="m-top-bar-title">{pageTitle}</span>
            </div>
            <div className="m-top-bar-right">
              <button type="button" className="m-top-bar-btn" aria-label="Search"
                onClick={(e) => { e.stopPropagation(); setSearch(true); }}>
                <Icon name="search" size={19} strokeWidth={1.8} />
              </button>
              <button type="button" className="m-top-bar-btn" aria-label="Notifications"
                aria-haspopup="true" aria-expanded={mNotif}
                onClick={(e) => { e.stopPropagation(); setMNotif((v) => !v); setMAccount(false); setMMore(false); }}>
                <Icon name="bell" size={19} strokeWidth={1.8} />
                {dueNotifs.length > 0 && <span className="m-top-bar-badge">{dueNotifs.length}</span>}
              </button>
              <button type="button" className="m-top-bar-btn" aria-label="Account"
                aria-haspopup="true" aria-expanded={mAccount}
                onClick={(e) => { e.stopPropagation(); setMAccount((v) => !v); setMNotif(false); setMMore(false); }}>
                <span className="m-top-bar-avatar">
                  {user.avatar
                    ? <img src={user.avatar} alt={user.username} />
                    : <span className="m-top-bar-avatar-default">{<UserGlyph />}</span>}
                </span>
              </button>
            </div>
          </header>

          {/* ── Mobile bottom nav ── */}
          <nav className="m-bottom-nav" id="m-bottom-nav">
            {BNAV_TABS.map((tab) => {
              const isMore = tab.key === "_more";
              const isActive = isMore ? mMore : page === tab.key;
              return isMore ? (
                <button key={tab.key}
                  type="button"
                  className={"m-bnav-tab" + (isActive ? " active" : "")}
                  onClick={() => { setMMore((v) => !v); setMNotif(false); setMAccount(false); }}>
                  <span className="m-bnav-icon"><Icon name={tab.icon} strokeWidth={isActive ? 2 : 1.8} /></span>
                  <span className="m-bnav-label">{t(tab.label)}</span>
                </button>
              ) : (
                <Link key={tab.key} href={NAV[tab.key]}
                  className={"m-bnav-tab" + (isActive ? " active" : "")}>
                  <span className="m-bnav-icon"><Icon name={tab.icon} strokeWidth={isActive ? 2 : 1.8} /></span>
                  <span className="m-bnav-label">{t(tab.label)}</span>
                </Link>
              );
            })}
          </nav>

          {/* ── Mobile More page (full-screen module grid) ── */}
          {mMore && (
            <MobileMore page={page} perms={perms} onClose={() => setMMore(false)} />
          )}

          {/* ── Mobile account sheet (v2.1 bottom sheet) ── */}
          {mAccount && <div className="m-sheet-scrim" onClick={() => setMAccount(false)} />}
          <div className={"m-acct-sheet" + (mAccount ? " open" : "")} onClick={(e) => e.stopPropagation()}
            ref={(el) => { if (el) el.inert = !mAccount; }} role={mAccount ? "dialog" : undefined} aria-hidden={!mAccount} aria-label={t("Account")}>
            <span className="m-sheet-grab" aria-hidden="true" />
            <div className="m-acct-sheet-head">
              <span className="m-acct-sheet-avatar">
                {user.avatar ? <img src={user.avatar} alt={user.username} /> : <UserGlyph />}
              </span>
              <span className="m-acct-sheet-id">
                <span className="m-acct-sheet-name">{user.username}</span>
                <span className="m-acct-sheet-full">{user.name && user.name !== user.username ? user.name : user.role_label}</span>
              </span>
              <span className="hms-acct-role">{user.role_label || (user.is_superuser ? t("Admin") : user.is_staff ? t("Staff") : t("Member"))}</span>
            </div>
            <a href={NAV.account} className="m-acct-row"><Icon name="user" size={18} /><span>{t("My Profile")}</span></a>
            <button type="button" className="m-acct-row" onClick={toggle}>
              <Icon name={theme === "light" ? "sun" : "moon"} size={18} /><span>{t("Theme")}</span>
              <span className="hms-acct-meta">{theme === "light" ? t("Light") : t("Dark")}</span>
            </button>
            <div className="m-acct-row m-acct-row--lang">
              <Icon name="globe" size={18} /><span>{t("Language")}</span>
              <LanguageSwitcher variant="mini" />
            </div>
            <form method="post" action={NAV.logout} style={{ margin: 0 }}>
              <Csrf />
              <button type="submit" className="m-acct-row m-acct-row--danger"><Icon name="logout" size={18} /><span>{t("Log out")}</span></button>
            </form>
            <button type="button" className="m-acct-sheet-close" onClick={() => setMAccount(false)}>{t("Close")}</button>
          </div>

          {/* ── Mobile notification sheet: the account sheet's frame, the desktop list's groups ── */}
          {mNotif && <div className="m-sheet-scrim" onClick={() => setMNotif(false)} />}
          <div className={"m-acct-sheet m-ntf-sheet" + (mNotif ? " open" : "")} onClick={(e) => e.stopPropagation()}
            ref={(el) => { if (el) el.inert = !mNotif; }} role={mNotif ? "dialog" : undefined} aria-hidden={!mNotif} aria-label={t("Notifications")}>
            <span className="m-sheet-grab" aria-hidden="true" />
            <div className="m-ntf-head">
              <span>{t("Notifications")}</span>
              {unread > 0 && <button type="button" className="m-ntf-mark" onClick={markRead}>{t("Mark all as read")}</button>}
            </div>
            <div className="m-ntf-body">
              {dueNotifs.length === 0 && <div className="m-ntf-empty">{t("No notifications")}</div>}
              {[[t("New"), fresh], [t("Earlier"), earlier]].map(([title, rows]) => rows.length > 0 && (
                <div key={title} role="group" aria-label={title}>
                  <div className="m-ntf-group">{title}</div>
                  {rows.map((n, i) => (
                    <Link key={i} className="m-ntf-row" href={n.url} onClick={() => setMNotif(false)}>
                      <span className="nm">{n.title}</span>
                      <span className={"when" + (n.days <= 1 ? " hot" : "")}>{notifLabel(n)}</span>
                      <span className="ref">{n.ref}</span>
                      {n.type === "invoice_due" && <span className="amt">{fmtSar(n.remaining)} SAR</span>}
                    </Link>
                  ))}
                </div>
              ))}
            </div>
            <button type="button" className="m-acct-sheet-close" onClick={() => setMNotif(false)}>{t("Close")}</button>
          </div>
        </>
      )}

      {/* v2.1 is a flat solid canvas — no ambient blobs, gradients, or texture. */}
      <div className="page-shell" id="main" tabIndex={-1}>{children}</div>

      {confirmTo && (
        <div className="ks-cq" onMouseDown={(e) => { if (e.target === e.currentTarget) setConfirmTo(null); }}>
          <div className="ks-cdlg" role="alertdialog" aria-modal="true" aria-labelledby="ks-cdt">
            <h2 id="ks-cdt">{t("Switch to {name}?", { name: confirmTo.name })}</h2>
            <p>{t("You have unsaved changes in")} <b>{dirty.current}</b>. {t("Switching branch reloads the page and these changes will be lost.")}</p>
            <div className="ks-cda">
              <button type="button" className="ks-b2" autoFocus onClick={() => setConfirmTo(null)}>{t("Stay on {name}", { name: branch.current?.name || "" })}</button>
              <button type="button" className="ks-bd" onClick={() => doSwitch(confirmTo)}>{t("Discard and switch")}</button>
            </div>
          </div>
        </div>
      )}
      {toast && (
        <div className="ks-toast" role="status">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10" /></svg>
          <span>{t("Now showing")} <b>{toast}</b></span>
        </div>
      )}
      <Toast />
      {user && <SearchOverlay open={search} onClose={() => setSearch(false)} />}
      {user && <DraftModal />}
      </div>
    </FormModalProvider>
  );
}
