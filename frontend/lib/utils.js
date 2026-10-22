import { clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// tailwind-merge only knows Tailwind's default scale; teach it the theme's own
// tokens (tailwind.css @theme) so `shadow-md` and `shadow-menu` resolve to one.
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      shadow: ["menu", "popover", "palette"],
      radius: ["control", "card"],
      ease: ["out-quint", "in-quick", "drawer"],
      animate: ["menu-in", "menu-out", "panel-in", "fade-in", "rise-in"],
    },
  },
});

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
