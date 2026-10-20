import { useEffect, useRef, useState } from "react";
import { Link } from "@inertiajs/react";
import { useI18n } from "../../utils/i18n.jsx";
import { usePresence } from "./usePresence.js";
import { NAV_TOP, NAV_GROUPS, DEFAULT_OPEN, NavIcon, allowed } from "./nav.jsx";
import logoLight from "../../assets/logo-konoz.png";
import logoDark from "../../assets/logo-konoz-dark.png";

// v2: the groups were renamed on 2026-10-20, so older saved states don't apply.
const GROUPS_KEY = "hms.sidebar.groups.v2";

function readGroups() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(GROUPS_KEY) || "null");
    if (saved && typeof saved === "object") return { ...DEFAULT_OPEN, ...saved };
  } catch { /* storage blocked */ }
  return DEFAULT_OPEN;
}

const Check = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10" /></svg>
);
const Chevron = ({ size = 15, className }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
);

// Sidebar (HMS Dashboard canvas "SidebarTree", 2026-10-20): a white card
// floating on the page. Logo with the branch under it (a switcher when the
// user covers more than one), Home and Calendar, then groups as rows with an
// icon and a chevron whose pages hang off a thin guide line. The collapse
// button sits at the foot. Collapsed (body.sidebar-collapsed) it is a rail:
// the branch code under the logo, one icon per group (a click reopens the
// sidebar on that group) and tooltips; the branch menu opens beside it.
export default function ShellSidebar({ page, perms, theme, branch, mini, onPickBranch, onToggleMini }) {
  const { t } = useI18n();
  const [groups, setGroups] = useState(readGroups);
  const [branchOpen, setBranchOpen] = useState(false);
  const [tip, setTip] = useState(null);
  const [fade, setFade] = useState(false);
  const sbRef = useRef(null);
  const navRef = useRef(null);
  const brRef = useRef(null);
  const [menuShown, menuClosing] = usePresence(branchOpen);
  const ok = allowed(perms);
  const choices = branch?.choices || [];
  const multi = choices.length > 1;
  const current = branch?.current;

  // The group holding the page you are on is always open.
  const activeGroup = NAV_GROUPS.find((g) => g.items.some((it) => it.key === page))?.id;
  const isOpen = (id) => !!groups[id] || id === activeGroup;
  const saveGroups = (next) => {
    setGroups(next);
    try { window.localStorage.setItem(GROUPS_KEY, JSON.stringify(next)); } catch { /* storage blocked */ }
  };
  const toggleGroup = (id) => {
    if (mini) {
      setTip(null);
      saveGroups({ ...groups, [id]: true });
      onToggleMini();
      return;
    }
    saveGroups({ ...groups, [id]: !isOpen(id) });
  };

  useEffect(() => { if (!mini) setTip(null); }, [mini]);

  // The nav scrolls on its own with no scrollbar; its foot fades while more
  // links sit below.
  const measure = () => {
    const n = navRef.current;
    if (n) setFade(n.scrollHeight - n.scrollTop - n.clientHeight > 4);
  };
  useEffect(() => {
    measure();
    const id = setTimeout(measure, 320); // after a group finishes folding
    window.addEventListener("resize", measure);
    return () => { clearTimeout(id); window.removeEventListener("resize", measure); };
  }, [groups, mini]);

  useEffect(() => {
    if (!branchOpen) return;
    const onDoc = (e) => { if (brRef.current && !brRef.current.contains(e.target)) setBranchOpen(false); };
    const onKey = (e) => { if (e.key === "Escape") setBranchOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onKey); };
  }, [branchOpen]);

  const tipIn = (label) => (e) => {
    if (!mini || !sbRef.current) return;
    const r = e.currentTarget.getBoundingClientRect();
    const o = sbRef.current.getBoundingClientRect();
    setTip({ label, top: Math.round(r.top - o.top + r.height / 2) });
  };
  const tipOut = () => setTip(null);

  const topLink = (it) => {
    const label = t(it.label);
    const on = page === it.key;
    return (
      <Link key={it.key} href={it.href} className={"ks-row" + (on ? " on" : "")} aria-current={on ? "page" : undefined}
        aria-label={mini ? label : undefined}
        onMouseEnter={tipIn(label)} onMouseLeave={tipOut} onFocus={tipIn(label)} onBlur={tipOut}>
        <NavIcon name={it.icon || it.key} />
        <span className="ks-lb">{label}</span>
      </Link>
    );
  };

  const pageLink = (it, open) => {
    const on = page === it.key;
    return (
      <Link key={it.key} href={it.href} className={"ks-row" + (on ? " on" : "")} aria-current={on ? "page" : undefined}
        tabIndex={open ? undefined : -1}>
        <span className="ks-lb">{t(it.label)}</span>
      </Link>
    );
  };

  const code = current ? (current.is_hq ? "HQ" : current.code) : "";
  const brand = (
    <>
      <img className="ks-logo" src={theme === "dark" ? logoDark : logoLight} alt="" />
      <span className="ks-code" aria-hidden="true">{code}</span>
      <span className="ks-bn"><b>Konoz United</b><span>{current ? current.name : t("Hotel Management")}{multi && <Chevron size={12} />}</span></span>
    </>
  );
  const switchLabel = t("{name}, switch branch", { name: current?.name || "" });

  return (
    <aside className="hms-sidebar ks-sb" aria-label={t("Sidebar")} ref={sbRef}>
      {tip && <div className="ks-tip" role="tooltip" style={{ top: tip.top }}>{tip.label}</div>}
      <div className="ks-top">
        <div className="ks-brw" ref={brRef}>
          {multi ? (
            <button type="button" className="ks-ws" aria-haspopup="listbox" aria-expanded={branchOpen}
              aria-label={t("Branch {name}, change branch", { name: current?.name || "" })}
              onClick={() => { setTip(null); setBranchOpen((v) => !v); }}
              onMouseEnter={branchOpen ? undefined : tipIn(switchLabel)} onMouseLeave={tipOut}>
              {brand}
            </button>
          ) : (
            <Link href="/dashboard/" className="ks-ws" aria-label="Konoz United, Home">{brand}</Link>
          )}
          {multi && menuShown && (
            <div className={"ks-bm" + (menuClosing ? " is-closing" : "")} role="listbox" aria-label={t("Branch")}>
              <div className="ks-bm-h">{t("Switch branch")}</div>
              {choices.map((b) => {
                const on = b.code === current?.code;
                return (
                  <button key={b.code} type="button" className={"ks-bo" + (on ? " on" : "")} role="option" aria-selected={on}
                    onClick={() => { setBranchOpen(false); if (!on) onPickBranch(b); }}>
                    <span className="ckm">{on && <Check />}</span>
                    {b.name}
                    {b.is_hq && <span className="hq">HQ</span>}
                    <span className="cd">{b.code}</span>
                  </button>
                );
              })}
              <p className="ks-bm-f">{t("Every page shows this branch only. Switch to see another.")}</p>
            </div>
          )}
        </div>
      </div>
      <nav className={"ks-nav" + (fade ? " fade" : "")} aria-label={t("Main")} ref={navRef} onScroll={measure}>
        {NAV_TOP.filter(ok).map(topLink)}
        <div className="ks-sec">{t("Menu")}</div>
        {NAV_GROUPS.map((g) => {
          const items = g.items.filter(ok);
          if (!items.length) return null;
          const open = isOpen(g.id);
          const heading = t(g.heading);
          return (
            <div key={g.id}>
              <button type="button" className={"ks-row" + (g.id === activeGroup ? " here" : "")} aria-expanded={open}
                aria-label={mini ? heading : undefined} onClick={() => toggleGroup(g.id)}
                onMouseEnter={tipIn(heading)} onMouseLeave={tipOut} onFocus={tipIn(heading)} onBlur={tipOut}>
                <NavIcon name={g.icon} />
                <span className="ks-lb">{heading}</span>
                <Chevron className="ch" />
              </button>
              <div className={"ks-kids" + (open ? "" : " shut")}>
                <div className="ks-kids-in"><div className="ks-tree">{items.map((it) => pageLink(it, open && !mini))}</div></div>
              </div>
            </div>
          );
        })}
      </nav>
      <div className="ks-foot">
        <button type="button" className="ks-row" aria-label={mini ? t("Expand sidebar") : t("Collapse sidebar")} aria-pressed={mini}
          onClick={() => { setTip(null); onToggleMini(); }}
          onMouseEnter={tipIn(mini ? t("Expand sidebar") : t("Collapse sidebar"))} onMouseLeave={tipOut}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 4h14a1 1 0 011 1v14a1 1 0 01-1 1H5a1 1 0 01-1-1V5a1 1 0 011-1zM9.5 4v16" /></svg>
          <span className="ks-lb">{mini ? t("Expand sidebar") : t("Collapse sidebar")}</span>
        </button>
      </div>
    </aside>
  );
}
