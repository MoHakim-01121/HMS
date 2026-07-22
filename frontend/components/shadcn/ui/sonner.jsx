import {
  CircleCheckIcon,
  InfoIcon,
  Loader2Icon,
  OctagonXIcon,
  TriangleAlertIcon,
} from "lucide-react"
import { Toaster as Sonner } from "sonner";

// This project doesn't use next-themes (it has its own data-theme attribute
// mechanism, see frontend/layouts/useTheme.js) — the CLI-generated version of
// this file imports next-themes, which isn't installed here. Sonner's own
// theme prop is dropped entirely; its CSS variables are mapped directly to
// this project's --background/--foreground/etc tokens instead, so toasts
// follow [data-theme] the same way every other shadcn component does.
const Toaster = ({
  ...props
}) => {
  return (
    <Sonner
      className="toaster group"
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      style={
        {
          "--normal-bg": "var(--background)",
          "--normal-text": "var(--foreground)",
          "--normal-border": "var(--border)",
          "--success-bg": "var(--background)",
          "--success-text": "var(--foreground)",
          "--success-border": "var(--primary)",
          "--error-bg": "var(--background)",
          "--error-text": "var(--destructive)",
          "--error-border": "var(--destructive)",
          "--border-radius": "var(--radius)",
        }
      }
      {...props} />
  );
}

export { Toaster }
