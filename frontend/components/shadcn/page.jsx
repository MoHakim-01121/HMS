import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils";

// The column every app page sits in. `page` is the list/detail width,
// `form` the narrower column of a form opened by URL. Inside the form modal
// the dialog supplies the frame, so the column flattens to nothing.
const IN_MODAL = "in-data-[slot=modal-body]:m-0 in-data-[slot=modal-body]:max-w-none in-data-[slot=modal-body]:animate-none in-data-[slot=modal-body]:p-0!";

export const pageVariants = cva(
  cn("relative z-1 mx-auto font-sans animate-page-in print:max-w-full print:animate-none print:p-0", IN_MODAL),
  {
    variants: {
      size: {
        page: "max-w-[1040px] px-5 pt-7 pb-15 max-[600px]:px-3 max-[600px]:pt-[calc(48px+env(safe-area-inset-top))] max-[600px]:pb-[calc(72px+env(safe-area-inset-bottom))]",
        form: "max-w-[680px] px-5 pt-5 pb-24 max-[600px]:px-3 max-[600px]:pt-3.5 max-[600px]:pb-28",
      },
    },
    defaultVariants: { size: "page" },
  },
);

export default function Page({ size, className, children, ...props }) {
  return <div className={cn(pageVariants({ size }), className)} {...props}>{children}</div>;
}
