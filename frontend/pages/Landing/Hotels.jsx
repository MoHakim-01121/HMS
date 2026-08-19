import { useEffect, useMemo, useRef, useState } from "react";
import { Link, router } from "@inertiajs/react";
import { motion, AnimatePresence, MotionConfig } from "framer-motion";
import { Icon } from "@/components/icons.jsx";
import { Button } from "@/components/shadcn/ui/button.jsx";
import { Input } from "@/components/shadcn/ui/input.jsx";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadcn/ui/select.jsx";
import HotelCard from "@/components/landing/HotelCard.jsx";
import LandingFooter from "@/components/landing/LandingFooter.jsx";
import heroBg from "@/assets/hero-makkah.jpg";

const CITY_LABEL = { makkah: "Makkah", madinah: "Madinah" };

const CITY_OPTIONS = [
  { value: "", label: "Semua" },
  { value: "makkah", label: "Makkah" },
  { value: "madinah", label: "Madinah" },
];

const STAR_OPTIONS = [
  { value: "", label: "Semua" },
  { value: "3", label: "3★" },
  { value: "4", label: "4★" },
  { value: "5", label: "5★" },
];

const DISTANCE_OPTIONS = [
  { value: "", label: "Semua" },
  { value: "500", label: "≤ 500 m" },
  { value: "1000", label: "≤ 1 km" },
  { value: "2000", label: "≤ 2 km" },
];

const SORT_OPTIONS = [
  { value: "stars", label: "Bintang tertinggi" },
  { value: "distance", label: "Terdekat dari Masjid" },
  { value: "name", label: "Nama A–Z" },
];

function buildQuery({ q, city, stars }) {
  const p = new URLSearchParams();
  if (q) p.set("q", q);
  if (city) p.set("city", city);
  if (stars) p.set("stars", stars);
  const qs = p.toString();
  return "/properties/" + (qs ? `?${qs}` : "");
}

// Same fade+rise language as Landing/Index.jsx, so navigating between the
// two public pages feels like one continuous product, not two builds.
const stagger = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.1, delayChildren: 0.05 } },
};

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: [0.16, 1, 0.3, 1] } },
};

const fadeDown = {
  hidden: { opacity: 0, y: -16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: [0.16, 1, 0.3, 1] } },
};

// design.css defines an unlayered `*, *::before, *::after { margin: 0;
// padding: 0 }` that beats every Tailwind margin/padding utility regardless
// of specificity (see the matching comment in Landing/Index.jsx). This page
// also renders with no AppLayout (.layout override below), so there's no
// `.shadcn-root` scope to restate against — spacing has to live here as
// inline styles instead of px-*/py-*/mt-* classNames.
const s = {
  navWrap: { padding: "20px 24px 0" },
  navPill: { padding: "5px" },
  navLink: { padding: "10px 16px" },
  navCta: { padding: "10px 18px" },
  mobileMenu: { padding: "8px", marginTop: 8 },
  mobileMenuLink: { padding: "12px 14px" },
  hero: { margin: "0 auto", padding: "36px 24px 120px" },
  badge: { padding: "7px 14px" },
  heroTitle: { marginTop: 18 },
  heroSub: { marginTop: 12 },
  statLine: { marginTop: 18 },
  searchCardWrap: { margin: "-72px auto 0", padding: "0 24px" },
  searchCard: { padding: 10 },
  section: { margin: "0 auto", padding: "48px 24px 96px" },
  toolbar: { marginBottom: 16 },
  mobileFilters: { marginBottom: 16 },
  chipGroup: { marginTop: 10 },
  chip: { padding: "6px 12px" },
  sidebarCard: { padding: 20 },
  sidebarTitle: { marginBottom: 16 },
  groupTitle: { marginBottom: 8 },
  group: { marginBottom: 24 },
  radio: { padding: "9px 12px" },
  grid: { marginTop: 4 },
  empty: { padding: "72px 24px" },
};

