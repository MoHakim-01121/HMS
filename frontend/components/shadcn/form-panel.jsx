import { useContext } from "react";
import { FormModalContext } from "./form-modal.jsx";

export default function FormPanel({ children }) {
  // Inside a FormModal dialog, DialogContent already supplies the card
  // surface (bg + radius + shadow + padding) — wrapping again here would
  // draw a card inside a card.
  if (useContext(FormModalContext)?.inModal) {
    return <div data-slot="form-panel" style={{ display: "flex", flexDirection: "column", gap: 32 }}>{children}</div>;
  }
  return (
    <div data-slot="form-panel" style={{ background: "var(--card)", borderRadius: "var(--radius-card)", padding: 24, display: "flex", flexDirection: "column", gap: 32 }}>
      {children}
    </div>
  );
}
