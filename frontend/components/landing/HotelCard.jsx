import { useRef, useState } from "react";
import { motion, AnimatePresence, useMotionValue, useMotionTemplate, useSpring, useTransform, useReducedMotion } from "framer-motion";
import { ChevronLeft, ChevronRight, ArrowRight } from "lucide-react";
import { Icon } from "@/components/icons.jsx";
import { Badge } from "@/components/shadcn/ui/badge.jsx";
import { Button } from "@/components/shadcn/ui/button.jsx";

// No hotel photography exists in the data yet, so each city gets tuned
// gradients + geometric tile pattern (a stand-in "ambience", not a fake
// photo) instead of lorem stock images. Three frames per city give the
// reference card's carousel (dots + arrows) something honest to page
// through. Makkah leans warm/gold, Madinah cool/green — both are real, and
// no image is presented as a photograph.
const CITY_FRAMES = {
  makkah: [
    "bg-gradient-to-br from-amber-700 via-orange-800 to-rose-900",
    "bg-gradient-to-tr from-rose-900 via-orange-800 to-amber-700",
    "bg-gradient-to-b from-amber-800 via-orange-700 to-rose-950",
  ],
  madinah: [
    "bg-gradient-to-br from-emerald-800 via-teal-800 to-slate-900",
    "bg-gradient-to-tr from-slate-900 via-teal-800 to-emerald-700",
    "bg-gradient-to-b from-emerald-700 via-teal-700 to-slate-950",
  ],
};

const DOT_PATTERN = {
  backgroundImage: "radial-gradient(rgba(255,255,255,0.35) 1px, transparent 1px)",
  backgroundSize: "16px 16px",
};

const TILT_SPRING = { stiffness: 300, damping: 30, mass: 0.6 };

// Reference (@ravikatiyar162/card-22) carousel slide — enter from the side
// the arrow points, exit toward the other.
const carouselVariants = {
  enter: (direction) => ({ x: direction > 0 ? "100%" : "-100%", opacity: 0 }),
  center: { zIndex: 1, x: 0, opacity: 1 },
  exit: (direction) => ({ zIndex: 0, x: direction < 0 ? "100%" : "-100%", opacity: 0 }),
};

const CAROUSEL_TRANSITION = {
  x: { type: "spring", stiffness: 300, damping: 30 },
  opacity: { duration: 0.2 },
};

