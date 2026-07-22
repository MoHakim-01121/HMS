import { useCallback, useState } from "react";
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
export default function ConfirmDialog({
  open,
  title = "Are you sure?",
  message,
  detail,
  confirmLabel = "Delete",
  cancelLabel = "Cancel",
  danger = true,
  onConfirm,
  onClose,
}) {
  return (
    <AlertDialog open={open} onOpenChange={(next) => { if (!next) onClose?.(); }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>
            {message}
            {detail && <div style={{ marginTop: 6 }}>{detail}</div>}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onClose}>{cancelLabel}</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm} variant={danger ? "destructive" : "default"}>
            {confirmLabel}
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
