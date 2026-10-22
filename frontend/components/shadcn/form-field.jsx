import { cloneElement, isValidElement } from "react";
import { Label } from "./ui/label.jsx";
import { Input } from "./ui/input.jsx";
import { cn } from "@/lib/utils";

const SPAN = { 2: "col-span-2", 3: "col-span-3", 4: "col-span-4" };

// Whole-number money typed as text: shown grouped ("12,500,000") like the
// AmountIn fields, handed to onChange as plain digits ("12500000"), a leading
// "-" kept only when `signed`. A type="number" field had no grouping and its
// value changed under the mouse wheel.
export function amountValue(v, signed = false) {
  const s = String(v ?? "").trim();
  const d = s.split(".")[0].replace(/[^\d]/g, "");
  return (signed && s.startsWith("-") ? "-" : "") + d;
}
export function amountText(v, signed = false) {
  const c = amountValue(v, signed);
  const d = c.replace("-", "");
  return (c.startsWith("-") ? "-" : "") + (d ? Number(d).toLocaleString("en-US") : "");
}

// shadcn Label/Input-based rebuild of ../form/FormField.jsx — same props,
// same aria-describedby wiring for both the default <Input> and any custom
// `children` (e.g. a <select> or <textarea> passed in by a page).
export default function FormField({
  label, name, error, required, hint, type = "text",
  value, onChange, placeholder, autoFocus, span, inputMode, step, min, disabled, className, children,
  amount, signed,
}) {
  const describedBy = error ? `${name}-error` : hint ? `${name}-hint` : undefined;
  return (
    <div data-slot="form-field" className={cn("flex flex-col gap-1.5", SPAN[span], className)}>
      {label && <Label htmlFor={name}>{label}{required ? " *" : ""}</Label>}
      {children
        ? (describedBy && isValidElement(children) ? cloneElement(children, { "aria-describedby": describedBy }) : children)
        : (
          <Input
            id={name} name={name} type={amount ? "text" : type}
            value={amount ? amountText(value, signed) : value ?? ""}
            onChange={(e) => onChange?.(amount ? amountValue(e.target.value, signed) : e.target.value)}
            placeholder={placeholder} autoFocus={autoFocus}
            inputMode={amount ? "numeric" : inputMode} step={amount ? undefined : step} min={amount ? undefined : min} disabled={disabled}
            aria-invalid={error ? "true" : undefined}
            aria-describedby={describedBy}
          />
        )}
      {hint && !error && <div id={`${name}-hint`} className="text-[12px] text-muted-foreground">{hint}</div>}
      {error && <div id={`${name}-error`} role="alert" className="text-[12px] text-destructive">{error}</div>}
    </div>
  );
}
