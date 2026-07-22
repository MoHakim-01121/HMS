import { cloneElement, isValidElement } from "react";
import { Label } from "./ui/label.jsx";
import { Input } from "./ui/input.jsx";

// shadcn Label/Input-based rebuild of ../form/FormField.jsx — same props,
// same aria-describedby wiring for both the default <Input> and any custom
// `children` (e.g. a <select> or <textarea> passed in by a page).
export default function FormField({
  label, name, error, required, hint, type = "text",
  value, onChange, placeholder, autoFocus, span, inputMode, step, children,
}) {
  const describedBy = error ? `${name}-error` : hint ? `${name}-hint` : undefined;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, gridColumn: span ? `span ${span}` : undefined }}>
      {label && <Label htmlFor={name}>{label}{required ? " *" : ""}</Label>}
      {children
        ? (describedBy && isValidElement(children) ? cloneElement(children, { "aria-describedby": describedBy }) : children)
        : (
          <Input
            id={name} name={name} type={type} value={value ?? ""}
            onChange={(e) => onChange?.(e.target.value)}
            placeholder={placeholder} autoFocus={autoFocus}
            inputMode={inputMode} step={step}
            aria-invalid={error ? "true" : undefined}
            aria-describedby={describedBy}
          />
        )}
      {hint && !error && <div id={`${name}-hint`} style={{ fontSize: 12, color: "var(--muted-foreground)" }}>{hint}</div>}
      {error && <div id={`${name}-error`} role="alert" style={{ fontSize: 12, color: "var(--destructive)" }}>{error}</div>}
    </div>
  );
}
