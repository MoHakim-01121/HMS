import { useEffect, useRef, useState, useMemo } from "react";
import { Link, router, usePage } from "@inertiajs/react";
import { useTheme } from "./useTheme.js";
import { Icon } from "../components/icons.jsx";
import { getCsrf } from "../utils/csrf.js";
import { useI18n } from "../utils/i18n.jsx";
import SearchOverlay from "../components/shadcn/search-overlay.jsx";
import DraftModal from "../components/shadcn/draft-modal.jsx";
import Toast, { showToast } from "../components/shadcn/toast.jsx";
import LanguageSwitcher from "../components/shell/LanguageSwitcher.jsx";
import { FormModalProvider } from "../components/shadcn/form-modal.jsx";

const NAV = {
  home: "/",
  cl: "/cl/",
  invoice: "/invoice/",
  hotels: "/hotels/",
  calendar: "/calendar/",
  services: "/services/",
  clients: "/clients/",
  remittance: "/remittance/",
  users: "/users/",
  roles: "/roles/",
  account: "/account/profile/",
  logout: "/logout/",
};

const NAV_GROUPS = [
  {
    heading: "Overview",
    items: [{ key: "home", label: "Home", href: NAV.home, icon: "home" }],
  },
  {
    heading: "Operations",
    items: [
      { key: "cl", label: "Conf Letter", href: NAV.cl, icon: "cl", perm: "cl" },
      { key: "invoice", label: "Invoice", href: NAV.invoice, icon: "invoice", perm: "invoice" },
      { key: "hotels", label: "Hotels", href: NAV.hotels, icon: "hotels", perm: "hotels" },
      { key: "services", label: "Services", href: NAV.services, icon: "services", perm: "services" },
      { key: "clients", label: "Clients", href: NAV.clients, icon: "clients", perm: "clients" },
    ],
  },
  {
    heading: "Finance",
    items: [
      { key: "payments", label: "Payments", href: "/finance/payments/", icon: "remittance", perm: "invoice" },
      { key: "remittance", label: "Remittance", href: NAV.remittance, icon: "wallet", perm: "remittance" },
      { key: "statements", label: "Client Ledger", href: "/finance/statements/", icon: "clients", perm: "clients" },
      { key: "penalties", label: "Penalties", href: "/finance/penalties/", icon: "tag", perm: "penalty" },
      { key: "journal", label: "Journal", href: "/finance/journal/", icon: "invoice", perm: "invoice" },
      { key: "trial_balance", label: "Trial Balance", href: "/finance/trial-balance/", icon: "sort", perm: "invoice" },
      { key: "periods", label: "Periods", href: "/finance/periods/", icon: "calendar", perm: "remittance" },
    ],
  },
  {
    heading: "Schedule",
    items: [
      { key: "calendar", label: "Calendar", href: NAV.calendar, icon: "calendar", perm: "calendar" },
    ],
  },
  {
    heading: "Admin",
    items: [
      { key: "users", label: "Users", href: NAV.users, icon: "users", perm: "users" },
      { key: "roles", label: "Role", href: NAV.roles, icon: "shield", perm: "users" },
    ],
  },
];

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
  periods: "Periods",
  statements: "Client Ledger",
  penalties: "Penalties",
  journal: "Journal",
  trial_balance: "Trial Balance",
  users: "Users",
  roles: "Role",
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
    ["/hotels", "hotels"], ["/invoice", "invoice"], ["/services", "services"],
    ["/calendar", "calendar"], ["/clients", "clients"], ["/remittance", "remittance"],
    ["/cl", "cl"], ["/users", "users"], ["/roles", "roles"], ["/account", "users"],
    ["/finance/payments", "payments"], ["/finance/periods", "periods"],
    ["/finance/journal", "journal"], ["/finance/trial-balance", "trial_balance"],
    ["/finance/statements", "statements"], ["/finance/penalties", "penalties"],
    ["/penalty", "penalties"],
  ];
  for (const [pre, key] of map) if (url.startsWith(pre)) return key;
  return "home";
}

