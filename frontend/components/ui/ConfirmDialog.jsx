import { useCallback, useEffect, useState } from "react";
import { Icon } from "../icons.jsx";

// Reusable confirmation modal — replaces native confirm() for destructive
// actions. Render <ConfirmDialog> controlled by props, or use the useConfirm()
// hook below for the common "ask, then run a callback" flow.
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
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.();
      else if (e.key === "Enter") onConfirm?.();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onConfirm, onClose]);

  if (!open) return null;

  return (
    <div
      style={{ display: "flex", position: "fixed", inset: 0, zIndex: "var(--z-modal)", background: "rgba(0,0,0,.5)", alignItems: "center", justifyContent: "center", padding: 20 }}
      onClick={(e) => e.target === e.currentTarget && onClose?.()}
    >
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--r-xl)", width: "100%", maxWidth: 400, overflow: "hidden", boxShadow: "0 24px 48px rgba(0,0,0,.4)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "24px 24px 20px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ width: 36, height: 36, flexShrink: 0, background: "var(--red-muted)", borderRadius: "var(--r)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--red)" }}>
            <Icon name="trash" size={18} />
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text)" }}>{title}</div>
            <div style={{ fontSize: 12, color: "var(--text-2)", marginTop: 2 }}>This action cannot be undone</div>
          </div>
        </div>
        <div style={{ padding: "20px 24px", fontSize: 13, color: "var(--text-2)" }}>
          {message}
          {detail && <div style={{ marginTop: 6 }}>{detail}</div>}
        </div>
        <div style={{ display: "flex", gap: 8, padding: "0 24px 24px" }}>
          <button type="button" className="btn btn-secondary btn-full" style={{ flex: 1 }} onClick={onClose}>{cancelLabel}</button>
          <button type="button" className={danger ? "btn btn-danger-solid btn-full" : "btn btn-primary btn-full"} style={{ flex: 1 }} onClick={onConfirm} autoFocus>{confirmLabel}</button>
        </div>
      </div>
    </div>
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