function FilterChip({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`inline-flex shrink-0 items-center rounded-full border text-sm font-medium transition-colors ${
        active
          ? "border-foreground bg-foreground text-background"
          : "border-border bg-card text-foreground hover:border-ring"
      }`}
      style={s.chip}
    >
      {children}
    </button>
  );
}

function FilterRadio({ active, onClick, children, count }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`flex w-full items-center gap-3 rounded-xl text-sm transition-colors ${
        active
          ? "bg-muted font-medium text-foreground"
          : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
      }`}
      style={s.radio}
    >
      <span
        className={`flex size-4 shrink-0 items-center justify-center rounded-full border-2 transition-colors ${
          active ? "border-foreground" : "border-muted-foreground/50"
        }`}
      >
        <span className={`size-2 rounded-full ${active ? "bg-foreground" : "bg-transparent"}`} />
      </span>
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {count != null && (
        <span className={`shrink-0 text-xs tabular-nums ${active ? "text-foreground/70" : "text-muted-foreground/70"}`}>
          {count}
        </span>
      )}
    </button>
  );
}

function FilterGroup({ title, children }) {
  return (
    <div style={s.group}>
      <div className="text-sm font-semibold" style={s.groupTitle}>{title}</div>
      <div className="flex flex-col gap-1">{children}</div>
    </div>
  );
}

