import { Link } from "@inertiajs/react";

// Reusable back link (matches the .page-back style used on detail pages).
// Defaults to Home; pass href to point elsewhere.
export default function PageBack({ href = "/", label = "Back" }) {
  return (
    <Link href={href} className="page-back">
      <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M19 12H5m7-7l-7 7 7 7" />
      </svg>
      {label}
    </Link>
  );
}
