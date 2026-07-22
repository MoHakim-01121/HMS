import { cloneElement, isValidElement } from "react";

export default function FormField({
  label, name, error, required, hint, type = "text",
  value, onChange, placeholder, autoFocus, span, inputMode, step, children,
}) {
  const describedBy = error ? `${name}-error` : hint ? `${name}-hint` : undefined;
  return (
    <div className="ff" style={span ? { gridColumn: `span ${span}` } : undefined}>
      {label && <label htmlFor={name}>{label}{required ? " *" : ""}</label>}
      {children
        ? (describedBy && isValidElement(children) ? cloneElement(children, { "aria-describedby": describedBy }) : children)
        : (
          <input
            id={name} name={name} type={type} value={value ?? ""}
            onChange={(e) => onChange?.(e.target.value)}
            placeholder={placeholder} autoFocus={autoFocus}
            inputMode={inputMode} step={step}
            aria-invalid={error ? "true" : undefined}
            aria-describedby={describedBy}
          />
        )}
      {hint && !error && <div className="hint" id={`${name}-hint`} style={{ marginTop: 6 }}>{hint}</div>}
      {error && <div className="hint" id={`${name}-error`} role="alert" style={{ marginTop: 6, color: "var(--red)" }}>{error}</div>}
    </div>
  );
}
