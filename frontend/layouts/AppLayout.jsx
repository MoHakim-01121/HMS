import { useEffect, useRef, useState } from "react";
import { usePage } from "@inertiajs/react";
import { useTheme } from "./useTheme.js";
import { Icon, BrandMark } from "../components/icons.jsx";
import { getCsrf } from "../utils/csrf.js";
import SearchOverlay from "../components/shell/SearchOverlay.jsx";
import DraftModal from "../components/shell/DraftModal.jsx";
import Toast from "../components/shell/Toast.jsx";

// Paths to pages that are NOT yet migrated to Inertia → use a plain <a>
// (a full reload), since an Inertia <Link> would error on a non-Inertia response.
const NAV = {
  home: "/",
  cl: "/cl/",
  invoice: "/invoice/",
  hotels: "/hotels/",
  calendar: "/calendar/",
  account: "/account/profile/",
  logout: "/logout/",
  company: "/company/set/",
};

function pageKeyFromUrl(url) {
  if (url === "/" || url === "") return "home";
  const map = [
    ["/hotels", "hotels"], ["/invoice", "invoice"], ["/services", "services"],
    ["/calendar", "calendar"], ["/clients", "clients"], ["/remittance", "remittance"],
    ["/cl", "cl"], ["/users", "users"], ["/account", "users"],
  ];
  for (const [pre, key] of map) if (url.startsWith(pre)) return key;
  return "home";
}

function Csrf() {
  return <input type="hidden" name="csrfmiddlewaretoken" value={getCsrf()} />;
}

