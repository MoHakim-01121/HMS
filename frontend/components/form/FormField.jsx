export default function FormField({
  label, name, error, required, hint, type = "text",
  value, onChange, placeholder, autoFocus, span, inputMode, step, children,
}) {
  return (
    <div className="ff" style={span ? { gridColumn: `span ${span}` } : undefined}>
      {label && <label htmlFor={name}>{label}{required ? " *" : ""}</label>}
      {children ?? (
        <input
          id={name} name={name} type={type} value={value ?? ""}
          onChange={(e) => onChange?.(e.target.value)}
          placeholder={placeholder} autoFocus={autoFocus}
          inputMode={inputMode} step={step}
          aria-invalid={error ? "true" : undefined}
        />
      )}
      {hint && !error && <div className="hint" style={{ marginTop: 6 }}>{hint}</div>}
      {error && <div className="hint" style={{ marginTop: 6, color: "var(--red)" }}>{error}</div>}
    </div>
  );
}
