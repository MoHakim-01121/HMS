import { useEffect, useRef, useState } from "react";
import { Link } from "@inertiajs/react";
import { cn } from "@/lib/utils";
import { useI18n } from "../../utils/i18n.jsx";
import { usePresence } from "./usePresence.js";
import { NAV_TOP, NAV_GROUPS, DEFAULT_OPEN, NavIcon, allowed } from "./nav.jsx";
// The sidebar is a dark olive card in both themes, so it always takes the
// light-on-dark logo.
import logoOnDark from "../../assets/logo-konoz-dark.png";

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

// Row look shared by top links, group headings, pages and the collapse
// button. Icons default through :where() so a single svg (the chevron) can
// set its own transition. `font` was a shorthand, hence leading-[normal].
const ROW = cn(
  "box-border flex h-[38px] w-full flex-none cursor-pointer items-center gap-2.5 overflow-hidden rounded-[11px] border-0 bg-transparent px-2.5",
  "text-left font-sans text-[13.5px] leading-[normal] font-medium whitespace-nowrap no-underline",
  "transition-[background-color,color] duration-[140ms] ease-[ease]",
  "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid",
  "[:where(&)_svg]:flex-none [:where(&)_svg]:text-muted-foreground [:where(&)_svg]:transition-colors [:where(&)_svg]:duration-[140ms] [:where(&)_svg]:ease-[ease]",
);
const ROW_IDLE = "text-[color:color-mix(in_oklch,var(--foreground)_78%,var(--card))] hover:bg-secondary hover:text-foreground hover:[&_svg]:text-foreground";
const ROW_ON = "bg-sidebar-on font-semibold text-sidebar-on-fg [&_svg]:text-sidebar-on-fg";
const ROW_HERE = "font-semibold text-foreground hover:bg-secondary [&_svg]:text-foreground";
const ROW_MINI = "h-10 justify-center p-0";
const LABEL = "min-w-0 flex-1 overflow-hidden text-ellipsis";

