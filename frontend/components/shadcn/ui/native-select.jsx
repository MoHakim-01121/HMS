import * as React from "react"

import { cn } from "@/lib/utils"
import { controlClass } from "./input.jsx"

// A browser <select> with the Input look, for short fixed lists where a Radix
// Select would be more than the job needs.
function NativeSelect({ className, ...props }) {
  return <select data-slot="native-select" className={cn(controlClass, "cursor-pointer appearance-none", className)} {...props} />;
}

export { NativeSelect }
