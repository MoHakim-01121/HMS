# HMS

Django + Inertia + React 18 hotel management app. Backend in `hw/`, frontend in `frontend/`.

## Frontend UI standard: shadcn/ui + Tailwind utilities

The app (not the public landing page) has one way to style things. Consistency comes from shared components, not CSS classes.

1. **Tokens** live only in `frontend/styles/tailwind.css`. Values go in `:root` (light) and `[data-theme="dark"]`; they become utilities through `@theme inline` (`bg-card`, `text-danger-text`, `border-hairline`, `rounded-card`, `shadow-menu`, `ease-out-quint`, `animate-menu-in`). Never write hex, rgb or `var(--x)` colours in JSX. If a token is missing, add it to `:root` and `@theme`.
2. **Primitives** are `frontend/components/shadcn/ui/*` (button, input, select, dialog, dropdown-menu, popover, drawer, …). Variants use `cva` (see `ui/button.jsx`).
3. **Shared layouts**: `list-a.jsx` (ListPage, Kpi, Toolbar, TableCard, Pager, …), `form-a.jsx` (FormA, Field, Picker, …), `detail-a.jsx` (DPage, DHead, DCard, …), the shell (`layouts/AppLayout.jsx`, `components/shell/*`), and `dash.jsx` for dashboards. They style themselves with utilities and accept `className`, merged with `cn()` from `frontend/lib/utils.js`.
4. **Pages** compose components and use utilities for layout only (`grid`, `gap-*`, `col-span-*`, `mt-*`). Pages must not use custom class names, `<style>` blocks, `import "*.css"`, or `style={{}}` (except truly dynamic values such as a computed bar height or map coordinates).
5. A utility combination that repeats becomes a component (or a `cva` variant), never `@apply` or a new CSS class.
6. Arbitrary values (`text-[13px]`, `h-[38px]`) are fine inside shared components when they match the approved design. Do not invent new sizes in pages.
7. Motion: `transition-*` / `animate-*` with the theme easing tokens, under 200 ms for menus and overlays. Nothing animates on page mount (no row or card entrances), and nothing opened from the keyboard animates. Reduced motion is handled globally in `tailwind.css`. framer-motion is for the landing page only.
8. Non-utility CSS is allowed only in `tailwind.css`: tokens, `@theme`, `@utility` for things utilities cannot express, and overrides for third-party widgets (Leaflet, sonner).

**Tailwind v4 pitfalls met in this codebase:**
- `leading-normal` is 1.5, not the `normal` keyword; a CSS `font:` shorthand meant `leading-[normal]`.
- `outline-none` empties `--tw-outline-style`, so a focus ring needs `outline-solid` next to `outline-2`.
- `rotate-*`, `translate-*` and `scale-*` set their own CSS properties: transition `rotate`/`translate`, not `transform`.
- A descendant variant on a parent (`[&_th]:text-left`) outranks a utility on the child, so cells, rows and items are components that merge the page's classes with `cn()`.
- Class names that equal a Tailwind utility (`outline`, `static`, `hidden`, …) get that utility's CSS too.
- `cn()` is extended with the theme tokens in `frontend/lib/utils.js`; add a new theme token there too, or `twMerge` keeps both classes.
- Arbitrary colours that tailwind-merge cannot classify need a type hint: `bg-[color:color-mix(...)]`.
- Dark mode is `[data-theme="dark"]`, not the `dark:` variant (that follows the OS).

**Migration in progress.** Legacy CSS (`frontend/styles/legacy.css`, `list-a.css`, `form-a.css`, `detail-a.css`, `shell.css`, `dashboard.css`, `profile.css`, `calendar.css`, the custom-class sections of `tailwind.css`) is being moved into components; the plan lives in `~/.claude/plans/kita-plan-dulu-sebelum-robust-newell.md`. Do not add to those files or use their classes in new code. `npm run lint:ui` fails on new violations; files still being migrated are listed in `scripts/lint-ui-allowlist.json`, which may only shrink.

## Checking UI changes

- `npm run build` must pass.
- `node scripts/ui-shots.mjs current --compare` screenshots key pages (desktop and mobile, every dashboard role) and diffs them against `ui-shots/baseline/`. A refactor must report `0 changed` (`noise` lines are anti-aliasing and are fine). It needs runserver on :8000 and vite on :5173.

## Backend

- Python env: `.venv-linux`. Tests: `.venv-linux/bin/python3 manage.py test hw --noinput`, run serially.
- Local Postgres on port 5433 (TCP, `localhost`).
