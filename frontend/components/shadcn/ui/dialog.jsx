import * as React from "react"
import { XIcon } from "lucide-react"
import { Dialog as DialogPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"
import { Button } from "@/components/shadcn/ui/button"

function Dialog({
  ...props
}) {
  return <DialogPrimitive.Root data-slot="dialog" {...props} />;
}

function DialogTrigger({
  ...props
}) {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />;
}

function DialogPortal({
  ...props
}) {
  return <DialogPrimitive.Portal data-slot="dialog-portal" {...props} />;
}

function DialogClose({
  ...props
}) {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />;
}

const DialogOverlay = React.forwardRef(function DialogOverlay({
  className,
  ...props
}, ref) {
  return (
    <DialogPrimitive.Overlay
      ref={ref}
      data-slot="dialog-overlay"
      className={cn(
        // backdrop-blur-xs lives on the base scrim, not on individual call
        // sites. Homlu's own overlay measures as a flat black/50 with no
        // backdrop-filter, and the form modal was built to match that — but
        // that left it the only overlay in HMS without blur, while the ⌘K
        // palette, the Invoice CL-import modal and design.css's legacy
        // .modal-overlay all had it. One scrim treatment for every overlay
        // beats literal fidelity to the reference on this one detail.
        "fixed inset-0 z-50 bg-black/50 backdrop-blur-xs data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0",
        className
      )}
      {...props} />
  );
});

// Stock shadcn ships this as a bare 16px glyph at 70% opacity with a 2px
// radius and no hit area of its own — it reads as a stray icon rather than a
// control, and none of it (the faded ink, the square corner) belongs to the
// monochrome/full-pill language the rest of the app was moved to. Rebuilt as a
// real circular icon button on the same footing as every other Button: muted
// until hovered, then it picks up the standard hover surface. Exported so the
// form modal can place its own copy inside the header row instead of having
// one absolutely positioned over the content.
// Built on Button rather than styling the raw Radix Close directly: Tailwind's
// Preflight is off in this project, so a bare <button> keeps the UA's own
// chrome — a grey background and a 2px outset bevel — unless something
// explicitly clears it. Styling the primitive by hand missed that (the X
// rendered as a grey 3D-bevelled box), and Button's base already carries the
// `border-0 bg-transparent` reset plus the full-pill shape everything else
// uses. Button is forwardRef, so asChild passes the ref through correctly.
const DialogCloseButton = React.forwardRef(function DialogCloseButton({ className, ...props }, ref) {
  return (
    <DialogPrimitive.Close ref={ref} data-slot="dialog-close" asChild {...props}>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label="Close"
        className={cn("size-[32px] rounded-full text-muted-foreground hover:text-foreground", className)}>
        <XIcon />
        <span className="sr-only">Close</span>
      </Button>
    </DialogPrimitive.Close>
  );
});

const DialogContent = React.forwardRef(function DialogContent({
  className,
  overlayClassName,
  children,
  showCloseButton = true,
  ...props
}, ref) {
  return (
    <DialogPortal data-slot="dialog-portal">
      <DialogOverlay className={overlayClassName} />
      <DialogPrimitive.Content
        ref={ref}
        data-slot="dialog-content"
        className={cn(
          // font-sans: Radix portals to document.body, outside every page's
          // .shadcn-root wrapper — see dropdown-menu.jsx for the full story.
          // Without it this falls back to body's "Fira Sans".
          // border-border, not stock shadcn's bare `border`: Preflight is off in
          // this project (tailwind.css imports only theme.css + utilities.css),
          // so the base rule that would have set a default border-color never
          // lands. `border` alone sets width/style only and the colour falls
          // back to CSS's initial value, currentColor — i.e. --foreground, pure
          // white in dark mode — instead of the 8%-white --border every
          // hand-written surface in tailwind.css uses. Every shadcn primitive
          // that draws a border must name its colour explicitly here.
          "fixed top-[50%] left-[50%] z-50 grid w-full max-w-[calc(100%-2rem)] translate-x-[-50%] translate-y-[-50%] gap-4 rounded-lg border border-border bg-background p-6 font-sans shadow-lg duration-200 outline-none data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 sm:max-w-lg",
          className
        )}
        {...props}>
        {children}
        {showCloseButton && <DialogCloseButton className="absolute top-4 right-4" />}
      </DialogPrimitive.Content>
    </DialogPortal>
  );
});

function DialogHeader({
  className,
  ...props
}) {
  return (
    <div
      data-slot="dialog-header"
      className={cn("flex flex-col gap-2 text-center sm:text-left", className)}
      {...props} />
  );
}

function DialogFooter({
  className,
  showCloseButton = false,
  children,
  ...props
}) {
  return (
    <div
      data-slot="dialog-footer"
      className={cn("flex flex-col-reverse gap-2 sm:flex-row sm:justify-end", className)}
      {...props}>
      {children}
      {showCloseButton && (
        <DialogPrimitive.Close asChild>
          <Button variant="outline">Close</Button>
        </DialogPrimitive.Close>
      )}
    </div>
  );
}

function DialogTitle({
  className,
  ...props
}) {
  return (
    <DialogPrimitive.Title
      data-slot="dialog-title"
      className={cn("text-lg leading-none font-semibold", className)}
      {...props} />
  );
}

function DialogDescription({
  className,
  ...props
}) {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props} />
  );
}

export {
  Dialog,
  DialogClose,
  DialogCloseButton,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
}
