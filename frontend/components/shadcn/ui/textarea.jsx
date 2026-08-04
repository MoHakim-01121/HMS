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
        // Matches the .shadcn-root textarea rule in tailwind.css — see input.jsx.
        "flex field-sizing-content min-h-[96px] w-full rounded-[16px] border-2 border-input bg-card px-[14px] py-[12px] text-[14px] transition-[color,border-color] outline-none placeholder:text-muted-foreground focus-visible:border-ring disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive",
        className
      )}
      {...props} />
  );
}

export { Textarea }