// Sidebar (HMS Dashboard canvas "SidebarTree", 2026-10-20): a white card
// floating on the page. Logo with the branch under it (a switcher when the
// user covers more than one), Home and Calendar, then groups as rows with an
// icon and a chevron whose pages hang off a thin guide line. The collapse
// button sits at the foot. Collapsed (`mini`) it is a rail:
// the branch code under the logo, one icon per group (a click reopens the
// sidebar on that group) and tooltips; the branch menu opens beside it.
export default function ShellSidebar({ page, perms, branch, mini, onPickBranch, onToggleMini }) {
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

  const rowClass = (on) => cn(ROW, on ? ROW_ON : ROW_IDLE, mini && ROW_MINI);
  const label = (text) => <span className={cn(LABEL, mini && "hidden")}>{text}</span>;

  const topLink = (it) => {
    const text = t(it.label);
    const on = page === it.key;
    return (
      <Link key={it.key} href={it.href} className={rowClass(on)} aria-current={on ? "page" : undefined}
        aria-label={mini ? text : undefined}
        onMouseEnter={tipIn(text)} onMouseLeave={tipOut} onFocus={tipIn(text)} onBlur={tipOut}>
        <NavIcon name={it.icon || it.key} />
        {label(text)}
      </Link>
    );
  };

  // Pages hang off the guide line; the page you are on marks it with a short
  // cream tick.
  const pageLink = (it, open) => {
    const on = page === it.key;
    return (
      <Link key={it.key} href={it.href} aria-current={on ? "page" : undefined} tabIndex={open ? undefined : -1}
        className={cn(rowClass(on), "relative h-[34px] overflow-visible text-[13px] leading-[normal]",
          on && "before:absolute before:-left-3 before:h-5 before:w-[1.5px] before:rounded-[1px] before:bg-sidebar-on before:content-['']")}>
        {label(t(it.label))}
      </Link>
    );
  };

  const code = current ? (current.is_hq ? "HQ" : current.code) : "";
  const brand = (
    <>
      <img className="block size-[34px] flex-none object-contain" src={logoOnDark} alt="" />
      <span className={cn("hidden", mini && "block text-[10px] font-bold tracking-[.06em] text-muted-foreground uppercase")} aria-hidden="true">{code}</span>
      <span className={cn("flex min-w-0 flex-col leading-[1.25]", mini && "hidden")}>
        <b className="text-[14px] font-bold tracking-[-0.02em] whitespace-nowrap">KonozOps</b>
        <span className="flex items-center gap-1 overflow-hidden text-[12px] font-medium text-ellipsis whitespace-nowrap text-muted-foreground [&_svg]:flex-none">
          {current ? current.name : t("Hotel Management")}{multi && <Chevron size={12} />}
        </span>
      </span>
    </>
  );
  const brandClass = cn(
    "box-border flex h-[52px] w-full items-center gap-2.5 overflow-hidden rounded-[14px] border-0 bg-transparent px-1.5 text-left text-foreground no-underline [font:inherit]",
    "transition-[background-color,color] duration-[160ms] ease-[ease] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid",
    mini && "h-auto flex-col justify-center gap-[3px] px-0 py-1.5",
  );
  const switchLabel = t("{name}, switch branch", { name: current?.name || "" });

  return (
    <aside ref={sbRef} aria-label={t("Sidebar")}
      className={cn(
        "ink-sidebar fixed top-(--shell-gap) bottom-(--shell-gap) left-(--shell-gap) z-[var(--z-sticky,200)] hidden flex-col overflow-visible p-3 desk:flex",
        "w-[calc(var(--sidebar-w)-2*var(--shell-gap))] rounded-[20px] border border-sidebar bg-sidebar shadow-float transition-[width] duration-300 ease-drawer",
        mini && "w-[calc(var(--sidebar-w-collapsed)-2*var(--shell-gap))]",
      )}>
      {tip && (
        <div role="tooltip" style={{ top: tip.top }}
          className="pointer-events-none absolute left-[calc(100%+8px)] z-[70] flex h-[30px] -translate-y-1/2 animate-tip-in items-center rounded-[8px] bg-popover-foreground px-[11px] font-sans text-[12.5px] leading-[normal] font-medium whitespace-nowrap text-popover shadow-popover">
          {tip.label}
        </div>
      )}
      <div className="mb-3.5 flex-none">
        <div className="relative" ref={brRef}>
          {multi ? (
            <button type="button" className={cn(brandClass, "cursor-pointer hover:bg-secondary aria-expanded:bg-secondary")} aria-haspopup="listbox" aria-expanded={branchOpen}
              aria-label={t("Branch {name}, change branch", { name: current?.name || "" })}
              onClick={() => { setTip(null); setBranchOpen((v) => !v); }}
              onMouseEnter={branchOpen ? undefined : tipIn(switchLabel)} onMouseLeave={tipOut}>
              {brand}
            </button>
          ) : (
            <Link href="/dashboard/" className={brandClass} aria-label="KonozOps, Home">{brand}</Link>
          )}
          {multi && menuShown && (
            <div role="listbox" aria-label={t("Branch")}
              className={cn(
                "ink-menu surface absolute top-14 right-0 left-0 z-40 origin-top-left rounded-[12px] border border-border bg-popover p-1 shadow-menu",
                menuClosing ? "pointer-events-none animate-menu-out" : "animate-menu-in",
                mini && "top-0 right-auto left-[calc(100%+22px)] w-60",
              )}>
              <div className="px-2.5 pt-2 pb-1.5 text-[11.5px] font-semibold text-muted-foreground">{t("Switch branch")}</div>
              {choices.map((b) => {
                const on = b.code === current?.code;
                return (
                  <button key={b.code} type="button" role="option" aria-selected={on}
                    className={cn(
                      "flex w-full cursor-pointer items-center gap-2.5 rounded-[8px] border-0 bg-transparent px-2.5 py-[9px] text-left font-sans text-[13.5px] leading-[normal] font-medium text-foreground",
                      "transition-[background-color,color] duration-[160ms] ease-[ease] hover:bg-secondary",
                      on && "bg-secondary font-semibold",
                    )}
                    onClick={() => { setBranchOpen(false); if (!on) onPickBranch(b); }}>
                    <span className="grid w-4 flex-none text-foreground">{on && <Check />}</span>
                    {b.name}
                    {b.is_hq && <span className="inline-grid h-[18px] place-content-center rounded-full border border-input px-1.5 text-[10.5px] font-semibold text-muted-foreground">HQ</span>}
                    <span className="ml-auto text-[11px] font-semibold tracking-[.03em] text-muted-foreground uppercase">{b.code}</span>
                  </button>
                );
              })}
              <p className="mx-0 mt-1 mb-0 border-t border-hairline px-2.5 pt-2 pb-1.5 text-[12px] leading-[1.5] text-muted-foreground">{t("Every page shows this branch only. Switch to see another.")}</p>
            </div>
          )}
        </div>
      </div>
      <nav aria-label={t("Main")} ref={navRef} onScroll={measure}
        className={cn(
          "-mx-3 flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto overscroll-contain px-3 pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden [&>*]:shrink-0",
          fade && "mask-b-from-[calc(100%-48px)]",
        )}>
        {NAV_TOP.filter(ok).map(topLink)}
        <div className={cn("mt-3.5 mb-1 px-2.5 text-[11px] font-semibold tracking-[.08em] whitespace-nowrap text-muted-foreground uppercase", mini && "hidden")}>{t("Menu")}</div>
        {NAV_GROUPS.map((g) => {
          const items = g.items.filter(ok);
          if (!items.length) return null;
          const open = isOpen(g.id);
          const heading = t(g.heading);
          const here = g.id === activeGroup;
          return (
            <div key={g.id}>
              <button type="button" aria-expanded={open}
                className={cn(ROW, here ? ROW_HERE : ROW_IDLE, mini && ROW_MINI, mini && here && "bg-sidebar-on hover:bg-sidebar-on")}
                aria-label={mini ? heading : undefined} onClick={() => toggleGroup(g.id)}
                onMouseEnter={tipIn(heading)} onMouseLeave={tipOut} onFocus={tipIn(heading)} onBlur={tipOut}>
                <NavIcon name={g.icon} />
                {label(heading)}
                <Chevron className={cn("transition-[rotate] duration-200 ease-drawer", !open && "-rotate-90", mini && "hidden")} />
              </button>
              <div className={cn("grid grid-rows-[1fr] transition-[grid-template-rows] duration-[260ms] ease-drawer", !open && "grid-rows-[0fr]", mini && "hidden")}>
                <div className={cn("min-h-0 overflow-hidden transition-opacity duration-200 ease-[ease]", !open && "invisible opacity-0 transition-[opacity,visibility] duration-[150ms,0s] delay-[0s,260ms]")}>
                  <div className="relative mt-0.5 mb-1.5 ml-[19px] flex flex-col gap-0.5 pl-3 before:absolute before:top-0.5 before:bottom-0.5 before:left-0 before:w-[1.5px] before:rounded-[1px] before:bg-border before:content-['']">
                    {items.map((it) => pageLink(it, open && !mini))}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </nav>
      <div className="-mx-3 flex-none border-t border-hairline px-3 pt-2">
        <button type="button" aria-label={mini ? t("Expand sidebar") : t("Collapse sidebar")} aria-pressed={mini}
          className={cn(ROW, "text-muted-foreground hover:bg-secondary hover:[&_svg]:text-foreground", mini && ROW_MINI)}
          onClick={() => { setTip(null); onToggleMini(); }}
          onMouseEnter={tipIn(mini ? t("Expand sidebar") : t("Collapse sidebar"))} onMouseLeave={tipOut}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 4h14a1 1 0 011 1v14a1 1 0 01-1 1H5a1 1 0 01-1-1V5a1 1 0 011-1zM9.5 4v16" /></svg>
          {label(mini ? t("Expand sidebar") : t("Collapse sidebar"))}
        </button>
      </div>
    </aside>
  );
}
