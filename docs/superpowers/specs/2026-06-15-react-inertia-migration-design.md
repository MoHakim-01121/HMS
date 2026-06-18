# HMS Frontend Migration to React (Inertia.js) — Design Spec

**Date:** 2026-06-15
**Status:** Approved (design), pending implementation plan
**Scope of this spec:** Milestone #1 — Foundation + Invoice vertical slice (list + detail, read).

---

## 1. Goal

Migrate the HMS browser UI from Django server-rendered templates to **React**, **preserving the current design exactly** (faithful port, not a redesign). Establish the architecture and patterns so remaining modules can be migrated incrementally in later specs.

Non-goals (this milestone): redesigning the look, migrating forms, migrating other modules, building a REST API.

## 2. Architecture decision

**Inertia.js** bridges Django and React — no REST API is built.

- Django keeps: URL routing, views, ORM, authentication (`django-axes`, sessions), permissions, business logic.
- A page view returns `inertia.render(request, 'Invoice/Detail', props)` instead of `render(request, template, context)`.
- React renders the page component with `props`; navigation between Inertia pages is client-side (no full reload).

**Stack additions**
- `inertia-django` (Python adapter)
- `@inertiajs/react`, `react`, `react-dom`
- `vite` + `django-vite` (dev HMR; production manifest consumed by Django/WhiteNoise)

**Deploy (VPS / deploy.sh)**: add a Node build step — `npm ci && npm run build` — before `collectstatic`. WhiteNoise continues to serve the built assets. The deploy script installs Node alongside Python.

## 3. What stays Django (NOT migrated)

These are not HTML pages and remain unchanged; React calls them via `fetch` or Inertia POST:

- All PDF endpoints (`*_pdf`, `*_list_pdf`, `*_period_pdf`) — **WeasyPrint, server-side, must stay.**
- CSV exports (`*_export_csv`).
- JSON/AJAX endpoints: `global_search`, `ai_chat`, `ai_draft_message`, `attachment_upload`, `attachment_delete`, `hotel_map_data`, `client_map_data`.
- Action endpoints: `*_delete`, `*_duplicate`, `remittance_mark_received`, `remittance_upload_proof`, `company_quick_set`.

During transition, **Inertia pages and classic Django templates coexist**. Un-migrated modules keep working untouched.

## 4. Preserving the current design

- **`design.css` is reused as-is**, imported once from the React entry. All existing classes and CSS variables (`--surface`, `--border`, `--text`, `--r-xl`, `--shadow-xl`, `--z-overlay`, etc.) remain valid. No visual change.
- `_base.html` becomes a React **`<AppLayout>`** component reproducing, identically:
  - Desktop topbar (brand, search button, notification bell + badge, theme toggle, account dropdown).
  - Mobile bottom tab bar (CL, Invoice, Home-center, Hotels, Calendar) + mobile top-right utility cluster.
  - Global search overlay (`/` and `⌘`), notification dropdown, account dropdowns.
  - AI draft-message modal; attachment upload/delete helpers.
  - Theme (dark default + light toggle) persisted in `localStorage`.
  - Per-page animated blob background — current `data-page` logic moves to an `AppLayout` prop derived from the active Inertia page.
- Each page component contains the **same markup** as the old template; only `{{ var }}` → `{props.x}` and `{% url %}` → Inertia `<Link>`.

## 5. Frontend structure & best practices (baked in)

```
frontend/
  main.jsx                 # Inertia createInertiaApp entry; imports design.css
  layouts/
    AppLayout.jsx          # the former _base.html shell
  components/
    ui/                    # reusable, data-dumb primitives
      Money.jsx            # <Money value={84000} /> -> "SAR 84,000"
      StatusBadge.jsx      # Paid / Partial / Unpaid -> consistent color+label
      Card.jsx, Button.jsx, Badge.jsx, Pill.jsx
    icons.jsx              # all SVG icons in one module (de-dupe inline SVG)
    search/Overlay.jsx
    notifications/Dropdown.jsx
    account/Menu.jsx
  pages/
    Invoice/
      List.jsx
      Detail.jsx
      components/          # page-local pieces
        InvoiceHero.jsx
        ReservationTable.jsx
        PaymentTimeline.jsx
  lib/
    csrf.js, fetchJson.js  # wrappers for the JSON endpoints
```

**Best-practice rules adopted as spec requirements:**
1. Components small and single-purpose; split when a file grows past ~200 lines.
2. Reusable primitives in `components/ui/` are data-dumb (props only).
3. `<Money>` and `<StatusBadge>` are the single source for currency formatting and status display — no ad-hoc duplication.
4. All SVG icons live in `icons.jsx`.
5. Lists use stable unique `key` (model `id`, never array index).
6. Derive, don't store: `remaining`, `status`, totals computed at render, not in `useState`.
7. `useEffect` only for outside-world sync (key listeners, fetch, title); always clean up timers/listeners.
8. Icon-only buttons require `aria-label`; `Esc` closes overlays and returns focus to trigger.
9. CSS Modules for any new component-specific styles; keep CSS variables as design tokens. `design.css` stays global for the faithful port.
10. No global state library yet — `useState` + a small `ThemeContext` / active-company context only.

## 6. Data flow

- View builds the same data dict it used as template context and passes it as Inertia props.
- Invoice slice props:
  - `List.jsx`: `{ invoices: [{id, number, customer, company, total_sar, remaining_sar, status, ...}], pagination, filters }`
  - `Detail.jsx`: `{ invoice: {...}, reservations: [...], payments: [...], totals: {total, paid, remaining}, company }`
- Status (`paid`/`partial`/`unpaid`) is derived in React from `remaining_sar`/`total_paid_sar`, matching the Django model properties.

## 7. Vertical slice: Invoice (list + detail)

Migrate exactly two views to Inertia:
- `invoice_list` → `pages/Invoice/List.jsx` (preserve existing pagination, search persistence, status filters).
- `invoice_detail` → `pages/Invoice/Detail.jsx` (hero, reservations table, payments, terms; PDF/print buttons still hit the Django `invoice_pdf` route).

All other invoice routes (`invoice_new`, `invoice_edit`, `invoice_delete`, `invoice_pdf`, `invoice_duplicate`, `invoice_export_csv`, `invoice_list_pdf`) remain Django for now. Links from the migrated pages point to those existing routes.

## 8. Testing & rollback

- **Build gate:** `npm run build` must succeed; `python manage.py check` passes.
- **Visual parity:** migrated Invoice list/detail compared against current screenshots; must look identical.
- **Smoke:** load list, paginate, search, open a detail, click PDF/print, switch company, toggle theme, open search overlay (`/`), open notifications/account dropdowns.
- **Rollback per page:** revert the view's `inertia.render(...)` line back to `render(template, ...)`; the old template files are retained until the module is fully migrated and verified.

## 9. Risks

- **Build pipeline on VPS** — adding the Node build step to the deploy is the main integration risk; validate the deploy early.
- **Auth + Inertia** — login page can stay a classic Django template initially; Inertia handles authenticated session requests normally.
- **Duplicated shell logic** — until `_base.html` is fully retired, both the React `AppLayout` and the Django base exist; only migrated pages use the React shell.

## 10. Out of scope / future specs (sequence)

1. CL (list + detail)
2. Hotel (list + detail + map)
3. Client (list + detail + map)
4. Remittance (list + detail + recap)
5. Calendar
6. Forms (invoice/CL/services/hotel/client/remittance create+edit) — `useForm`, server validation as Inertia errors
7. Users / Account / Penalty / Services pages
8. Retire `_base.html` and legacy per-page templates once all consumers are migrated
