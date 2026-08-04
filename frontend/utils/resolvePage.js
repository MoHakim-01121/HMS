// Mirrors main.jsx's Inertia `resolve` — used by form-modal.jsx to mount a
// page component fetched manually (outside Inertia's own router.visit), so
// Create/Edit forms can render as a dialog instead of a full navigation.
const pages = import.meta.glob("../pages/**/*.jsx", { eager: true });

export function resolvePage(name) {
  return pages[`../pages/${name}.jsx`]?.default;
}