export default function HotelCard({ hotel }) {
  const frames = CITY_FRAMES[hotel.city] || CITY_FRAMES.makkah;
  const tags = [hotel.city_display, ...(hotel.area ? [hotel.area] : [])];

  // Same meta rhythm as the reference's "May 1 - 6 • Business host": the
  // thing agents actually shop on (walking time to Masjid) then the city.
  // Falls back to area when a hotel has no coordinates yet.
  const metaParts = [];
  if (hotel.walk_label) {
    metaParts.push(`${hotel.walk_label} dari Masjid`);
  } else if (hotel.distance_label && hotel.distance_label !== "—") {
    metaParts.push(`${hotel.distance_label} ke Masjid`);
  } else if (hotel.area) {
    metaParts.push(hotel.area);
  }
  metaParts.push(hotel.city_display);

  const description =
    hotel.note?.trim() ||
    `Hotel bintang ${hotel.stars} di ${hotel.city_display}${hotel.area ? `, area ${hotel.area}` : ""}.`;

  const [index, setIndex] = useState(0);
  const [direction, setDirection] = useState(0);

  const changeImage = (newDirection) => {
    setDirection(newDirection);
    setIndex((prev) => (prev + newDirection + frames.length) % frames.length);
  };

  const ref = useRef(null);
  const prefersReducedMotion = useReducedMotion();

  // Pointer position normalized to 0-1 within the card, centered at rest.
  // Drives the 3D tilt and the glare that tracks it — the whole card tips
  // like a photo card held in hand, no real photography required since the
  // gradient blocks themselves are what's tilting.
  const px = useMotionValue(0.5);
  const py = useMotionValue(0.5);

  const rotateX = useSpring(useTransform(py, [0, 1], [8, -8]), TILT_SPRING);
  const rotateY = useSpring(useTransform(px, [0, 1], [-8, 8]), TILT_SPRING);
  const glareX = useTransform(px, [0, 1], ["0%", "100%"]);
  const glareY = useTransform(py, [0, 1], ["0%", "100%"]);
  const glare = useMotionTemplate`radial-gradient(circle at ${glareX} ${glareY}, rgba(255,255,255,0.25), transparent 55%)`;

  const handleMouseMove = (e) => {
    if (prefersReducedMotion || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    px.set((e.clientX - rect.left) / rect.width);
    py.set((e.clientY - rect.top) / rect.height);
  };
  const handleMouseLeave = () => {
    px.set(0.5);
    py.set(0.5);
  };

  return (
    <motion.div
      ref={ref}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      whileHover={prefersReducedMotion ? undefined : { scale: 1.02 }}
      transition={{ scale: TILT_SPRING }}
      style={{ rotateX, rotateY, transformPerspective: 1000 }}
      className="group w-full overflow-hidden rounded-2xl border border-border bg-card text-card-foreground shadow-lg transition-shadow duration-300 hover:shadow-2xl hover:shadow-black/20"
    >
      {/* Image carousel section */}
      <div className="relative h-64">
        <AnimatePresence initial={false} custom={direction}>
          <motion.div
            key={index}
            custom={direction}
            variants={carouselVariants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={CAROUSEL_TRANSITION}
            className={`absolute inset-0 flex items-center justify-center ${frames[index]}`}
          >
            <div className="absolute inset-0 opacity-40" style={DOT_PATTERN} />
            <Icon
              name="building"
              size={64}
              strokeWidth={1}
              className="relative text-white/25"
            />
          </motion.div>
        </AnimatePresence>

        {/* Carousel navigation — revealed on hover, like the reference */}
        <div
          className="absolute inset-0 flex items-center justify-between opacity-0 transition-opacity duration-200 group-hover:opacity-100"
          style={{ padding: 8 }}
        >
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="rounded-full bg-black/30 text-white hover:bg-black/50 hover:text-white"
            onClick={() => changeImage(-1)}
            aria-label="Previous image"
          >
            <ChevronLeft className="size-5" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="rounded-full bg-black/30 text-white hover:bg-black/50 hover:text-white"
            onClick={() => changeImage(1)}
            aria-label="Next image"
          >
            <ChevronRight className="size-5" />
          </Button>
        </div>

        {/* Top badges: tags left, rating right */}
        <div className="absolute top-3 left-3 flex gap-2">
          {tags.map((tag) => (
            <Badge key={tag} variant="secondary" className="bg-background/70 backdrop-blur-sm" style={{ padding: "2px 8px" }}>
              {tag}
            </Badge>
          ))}
        </div>
        <div className="absolute top-3 right-3">
          <Badge variant="secondary" className="flex items-center gap-1 bg-background/70 backdrop-blur-sm" style={{ padding: "2px 8px" }}>
            <Icon name="star" size={12} className="text-yellow-400" />
            {hotel.stars.toFixed(1)}
          </Badge>
        </div>

        {/* Pagination dots */}
        <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 gap-1.5">
          {frames.map((_, i) => (
            <button
              key={i}
              type="button"
              onClick={() => {
                setDirection(i > index ? 1 : -1);
                setIndex(i);
              }}
              className={`h-1.5 rounded-full border-0 transition-all ${i === index ? "w-4 bg-white" : "w-1.5 bg-white/50"}`}
              style={{ padding: 0 }}
              aria-label={`Go to image ${i + 1}`}
            />
          ))}
        </div>

        {/* Pointer-tracking glare, kept on top of the frames */}
        <motion.div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
          style={{ background: glare }}
        />
      </div>

      {/* Content section — reference spacing (p-5 / space-y-4) restated
          inline because design.css's unlayered `* { padding: 0; margin: 0 }`
          beats the equivalent Tailwind utilities on these pages. */}
      <div style={{ padding: 20 }}>
        <div className="flex items-start justify-between gap-2" style={{ marginBottom: 16 }}>
          <h3 className="text-xl font-bold">{hotel.name}</h3>
          {hotel.stars >= 5 && (
            <Badge variant="outline" style={{ padding: "2px 8px" }}>
              Top rated
            </Badge>
          )}
        </div>

        <div className="text-sm text-muted-foreground" style={{ marginBottom: 16 }}>
          {metaParts.join(" • ")}
        </div>

        <p className="text-sm leading-relaxed text-muted-foreground" style={{ marginBottom: 16 }}>
          {description}
        </p>

        <div className="flex items-center justify-between" style={{ paddingTop: 8 }}>
          <p className="font-semibold">
            {hotel.stars} <span className="text-sm font-normal text-muted-foreground">Bintang</span>
          </p>
          <Button type="button" className="group">
            Book Now
            <ArrowRight className="transition-transform group-hover:translate-x-1" />
          </Button>
        </div>
      </div>
    </motion.div>
  );
}