function Csrf() {
  return <input type="hidden" name="csrfmiddlewaretoken" value={getCsrf()} />;
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
    const filtered = NAV_GROUPS.map((g) => ({
      ...g,
      items: g.items.filter((it) => {
        if (it.key === "home") return false; // already in bottom nav
        if (!it.perm || (perms[it.perm] || []).length) {
          if (!query) return true;
          return t(it.label).toLowerCase().includes(query.toLowerCase());
        }
        return false;
      }),
    })).filter((g) => g.items.length);
    return filtered;
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
          <div key={g.heading} className="m-more-group">
            <div className="m-more-heading">{t(g.heading)}</div>
            {g.items.map((item) => (
              <a
                key={item.key}
                href={item.href}
                className={"m-more-item" + (page === item.key ? " active" : "")}
                onClick={onClose}
              >
                <span className="m-more-icon"><Icon name={item.icon} size={20} strokeWidth={1.8} /></span>
                <span className="m-more-label">{t(item.label)}</span>
              </a>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AppLayout({ children }) {
  const { props, url } = usePage();
  const { t } = useI18n();
  const user = props.auth?.user;
  const dueCount = props.due_soon_count || 0;
  const dueNotifs = props.due_soon_notifs || [];
  const { theme, toggle } = useTheme();
  const page = pageKeyFromUrl(url);
  const isMap = url.split("?")[0].includes("/map/");

  const [search, setSearch] = useState(false);
  const [notif, setNotif] = useState(false);
  const [account, setAccount] = useState(false);
  const [mAccount, setMAccount] = useState(false);
  const [mMore, setMMore] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const accountWrap = useRef(null);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") { setSearch(false); setNotif(false); setAccount(false); setMAccount(false); setMMore(false); }
      const tag = document.activeElement?.tagName;
      if (e.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA") { e.preventDefault(); setSearch(true); }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
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

  useEffect(() => {
    const onClick = (e) => {
      if (accountWrap.current && !accountWrap.current.contains(e.target)) setAccount(false);
      setNotif(false);
      setMAccount(false);
    };
    if (account || notif || mAccount) {
      document.addEventListener("click", onClick);
      return () => document.removeEventListener("click", onClick);
    }
  }, [account, notif, mAccount]);

  useEffect(() => {
    document.body.classList.toggle("sidebar-collapsed", collapsed);
    return () => document.body.classList.remove("sidebar-collapsed");
  }, [collapsed]);

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

  const notifLabel = (n) => {
    const kind = n.type === "check_in" ? "Check-in" : n.type === "check_out" ? "Check-out" : "Due";
    if (n.days === 0) return t(`${kind} today`);
    if (n.days === 1) return t(`${kind} tomorrow`);
    return t(`${kind} in {n} days`, { n: n.days });
  };

  const NotifList = () => (
    <>
      <div className="notif-head">
        <span>{t("Notifications")}</span>
        {dueCount > 0 && <span className="notif-head-count">{t("{count} upcoming", { count: dueCount })}</span>}
      </div>
      <div className="notif-body">
        {dueNotifs.length ? (
          dueNotifs.map((n, i) => (
            <a key={i} href={n.url} className="notif-item">
              <div className="notif-item-top">
                <span className="notif-ref">{n.ref}</span>
                <span className={"notif-days" + (n.days === 0 ? " notif-today" : n.days <= 2 ? " notif-urgent" : "")}>{notifLabel(n)}</span>
              </div>
              <div className="notif-item-bot">
                <span className="notif-customer">{n.title}</span>
                <span className="notif-amount">
                  {n.type === "invoice_due"
                    ? `${new Intl.NumberFormat("en-US").format(Math.round(n.remaining))} SAR`
                    : n.meta}
                </span>
              </div>
            </a>
          ))
        ) : (
          <div className="notif-empty">{t("No notifications")}</div>
        )}
      </div>
    </>
  );

  const pageTitle = t(PAGE_TITLES[page] || "Home");
  const perms = user?.perms || {};

  return (
    <FormModalProvider>
      <div data-page={page}>
      {user && (
        <>
          {/* ── Desktop sidebar ── */}
          <aside className="hms-sidebar" aria-label="Sidebar">
            <nav className="hms-sidebar-nav">
              {NAV_GROUPS.map((g) => {
                const items = g.items.filter((it) => !it.perm || (perms[it.perm] || []).length);
                if (!items.length) return null;
                return (
                  <div key={g.heading} className="hms-sidebar-group">
                    <div className="hms-sidebar-heading">{t(g.heading)}</div>
                    {items.map((item) => (
                      <a key={item.key} href={item.href}
                        className={"hms-sidebar-link" + (page === item.key ? " active" : "")}
                        title={t(item.label)}>
                        <Icon name={item.icon} size={18} />
                        <span>{t(item.label)}</span>
                      </a>
                    ))}
                  </div>
                );
              })}
            </nav>
          </aside>

          {/* ── Desktop topbar ── */}
          <header className="hms-topbar">
            <div className="hms-topbar-left">
              <button type="button" className="hms-collapse-btn"
                title={collapsed ? t("Expand sidebar") : t("Collapse sidebar")}
                aria-label={collapsed ? t("Expand sidebar") : t("Collapse sidebar")}
                onClick={() => setCollapsed((v) => !v)}>
                <Icon name={collapsed ? "panel-left-open" : "panel-left-close"} size={16} />
              </button>
              <div className="hms-topbar-crumb">
                <span className="hms-topbar-crumb-ws">Konoz United</span>
                <span className="hms-topbar-crumb-sep"><Icon name="chevron" size={12} strokeWidth={2.5} style={{ transform: "rotate(-90deg)" }} /></span>
                <span className="hms-topbar-crumb-page">{pageTitle}</span>
              </div>
            </div>

            <div className="hms-topbar-right">
              <button type="button" className="hms-topbar-search" title={`${t("Search")} (/)`} aria-label={t("Search")}
                onClick={() => setSearch(true)}>
                <Icon name="search" size={15} />
                <span>{t("Search")}</span>
                <kbd>/</kbd>
              </button>

              <button type="button" className="topbar-icon-btn" title={t("Notifications")} aria-label={t("Notifications")}
                aria-haspopup="true" aria-expanded={notif}
                onClick={(e) => { e.stopPropagation(); setNotif((v) => !v); setAccount(false); }}>
                <Icon name="bell" />
                {dueCount > 0 && <span className="notif-badge">{dueCount}</span>}
              </button>

              <button type="button" className="topbar-icon-btn" title={t("Toggle theme")} aria-label={t("Toggle theme")} onClick={toggle}>
                <Icon name={theme === "light" ? "sun" : "moon"} />
              </button>

              <LanguageSwitcher />

              <div className="hms-topbar-account" ref={accountWrap} style={{ position: "relative", display: "flex", alignItems: "center" }}>
                <button type="button" className="account-btn" aria-label="Account"
                  aria-haspopup="true" aria-expanded={account}
                  onClick={(e) => { e.stopPropagation(); setAccount((v) => !v); setNotif(false); }}>
                  {user.avatar
                    ? <img src={user.avatar} className="account-avatar-img" alt={user.username} />
                    : <Icon name="user" size={18} strokeWidth={0} fill="currentColor" className="account-avatar-default" />}
                  <span className="account-username">{user.username}</span>
                  <Icon name="chevron" size={10} strokeWidth={2.5} className="account-chevron" />
                </button>
                <div className={"account-dropdown hms-topbar-dropdown" + (account ? " open" : "")}>
                  <div className="account-dd-head">
                    <span className="account-dd-name">{user.username}</span>
                    {user.is_superuser && <span className="account-dd-role">{t("Admin")}</span>}
                  </div>
                  <a href={NAV.account} className="co-option"><Icon name="user" size={13} /> {t("My Profile")}</a>
                  <div className="co-dropdown-sep"></div>
                  <form method="post" action={NAV.logout} style={{ margin: 0 }}>
                    <Csrf />
                    <button type="submit" className="co-option co-option-muted"><Icon name="logout" size={13} /> {t("Log out")}</button>
                  </form>
                </div>
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
                aria-haspopup="true" aria-expanded={notif}
                onClick={(e) => { e.stopPropagation(); setNotif((v) => !v); setMAccount(false); setMMore(false); }}>
                <Icon name="bell" size={19} strokeWidth={1.8} />
                {dueCount > 0 && <span className="m-top-bar-badge">{dueCount}</span>}
              </button>
              <button type="button" className="m-top-bar-btn" aria-label="Account"
                aria-haspopup="true" aria-expanded={mAccount}
                onClick={(e) => { e.stopPropagation(); setMAccount((v) => !v); setNotif(false); setMMore(false); }}>
                <span className="m-top-bar-avatar">
                  {user.avatar
                    ? <img src={user.avatar} alt={user.username} />
                    : <span className="m-top-bar-avatar-default"><Icon name="user" size={16} strokeWidth={0} fill="currentColor" /></span>}
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
                  onClick={() => { setMMore((v) => !v); setNotif(false); setMAccount(false); }}>
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

          {/* ── Mobile account dropdown ── */}
          <div className={"bnav-account-dd" + (mAccount ? " open" : "")} onClick={(e) => e.stopPropagation()}>
            <div className="bnav-account-head">
              <span className="bnav-account-name">{user.username}</span>
              {user.is_superuser ? <span className="badge badge-blue" style={{ fontSize: 9 }}>{t("Admin")}</span>
                : user.is_staff ? <span className="badge badge-green" style={{ fontSize: 9 }}>{t("Staff")}</span> : null}
            </div>
            <a href={NAV.account} className="co-option"><Icon name="user" size={13} /> {t("My Profile")}</a>
            <button type="button" className="co-option" onClick={toggle}>
              <Icon name={theme === "light" ? "sun" : "moon"} size={13} /> {t("Toggle Theme")}
            </button>
            <LanguageSwitcher compact />
            <div className="co-dropdown-sep"></div>
            <form method="post" action={NAV.logout} style={{ margin: 0 }}>
              <Csrf />
              <button type="submit" className="co-option co-option-muted"><Icon name="logout" size={13} /> {t("Log out")}</button>
            </form>
          </div>

          {/* ── Shared notification dropdown ── */}
          {notif && (
            <div className="notif-dropdown notif-float open" onClick={(e) => e.stopPropagation()}>
              <NotifList />
            </div>
          )}
        </>
      )}

      {/* ── Animated ambient background ── */}
      <div className="base-bg" aria-hidden="true">
        <div className="base-blob base-blob-1"></div>
        <div className="base-blob base-blob-2"></div>
        <div className="base-blob base-blob-3"></div>
        <div className="base-blob base-blob-4"></div>
      </div>

      <div className="page-shell">{children}</div>

      <Toast />
      {user && <SearchOverlay open={search} onClose={() => setSearch(false)} />}
      {user && <DraftModal />}
      </div>
    </FormModalProvider>
  );
}
