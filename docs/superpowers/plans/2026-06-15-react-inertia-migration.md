# HMS → React (Inertia.js) Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up an Inertia.js + React + Vite frontend inside the existing Django HMS, then migrate the Invoice list + detail pages to React with the **current design preserved exactly**, leaving every other page on Django and fully working.

**Architecture:** Django keeps routing/views/ORM/auth. Page views call `inertia.render(request, 'Page/Name', props)`; `@inertiajs/react` renders the matching component. `django-vite` injects the Vite bundle (HMR in dev, manifest in prod). `design.css` is reused verbatim so there is zero visual change. PDFs, CSV, AI, search, map, and action endpoints stay Django and are called via `fetch`.

**Tech Stack:** Django 5.2, `inertia-django`, `django-vite`, Vite 5, `@vitejs/plugin-react`, React 18, `@inertiajs/react`, WhiteNoise (prod static).

**Verification model:** Each task ends with one or more of: `npm run build` succeeds, `python manage.py check` passes, dev server renders the page, and a named manual smoke check. The legacy template for any migrated view is kept on disk until the whole module is migrated, so every step is reversible.

---

## File Structure

```
package.json                         # NEW — Node deps + build scripts
vite.config.js                       # NEW — Vite + React plugin, manifest build
.gitignore                           # MODIFY — add node_modules, frontend build dir
requirements.txt                     # MODIFY — add inertia-django, django-vite
config/settings.py (or config/*)     # MODIFY — INSTALLED_APPS, MIDDLEWARE, INERTIA/VITE config
hw/templates/hw/base_inertia.html    # NEW — Inertia root document (loads Vite + design.css link)
nixpacks.toml                        # MODIFY — add Node build step

frontend/
  main.jsx                           # NEW — createInertiaApp entry; imports design.css
  layouts/AppLayout.jsx              # NEW — port of _base.html shell
  layouts/useTheme.js                # NEW — dark/light persistence hook
  layouts/useShellMenus.js           # NEW — search/notif/account/draft overlay logic
  components/icons.jsx               # NEW — all SVG icons, single module
  components/ui/Money.jsx            # NEW — <Money value={} />
  components/ui/StatusBadge.jsx      # NEW — Paid/Partial/Unpaid
  components/ui/Card.jsx             # NEW
  components/ui/Button.jsx           # NEW
  lib/csrf.js                        # NEW — read CSRF cookie
  lib/fetchJson.js                   # NEW — JSON endpoint wrapper
  pages/Invoice/List.jsx             # NEW — invoice_list
  pages/Invoice/Detail.jsx           # NEW — invoice_detail
  pages/Invoice/components/InvoiceHero.jsx        # NEW
  pages/Invoice/components/ReservationTable.jsx   # NEW
  pages/Invoice/components/PaymentTimeline.jsx    # NEW

hw/views/invoice_views.py            # MODIFY — invoice_list, invoice_detail return inertia.render
```

---

## Task 1: Add Python + Node dependencies

**Files:**
- Modify: `requirements.txt`
- Create: `package.json`
- Modify: `.gitignore`

- [ ] **Step 1: Add Python packages to `requirements.txt`**

Append under a new section:

```
# React / Inertia frontend
inertia-django==1.2.0
django-vite==3.0.6
```

- [ ] **Step 2: Install them into the venv**

Run: `python -m pip install inertia-django==1.2.0 django-vite==3.0.6`
Expected: `Successfully installed inertia-django ... django-vite ...`

- [ ] **Step 3: Create `package.json`**

```json
{
  "name": "hms-frontend",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  },
  "dependencies": {
    "@inertiajs/react": "^1.2.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.4",
    "vite": "^5.4.11"
  }
}
```

- [ ] **Step 4: Install Node deps**

Run: `npm install`
Expected: `node_modules/` created, `package-lock.json` written, no errors.

- [ ] **Step 5: Update `.gitignore`**

Add these lines:

```
# Frontend build
node_modules/
hw/static/dist/
```

