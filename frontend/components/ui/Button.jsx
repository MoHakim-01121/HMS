// Wraps the existing .btn / .btn-* classes from design.css.
export default function Button({
  variant = "primary",
  size,
  className = "",
  children,
  ...rest
}) {
  const cls = ["btn", `btn-${variant}`, size && `btn-${size}`, className]
    .filter(Boolean)
    .join(" ");
  return (
    <button className={cls} {...rest}>
      {children}
    </button>
  );
}
