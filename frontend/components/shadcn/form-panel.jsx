import { Children, useContext } from "react";
import { cn } from "@/lib/utils";
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
        <div key={`sep-${i}`} data-slot="form-section-sep" className="h-px shrink-0 bg-border" />,
        child,
      ];
    }
    return [child];
  });
  // min-w-0 on the children: a flex item will not shrink below its content,
  // so a wide table inside an overflow-x wrapper would push past the dialog
  // instead of scrolling.
  const inModal = useContext(FormModalContext)?.inModal;
  return (
    <div data-slot="form-panel" className={cn("flex flex-col gap-[52px] *:min-w-0", !inModal && "rounded-card bg-card p-6")}>
      {separated}
    </div>
  );
}
