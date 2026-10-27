import * as React from "react"

import { cn } from "@/lib/utils"

// One control look for every field: 40px, 14px radius (--radius-control),
// 2px --field stroke (3:1 on card), ring outline on focus. 16px text on
// phones so iOS does not zoom into the field.
export const controlClass = cn(
  "h-10 w-full min-w-0 rounded-control border-2 border-field bg-card px-3.5 text-[14px] text-foreground shadow-none transition-[border-color] duration-[140ms] ease-[ease] outline-none max-[600px]:text-[16px]",
  "focus:border-ring focus:shadow-none focus:outline-2 focus:outline-solid focus:outline-offset-2 focus:outline-ring",
  "aria-invalid:border-destructive",
);

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
        controlClass,
        "selection:bg-primary selection:text-primary-foreground file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
        // A native file input draws its own button and file name.
        type === "file" && "h-auto min-h-10 px-2.5 py-[7px] text-[13px]",
        className
      )}
      {...props} />
  );
}

export { Input }