- [ ] **Step 6: Commit**

```bash
git add requirements.txt package.json package-lock.json .gitignore
git commit -m "Build: tambah dependency Inertia + Vite (Python & Node)"
```

---

## Task 2: Configure Vite

**Files:**
- Create: `vite.config.js`

- [ ] **Step 1: Create `vite.config.js`**

Builds into `hw/static/dist` with a manifest so `django-vite` can resolve hashed filenames; dev server on port 5173.

```js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  root: resolve("./frontend"),
  base: "/static/dist/",
  build: {
    manifest: "manifest.json",
    outDir: resolve("./hw/static/dist"),
    emptyOutDir: true,
    rollupOptions: {
      input: resolve("./frontend/main.jsx"),
    },
  },
  server: {
    host: "localhost",
    port: 5173,
    origin: "http://localhost:5173",
  },
});
```

- [ ] **Step 2: Create a placeholder entry so build can run**

Create `frontend/main.jsx` with a temporary body (replaced in Task 4):

```jsx
console.log("HMS frontend entry");
```

- [ ] **Step 3: Verify build works**

Run: `npm run build`
Expected: `hw/static/dist/manifest.json` and `hw/static/dist/assets/*.js` are produced; exit code 0.

- [ ] **Step 4: Commit**

```bash
git add vite.config.js frontend/main.jsx
git commit -m "Build: konfigurasi Vite (manifest build ke hw/static/dist)"
```

---

## Task 3: Wire Django to Inertia + django-vite

**Files:**
- Modify: `config/settings.py`
- Create: `hw/templates/hw/base_inertia.html`

> Note: confirm the settings module path first (`config/settings.py` vs split settings). Apply edits to the active settings file.

- [ ] **Step 1: Register apps**

In `INSTALLED_APPS` add `"inertia"` and `"django_vite"` (after Django contrib apps, before/around `"hw"`).

- [ ] **Step 2: Add Inertia middleware**

In `MIDDLEWARE`, after `django.contrib.sessions...` and after `AuthenticationMiddleware`, add:

```python
"inertia.middleware.InertiaMiddleware",
```

- [ ] **Step 3: Add Inertia + Vite config block**

Append to `settings.py`:

```python
# ── Inertia ──
INERTIA_LAYOUT = "hw/base_inertia.html"

# ── django-vite ──
DJANGO_VITE = {
    "default": {
        "dev_mode": DEBUG,
        "manifest_path": BASE_DIR / "hw" / "static" / "dist" / "manifest.json",
        "static_url_prefix": "dist",
    }
}
```

Ensure `BASE_DIR` is imported/defined (it already is in a standard Django settings). Ensure `hw/static` is covered by `STATICFILES_DIRS` or app static dirs (it is, via the app).

- [ ] **Step 4: Create the Inertia root document `hw/templates/hw/base_inertia.html`**

This is the single HTML shell Inertia renders into. It loads `design.css` (so the global styles apply) and the Vite client + entry.

```html
{% load static django_vite %}
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}Workspace{% endblock %}</title>
  <script>(function(){var t=localStorage.getItem('theme')||'dark';document.documentElement.setAttribute('data-theme',t);})();</script>
  <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23FF6C37' stroke-width='2'><path stroke-linecap='round' stroke-linejoin='round' d='M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z'/></svg>">
  <link rel="stylesheet" href="{% static 'hw/css/design.css' %}">
  {% vite_hmr_client %}
  {% vite_asset 'main.jsx' %}
</head>
<body>
  {% block inertia %}{% endblock %}
</body>
</html>
```

- [ ] **Step 5: Verify Django still boots**

