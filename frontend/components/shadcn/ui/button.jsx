import * as React from "react"
import { cva } from "class-variance-authority";
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

// Homlu direction: full-pill shape on every size/variant (measured off the
// live homlu-dashboard-template.vercel.app reference — primary CTAs and
// toolbar buttons are both stadium-shaped, never rounded-rect).
//
// `no-underline text-current` in the base is load-bearing for `asChild` +
// anchor usage (Calendar's PDF / "Hari ini" / settings buttons): tailwind.css
// imports only theme.css and utilities.css, never preflight.css, so nothing in
// the app resets the UA `a` rule — an <a> inside a Button rendered at
// rgb(0,0,238) with an underline. Variants that do set a text color
// (default/destructive/secondary/link) still win, since cva emits them after
// the base and twMerge keeps the last of a conflicting pair.
const buttonVariants = cva(
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-full border-0 bg-transparent text-sm font-medium whitespace-nowrap no-underline text-current transition-all outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        destructive:
          "bg-destructive text-white hover:bg-destructive/90 focus-visible:ring-destructive/20 dark:bg-destructive/60 dark:focus-visible:ring-destructive/40",
        // 2px stroke, no shadow — the same treatment Homlu gives every
        // bordered control (search box, date-range pills, the appearance
        // sheet's choice cards all measured `border-2` with `box-shadow: none`).
        // A hairline + shadow-xs here read as a different system sitting next
        // to the 2px form fields.
        outline:
          "border-2 border-input bg-card hover:border-ring hover:text-foreground",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost:
          "hover:bg-accent hover:text-accent-foreground dark:hover:bg-accent/50",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2 has-[>svg]:px-3",
        xs: "h-6 gap-1 px-2 text-xs has-[>svg]:px-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-1.5 px-3 has-[>svg]:px-2.5",
        // Form scale: matches the 40px control height so a submit row doesn't
        // sit visibly shorter than the fields above it. (Was h-10 and unused
        // anywhere in the app, so re-tuning it breaks nothing.) Explicit px —
        // html is 14px here, so h-11 would resolve to 38.5px. See --radius-control.
        // (Horizontal padding is also restated in tailwind.css — design.css's
        // universal reset zeroes padding on everything and outranks utilities.)
        lg: "h-[40px] px-[22px] text-[14px] has-[>svg]:px-[18px]",
        icon: "size-9",
        "icon-xs": "size-6 [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-8",
        "icon-lg": "size-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

// forwardRef is required, not stylistic: Radix triggers (DropdownMenuTrigger
// asChild, PopoverTrigger asChild, ...) clone this component and need a real
// ref to the underlying DOM button to measure its position for the popper —
// without it the anchor ref silently fails and the menu renders at (0,0).
const Button = React.forwardRef(function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}, ref) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      ref={ref}
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props} />
  );
});

export { Button, buttonVariants }
