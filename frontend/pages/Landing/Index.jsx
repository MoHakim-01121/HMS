import { useEffect, useRef, useState } from "react";
import { Link } from "@inertiajs/react";
import { motion, AnimatePresence, MotionConfig, animate, useInView, useScroll, useTransform } from "framer-motion";
import Lenis from "lenis";
import { Icon, WhatsAppIcon } from "@/components/icons.jsx";
import { Button } from "@/components/shadcn/ui/button.jsx";
import { Marquee } from "@/components/ui/Marquee.jsx";
import HotelCard from "@/components/landing/HotelCard.jsx";
import LandingFooter from "@/components/landing/LandingFooter.jsx";
import heroBg from "@/assets/hero-makkah.jpg";

// design.css defines an unlayered `*, *::before, *::after { margin: 0;
// padding: 0 }` (see tailwind.css's own comments on Button/Input/Dialog for
// the same fight) that beats every Tailwind margin/padding utility
// regardless of specificity. AppLayout pages route around it through
// restated, data-slot-keyed CSS; this page renders with no AppLayout at all
// (see .layout override below), so there's nothing to restate against.
// Inline styles win the cascade unconditionally, so spacing lives here
// instead of in px-*/py-*/mt-* classNames. Everything else (color, flex,
// grid, gap, typography, border, shadow) is untouched by the reset and
// stays as Tailwind classes.
const s = {
  navWrap: { padding: "28px 24px 0" },
  navPill: { padding: "5px" },
  navLink: { padding: "14px 22px" },
  navCta: { padding: "14px 22px" },
  navToggle: { padding: "9px" },
  mobileMenu: { padding: "8px", marginTop: 8 },
  mobileMenuLink: { padding: "12px 14px" },
  hero: { margin: "0 auto", padding: "64px 24px 64px" },
  badge: { padding: "8px 10px" },
  chip: { padding: "2px 10px" },
  h1: { marginTop: 28 },
  sub: { marginTop: 24 },
  ctaWrap: { marginTop: 32 },
  ctaSecondary: { padding: "13px 22px" },
  statBand: { marginTop: 48 },
  section: { margin: "0 auto", padding: "96px 24px 32px" },
  sectionGrid: { marginTop: 40 },
  propCard: { padding: 24 },
  hotelsSection: { margin: "0 auto", padding: "80px 24px" },
  teamSection: { margin: "0 auto", padding: "96px 24px" },
  ctaSection: { margin: "0 auto", padding: "80px 24px" },
};

// Shared scroll/mount reveal variants — one fade+rise motion used for the
// hero's entrance and every below-the-fold section's whileInView reveal, so
// the page reads as one consistent animation language instead of a grab-bag.
const stagger = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.12, delayChildren: 0.1 } },
};

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.7, ease: [0.16, 1, 0.3, 1] } },
};

const fadeDown = {
  hidden: { opacity: 0, y: -16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: [0.16, 1, 0.3, 1] } },
};

// Counts up from 0 to `value` once its own element scrolls into view — used
// for the hero stat band so the numbers feel alive instead of static text.
function AnimatedCounter({ value, suffix = "", duration = 1.2 }) {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-40px" });
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    if (!isInView) return;
    const controls = animate(0, value, {
      duration,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setDisplay(Math.round(v)),
    });
    return () => controls.stop();
  }, [isInView, value, duration]);

  return (
    <strong ref={ref} className="font-semibold text-white">
      {display}
      {suffix}
    </strong>
  );
}

const VALUE_PROPS = [
  {
    icon: "key",
    title: "Harga Kontrak Langsung",
    body: "Rate hotel Makkah & Madinah dari kontrak langsung dengan hotel partner, tanpa markup broker lain.",
  },
  {
    icon: "cl",
    title: "Confirmation Letter Cepat",
    body: "Reservasi diterbitkan sebagai Confirmation Letter resmi, siap dipakai untuk proses visa & manifest jemaah.",
  },
  {
    icon: "wallet",
    title: "Tagihan & Pembayaran Rapi",
    body: "Tagihan hotel, pembayaran, dan rekapan untuk agen travel dikelola dengan rapi sejak reservasi sampai pelunasan.",
  },
];

