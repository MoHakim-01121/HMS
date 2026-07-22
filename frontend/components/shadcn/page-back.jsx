import { Link } from "@inertiajs/react";

// Token-restyled rebuild of ../ui/PageBack.jsx — same props.
export default function PageBack({ href = "/", label = "Back" }) {
  return (
    <Link href={href} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--muted-foreground)", textDecoration: "none", marginBottom: 16 }}>
      <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M19 12H5m7-7l-7 7 7 7" />
      </svg>
      {label}
    </Link>
  );
}
