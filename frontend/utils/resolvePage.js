// Mirrors main.jsx's Inertia `resolve` — used by form-modal.jsx to mount a
// page component fetched manually (outside Inertia's own router.visit), so
// Create/Edit forms can render as a dialog instead of a full navigation.
// Lazy on purpose: the modal loads one page chunk, not the whole app.
const pages = import.meta.glob("../pages/**/*.jsx");

export async function resolvePage(name) {
  const load = pages[`../pages/${name}.jsx`];
  return load ? (await load()).default : undefined;
}
