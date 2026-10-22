export default function FormSection({ label, sub, action, children }) {
  return (
    <div data-slot="form-section" className="flex flex-col gap-3 *:min-w-0">
      {(label || action) && (
        <div className="flex items-center justify-between gap-2">
          {label && (
            <div className="text-[14px] font-bold text-foreground">
              {label}
              {sub && <span className="ml-1.5 font-normal text-muted-foreground">{sub}</span>}
            </div>
          )}
          {action}
        </div>
      )}
      {children}
    </div>
  );
}