Run: `python manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 6: Commit**

```bash
git add config/settings.py hw/templates/hw/base_inertia.html
git commit -m "Feat: integrasi Inertia + django-vite di Django (root document + config)"
```

---

## Task 4: React entry + AppLayout shell (faithful port of _base.html)

**Files:**
- Modify: `frontend/main.jsx`
- Create: `frontend/layouts/AppLayout.jsx`
- Create: `frontend/layouts/useTheme.js`
- Create: `frontend/layouts/useShellMenus.js`

**Port rule:** AppLayout reproduces `hw/templates/hw/partials/_base.html` exactly. Copy each markup block verbatim into JSX with these mechanical substitutions:
- `class=` → `className=`; `for=` → `htmlFor=`; self-close void tags; `style="a:b;c:d"` → `style={{a:'b',c:'d'}}`.
- `{% url 'name' %}` for an Inertia page → `<Link href="/path">`; for a non-Inertia route (PDF/CSV/action) → plain `<a href="/path">`.
- `{% if user.is_authenticated %}` → `props.auth.user && (...)`; `{{ user.username }}` → `props.auth.user.username`.
- Inline `<script>` behavior (theme toggle, search overlay, notif/account dropdowns, draft modal) → the hooks below; do not paste `<script>` tags.
- `data-page` blob theming → set `data-page` on a wrapper `<div>` from the `page` prop (see Step 3).

- [ ] **Step 1: Replace `frontend/main.jsx`**

```jsx
import "../hw/static/hw/css/design.css"; // ensure design tokens load via bundle too
import { createInertiaApp } from "@inertiajs/react";
import { createRoot } from "react-dom/client";
import AppLayout from "./layouts/AppLayout.jsx";

const pages = import.meta.glob("./pages/**/*.jsx", { eager: true });

createInertiaApp({
  resolve: (name) => {
    const page = pages[`./pages/${name}.jsx`].default;
    page.layout = page.layout || ((p) => <AppLayout>{p}</AppLayout>);
    return page;
  },
  setup({ el, App, props }) {
    createRoot(el).render(<App {...props} />);
  },
});
```

> If importing `design.css` by relative path from `frontend/` is awkward, instead keep the `<link>` in `base_inertia.html` (Task 3 already has it) and drop this import line. The `<link>` is sufficient; the import is belt-and-suspenders. Choose the `<link>`-only approach if the relative import errors.

- [ ] **Step 2: Create `frontend/layouts/useTheme.js`**

```js
import { useEffect, useState } from "react";

export function useTheme() {
  const [theme, setTheme] = useState(
    () => localStorage.getItem("theme") || "dark"
  );
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);
  const toggle = () => setTheme((t) => (t === "light" ? "dark" : "light"));
  return { theme, toggle };
}
```

- [ ] **Step 3: Create `frontend/layouts/useShellMenus.js`**

Encapsulates open/close state for search overlay, notifications, and account menu, plus the global `/` and `Esc` key handling (ported from `_base.html` lines 571–588).

```js
import { useEffect, useState, useCallback } from "react";

export function useShellMenus() {
  const [search, setSearch] = useState(false);
  const [notif, setNotif] = useState(false);
  const [account, setAccount] = useState(false);

  const openSearch = useCallback(() => setSearch(true), []);
  const closeAll = useCallback(() => {
    setSearch(false); setNotif(false); setAccount(false);
  }, []);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") closeAll();
      const tag = document.activeElement?.tagName;
      if (e.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA") {
        e.preventDefault();
        setSearch(true);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [closeAll]);

  return { search, setSearch, notif, setNotif, account, setAccount, openSearch, closeAll };
}
```

- [ ] **Step 4: Create `frontend/layouts/AppLayout.jsx`**

Skeleton below; fill the marked regions by porting the corresponding `_base.html` blocks verbatim per the Port rule. The `page` prop drives blob theming; derive it from the current URL (Inertia exposes it via `usePage().url`).

```jsx
import { usePage, Link } from "@inertiajs/react";
import { useTheme } from "./useTheme.js";
import { useShellMenus } from "./useShellMenus.js";
import { Icon } from "../components/icons.jsx";

function pageKeyFromUrl(url) {
  if (url === "/" || url === "") return "home";
  const map = [["/hotels","hotels"],["/invoice","invoice"],["/services","services"],
    ["/calendar","calendar"],["/clients","clients"],["/remittance","remittance"],
    ["/cl","cl"],["/users","users"],["/account","users"]];
  for (const [pre, key] of map) if (url.startsWith(pre)) return key;
  return "home";
}

