import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils";

// An inline notice box on a form or page: a server error, or a warning.
const alertVariants = cva("rounded-[10px] border px-3.5 py-2.5 text-[13px] leading-normal font-medium", {
  variants: {
    variant: {
      default: "border-border",
      destructive: "border-red/40 bg-red/8 text-red",
    },
  },
  defaultVariants: { variant: "default" },
});

function Alert({ className, variant, ...props }) {
  return <div data-slot="alert" role="alert" className={cn(alertVariants({ variant }), className)} {...props} />;
}

export { Alert, alertVariants };
