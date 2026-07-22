import { Icon } from "../icons.jsx";
import { Drawer, DrawerClose, DrawerContent, DrawerHeader, DrawerTitle } from "./ui/drawer.jsx";

// shadcn/vaul rebuild of ../ui/ActionSheet.jsx — same props. Drawer already
// owns the drag handle, focus trap, Escape-to-close, and drag-to-dismiss
// that the old manual createPortal + CSS implementation didn't have.
export default function ActionSheet({ open, onClose, title, actions }) {
  return (
    <Drawer open={open} onOpenChange={(next) => { if (!next) onClose(); }} direction="bottom">
      <DrawerContent>
        {title && (
          <DrawerHeader>
            <DrawerTitle>{title}</DrawerTitle>
          </DrawerHeader>
        )}
        <div style={{ display: "flex", flexDirection: "column", padding: "8px 16px 16px", gap: 4 }}>
          {actions.filter(Boolean).map((a, i) => {
            const style = { display: "flex", alignItems: "center", gap: 10, padding: "12px 8px", borderRadius: 8, textDecoration: "none", color: a.variant === "red" ? "var(--destructive)" : "var(--foreground)", background: "none", border: "none", fontSize: 14, textAlign: "left", cursor: "pointer" };
            return a.href ? (
              <a key={i} href={a.href} style={style} onClick={onClose}
                {...(a.external ? { target: "_blank", rel: "noreferrer" } : {})}>
                <Icon name={a.icon} size={16} /> {a.label}
              </a>
            ) : (
              <button key={i} type="button" style={style}
                onClick={(e) => { onClose(); a.onClick && a.onClick(e); }}>
                <Icon name={a.icon} size={16} /> {a.label}
              </button>
            );
          })}
          <DrawerClose asChild>
            <button type="button" style={{ marginTop: 8, padding: "12px 8px", borderRadius: 8, border: "1px solid var(--border)", background: "none", color: "var(--muted-foreground)", fontSize: 14, cursor: "pointer" }}>
              Cancel
            </button>
          </DrawerClose>
        </div>
      </DrawerContent>
    </Drawer>
  );
}
