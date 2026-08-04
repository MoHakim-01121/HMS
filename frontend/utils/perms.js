/**
 * Client-side mirror of the server permission matrix (hw/permissions.py).
 *
 * These helpers decide what the UI *offers*. They are not a security boundary:
 * every guarded route re-checks the same matrix server-side with @require_perm,
 * so a hidden button and a forged request end up at the same 403/redirect.
 * Hiding is purely so users are not shown doors that will not open.
 *
 * Shape of the shared prop (see hw/inertia_share.py):
 *   auth.user.perms = { cl: ["create", "edit", "export", "view"], ... }
 */
import { usePage } from "@inertiajs/react";

export function can(user, module, action) {
  const perms = user?.perms;
  if (!perms) return false;
  const actions = perms[module];
  return Array.isArray(actions) && actions.includes(action);
}

/** Permission helpers bound to the current page's authenticated user. */
export function usePerms() {
  const { props } = usePage();
  const user = props?.auth?.user ?? null;

  return {
    user,
    role: user?.role ?? null,
    roleLabel: user?.role_label ?? "",
    companies: user?.companies ?? [],
    can: (module, action) => can(user, module, action),
    canAny: (module, ...actions) => actions.some((a) => can(user, module, a)),
    /** True when the module is visible at all (any permission on it). */
    sees: (module) => Boolean(user?.perms?.[module]?.length),
    isAdmin: user?.role === "admin",
  };
}

export default usePerms;
