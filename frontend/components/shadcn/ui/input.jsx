import * as React from "react"

import { cn } from "@/lib/utils"

function Input({
  className,
  type,
  ...props
}) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        // Geometry mirrors the form-control rule in tailwind.css: 40px tall,
        // 16px radius, 2px stroke. Radius and stroke are Homlu's measured
        // values; the height is two steps under its 48px, since HMS forms carry
        // far more fields per screen than Homlu's reference does. That CSS rule
        // is the one that actually paints, since design.css's unlayered input
        // reset outranks these utilities — see the comment there.
        "h-[40px] w-full min-w-0 rounded-[16px] border-2 border-input bg-card px-[14px] text-[14px] transition-[color,border-color] outline-none selection:bg-primary selection:text-primary-foreground file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
        "focus-visible:border-ring",
        "aria-invalid:border-destructive",
        className
      )}
      {...props} />
  );
}

export { Input }