export default function AppLayout({ children }) {
  const { props, url } = usePage();
  const user = props.auth?.user;
  const { theme, toggle } = useTheme();
  const menus = useShellMenus();
  const page = pageKeyFromUrl(url);

  return (
    <div data-page={page}>
      {/* === PORT: <nav class="topbar"> ... </nav>  (_base.html 160–251) ===
          - search button onClick={menus.openSearch}
          - notif button onClick={() => menus.setNotif(v=>!v)} + badge from props.due_soon_count
          - theme button onClick={toggle}, swap moon/sun by {theme}
          - account dropdown open state = menus.account */}

      {/* === PORT: mobile #m-topbar (_base.html 256–282) === */}
      {/* === PORT: mobile <nav class="bottom-nav"> (_base.html 285–316), {% url %} -> <Link> === */}
      {/* === PORT: mobile #bnav-account-dd (_base.html 319–356) === */}
      {/* === PORT: #notif-dropdown (_base.html 362–383) fed by props.due_soon_notifs === */}

      {/* === PORT: ambient background (_base.html 387–392) verbatim === */}
      <div className="base-bg" aria-hidden="true">
        <div className="base-blob base-blob-1" />
        <div className="base-blob base-blob-2" />
        <div className="base-blob base-blob-3" />
        <div className="base-blob base-blob-4" />
      </div>

      {children}

      {/* === PORT: search overlay (_base.html 462–479) — input wired to global_search fetch (Task 5 lib/fetchJson) === */}
      {/* === PORT: draft modal (_base.html 398–420) — opened via window event or context === */}
    </div>
  );
}
```

> The blob CSS, per-page `--b*-c` variables, and keyframes live in the `<style>` block of `_base.html` (lines 72–155). Move that CSS block into a new `frontend/layouts/AppLayout.module.css` (or append to `design.css`) so the blob theming still applies. Recommended: append those rules to `design.css` to keep a single source of truth.

- [ ] **Step 5: Build to confirm it compiles**

Run: `npm run build`
Expected: build succeeds; no JSX syntax errors. (Pages don't exist yet — that's fine; AppLayout compiles standalone.)

- [ ] **Step 6: Commit**

```bash
git add frontend/main.jsx frontend/layouts hw/static/hw/css/design.css
git commit -m "Feat: AppLayout React (port shell _base.html) + hook theme & menu"
```

---

## Task 5: Shared UI primitives + lib helpers

**Files:**
- Create: `frontend/components/icons.jsx`
- Create: `frontend/components/ui/Money.jsx`
- Create: `frontend/components/ui/StatusBadge.jsx`
- Create: `frontend/components/ui/Card.jsx`
- Create: `frontend/components/ui/Button.jsx`
- Create: `frontend/lib/csrf.js`
- Create: `frontend/lib/fetchJson.js`

- [ ] **Step 1: `frontend/components/icons.jsx`**

One component, name → SVG. Seed with the icons used by the shell + invoice pages (search, bell, moon, sun, user, chevron, doc, print, download). Copy the exact `<path>` data from `_base.html`.

```jsx
const PATHS = {
  search: <><circle cx="11" cy="11" r="7"/><path strokeLinecap="round" d="M21 21l-4.35-4.35"/></>,
  bell: <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"/>,
  moon: <path strokeLinecap="round" strokeLinejoin="round" d="M21 12.79A9 9 0 1111.21 3a7 7 0 009.79 9.79z"/>,
  sun: <><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></>,
  download: <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v12m0 0l4-4m-4 4l-4-4M5 21h14"/>,
  print: <path strokeLinecap="round" strokeLinejoin="round" d="M6 9V3h12v6M6 18H4v-7h16v7h-2M8 14h8v7H8z"/>,
};

