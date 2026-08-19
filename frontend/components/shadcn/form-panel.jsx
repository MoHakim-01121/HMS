import { Children, useContext } from "react";
import { FormModalContext } from "./form-modal.jsx";
import FormSection from "./form-section.jsx";

export default function FormPanel({ children }) {
  // Inside a FormModal dialog, DialogContent already supplies the card
  // surface (bg + radius + shadow + padding) — wrapping again here would
  // draw a card inside a card.
  const rows = Children.toArray(children);
  const separated = rows.flatMap((child, i) => {
    const isSection = child.type === FormSection;
    const prevSection = i > 0 && rows[i - 1].type === FormSection;
    if (isSection && prevSection) {
      return [
        <div key={`sep-${i}`} data-slot="form-section-sep" style={{ height: 1, background: "var(--border)", flexShrink: 0 }} />,
        child,
      ];
    }
    return [child];
  });
  const gap = 52;
  if (useContext(FormModalContext)?.inModal) {
    return <div data-slot="form-panel" style={{ display: "flex", flexDirection: "column", gap }}>{separated}</div>;
  }
  return (
    <div data-slot="form-panel" style={{ background: "var(--card)", borderRadius: "var(--radius-card)", padding: 24, display: "flex", flexDirection: "column", gap }}>
      {separated}
    </div>
  );
}
