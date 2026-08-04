import { useCallback, useState } from "react";
import { Icon } from "@/components/icons.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "./ui/alert-dialog.jsx";

// shadcn/Radix rebuild of ../ui/ConfirmDialog.jsx — same props, same useConfirm()
// API. Radix's AlertDialog owns focus trap + Escape + Tab cycling, so the
// manual keydown listener the old version needed is gone entirely.
//
// Layout is the reference alert dialog: a small icon inline with the title, the
// description on its own full-width line below, actions right-aligned. The icon
// deliberately does NOT go through AlertDialogMedia — that slot is the other
// variant of this component, a 64px tinted square that takes its own grid
// column (row-span-2 at sm+) and pushes the title and description into a second
// column. Both are stock; this is the one that was picked.
//
// Also don't pass max-w/p/gap overrides to AlertDialogContent: `sm:max-w-*`
// loses to the primitive's `data-[size=default]:sm:max-w-lg`, which twMerge
// can't dedupe (different variant sets) and which wins on specificity anyway
// (class+attribute). Use the `size` prop instead — "sm" is the narrow variant.
export default function ConfirmDialog({
  open,
  title = "Are you sure?",
  message,
  detail,
  confirmLabel = "Delete",
  cancelLabel = "Cancel",
  danger = true,
  icon,
  onConfirm,
  onClose,
}) {
  const { t } = useI18n();
  return (
    <AlertDialog open={open} onOpenChange={(next) => { if (!next) onClose?.(); }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          {/* The icon rides inside the title so it sits on the text baseline row
              and the description below it stays full width. shrink-0 keeps it
              from being squeezed when the title wraps on a phone. */}
          <AlertDialogTitle className="flex items-center gap-2">
            <Icon name={icon || (danger ? "trash" : "alert")} size={18} strokeWidth={1.75} className="shrink-0" />
            {t(title)}
          </AlertDialogTitle>
          <AlertDialogDescription>{message}</AlertDialogDescription>
        </AlertDialogHeader>
        {/* Sibling of the header, not a child: `detail` must never nest a div in a <p>. */}
        {detail && (
          <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs leading-5 text-muted-foreground">
            {detail}
          </div>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onClose}>{t(cancelLabel)}</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm} variant={danger ? "destructive" : "default"}>
            {t(confirmLabel)}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// Hook for the ask-then-run flow. Returns [confirm, dialog]:
//   const [confirm, confirmDialog] = useConfirm();
//   confirm({ message: "Delete X?", onConfirm: () => router.post(...) });
//   ...render {confirmDialog} once in the page.
export function useConfirm() {
  const [cfg, setCfg] = useState(null);

  const confirm = useCallback((options) => setCfg(options || {}), []);
  const close = useCallback(() => setCfg(null), []);

  const dialog = (
    <ConfirmDialog
      {...(cfg || {})}
      open={!!cfg}
      onClose={close}
      onConfirm={() => {
        cfg?.onConfirm?.();
        close();
      }}
    />
  );

  return [confirm, dialog];
}