export function Icon({ name, size = 15, ...rest }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" {...rest}>
      {PATHS[name]}
    </svg>
  );
}
```

- [ ] **Step 2: `frontend/components/ui/Money.jsx`**

```jsx
const nf = new Intl.NumberFormat("en-US");
export default function Money({ value, currency = "SAR", className }) {
  return <span className={className}>{currency} {nf.format(Math.round(value || 0))}</span>;
}
```

- [ ] **Step 3: `frontend/components/ui/StatusBadge.jsx`**

Derives label+class from status; matches existing badge classes in `design.css` (`badge-green`/`badge-amber`/`badge-red` — confirm exact names in `design.css` and use those).

```jsx
const MAP = {
  paid:    { label: "Lunas",   cls: "badge badge-green" },
  partial: { label: "Sebagian",cls: "badge badge-amber" },
  unpaid:  { label: "Belum",   cls: "badge badge-red" },
};
export default function StatusBadge({ status }) {
  const m = MAP[status] || MAP.unpaid;
  return <span className={m.cls}>{m.label}</span>;
}
```

- [ ] **Step 4: `frontend/components/ui/Card.jsx` and `Button.jsx`**

```jsx
// Card.jsx
export default function Card({ className = "", children, ...rest }) {
  return <div className={`card ${className}`} {...rest}>{children}</div>;
}
```

```jsx
// Button.jsx
export default function Button({ variant = "primary", size, className = "", children, ...rest }) {
  const cls = ["btn", `btn-${variant}`, size && `btn-${size}`, className].filter(Boolean).join(" ");
  return <button className={cls} {...rest}>{children}</button>;
}
```

- [ ] **Step 5: `frontend/lib/csrf.js`**

```js
export function getCsrf() {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}
```

- [ ] **Step 6: `frontend/lib/fetchJson.js`**

```js
import { getCsrf } from "./csrf.js";
export async function fetchJson(url, { method = "GET", body, json } = {}) {
  const headers = { "X-CSRFToken": getCsrf() };
  let payload = body;
  if (json !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(json); }
  const res = await fetch(url, { method, headers, body: payload });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
```

- [ ] **Step 7: Build**

Run: `npm run build`
Expected: success.

- [ ] **Step 8: Commit**

```bash
git add frontend/components frontend/lib
git commit -m "Feat: primitives UI React (Icon, Money, StatusBadge, Card, Button) + lib csrf/fetch"
```

---

## Task 6: Migrate `invoice_list` to Inertia

**Files:**
- Modify: `hw/views/invoice_views.py` (the `invoice_list` view)
- Create: `frontend/pages/Invoice/List.jsx`

> Before editing: read the current `invoice_list` view and `hw/templates/hw/invoice/invoice_list.html` to capture the exact context keys (pagination, filters, search persistence) and the exact markup/classes.

- [ ] **Step 1: Make the view return Inertia props**

In `invoice_list`, keep all existing queryset/pagination/filter logic; replace the final `render(...)` with:

```python
from inertia import render as inertia_render
# ...
return inertia_render(request, "Invoice/List", props={
    "invoices": [
        {
            "id": inv.id,
            "number": inv.invoice_number,
            "customer": inv.customer_name,
            "company": inv.company,
            "total_sar": inv.total_sar,
            "remaining_sar": inv.remaining_sar,
            "status": ("paid" if inv.remaining_sar <= 0 else "partial" if inv.total_paid_sar > 0 else "unpaid"),
            "issued_date": inv.issued_date.isoformat() if inv.issued_date else None,
            "due_date": inv.due_date.isoformat() if inv.due_date else None,
            "url": inv.get_absolute_url(),
        }
        for inv in page_obj  # use the actual paginated variable name from the view
    ],
    "pagination": {
        "page": page_obj.number,
        "num_pages": page_obj.paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_prev": page_obj.has_previous(),
    },
    "filters": {"q": request.GET.get("q", ""), "status": request.GET.get("status", "")},
    "due_soon_count": context_due_soon_count,  # match what _base.html expected
})
```

Adjust variable names (`page_obj`, due-soon count) to the view's actual locals.

- [ ] **Step 2: Create `frontend/pages/Invoice/List.jsx`**

Port `invoice_list.html`'s markup verbatim (same wrapper `.page`, list/table classes), substituting props. Use `<Link>` for row navigation and pagination; `<StatusBadge>` and `<Money>` for cells.

```jsx
import { Link, router } from "@inertiajs/react";
import StatusBadge from "../../components/ui/StatusBadge.jsx";
import Money from "../../components/ui/Money.jsx";

export default function List({ invoices, pagination, filters }) {
  // PORT the .page header + filter bar + list markup from invoice_list.html.
  // Search input: onChange debounced -> router.get('/invoice', {q}, {preserveState:true})
  return (
    <div className="page">
      {/* header / filter bar ported here */}
      <div className="card">
        {invoices.map((inv) => (
          <Link key={inv.id} href={inv.url} className="list-row">
            <span className="list-num">{inv.number}</span>
            <span className="list-name">{inv.customer}</span>
            <Money value={inv.total_sar} className="list-amt" />
            <StatusBadge status={inv.status} />
          </Link>
        ))}
      </div>
      {/* pagination ported here using <Link href={`/invoice?page=${n}`}> */}
    </div>
  );
}
```

- [ ] **Step 3: Build**

Run: `npm run build`
Expected: success.

- [ ] **Step 4: Run dev servers and smoke test**

Run (two terminals): `npm run dev` and `python manage.py runserver`
Smoke: open `/invoice` →
- list renders with same look as before,
- pagination works (URL updates, list changes),
- typing in search filters (debounced),
- status badges show correct colors,
- clicking a row navigates to the (still-Django) detail without a full reload error.
Expected: visually identical to the previous Django page.

- [ ] **Step 5: Commit**

```bash
git add hw/views/invoice_views.py frontend/pages/Invoice/List.jsx
git commit -m "Feat: migrasi invoice_list ke Inertia + React (List.jsx)"
```

---

## Task 7: Migrate `invoice_detail` to Inertia

**Files:**
- Modify: `hw/views/invoice_views.py` (the `invoice_detail` view)
- Create: `frontend/pages/Invoice/Detail.jsx`
- Create: `frontend/pages/Invoice/components/InvoiceHero.jsx`
- Create: `frontend/pages/Invoice/components/ReservationTable.jsx`
- Create: `frontend/pages/Invoice/components/PaymentTimeline.jsx`

> Before editing: read `invoice_detail` view and `hw/templates/hw/invoice/invoice_detail.html` for exact context + markup (hero badges, reservation rows, payments, terms, attachments block, PDF/print/draft buttons).

- [ ] **Step 1: View returns Inertia props**

Replace the `render(...)` in `invoice_detail` with `inertia_render(request, "Invoice/Detail", props={...})` carrying:

```python
return inertia_render(request, "Invoice/Detail", props={
    "invoice": {
        "id": invoice.id, "number": invoice.invoice_number,
        "customer": invoice.customer_name, "company": invoice.company,
        "type": invoice.invoice_type,
        "issued_date": invoice.issued_date.isoformat() if invoice.issued_date else None,
        "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
        "pdf_url": reverse("invoice_pdf", args=[invoice.id]),
    },
    "reservations": [
        {"id": r.id, "number": r.reservation_number, "hotel": r.hotel,
         "check_in": r.check_in.isoformat() if r.check_in else None,
         "check_out": r.check_out.isoformat() if r.check_out else None,
         "total_sar": r.total_sar}
        for r in invoice.reservations.all()
    ],
    "payments": [
        {"id": p.id, "date": p.payment_date.isoformat() if p.payment_date else None,
         "method": p.method, "amount_sar": p.amount_sar, "ref": p.linked_number, "note": p.note}
        for p in invoice.payments.all()
    ],
    "totals": {"total": invoice.total_sar, "paid": invoice.total_paid_sar, "remaining": invoice.remaining_sar},
})
```

- [ ] **Step 2: `components/InvoiceHero.jsx`**

Port the hero block from `invoice_detail.html` (number, customer, total, status pill, issued/due). Use `<StatusBadge>` and `<Money>`; derive status from `totals`.

```jsx
import StatusBadge from "../../../components/ui/StatusBadge.jsx";
import Money from "../../../components/ui/Money.jsx";

export default function InvoiceHero({ invoice, totals }) {
  const status = totals.remaining <= 0 ? "paid" : totals.paid > 0 ? "partial" : "unpaid";
  // PORT the existing hero markup/classes here.
  return (
    <div className="dhero">
      <div className="dhero-badges"><StatusBadge status={status} /></div>
      <h1>{invoice.customer}</h1>
      <Money value={totals.total} />
      {/* issued / due ported */}
    </div>
  );
}
```

- [ ] **Step 3: `components/ReservationTable.jsx`**

```jsx
import Money from "../../../components/ui/Money.jsx";

function nights(ci, co) {
  if (!ci || !co) return 0;
  return Math.round((new Date(co) - new Date(ci)) / 86400000);
}

export default function ReservationTable({ reservations, total }) {
  // PORT the reservation table markup/classes (col-num etc.) here.
  return (
    <table className="t">
      <thead><tr><th>Ref</th><th>Hotel</th><th>Stay</th><th className="col-num">Nights</th><th className="col-num">Total</th></tr></thead>
      <tbody>
        {reservations.map((r) => (
          <tr key={r.id}>
            <td>{r.number}</td><td>{r.hotel}</td>
            <td>{r.check_in} → {r.check_out}</td>
            <td className="col-num">{nights(r.check_in, r.check_out)}</td>
            <td className="col-num"><Money value={r.total_sar} /></td>
          </tr>
        ))}
      </tbody>
      <tfoot><tr><td colSpan={4}>Total</td><td className="col-num"><Money value={total} /></td></tr></tfoot>
    </table>
  );
}
```

- [ ] **Step 4: `components/PaymentTimeline.jsx`**

```jsx
import Money from "../../../components/ui/Money.jsx";
export default function PaymentTimeline({ payments }) {
  if (!payments.length) return <p className="text-muted">Belum ada pembayaran</p>;
  // PORT the payments list markup here.
  return (
    <ul className="timeline">
      {payments.map((p) => (
        <li key={p.id}>
          <span>{p.date}</span><span>{p.method}</span>
          <Money value={p.amount_sar} />
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 5: `pages/Invoice/Detail.jsx`**

Compose the page; port the page-back header and terms block; PDF/print buttons link to `invoice.pdf_url`.

```jsx
import InvoiceHero from "./components/InvoiceHero.jsx";
import ReservationTable from "./components/ReservationTable.jsx";
import PaymentTimeline from "./components/PaymentTimeline.jsx";
import Button from "../../components/ui/Button.jsx";
import { Icon } from "../../components/icons.jsx";

export default function Detail({ invoice, reservations, payments, totals }) {
  return (
    <div className="page">
      {/* PORT page-header + back button (existing .page-back) */}
      <div className="page-actions">
        <a className="btn btn-ghost btn-sm" href={invoice.pdf_url} target="_blank" rel="noreferrer">
          <Icon name="download" size={13} /> PDF
        </a>
      </div>
      <InvoiceHero invoice={invoice} totals={totals} />
      <ReservationTable reservations={reservations} total={totals.total} />
      <PaymentTimeline payments={payments} />
      {/* PORT terms & conditions block verbatim */}
    </div>
  );
}
```

- [ ] **Step 6: Build**

Run: `npm run build`
Expected: success.

- [ ] **Step 7: Smoke test**

Run dev servers; open an invoice detail via a row click from `/invoice`.
Verify: hero/status/total, reservation table with nights + totals footer, payments, terms — all visually identical; PDF button opens the WeasyPrint PDF; back button returns to list via client-side nav.

- [ ] **Step 8: Commit**

```bash
git add hw/views/invoice_views.py frontend/pages/Invoice
git commit -m "Feat: migrasi invoice_detail ke Inertia + React (Detail + komponen hero/table/timeline)"
```

---

## Task 8: Production build pipeline (Railway / nixpacks)

**Files:**
- Modify: `nixpacks.toml`

> Goal: Railway installs Node deps and runs `npm run build` (producing the manifest) before `collectstatic`, so WhiteNoise serves hashed assets.

- [ ] **Step 1: Inspect current `nixpacks.toml`**

Run: `cat nixpacks.toml`
Note the existing phases (install/build/start).

- [ ] **Step 2: Add Node + frontend build**

Edit `nixpacks.toml` to add `nodejs` to nix packages and a build phase that runs the Vite build before static collection. Example shape (adapt to existing file):

```toml
[phases.setup]
nixPkgs = ["python3", "nodejs_20"]

[phases.install]
cmds = [
  "python -m venv --copies /opt/venv && . /opt/venv/bin/activate && pip install -r requirements.txt",
  "npm ci",
]

[phases.build]
cmds = [
  "npm run build",
  ". /opt/venv/bin/activate && python manage.py collectstatic --noinput",
]
```

- [ ] **Step 3: Set production `dev_mode` off**

Confirm `DJANGO_VITE["default"]["dev_mode"]` is `DEBUG` (Task 3) so production (`DEBUG=False`) uses the manifest, not the dev server.

- [ ] **Step 4: Local production-mode smoke**

Run:
```
npm run build
python manage.py collectstatic --noinput
```
Then with `DEBUG=False` (and `ALLOWED_HOSTS` set) run the server and load `/invoice`.
Expected: page loads with assets from `static/dist` (no call to `localhost:5173`).

- [ ] **Step 5: Commit**

```bash
git add nixpacks.toml
git commit -m "Build: pipeline produksi — Node build (Vite) sebelum collectstatic di nixpacks"
```

---

## Task 9: Final verification & PR

- [ ] **Step 1: Full build + check**

Run: `npm run build` then `python manage.py check`
Expected: both succeed.

- [ ] **Step 2: Regression smoke of un-migrated pages**

Open `/` (home), `/cl`, `/hotels`, `/clients`, `/remittance`, `/calendar`.
Expected: all still render via classic Django templates, unaffected. (They do not use the React shell yet — that is expected.)

- [ ] **Step 3: Migrated-page smoke checklist**

- `/invoice` list: render, paginate, search, status badges.
- invoice detail: hero, reservations + totals, payments, terms, PDF, back.
- theme toggle persists; search overlay (`/`); notifications + account dropdowns open/close; company switch.

- [ ] **Step 4: Push branch and open PR**

```bash
git push -u origin feat/react-inertia-migration
gh pr create --fill --title "Migrasi frontend HMS ke React (Inertia) — fondasi + slice Invoice"
```

---

## Self-Review notes (author)

- **Spec coverage:** arch (T1–T3), design preserved/`design.css` reused (T3,T4), AppLayout port (T4), primitives + best-practice rules (T5), data flow (T6,T7), invoice slice (T6,T7), deploy (T8), testing/rollback (T9 + legacy templates retained). All spec sections map to a task.
- **Stays-Django endpoints** (PDF/CSV/AI/search/map/actions): untouched; called via `<a href>` / `fetchJson`. Covered in T7 (PDF link) and T4 (search/draft).
- **Reversibility:** every migrated view can revert its `inertia_render` line to `render`; legacy templates kept until module complete (stated in plan intro + T6/T7).
- **Naming consistency:** `inertia_render` alias used in T6 & T7; `fetchJson`, `getCsrf`, `Icon`, `Money`, `StatusBadge` names consistent across tasks.
- **Open confirmations for the implementer:** (a) exact settings module path; (b) exact paginator local-variable name in `invoice_list`; (c) exact badge class names in `design.css` for StatusBadge. Each is flagged inline at its task.
