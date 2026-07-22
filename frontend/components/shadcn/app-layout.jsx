import { useEffect, useState } from "react";
import { Link, usePage } from "@inertiajs/react";
import { useTheme } from "../../layouts/useTheme.js";
import { Icon, BrandMark } from "../icons.jsx";
import { getCsrf } from "../../utils/csrf.js";
import SearchOverlay from "./search-overlay.jsx";
import DraftModal from "./draft-modal.jsx";
import Toast from "./toast.jsx";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "./ui/dropdown-menu.jsx";

// shadcn rebuild of ../../layouts/AppLayout.jsx — same {children} prop, same
// behavior. Desktop account + notification dropdowns now use Radix
// DropdownMenu (batch 1's dropdown-menu.jsx): outside-click, Escape, and
// focus management are handled by the primitive, so the manual document
// click/keydown listeners the old version needed for those two are gone.
// The mobile bottom-nav and its account panel are intentionally left custom
// (restyled only) — they're anchored near the bottom nav for thumb reach,
// a deliberate mobile pattern that a generic trigger-anchored DropdownMenu
// would break by repositioning the panel back up near the avatar button.
// Also wires in the batch 1/2/3 shadcn Toast/SearchOverlay/DraftModal.

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
  const bnavIdx = BNAV_TABS.findIndex((t) => t.key === page);

  const [search, setSearch] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [mNotifOpen, setMNotifOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [mAccount, setMAccount] = useState(false);

  // Global `/` to open search. Escape for search + the custom mobile account
  // panel — the two Radix DropdownMenus already close on Escape themselves.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") { setSearch(false); setMAccount(false); }
      const tag = document.activeElement?.tagName;
      if (e.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA") { e.preventDefault(); setSearch(true); }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Outside-click for the custom mobile account panel only (the two Radix
  // DropdownMenus already close on outside click themselves).
  useEffect(() => {
    if (!mAccount) return;
    const onClick = () => setMAccount(false);
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, [mAccount]);

  const NotifList = () => (
    <>
      <DropdownMenuLabel style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span>Notifications</span>
        {dueCount > 0 && <span className="notif-head-count">{dueCount} due</span>}
      </DropdownMenuLabel>
      <DropdownMenuSeparator />
      {dueNotifs.length ? (
        dueNotifs.map((n, i) => (
          <DropdownMenuItem key={i} asChild>
            <a href={n.url} className="notif-item">
              <div className="notif-item-top">
                <span className="notif-ref">{n.inv_number}</span>
                <span className={"notif-days" + (n.days === 0 ? " notif-today" : n.days <= 2 ? " notif-urgent" : "")}>{n.label}</span>
              </div>
              <div className="notif-item-bot">
                <span className="notif-customer">{n.customer}</span>
                <span className="notif-amount">{new Intl.NumberFormat("en-US").format(Math.round(n.remaining))} SAR</span>
              </div>
            </a>
          </DropdownMenuItem>
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
          <DropdownMenuItem asChild>
            <button type="submit" name="company" value="konoz" className={"co-option" + (activeCompany === "konoz" ? " co-active" : "")}>
              <span className="co-dot co-dot-konoz"></span>Konoz United
              {activeCompany === "konoz" && <Icon name="check" size={12} strokeWidth={2.5} style={{ marginLeft: "auto" }} />}
            </button>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <button type="submit" name="company" value="ijabah" className={"co-option" + (activeCompany === "ijabah" ? " co-active" : "")}>
              <span className="co-dot co-dot-ijabah"></span>Ijabah
              {activeCompany === "ijabah" && <Icon name="check" size={12} strokeWidth={2.5} style={{ marginLeft: "auto" }} />}
            </button>
          </DropdownMenuItem>
        </form>
        <DropdownMenuSeparator />
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
            <button type="button" className="topbar-icon-btn" title="Search (/)" aria-label="Search" onClick={() => setSearch(true)}>
              <Icon name="search" />
            </button>

            <DropdownMenu open={notifOpen} onOpenChange={(v) => { setNotifOpen(v); if (v) setAccountOpen(false); }}>
              <DropdownMenuTrigger asChild>
                <button type="button" className="topbar-icon-btn" title="Notifications" aria-label="Notifications">
                  <Icon name="bell" />
                  {dueCount > 0 && <span className="notif-badge">{dueCount}</span>}
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" style={{ width: 320 }}>
                <NotifList />
              </DropdownMenuContent>
            </DropdownMenu>

            <button type="button" className="topbar-icon-btn" title="Toggle theme" aria-label="Toggle theme" onClick={toggle}>
              <Icon name={theme === "light" ? "sun" : "moon"} />
            </button>

            <DropdownMenu open={accountOpen} onOpenChange={(v) => { setAccountOpen(v); if (v) setNotifOpen(false); }}>
              <DropdownMenuTrigger asChild>
                <button type="button" className="account-btn" aria-label="Account">
                  {user.avatar
                    ? <img src={user.avatar} className="account-avatar-img" alt={user.username} />
                    : <Icon name="user" size={18} strokeWidth={0} fill="currentColor" className="account-avatar-default" />}
                  <span className="account-username">{user.username}</span>
                  <Icon name="chevron" size={10} strokeWidth={2.5} className="account-chevron" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" style={{ width: 220 }}>
                <DropdownMenuLabel style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span>{user.username}</span>
                  {user.is_superuser && <span className="account-dd-role">Admin</span>}
                </DropdownMenuLabel>
                <DropdownMenuItem asChild>
                  <a href={NAV.account}><Icon name="user" size={13} /> My Profile</a>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <CompanySwitch />
                <form method="post" action={NAV.logout} style={{ margin: 0 }}>
                  <Csrf />
                  <DropdownMenuItem asChild>
                    <button type="submit" className="co-option-muted"><Icon name="logout" size={13} /> Log out</button>
                  </DropdownMenuItem>
                </form>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )}
      </nav>

      {user && (
        <>
          {/* ── Mobile top-right utility cluster ── */}
          <div className="m-topbar" id="m-topbar">
            <button type="button" className="m-top-btn" aria-label="Search" onClick={() => setSearch(true)}>
              <Icon name="search" size={17} strokeWidth={1.8} />
            </button>

            <DropdownMenu open={mNotifOpen} onOpenChange={setMNotifOpen}>
              <DropdownMenuTrigger asChild>
                <button type="button" className="m-top-btn" aria-label="Notifications">
                  <Icon name="bell" size={17} strokeWidth={1.8} />
                  {dueCount > 0 && <span className="m-top-badge">{dueCount}</span>}
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" style={{ width: "min(320px, 90vw)" }}>
                <NotifList />
              </DropdownMenuContent>
            </DropdownMenu>

            <button type="button" className="m-top-avatar" aria-label="Account"
              onClick={(e) => { e.stopPropagation(); setMAccount((v) => !v); }}>
              {user.avatar ? <img src={user.avatar} alt={user.username} /> : <Icon name="user" size={18} strokeWidth={0} fill="currentColor" />}
            </button>
          </div>

          {/* ── Mobile bottom tab bar (docked notch: disc mengikuti tab aktif) — custom, restyled only ── */}
          <nav
            className={"bottom-nav" + (bnavIdx < 0 ? " bnav-flat" : "")}
            id="bottom-nav"
            style={{ "--bnav-i": bnavIdx < 0 ? 2 : bnavIdx }}
          >
            <div className="bnav-disc" aria-hidden="true"></div>
            {BNAV_TABS.map((t, i) => (
              <Link key={t.key} href={NAV[t.key]} className={"bnav-tab" + (i === bnavIdx ? " bnav-active" : "")}>
                <span className="bnav-ico"><Icon name={t.icon} strokeWidth={1.8} /></span>
                <span className="bnav-label">{t.label}</span>
              </Link>
            ))}
          </nav>

          {/* ── Mobile account dropdown — custom, anchored near bottom-nav for thumb reach ── */}
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
            {activeCompany ? (
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
            ) : null}
            <form method="post" action={NAV.logout} style={{ margin: 0 }}>
              <Csrf />
              <button type="submit" className="co-option co-option-muted"><Icon name="logout" size={13} /> Log out</button>
            </form>
          </div>
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