export default function LandingIndex({ stats, featured_hotels, team_members, pricelist }) {
  // This page has no sidebar/topbar (see .layout override below) — drop the
  // shell's reserved sidebar inset, same escape hatch AppLayout uses for
  // fullscreen maps (body.map-fullscreen in tailwind.css).
  useEffect(() => {
    document.body.classList.add("public-page");
    return () => document.body.classList.remove("public-page");
  }, []);

  // Lenis smooth-scroll — landing-only touch, scoped to this page's mount
  // lifecycle so it never leaks into the AppLayout-driven app shell. Its own
  // scroll event doubles as the trigger for the sticky nav below, since Lenis
  // is what's actually driving window.scrollY here.
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const lenis = new Lenis({
      duration: 1.1,
      easing: (t) => Math.min(1, 1.001 - 2 ** (-10 * t)),
    });
    lenis.on("scroll", ({ scroll }) => setScrolled(scroll > 60));
    let frameId = requestAnimationFrame(function raf(time) {
      lenis.raf(time);
      frameId = requestAnimationFrame(raf);
    });
    return () => {
      cancelAnimationFrame(frameId);
      lenis.destroy();
    };
  }, []);

  // Subtle parallax on the hero photo: the image is scaled up 12% via
  // className so this translate range (±5%) never reveals an edge, tracked
  // against how far the hero itself has scrolled rather than whole-page
  // scroll so the effect finishes exactly as the hero leaves view.
  const heroRef = useRef(null);
  const { scrollYProgress: heroScrollProgress } = useScroll({
    target: heroRef,
    offset: ["start start", "end start"],
  });
  const heroImgY = useTransform(heroScrollProgress, [0, 1], ["-5%", "5%"]);

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Pricelist goes straight to the uploaded file — the navbar link opens it
  // in a new tab, so it only appears once a file has been uploaded.
  const navLinks = [
    { label: "Home", href: "/", internal: true },
    ...(pricelist?.file_url ? [{ label: "Pricelist", href: pricelist.file_url, external: true }] : []),
    { label: "Hotels", href: "/properties/", internal: true },
    { label: "Our Team", href: "#our-team" },
  ];

  const renderNavLink = (link, className, style, onClose) =>
    link.internal ? (
      <Link key={link.label} href={link.href} className={className} style={style} onClick={onClose}>
        {link.label}
      </Link>
    ) : (
      <a
        key={link.label}
        href={link.href}
        target={link.external ? "_blank" : undefined}
        rel={link.external ? "noreferrer" : undefined}
        className={className}
        style={style}
        onClick={onClose}
      >
        {link.label}
      </a>
    );

  return (
    <MotionConfig reducedMotion="user">
    <div className="min-h-screen bg-background text-foreground">
      {/* Sticky nav — condensed duplicate of the in-hero nav, pinned to the
          viewport and faded in once scrolled past the hero so navigation
          stays reachable over the light section backgrounds below. Desktop
          only: on mobile the in-hero toggle stays within easy reach of a
          short viewport, so a second bar would just be redundant chrome. */}
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
          {navLinks.map((link) =>
            renderNavLink(link, "rounded-full text-sm font-medium text-foreground/70 no-underline transition-colors hover:text-foreground", s.navLink)
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

      {/* Hero */}
      <header ref={heroRef} className="relative isolate min-h-screen overflow-hidden bg-[oklch(0.12_0_0)] text-white">
        <motion.img
          src={heroBg}
          alt=""
          aria-hidden="true"
          className="absolute inset-0 h-full w-full scale-[1.12] object-cover"
          style={{ y: heroImgY }}
        />
        <div
          className="pointer-events-none absolute inset-0"
          aria-hidden="true"
          style={{
            background:
              "radial-gradient(60% 55% at 50% 42%, rgba(10,8,4,0.35) 0%, rgba(10,8,4,0.55) 60%, rgba(10,8,4,0.78) 100%)," +
              "linear-gradient(180deg, rgba(10,8,4,0.82) 0%, rgba(10,8,4,0.4) 22%, rgba(10,8,4,0.42) 68%, rgba(10,8,4,0.85) 100%)",
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
              {navLinks.map((link) =>
                renderNavLink(link, "rounded-full text-base font-medium text-white/75 no-underline transition-colors hover:text-white", s.navLink)
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
                {navLinks.map((link) =>
                  renderNavLink(link, "rounded-xl text-sm font-medium text-white/80 no-underline transition-colors hover:bg-white/10 hover:text-white", s.mobileMenuLink, () => setMobileMenuOpen(false))
                )}
                <a
                  href="/login/"
                  className="inline-flex items-center gap-1.5 rounded-xl bg-white text-sm font-medium text-black no-underline"
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
          className="relative z-10 flex flex-col items-center text-center"
          style={s.hero}
          initial="hidden"
          animate="visible"
          variants={stagger}
        >
          <motion.div variants={fadeUp} className="inline-flex items-center gap-3 rounded-full bg-white/10 ring-1 ring-white/15 backdrop-blur" style={s.badge}>
            <span className="rounded-full bg-white/90 text-[11px] font-semibold text-black" style={s.chip}>
              B2B
            </span>
            <span className="text-sm font-medium text-white/90">
              Broker Hotel untuk Agen Umrah &amp; Haji
            </span>
          </motion.div>

          <motion.h1 variants={fadeUp} className="max-w-3xl text-4xl leading-[1.08] font-bold tracking-tight text-balance sm:text-6xl lg:text-7xl" style={s.h1}>
            Satu Mitra Hotel untuk{" "}
            <br className="hidden sm:block" />
            Setiap <em className="font-medium text-white italic">Jemaah</em> yang Berangkat
          </motion.h1>
          <motion.p variants={fadeUp} className="max-w-xl text-base text-white/70 sm:text-lg" style={s.sub}>
            Konoz United melayani agen travel Umrah &amp; Haji dengan inventori
            hotel berkontrak langsung di Makkah &amp; Madinah: reservasi,
            Confirmation Letter, hingga pembayaran.
          </motion.p>
          <motion.div variants={fadeUp} className="flex flex-col items-center gap-3 sm:flex-row" style={s.ctaWrap}>
            <Button asChild size="lg" className="bg-white text-black shadow-lg shadow-black/40 hover:bg-white/90" style={{ paddingInline: 32 }}>
              <Link href="/properties/">
                Lihat Daftar Hotel
                <Icon name="arrowRight" size={16} />
              </Link>
            </Button>
            <a
              href="#alur-kerja"
              className="inline-flex items-center gap-2 rounded-full bg-white/10 text-sm font-medium text-white no-underline ring-1 ring-white/15 backdrop-blur transition-colors hover:bg-white/15"
              style={s.ctaSecondary}
            >
              Lihat Cara Kerja
              <Icon name="chevron" size={14} />
            </a>
          </motion.div>

          {stats?.total_hotels ? (
            <motion.div variants={fadeUp} className="flex flex-wrap items-center justify-center gap-x-3 gap-y-2 text-sm text-white/55" style={s.statBand}>
              <span><AnimatedCounter value={stats.total_hotels} suffix="+" /> Hotel Partner Aktif</span>
              <span className="text-white/25">•</span>
              <span><AnimatedCounter value={stats.cities_covered} /> Kota: Makkah &amp; Madinah</span>
            </motion.div>
          ) : null}
        </motion.div>

        {/* Scroll-down cue — fades out once the user actually starts
            scrolling (reuses the sticky-nav `scrolled` flag), since its job
            is just to signal there's more content below the fold. */}
        <motion.a
          href="#alur-kerja"
          aria-label="Gulir ke bawah"
          className="absolute bottom-8 left-1/2 z-10 flex size-9 -translate-x-1/2 items-center justify-center text-white/70 no-underline transition-colors hover:text-white"
          initial={{ opacity: 0 }}
          animate={{ opacity: scrolled ? 0 : 1 }}
          transition={{ duration: 0.4 }}
        >
          <motion.span
            animate={{ y: [0, 8, 0] }}
            transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
          >
            <Icon name="chevron" size={20} />
          </motion.span>
        </motion.a>
      </header>

      {/* Value props */}
      <motion.section
        id="alur-kerja"
        className="max-w-6xl"
        style={s.section}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-80px" }}
        variants={stagger}
      >
        <motion.h2 variants={fadeUp} className="text-3xl font-semibold tracking-tight text-balance">
          Keunggulan Konoz United untuk Agen Travel
        </motion.h2>
        <motion.div variants={stagger} className="grid gap-6 sm:grid-cols-3" style={s.sectionGrid}>
          {VALUE_PROPS.map((v) => (
            <motion.div key={v.title} variants={fadeUp} className="flex flex-col gap-3 rounded-xl border border-border bg-card transition-all duration-300 hover:-translate-y-1 hover:border-amber-300/60 hover:shadow-[0_18px_40px_-16px_rgba(146,84,0,0.18)]" style={s.propCard}>
              <div className="flex size-10 items-center justify-center rounded-full bg-amber-100 text-amber-700">
                <Icon name={v.icon} size={18} />
              </div>
              <div className="text-base font-medium">{v.title}</div>
              <p className="text-sm text-muted-foreground">{v.body}</p>
            </motion.div>
          ))}
        </motion.div>
      </motion.section>

      {/* Featured hotels */}
      {featured_hotels?.length > 0 && (
        <motion.section
          className="max-w-6xl"
          style={s.hotelsSection}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
          variants={stagger}
        >
          <motion.div variants={fadeUp} className="flex items-end justify-between gap-4">
            <h2 className="text-3xl font-semibold tracking-tight text-balance">
              Hotel Pilihan
            </h2>
            <Link href="/properties/" className="inline-flex shrink-0 items-center gap-1.5 text-sm font-medium text-foreground no-underline hover:underline">
              Lihat semua
              <Icon name="arrowRight" size={14} />
            </Link>
          </motion.div>
          <motion.div variants={stagger} className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3" style={s.sectionGrid}>
            {featured_hotels.map((h) => (
              <motion.div key={h.id} variants={fadeUp}>
                <HotelCard hotel={h} />
              </motion.div>
            ))}
          </motion.div>
        </motion.section>
      )}

      {/* Our Team */}
      {team_members?.length > 0 && (
        <motion.section
          id="our-team"
          className="max-w-6xl"
          style={s.teamSection}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
          variants={stagger}
        >
          <motion.div variants={fadeUp} className="flex flex-col items-center gap-3 text-center">
            <h2 className="text-3xl font-semibold tracking-tight text-balance">
              Our Team
            </h2>
            <p className="max-w-xl text-sm text-muted-foreground">
              Tim Konoz United yang siap membantu kebutuhan reservasi Anda.
            </p>
          </motion.div>
          <motion.div variants={fadeUp} className="relative w-full" style={s.sectionGrid}>
            {/* Reference uses from-white — hardcoded here as from-background instead,
                since HMS defaults to a dark theme (useTheme.js) and Tailwind's dark:
                variant isn't wired to this app's [data-theme] toggle, so from-white
                would show as a literal white bar over the dark page background. */}
            <div className="pointer-events-none absolute top-0 left-0 z-10 h-full w-32 bg-gradient-to-r from-background to-transparent" />
            <div className="pointer-events-none absolute top-0 right-0 z-10 h-full w-32 bg-gradient-to-l from-background to-transparent" />

            <Marquee className="[--gap:1.5rem]" pauseOnHover>
              {team_members.map((m) => {
                const waDigits = m.wa ? m.wa.replace(/\D/g, "") : "";
                return (
                  <div key={m.id} className="group flex w-64 shrink-0 flex-col">
                    <div className="relative h-92 w-full overflow-hidden rounded-2xl bg-black/20">
                      {m.photo_url ? (
                        <img
                          src={m.photo_url}
                          alt={m.name}
                          className="h-full w-full object-cover grayscale transition-all duration-300 hover:grayscale-0"
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center bg-amber-100 text-amber-700">
                          <Icon name="user" size={48} strokeWidth={1} />
                        </div>
                      )}

                      {waDigits && (
                        <a
                          href={`https://wa.me/${waDigits}`}
                          target="_blank"
                          rel="noreferrer"
                          aria-label={`Hubungi ${m.name} via WhatsApp`}
                          className="absolute top-3 right-3 inline-flex size-9 items-center justify-center rounded-full border border-white/20 bg-black/25 text-[#25D366] backdrop-blur-md transition-colors hover:bg-[#25D366] hover:text-white"
                        >
                          <WhatsAppIcon size={16} />
                        </a>
                      )}

                      <div
                        className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/45 to-transparent"
                        style={{ padding: "40px 12px 12px" }}
                      >
                        <h3 className="font-semibold text-white">{m.name}</h3>
                        <p className="text-white/75 text-sm">{m.position || "—"}</p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </Marquee>
          </motion.div>
        </motion.section>
      )}

      {/* CTA band */}
      <section className="border-t border-border bg-muted/30">
        <motion.div
          className="flex max-w-6xl flex-col items-center gap-5 text-center"
          style={s.ctaSection}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
          variants={stagger}
        >
          <motion.h2 variants={fadeUp} className="text-3xl font-semibold tracking-tight text-balance">
            Jelajahi seluruh hotel partner kami di Makkah &amp; Madinah
          </motion.h2>
          <motion.div variants={fadeUp}>
            <Button asChild size="lg">
              <Link href="/properties/">
                Lihat Semua Hotel
                <Icon name="arrowRight" size={16} />
              </Link>
            </Button>
          </motion.div>
        </motion.div>
      </section>

      <LandingFooter pricelist={pricelist} team_members={team_members} />
    </div>
    </MotionConfig>
  );
}

// Public marketing page — stands alone, no sidebar/topbar shell.
LandingIndex.layout = (page) => page;
