import { Link } from "@inertiajs/react";
import { motion } from "framer-motion";
import { Icon, WhatsAppIcon } from "@/components/icons.jsx";

// Shared public-page footer (Landing/Index.jsx + Landing/Hotels.jsx) so the
// two marketing pages stay identical: brand column, nav links, and WhatsApp
// contact over a slim bottom bar.
//
// Like the pages it lives on, spacing is inline-styled because design.css's
// unlayered `* { margin: 0; padding: 0 }` beats every Tailwind spacing
// utility — see the comment atop Landing/Index.jsx.
const COMPANIES = "Konoz United";

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.7, ease: [0.16, 1, 0.3, 1] } },
};

const s = {
  wrap: { padding: "64px 24px 40px" },
  link: { padding: "5px 0" },
  bottom: { padding: "18px 24px" },
};

export default function LandingFooter({ pricelist, team_members }) {
  const year = new Date().getFullYear();

  const waContacts = (team_members || [])
    .filter((m) => m.wa)
    .map((m) => ({ digits: m.wa.replace(/\D/g, ""), label: m.wa }));

  const navLinks = [
    { label: "Home", href: "/", internal: true },
    ...(pricelist?.file_url ? [{ label: "Pricelist", href: pricelist.file_url, external: true }] : []),
    { label: "Hotels", href: "/properties/", internal: true },
    { label: "Our Team", href: "/#our-team", anchor: true },
  ];

  return (
    <footer className="border-t border-border bg-muted/30">
      <motion.div
        className="grid gap-10 text-center sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr]"
        style={s.wrap}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-40px" }}
        variants={fadeUp}
      >
        {/* Brand */}
        <div className="flex flex-col items-center gap-4">
          <Link href="/" className="flex items-center gap-2 no-underline">
            <img
              src="/static/hw/img/KONOZLOGOPB.png"
              alt={COMPANIES}
              className="h-20 w-auto object-contain"
            />
          </Link>
          <p className="text-sm leading-relaxed text-muted-foreground">
            Broker hotel untuk agen travel Umrah &amp; Haji dengan inventori
            hotel berkontrak langsung di Makkah &amp; Madinah.
          </p>
          <div className="text-sm text-muted-foreground">
            Bagian dari {COMPANIES}
          </div>
        </div>

        {/* Navigasi */}
        <div className="flex flex-col items-center">
          <h3 className="text-sm font-semibold text-foreground" style={{ padding: "5px 0" }}>
            Navigasi
          </h3>
          {navLinks.map((link) =>
            link.internal ? (
              <Link
                key={link.label}
                href={link.href}
                className="inline-flex items-center gap-1.5 text-sm text-muted-foreground no-underline transition-colors hover:text-foreground"
                style={s.link}
              >
                {link.label}
              </Link>
            ) : (
              <a
                key={link.label}
                href={link.href}
                target={link.external ? "_blank" : undefined}
                rel={link.external ? "noreferrer" : undefined}
                className="inline-flex items-center gap-1.5 text-sm text-muted-foreground no-underline transition-colors hover:text-foreground"
                style={s.link}
              >
                {link.label}
                {link.external && <Icon name="arrow-up-right" size={12} />}
              </a>
            )
          )}
        </div>

        {/* Kontak */}
        <div className="flex flex-col items-center">
          <h3 className="text-sm font-semibold text-foreground" style={{ padding: "5px 0" }}>
            Hubungi Kami
          </h3>
          {waContacts.length ? (
            waContacts.map((c) => (
              <a
                key={c.digits}
                href={`https://wa.me/${c.digits}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 text-sm text-muted-foreground no-underline transition-colors hover:text-foreground"
                style={s.link}
              >
                <WhatsAppIcon size={15} className="text-[#25D366]" />
                {c.label}
              </a>
            ))
          ) : (
            <p className="text-sm text-muted-foreground">
              Kontak kami untuk info reservasi &amp; rate hotel.
            </p>
          )}
        </div>
      </motion.div>

      {/* Bottom bar */}
      <div
        className="flex items-center justify-center border-t border-border text-center text-sm text-muted-foreground"
        style={s.bottom}
      >
        <span>
          © {year} {COMPANIES}. All rights reserved.
        </span>
      </div>
    </footer>
  );
}