export default function AppLayout({ children }) {
  const { props, url } = usePage();
  const user = props.auth?.user;
  const activeCompany = props.active_company;
  const dueCount = props.due_soon_count || 0;
  const dueNotifs = props.due_soon_notifs || [];
  const { theme, toggle } = useTheme();
  const page = pageKeyFromUrl(url);

  const [search, setSearch] = useState(false);
  const [notif, setNotif] = useState(false);
  const [account, setAccount] = useState(false);
  const [mAccount, setMAccount] = useState(false);
  const accountWrap = useRef(null);

  // Global `/` to open search, `Esc` to close everything.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") { setSearch(false); setNotif(false); setAccount(false); setMAccount(false); }
      const tag = document.activeElement?.tagName;
      if (e.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA") { e.preventDefault(); setSearch(true); }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Close dropdowns on outside click.
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

  const NotifList = () => (
    <>
      <div className="notif-head">
        <span>Notifications</span>
        {dueCount > 0 && <span className="notif-head-count">{dueCount} due</span>}
      </div>
      {dueNotifs.length ? (
        dueNotifs.map((n, i) => (
          <a key={i} href={n.url} className="notif-item">
            <div className="notif-item-top">
              <span className="notif-ref">{n.inv_number}</span>
              <span className={"notif-days" + (n.days === 0 ? " notif-today" : n.days <= 2 ? " notif-urgent" : "")}>{n.label}</span>
            </div>
            <div className="notif-item-bot">
              <span className="notif-customer">{n.customer}</span>
              <span className="notif-amount">{new Intl.NumberFormat("en-US").format(Math.round(n.remaining))} SAR</span>
            </div>
          </a>
        ))
      ) : (
        <div className="notif-empty">No notifications</div>
      )}
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

  return (
    <div data-page={page}>
      {/* ── Desktop topbar ── */}
      <nav className="topbar">
        <a href={NAV.home} className="topbar-brand"><BrandMark /> Workspace</a>
        <div className="topbar-space"></div>

        {user && (
          <div className="topbar-right">
            <button type="button" className="topbar-icon-btn" title="Search (/)" aria-label="Search"
              onClick={(e) => { e.stopPropagation(); setSearch(true); }}>
              <Icon name="search" />
            </button>

            <button type="button" className="topbar-icon-btn" title="Notifications" aria-label="Notifications"
              onClick={(e) => { e.stopPropagation(); setNotif((v) => !v); setAccount(false); }}>
              <Icon name="bell" />
              {dueCount > 0 && <span className="notif-badge">{dueCount}</span>}
            </button>

            <button type="button" className="topbar-icon-btn" title="Toggle theme" aria-label="Toggle theme" onClick={toggle}>
              <Icon name={theme === "light" ? "sun" : "moon"} />
            </button>

            <div className="account-wrap" ref={accountWrap}>
              <button type="button" className="account-btn" aria-label="Account"
                onClick={(e) => { e.stopPropagation(); setAccount((v) => !v); setNotif(false); }}>
                {user.avatar
                  ? <img src={user.avatar} className="account-avatar-img" alt={user.username} />
                  : <Icon name="user" size={18} strokeWidth={0} fill="currentColor" className="account-avatar-default" />}
                <span className="account-username">{user.username}</span>
                <Icon name="chevron" size={10} strokeWidth={2.5} className="account-chevron" />
              </button>
              <div className={"account-dropdown" + (account ? " open" : "")}>
                <div className="account-dd-head">
                  <span className="account-dd-name">{user.username}</span>
                  {user.is_superuser && <span className="account-dd-role">Admin</span>}
                </div>
                <a href={NAV.account} className="co-option"><Icon name="user" size={13} /> My Profile</a>
                <div className="co-dropdown-sep"></div>
                <CompanySwitch />
                <form method="post" action={NAV.logout} style={{ margin: 0 }}>
                  <Csrf />
                  <button type="submit" className="co-option co-option-muted"><Icon name="logout" size={13} /> Log out</button>
                </form>
              </div>
            </div>
          </div>
        )}
      </nav>

      {user && (
        <>
          {/* ── Mobile top-right utility cluster ── */}
          <div className="m-topbar" id="m-topbar">
            <button type="button" className="m-top-btn" aria-label="Search" onClick={(e) => { e.stopPropagation(); setSearch(true); }}>
              <Icon name="search" size={17} strokeWidth={1.8} />
            </button>
            <button type="button" className="m-top-btn" aria-label="Notifications" onClick={(e) => { e.stopPropagation(); setNotif((v) => !v); }}>
              <Icon name="bell" size={17} strokeWidth={1.8} />
              {dueCount > 0 && <span className="m-top-badge">{dueCount}</span>}
            </button>
            <button type="button" className="m-top-avatar" aria-label="Account" onClick={(e) => { e.stopPropagation(); setMAccount((v) => !v); }}>
              {user.avatar ? <img src={user.avatar} alt={user.username} /> : <Icon name="user" size={18} strokeWidth={0} fill="currentColor" />}
            </button>
          </div>

          {/* ── Mobile bottom tab bar ── */}
          <nav className="bottom-nav" id="bottom-nav">
            <a href={NAV.cl} className="bnav-tab bnav-tab-cl"><Icon name="cl" strokeWidth={1.8} /><span className="bnav-label">CL</span></a>
            <a href={NAV.invoice} className="bnav-tab bnav-tab-invoice"><Icon name="invoice" strokeWidth={1.8} /><span className="bnav-label">Invoice</span></a>
            <a href={NAV.home} className="bnav-home" aria-label="Home"><Icon name="home" strokeWidth={1.8} /></a>
            <a href={NAV.hotels} className="bnav-tab bnav-tab-hotels"><Icon name="hotels" strokeWidth={1.8} /><span className="bnav-label">Hotels</span></a>
            <a href={NAV.calendar} className="bnav-tab bnav-tab-calendar"><Icon name="calendar" strokeWidth={1.8} /><span className="bnav-label">Calendar</span></a>
          </nav>

          {/* ── Mobile account dropdown ── */}
          <div className={"bnav-account-dd" + (mAccount ? " open" : "")} onClick={(e) => e.stopPropagation()}>
            <div className="bnav-account-head">
              <span className="bnav-account-name">{user.username}</span>
              {user.is_superuser ? <span className="badge badge-blue" style={{ fontSize: 9 }}>Admin</span>
                : user.is_staff ? <span className="badge badge-green" style={{ fontSize: 9 }}>Staff</span> : null}
            </div>
            <a href={NAV.account} className="co-option"><Icon name="user" size={13} /> My Profile</a>
            <button type="button" className="co-option" onClick={toggle}>
              <Icon name={theme === "light" ? "sun" : "moon"} size={13} /> Toggle Theme
            </button>
            <div className="co-dropdown-sep"></div>
            <CompanySwitch />
            <form method="post" action={NAV.logout} style={{ margin: 0 }}>
              <Csrf />
              <button type="submit" className="co-option co-option-muted"><Icon name="logout" size={13} /> Log out</button>
            </form>
          </div>

          {/* ── Shared notification dropdown ── */}
          {notif && (
            <div className="notif-dropdown open" style={{ position: "fixed", top: 54, right: 14, width: 300, zIndex: "var(--z-overlay)" }} onClick={(e) => e.stopPropagation()}>
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
  );
}
