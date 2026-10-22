import * as React from "react"

import { cn } from "@/lib/utils"

function Textarea({
  className,
  ...props
}) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        // Same control look as input.jsx.
        "flex field-sizing-content min-h-24 w-full rounded-control border-2 border-field bg-card px-3.5 py-3 text-[14px] leading-[1.55] text-foreground shadow-none transition-[border-color] duration-[140ms] ease-[ease] outline-none max-[600px]:text-[16px] placeholder:text-muted-foreground focus:border-ring focus:shadow-none focus:outline-2 focus:outline-solid focus:outline-offset-2 focus:outline-ring disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive",
        className
      )}
      {...props} />
  );
}

export { Textarea }