export default function LandingHotels({ hotels, q, city_filter, stars_filter, stats, pricelist }) {
  // See the matching effect in Landing/Index.jsx — this page also has no
  // sidebar/topbar, so the shell's reserved sidebar inset must come off.
  useEffect(() => {
    document.body.classList.add("public-page");
    return () => document.body.classList.remove("public-page");
  }, []);

  const [query, setQuery] = useState(q || "");
  const debounce = useRef(null);
  const first = useRef(true);

  const [distance, setDistance] = useState("");
  const [sort, setSort] = useState("stars");

  const go = (extra = {}) =>
    router.get(
      buildQuery({ q: query, city: city_filter, stars: stars_filter, ...extra }),
      {},
      { preserveState: true, preserveScroll: true, replace: true }
    );

  useEffect(() => {
    if (first.current) { first.current = false; return; }
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => go({ q: query }), 300);
    return () => clearTimeout(debounce.current);
  }, [query]);

  // Distance filter and sort run client-side over the server-filtered list —
  // they're view-only conveniences, so the shareable URL keeps only the real
  // search params (q/city/stars) and instant toggling never re-requests.
  const visibleHotels = useMemo(() => {
    let list = hotels;
    if (distance) {
      const max = Number(distance);
      list = list.filter((h) => h.distance != null && h.distance <= max);
    }
    const sorted = [...list];
    if (sort === "distance") {
      sorted.sort((a, b) => (a.distance ?? Infinity) - (b.distance ?? Infinity));
    } else if (sort === "name") {
      sorted.sort((a, b) => a.name.localeCompare(b.name));
    } else {
      sorted.sort((a, b) => b.stars - a.stars || a.name.localeCompare(b.name));
    }
    return sorted;
  }, [hotels, distance, sort]);

  const clearFilter = (key) => {
    if (key === "q") setQuery("");
    if (key === "distance") { setDistance(""); return; }
    go({ [key]: "" });
  };
  const clearAll = () => {
    setQuery("");
    setDistance("");
    setSort("stars");
    go({ q: "", city: "", stars: "" });
  };

  const activeFilters = [
    q && { key: "q", label: `"${q}"` },
    city_filter && { key: "city", label: CITY_LABEL[city_filter] || city_filter },
    stars_filter && { key: "stars", label: `${stars_filter}★` },
    distance && { key: "distance", label: DISTANCE_OPTIONS.find((o) => o.value === distance)?.label },
  ].filter(Boolean);

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Condensed nav fade-in on scroll — same trigger/threshold as Landing/Index.jsx,
  // just driven by native scroll here since this page has no Lenis smooth-scroll.
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 60);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const navItems = [
    { label: "Home", href: "/", type: "inertia" },
    ...(pricelist?.file_url ? [{ label: "Pricelist", href: pricelist.file_url, type: "external" }] : []),
    { label: "Hotel Kami", type: "current" },
    { label: "Our Team", href: "/#our-team", type: "anchor" },
  ];

  const renderNavItem = (item, className, activeClassName, style, onClose) => {
    if (item.type === "current") {
      return (
        <span key={item.label} className={`font-semibold ${activeClassName}`} style={style}>
          {item.label}
        </span>
      );
    }
    if (item.type === "inertia") {
      return (
        <Link key={item.label} href={item.href} className={className} style={style} onClick={onClose}>
          {item.label}
        </Link>
      );
    }
    return (
      <a
        key={item.label}
        href={item.href}
        target={item.type === "external" ? "_blank" : undefined}
        rel={item.type === "external" ? "noreferrer" : undefined}
        className={className}
        style={style}
        onClick={onClose}
      >
        {item.label}
      </a>
    );
  };

  const renderCityRadios = () =>
    CITY_OPTIONS.map((o) => (
      <FilterRadio
        key={o.value}
        active={city_filter === o.value}
        onClick={() => go({ city: o.value })}
        count={o.value === "" ? stats?.total_hotels : stats?.count_by_city?.[o.value]}
      >
        {o.label}
      </FilterRadio>
    ));

  const renderStarRadios = () =>
    STAR_OPTIONS.map((o) => (
      <FilterRadio
        key={o.value}
        active={stars_filter === o.value}
        onClick={() => go({ stars: o.value })}
        count={o.value === "" ? stats?.total_hotels : stats?.count_by_star?.[o.value]}
      >
        {o.label}
      </FilterRadio>
    ));

  const renderDistanceRadios = () =>
    DISTANCE_OPTIONS.map((o) => (
      <FilterRadio
        key={o.value}
        active={distance === o.value}
        onClick={() => setDistance(o.value)}
        count={o.value === "" ? stats?.total_hotels : stats?.count_by_distance?.[o.value]}
      >
        {o.label}
      </FilterRadio>
    ));

  const renderCityChips = () =>
    CITY_OPTIONS.map((o) => (
      <FilterChip key={o.value} active={city_filter === o.value} onClick={() => go({ city: o.value })}>
        {o.label}
      </FilterChip>
    ));

  const renderStarChips = () =>
    STAR_OPTIONS.map((o) => (
      <FilterChip key={o.value} active={stars_filter === o.value} onClick={() => go({ stars: o.value })}>
        {o.label}
      </FilterChip>
    ));

  const renderDistanceChips = () =>
    DISTANCE_OPTIONS.map((o) => (
      <FilterChip key={o.value} active={distance === o.value} onClick={() => setDistance(o.value)}>
        {o.label}
      </FilterChip>
    ));

  return (
    <MotionConfig reducedMotion="user">
    <div className="min-h-screen bg-background text-foreground">
      {/* Condensed nav — fades in once scrolled past the hero, mirrors the
          sticky duplicate nav in Landing/Index.jsx so both public pages share
          the exact same nav position/behaviour once the hero scrolls away. */}
      <motion.div
        className="fixed inset-x-0 top-0 z-50 hidden items-center justify-between border-b border-border bg-background/85 backdrop-blur-md md:flex"
        style={{ padding: "12px 24px", pointerEvents: scrolled ? "auto" : "none" }}
        initial={false}
        animate={scrolled ? { y: 0, opacity: 1 } : { y: -72, opacity: 0 }}
        transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      >
        <Link href="/" className="flex items-center gap-2 no-underline">
          <img
            src="/static/hw/img/KONOZLOGOPB.png"
            alt="Konoz United"
            className="h-20 w-auto object-contain"
            style={{ marginBlock: -20 }}
          />
        </Link>
        <nav className="flex items-center gap-1 rounded-full bg-muted ring-1 ring-border" style={s.navPill}>
          {navItems.map((item) =>
            renderNavItem(item, "rounded-full text-sm no-underline text-foreground/70 transition-colors hover:text-foreground", "text-foreground", s.navLink)
          )}
          <a
            href="/login/"
            className="inline-flex items-center gap-1.5 rounded-full bg-foreground text-sm font-medium text-background no-underline transition-colors hover:opacity-90"
            style={s.navCta}
          >
            Login
            <Icon name="arrow-up-right" size={14} />
          </a>
        </nav>
      </motion.div>

      {/* Hero band — nav lives inside it (transparent-on-photo), same
          composition as Landing/Index.jsx's in-hero nav. */}
      <header className="relative isolate overflow-hidden bg-[oklch(0.12_0_0)] text-white">
        <img src={heroBg} alt="" aria-hidden="true" className="absolute inset-0 h-full w-full object-cover" />
        <div
          className="pointer-events-none absolute inset-0"
          aria-hidden="true"
          style={{
            background:
              "radial-gradient(60% 70% at 50% 20%, rgba(10,8,4,0.35) 0%, rgba(10,8,4,0.62) 60%, rgba(10,8,4,0.88) 100%)," +
              "linear-gradient(180deg, rgba(10,8,4,0.7) 0%, rgba(10,8,4,0.5) 40%, rgba(10,8,4,0.92) 100%)",
          }}
        />

        <div className="relative z-20">
          <motion.div
            className="relative flex items-center justify-between"
            style={s.navWrap}
            initial="hidden"
            animate="visible"
            variants={fadeDown}
          >
            <Link href="/" className="flex items-center gap-2 no-underline">
              <img
                src="/static/hw/img/KONOZLOGOPB.png"
                alt="Konoz United"
                className="h-32 w-auto object-contain"
              />
            </Link>

            <nav className="hidden items-center gap-1 rounded-full bg-white/5 ring-1 ring-white/10 backdrop-blur md:flex" style={s.navPill}>
              {navItems.map((item) =>
                renderNavItem(item, "rounded-full text-base font-medium text-white/75 no-underline transition-colors hover:text-white", "text-white", s.navLink)
              )}
              <a
                href="/login/"
                className="inline-flex items-center gap-1.5 rounded-full bg-white text-base font-medium text-black no-underline transition-colors hover:bg-white/90"
                style={s.navCta}
              >
                Login
                <Icon name="arrow-up-right" size={14} />
              </a>
            </nav>

            <button
              type="button"
              onClick={() => setMobileMenuOpen((open) => !open)}
              className="inline-flex size-10 items-center justify-center rounded-full bg-white/10 text-white ring-1 ring-white/15 backdrop-blur md:hidden"
              aria-expanded={mobileMenuOpen}
              aria-label="Menu"
            >
              <Icon name={mobileMenuOpen ? "close" : "menu"} size={18} />
            </button>
          </motion.div>

          <AnimatePresence>
            {mobileMenuOpen && (
              <motion.div
                className="absolute inset-x-6 top-full flex flex-col gap-1 rounded-2xl bg-black/80 ring-1 ring-white/15 backdrop-blur-xl md:hidden"
                style={s.mobileMenu}
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.18, ease: "easeOut" }}
              >
                {navItems.map((item) =>
                  renderNavItem(item, "rounded-lg text-sm font-medium text-white/80 no-underline transition-colors hover:bg-white/10 hover:text-white", "text-white", s.mobileMenuLink, () => setMobileMenuOpen(false))
                )}
                <a
                  href="/login/"
                  className="inline-flex items-center gap-1.5 rounded-lg bg-white text-sm font-medium text-black no-underline"
                  style={s.mobileMenuLink}
                >
                  Login
                  <Icon name="arrow-up-right" size={14} />
                </a>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <motion.div
          className="relative z-10 mx-auto flex max-w-3xl flex-col items-center text-center"
          style={s.hero}
          initial="hidden"
          animate="visible"
          variants={stagger}
        >
          <motion.span
            variants={fadeUp}
            className="inline-flex items-center gap-1.5 rounded-full bg-white/10 text-xs font-medium text-white/90 ring-1 ring-white/15 backdrop-blur"
            style={s.badge}
          >
            <Icon name="building" size={13} />
            Inventori Hotel Partner
          </motion.span>
          <motion.h1 variants={fadeUp} className="text-4xl leading-[1.1] font-bold tracking-tight text-balance sm:text-5xl" style={s.heroTitle}>
            Cari Hotel untuk Jemaah Anda
          </motion.h1>
          <motion.p variants={fadeUp} className="max-w-xl text-base text-white/70" style={s.heroSub}>
            Bandingkan inventori hotel partner berkontrak langsung di Makkah
            dan Madinah — urutkan berdasarkan bintang, kota, hingga jarak dari
            Masjid.
          </motion.p>
          {stats?.total_hotels ? (
            <motion.p variants={fadeUp} className="text-sm text-white/55" style={s.statLine}>
              <strong className="font-semibold text-white">{stats.total_hotels}+</strong> Hotel Partner Aktif
              <span className="mx-2 text-white/25">•</span>
              <strong className="font-semibold text-white">{stats.cities_covered}</strong> Kota
            </motion.p>
          ) : null}
        </motion.div>
      </header>

      {/* Floating search bar — overlaps the hero/content boundary */}
      <div className="relative z-20 mx-auto max-w-6xl" style={s.searchCardWrap}>
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.25, ease: [0.16, 1, 0.3, 1] }}
          className="flex flex-col gap-3 rounded-[26px] border border-border bg-card shadow-2xl shadow-black/15 sm:flex-row sm:items-center"
          style={s.searchCard}
        >
          <div className="relative flex-1">
            <Icon name="search" size={15} className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Cari nama hotel atau area..."
              style={{ paddingLeft: 36 }}
            />
          </div>
          <div className="hidden h-10 w-px shrink-0 bg-border sm:block" aria-hidden="true" />
          <Select value={city_filter || "all"} onValueChange={(v) => go({ city: v === "all" ? "" : v })}>
            <SelectTrigger className="w-full sm:w-40">
              <SelectValue placeholder="Semua Kota" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Semua Kota</SelectItem>
              <SelectItem value="makkah">Makkah</SelectItem>
              <SelectItem value="madinah">Madinah</SelectItem>
            </SelectContent>
          </Select>
          <div className="hidden h-10 w-px shrink-0 bg-border sm:block" aria-hidden="true" />
          <Select value={stars_filter || "all"} onValueChange={(v) => go({ stars: v === "all" ? "" : v })}>
            <SelectTrigger className="w-full sm:w-36">
              <SelectValue placeholder="Semua Bintang" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Semua Bintang</SelectItem>
              <SelectItem value="3">3 Bintang</SelectItem>
              <SelectItem value="4">4 Bintang</SelectItem>
              <SelectItem value="5">5 Bintang</SelectItem>
            </SelectContent>
          </Select>
          <Button
            size="lg"
            className="gap-2 rounded-[16px] sm:shrink-0"
            onClick={() => go({ q: query })}
          >
            Cari Hotel
            <Icon name="arrow-right" size={15} />
          </Button>
        </motion.div>
      </div>

      <div className="mx-auto max-w-6xl" style={s.section}>
        <div className="lg:grid lg:grid-cols-[248px_1fr] lg:gap-8">
          {/* Filter sidebar — desktop only, Booking-style radio groups */}
          <aside className="hidden lg:block">
            <div className="sticky rounded-2xl border border-border bg-card" style={{ ...s.sidebarCard, top: 88 }}>
              <div className="text-base font-bold" style={s.sidebarTitle}>Filter</div>
              <FilterGroup title="Kota">{renderCityRadios()}</FilterGroup>
              <FilterGroup title="Bintang">{renderStarRadios()}</FilterGroup>
              <FilterGroup title="Jarak dari Masjid">{renderDistanceRadios()}</FilterGroup>
              {activeFilters.length > 0 && (
                <button
                  type="button"
                  onClick={clearAll}
                  className="text-sm font-medium text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                >
                  Hapus semua filter
                </button>
              )}
            </div>
          </aside>

          <div className="min-w-0">
            {/* Results toolbar — count left, sort right */}
            <motion.div
              className="flex flex-wrap items-center justify-between gap-3"
              style={s.toolbar}
              initial="hidden"
              animate="visible"
              variants={stagger}
            >
              <motion.p variants={fadeUp} className="text-sm text-muted-foreground">
                <strong className="font-semibold text-foreground">{visibleHotels.length}</strong>{" "}
                hotel ditemukan
              </motion.p>
              <motion.div variants={fadeUp} className="flex items-center">
                <span className="hidden text-sm text-muted-foreground sm:inline" style={{ marginRight: 8 }}>
                  Urutkan
                </span>
                <Select value={sort} onValueChange={setSort}>
                  <SelectTrigger className="w-52">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SORT_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </motion.div>
            </motion.div>

            {/* Mobile filter chips — same groups as the sidebar, single row,
                sticky so the refinement controls survive scrolling (Traveloka/
                Tiket mobile pattern). */}
            <div
              className="sticky top-0 z-30 -mx-6 flex items-center gap-2 overflow-x-auto bg-background/85 px-6 backdrop-blur-md lg:hidden"
              style={s.mobileFilters}
            >
              {renderCityChips()}
              <span className="mx-1 h-4 w-px shrink-0 bg-border" aria-hidden="true" />
              {renderStarChips()}
              <span className="mx-1 h-4 w-px shrink-0 bg-border" aria-hidden="true" />
              {renderDistanceChips()}
            </div>

            {/* Active filter chips + clear all */}
            {activeFilters.length > 0 && (
              <div className="flex flex-wrap items-center gap-2" style={s.chipGroup}>
                {activeFilters.map((f) => (
                  <button
                    key={f.key}
                    type="button"
                    onClick={() => clearFilter(f.key)}
                    className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted text-xs font-medium text-foreground transition-colors hover:border-ring"
                    style={s.chip}
                  >
                    {f.label}
                    <Icon name="close" size={12} className="text-muted-foreground" />
                  </button>
                ))}
                <button
                  type="button"
                  onClick={clearAll}
                  className="text-xs font-medium text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                >
                  Hapus semua
                </button>
              </div>
            )}

            {visibleHotels.length === 0 ? (
              <div className="flex flex-col items-center gap-3 text-center text-muted-foreground" style={s.empty}>
                <Icon name="building" size={28} strokeWidth={1.25} />
                <p>{hotels.length === 0 ? "Tidak ada hotel yang cocok dengan pencarian ini." : "Tidak ada hotel dalam jarak yang dipilih."}</p>
                {activeFilters.length > 0 && (
                  <Button variant="outline" onClick={clearAll}>
                    Reset Filter
                  </Button>
                )}
              </div>
            ) : (
              <motion.div
                key={visibleHotels.map((h) => h.id).join(",")}
                className="grid gap-6 sm:grid-cols-2"
                style={s.grid}
                initial="hidden"
                animate="visible"
                variants={stagger}
              >
                {visibleHotels.map((h) => (
                  <motion.div key={h.id} variants={fadeUp}>
                    <HotelCard hotel={h} />
                  </motion.div>
                ))}
              </motion.div>
            )}
          </div>
        </div>
      </div>

      <LandingFooter pricelist={pricelist} />
    </div>
    </MotionConfig>
  );
}

// Public marketing page — stands alone, no sidebar/topbar shell.
LandingHotels.layout = (page) => page;
