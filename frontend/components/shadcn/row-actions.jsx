import { useState } from "react";
import { Icon } from "../icons.jsx";
import ActionSheet from "../ui/ActionSheet.jsx";
import { Button } from "./ui/button.jsx";

// shadcn Button-based rebuild of ../ui/RowActions.jsx — same `actions` prop
// shape. The kebab button still opens the existing ActionSheet (mobile bottom
// sheet) unchanged; that component is out of scope for this batch.
export default function RowActions({ actions }) {
  const [open, setOpen] = useState(false);
  const list = actions.filter(Boolean);
  return (
    <div className="row-actions" onClick={(e) => e.stopPropagation()}>
      <span className="ra-inline">
        {list.map((a, i) => {
          const variantCls = a.variant ? `btn-icon-${a.variant}` : undefined;
          return a.href ? (
            <Button key={i} asChild variant="ghost" size="icon" className={variantCls} title={a.label}>
              <a href={a.href} {...(a.external ? { target: "_blank", rel: "noreferrer" } : {})}>
                <Icon name={a.icon} size={14} strokeWidth={a.strokeWidth} />
              </a>
            </Button>
          ) : (
            <Button key={i} variant="ghost" size="icon" className={variantCls} title={a.label} onClick={a.onClick}>
              <Icon name={a.icon} size={14} strokeWidth={a.strokeWidth} />
            </Button>
          );
        })}
      </span>
      <Button
        variant="ghost" size="icon" className="ra-kebab" aria-label="Actions"
        aria-haspopup="true" aria-expanded={open} onClick={() => setOpen(true)}
      >
        <Icon name="dots" size={17} />
      </Button>
      <ActionSheet open={open} onClose={() => setOpen(false)} actions={list} />
    </div>
  );
}
