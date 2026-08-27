import { useEffect, useRef, useState } from "react";
import { Link, router, usePage } from "@inertiajs/react";
import { useTheme } from "./useTheme.js";
import { Icon } from "../components/icons.jsx";
import { getCsrf } from "../utils/csrf.js";
import { useI18n } from "../utils/i18n.jsx";
import SearchOverlay from "../components/shadcn/search-overlay.jsx";
import DraftModal from "../components/shell/DraftModal.jsx";
import Toast, { showToast } from "../components/shell/Toast.jsx";
import LanguageSwitcher from "../components/shell/LanguageSwitcher.jsx";
import { FormModalProvider } from "../components/shadcn/form-modal.jsx";

// Paths to pages that are NOT yet migrated to Inertia → use a plain <a>
// (a full reload), since an Inertia <Link> would error on a non-Inertia response.
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
  company: "/company/set/",
};

// Sidebar navigation, grouped as in the shell CSS (Operations / Schedule / Admin).
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
      { key: "remittance", label: "Remittance", href: NAV.remittance, icon: "remittance", perm: "remittance" },
    ],
  },
  {
    heading: "Finance",
    items: [
      { key: "payments", label: "Payments", href: "/finance/payments/", icon: "remittance", perm: "invoice" },
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
  users: "Users",
  roles: "Role",
};

const COMPANY_NAMES = { konoz: "Konoz United", ijabah: "Ijabah" };
const COMPANY_MARKS = { konoz: "K", ijabah: "I" };

// Bottom nav mobile: 5 tab setara; tab aktif terangkat dalam disc (docked notch).
const BNAV_TABS = [
  { key: "cl", label: "CL", icon: "cl" },
  { key: "invoice", label: "Invoice", icon: "invoice" },
  { key: "home", label: "Home", icon: "home" },
  { key: "hotels", label: "Hotels", icon: "hotels" },
  { key: "calendar", label: "Calendar", icon: "calendar" },
];

function pageKeyFromUrl(url) {
  if (url === "/" || url === "") return "home";
  const map = [
    ["/hotels", "hotels"], ["/invoice", "invoice"], ["/services", "services"],
    ["/calendar", "calendar"], ["/clients", "clients"],     ["/remittance", "remittance"],
    ["/cl", "cl"], ["/users", "users"], ["/roles", "roles"], ["/account", "users"],
    ["/finance/payments", "payments"], ["/finance/periods", "periods"],
  ];
  for (const [pre, key] of map) if (url.startsWith(pre)) return key;
  return "home";
}

function Csrf() {
  return <input type="hidden" name="csrfmiddlewaretoken" value={getCsrf()} />;
}

export default function AppLayout({ children }) {
  const { props, url } = usePage();
  const { t } = useI18n();
  const user = props.auth?.user;
  const activeCompany = props.active_company;
  const dueCount = props.due_soon_count || 0;
  const dueNotifs = props.due_soon_notifs || [];
  const { theme, toggle } = useTheme();
  const page = pageKeyFromUrl(url);
  // Fullscreen map pages (client/hotel maps) drop the shell chrome entirely —
  // no sidebar, topbar or bottom nav, so the map owns the whole viewport.
  const isMap = url.split("?")[0].includes("/map/");
  const bnavIdx = BNAV_TABS.findIndex((t) => t.key === page);

  const [search, setSearch] = useState(false);
  const [notif, setNotif] = useState(false);
  const [account, setAccount] = useState(false);
  const [mAccount, setMAccount] = useState(false);
  const [wsOpen, setWsOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const accountWrap = useRef(null);
  const wsWrap = useRef(null);

  // Global `/` to open search, `Esc` to close everything.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") { setSearch(false); setNotif(false); setAccount(false); setMAccount(false); setWsOpen(false); }
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

  // Close dropdowns on outside click.
  useEffect(() => {
    const onClick = (e) => {
      if (wsWrap.current && !wsWrap.current.contains(e.target)) setWsOpen(false);
      if (accountWrap.current && !accountWrap.current.contains(e.target)) setAccount(false);
      setNotif(false);
      setMAccount(false);
    };
    if (account || notif || mAccount || wsOpen) {
      document.addEventListener("click", onClick);
      return () => document.removeEventListener("click", onClick);
    }
  }, [account, notif, mAccount, wsOpen]);

  // Sidebar collapse is driven by a class on <body> (see tailwind.css).
  useEffect(() => {
    document.body.classList.toggle("sidebar-collapsed", collapsed);
    return () => document.body.classList.remove("sidebar-collapsed");
  }, [collapsed]);

  // Fullscreen maps hide the app shell (sidebar/topbar/bottom nav) so the map
  // fills the viewport — see the body.map-fullscreen rules in tailwind.css.
  useEffect(() => {
    document.body.classList.toggle("map-fullscreen", isMap);
    return () => document.body.classList.remove("map-fullscreen");
  }, [isMap]);

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

  const CompanySwitch = () => (
    activeCompany ? (
      <>
        <form method="post" action={NAV.company}>
          <Csrf />
          <button type="submit" name="company" value="konoz" className={"co-option" + (activeCompany === "konoz" ? " co-active" : "")}>
            <span className="co-dot co-dot-konoz"></span>Konoz United
            {activeCompany === "konoz" && <Icon name="check" size={12} strokeWidth={2.5} style={{ marginLeft: "auto" }} />}
          </button>
          <button type="submit" name="company" value="ijabah" className={"co-option" + (activeCompany === "ijabah" ? " co-active" : "")}>
            <span className="co-dot co-dot-ijabah"></span>Ijabah
            {activeCompany === "ijabah" && <Icon name="check" size={12} strokeWidth={2.5} style={{ marginLeft: "auto" }} />}
          </button>
        </form>
        <div className="co-dropdown-sep"></div>
      </>
    ) : null
  );

  const wsName = activeCompany ? COMPANY_NAMES[activeCompany] : "Workspace";
  const wsMark = activeCompany ? COMPANY_MARKS[activeCompany] : "W";
  const wsRole = user ? (user.is_superuser ? t("Admin") : user.is_staff ? t("Staff") : t("User")) : "";
  const pageTitle = t(PAGE_TITLES[page] || "Home");
  const perms = user?.perms || {};

  return (
    <FormModalProvider>
      <div data-page={page}>
      {user && (
        <>
          {/* ── Desktop sidebar (Homlu/shadcn shell, tailwind.css .hms-sidebar) ── */}
          <aside className="hms-sidebar" aria-label="Sidebar">
            <div className={"hms-ws-switcher" + (wsOpen ? " open" : "")} ref={wsWrap}>
              <button type="button" className="hms-ws-trigger" aria-haspopup="true" aria-expanded={wsOpen}
                title={t("Switch workspace")}
                onClick={(e) => { e.stopPropagation(); setWsOpen((v) => !v); setAccount(false); setNotif(false); }}>
                <span className="hms-ws-mark">{wsMark}</span>
                <span className="hms-ws-text">
                  <span className="hms-ws-name">{wsName}</span>
                  <span className="hms-ws-role">{wsRole}</span>
                </span>
                <Icon name="chevron" size={12} strokeWidth={2.5} className="hms-ws-chevron" />
              </button>
              {wsOpen && activeCompany && (
                <div className="hms-ws-panel" style={{ minWidth: 220 }} onClick={(e) => e.stopPropagation()}>
                  <div className="hms-ws-panel-label">{t("Workspace")}</div>
                  <CompanySwitch />
                </div>
              )}
            </div>

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

          {/* ── Desktop topbar (Homlu/shadcn shell, tailwind.css .hms-topbar) ── */}
          <header className="hms-topbar">
            <div className="hms-topbar-left">
              <button type="button" className="hms-collapse-btn"
                title={collapsed ? t("Expand sidebar") : t("Collapse sidebar")}
                aria-label={collapsed ? t("Expand sidebar") : t("Collapse sidebar")}
                onClick={() => setCollapsed((v) => !v)}>
                <Icon name={collapsed ? "panel-left-open" : "panel-left-close"} size={16} />
              </button>
              <div className="hms-topbar-crumb">
                <span className="hms-topbar-crumb-ws">{wsName}</span>
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
                  <CompanySwitch />
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
          {/* ── Mobile top-right utility cluster ── */}
          <div className="m-topbar" id="m-topbar">
            <button type="button" className="m-top-btn" aria-label="Search" onClick={(e) => { e.stopPropagation(); setSearch(true); }}>
              <Icon name="search" size={17} strokeWidth={1.8} />
            </button>
            <button type="button" className="m-top-btn" aria-label="Notifications" aria-haspopup="true" aria-expanded={notif} onClick={(e) => { e.stopPropagation(); setNotif((v) => !v); }}>
              <Icon name="bell" size={17} strokeWidth={1.8} />
              {dueCount > 0 && <span className="m-top-badge">{dueCount}</span>}
            </button>
            <button type="button" className="m-top-avatar" aria-label="Account" aria-haspopup="true" aria-expanded={mAccount} onClick={(e) => { e.stopPropagation(); setMAccount((v) => !v); }}>
              {user.avatar ? <img src={user.avatar} alt={user.username} /> : <Icon name="user" size={18} strokeWidth={0} fill="currentColor" />}
            </button>
          </div>

          {/* ── Mobile bottom tab bar (docked notch: disc mengikuti tab aktif) ── */}
          <nav
            className={"bottom-nav" + (bnavIdx < 0 ? " bnav-flat" : "")}
            id="bottom-nav"
            style={{ "--bnav-i": bnavIdx < 0 ? 2 : bnavIdx }}
          >
            <div className="bnav-disc" aria-hidden="true"></div>
            {BNAV_TABS.map((tab, i) => (
              <Link key={tab.key} href={NAV[tab.key]} className={"bnav-tab" + (i === bnavIdx ? " bnav-active" : "")}>
                <span className="bnav-ico"><Icon name={tab.icon} strokeWidth={1.8} /></span>
                <span className="bnav-label">{t(tab.label)}</span>
              </Link>
            ))}          </nav>

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
            <CompanySwitch />
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
