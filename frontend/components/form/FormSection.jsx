export default function FormSection({ label, sub, children }) {
  return (
    <div className="form-section">
      {label && (
        <div className="form-section-label">
          {label}
          {sub && (
            <span style={{ fontFamily: "inherit", fontWeight: 400, fontSize: 11, textTransform: "none", letterSpacing: 0, color: "var(--text-3)", marginLeft: 4 }}>{sub}</span>
          )}
        </div>
      )}
      {children}
    </div>
  );
}
