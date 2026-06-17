# React Form Migration (Simple Forms) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the three simple HMS forms (Client, Penalty, User) plus their non-migrated redirect destinations (penalty_detail, user_list) from Django templates to React/Inertia, with idiomatic `useForm`, server-side validation returning Inertia `errors`, and a global flash-toast system.

**Architecture:** Each form becomes one React component (`X/Form.jsx`) handling both new & edit, submitting via `@inertiajs/react`'s `useForm`. Views switch GET to `inertia_render`; on POST validation failure they re-render the SAME Inertia component with an `errors` prop (Inertia populates `form.errors`); on success they `redirect` to an already-migrated page and flash a Django message rendered as a toast.

**Tech Stack:** Django + inertia-django, django-vite, React 18, `@inertiajs/react` v1.2, Vite.

## Global Constraints

- Inertia redirect targets MUST be Inertia-rendered pages, else Inertia errors with "All Inertia requests must receive a valid Inertia response." (This is why Penalty bundles `penalty_detail` and User bundles `user_list`.)
- No `Co-Authored-By: Claude` trailer in any commit (user preference).
- Reuse existing form CSS classes verbatim for visual parity: `.form-page`, `.form-panel`, `.form-section`, `.form-section-label`, `.ff`, `.fg-2`, `.ff-check`, `.check-sub`, `.form-actions`, `.hint`.
- Edit submissions use `form.post(editUrl)` (not PUT) — existing Django routes accept POST for edit.
- `is_active`/`is_paid`/`is_staff` checkboxes: Django views read `data.get('field') == 'on'`. Send the literal string `"on"` (or omit) from `useForm` so existing `_save_*` helpers keep working unchanged. (See Task 3 note for the exact approach.)
- Verification per task: `npm run build` succeeds AND `python manage.py check` passes. Backend validation logic is covered by Django `TestCase` run via `python manage.py test hw`. React components are verified by build + manual check (no JS test runner in this project — out of scope to add one).
- Commands assume repo root `C:\Users\konoz\OneDrive\Desktop\HMS`, PowerShell shell. The venv interpreter is `.venv\Scripts\python.exe`.

---

## File Structure

**New (frontend):**
- `frontend/components/form/FormField.jsx` — label + input/children + inline error
- `frontend/components/form/FormPanel.jsx` — `.form-panel` wrapper
- `frontend/components/form/FormSection.jsx` — `.form-section` + section label
- `frontend/components/form/FormActions.jsx` — cancel + submit buttons
- `frontend/components/shell/Toast.jsx` — flash toast
- `frontend/pages/Client/Form.jsx`
- `frontend/pages/Penalty/Form.jsx`, `frontend/pages/Penalty/Detail.jsx`
- `frontend/pages/User/Form.jsx`, `frontend/pages/User/List.jsx`

**Modified (frontend):**
- `frontend/layouts/AppLayout.jsx` — mount `<Toast>`

**Modified (backend):**
- `hw/inertia_share.py` — share `flash`
- `hw/templates/hw/base_inertia.html` — load `forms.css`
- `hw/views/client_views.py` — `client_new`, `client_edit`
- `hw/views/penalty_views.py` — `penalty_new`, `penalty_edit`, `penalty_detail`
- `hw/views/user_views.py` — `user_list`, `user_new`, `user_edit`

**New (tests):**
- `hw/tests/__init__.py`
- `hw/tests/test_form_views.py`

**Deleted after verification:**
- `hw/templates/hw/client/client_form.html`
- `hw/templates/hw/penalty/penalty_form.html`, `hw/templates/hw/penalty/penalty_detail.html`
- `hw/templates/hw/users/user_form.html`, `hw/templates/hw/users/user_list.html`

---

## SLICE A — Foundation + Client Form

### Task 1: Flash toast infrastructure

**Files:**
- Modify: `hw/inertia_share.py`
- Create: `frontend/components/shell/Toast.jsx`
- Modify: `frontend/layouts/AppLayout.jsx`
- Test: `hw/tests/__init__.py`, `hw/tests/test_form_views.py`

**Interfaces:**
- Produces: Inertia shared prop `flash: {"success": str|None, "error": str|None}` available on every page via `usePage().props.flash`. `<Toast />` component (no props) mounted in `AppLayout`.

- [ ] **Step 1: Write the failing test**

Create `hw/tests/__init__.py` (empty), then `hw/tests/test_form_views.py`:

```python
from django.contrib.auth.models import User
from django.test import TestCase


class FlashShareTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="pw12345")
        self.client.force_login(self.user)
        session = self.client.session
        session["active_company"] = "konoz"
        session.save()

    def test_success_message_shared_as_flash(self):
        # client_delete already redirects to the (Inertia) client_list with a
        # messages.success — this exercises flash sharing WITHOUT depending on
        # any view migrated in a later task.
        from hw.models import Client
        c = Client.objects.create(company="konoz", name="PT Uji Flash")
        resp = self.client.post(
            f"/clients/{c.pk}/delete/",
            HTTP_X_INERTIA="true",
            HTTP_X_INERTIA_VERSION="1",
            follow=True,
        )
        # After following the redirect, the Inertia page JSON carries flash.success.
        page = resp.json()
        self.assertIn("flash", page["props"])
        self.assertIsNotNone(page["props"]["flash"]["success"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test hw.tests.test_form_views.FlashShareTests -v2`
Expected: FAIL — `flash` not in `page["props"]` (middleware does not yet share it). After Step 3 this passes within Task 1, since it relies only on the already-migrated `client_delete`/`client_list` flow.
Note: confirm the delete URL path (`/clients/<pk>/delete/`) in `hw/urls.py`; adjust if different.

- [ ] **Step 3: Add flash sharing in middleware**

In `hw/inertia_share.py`, add the import and share `flash` from Django messages. Replace the `share(...)` call body to include flash:

```python
from django.contrib.messages import get_messages
from inertia import share

from .context_processors import due_soon


def _flash(request):
    success = error = None
    for m in get_messages(request):  # iterating consumes the message store
        if m.level_tag == "error":
            error = m.message
        elif m.level_tag in ("success", "info"):
            success = m.message
    return {"success": success, "error": error}
```

Then inside `__call__`, within the `if user ... is_authenticated:` block, add `flash=_flash(request),` to the `share(...)` kwargs (alongside `auth=...`, `active_company=...`, `**due_soon(request)`).

- [ ] **Step 4: Create the Toast component**

Create `frontend/components/shell/Toast.jsx`:

```jsx
import { useEffect, useState } from "react";
import { usePage } from "@inertiajs/react";

export default function Toast() {
  const { props } = usePage();
  const flash = props.flash || {};
  const [items, setItems] = useState([]);

  useEffect(() => {
    const next = [];
    if (flash.success) next.push({ id: Date.now() + "s", kind: "success", msg: flash.success });
    if (flash.error) next.push({ id: Date.now() + "e", kind: "error", msg: flash.error });
    if (!next.length) return;
    setItems((cur) => [...cur, ...next]);
    const t = setTimeout(() => {
      setItems((cur) => cur.filter((i) => !next.some((n) => n.id === i.id)));
    }, 3200);
    return () => clearTimeout(t);
  }, [flash.success, flash.error]);

  if (!items.length) return null;
  return (
    <div style={{ position: "fixed", top: 64, right: 16, zIndex: 9999, display: "flex", flexDirection: "column", gap: 8 }}>
      {items.map((i) => (
        <div key={i.id} className={"badge " + (i.kind === "error" ? "badge-red" : "badge-green")}
          style={{ padding: "10px 14px", fontSize: 13, boxShadow: "var(--shadow, 0 4px 16px rgba(0,0,0,.25))", borderRadius: "var(--r-sm, 8px)", maxWidth: 320 }}>
          {i.msg}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Mount Toast in AppLayout**

In `frontend/layouts/AppLayout.jsx`, add the import near the other shell imports:

```jsx
import Toast from "../components/shell/Toast.jsx";
```

Then render it just after `{children}` (around line 232), before the `SearchOverlay` line:

```jsx
      {children}

      <Toast />
      {user && <SearchOverlay open={search} onClose={() => setSearch(false)} />}
```

- [ ] **Step 6: Build and check**

Run: `npm run build`
Expected: build succeeds (modules transformed, bundle emitted).
Run: `.venv\Scripts\python.exe manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 7: Commit**

```bash
git add hw/inertia_share.py frontend/components/shell/Toast.jsx frontend/layouts/AppLayout.jsx hw/tests/__init__.py hw/tests/test_form_views.py
git commit -m "Feat: share Django flash messages to Inertia + Toast component"
```

---

### Task 2: Reusable form components + form CSS

**Files:**
- Create: `frontend/components/form/FormField.jsx`
- Create: `frontend/components/form/FormPanel.jsx`
- Create: `frontend/components/form/FormSection.jsx`
- Create: `frontend/components/form/FormActions.jsx`
- Modify: `hw/templates/hw/base_inertia.html`

**Interfaces:**
- Produces:
  - `FormField({ label, name, error, required, hint, type="text", value, onChange, placeholder, autoFocus, span, inputMode, step, children })` — renders `.ff`; if `children` given, renders them instead of a default `<input>`; shows `error` text below when present.
  - `FormPanel({ children })` — `.form-panel`.
  - `FormSection({ label, sub, children })` — `.form-section` with `.form-section-label` (optional `sub`).
  - `FormActions({ cancelHref, submitLabel, processing })` — `.form-actions` with Batal link + primary submit (disabled while `processing`).

- [ ] **Step 1: Load form CSS in the Inertia base template**

In `hw/templates/hw/base_inertia.html`, add after the `shell.css` link (line 11):

```html
  <link rel="stylesheet" href="{% static 'hw/css/forms.css' %}">
```

(This makes the existing form styles available to React pages with zero visual drift — same approach as `design.css`/`shell.css`.)

- [ ] **Step 2: Create FormField**

Create `frontend/components/form/FormField.jsx`:

```jsx
export default function FormField({
  label, name, error, required, hint, type = "text",
  value, onChange, placeholder, autoFocus, span, inputMode, step, children,
}) {
  return (
    <div className="ff" style={span ? { gridColumn: `span ${span}` } : undefined}>
      {label && <label htmlFor={name}>{label}{required ? " *" : ""}</label>}
      {children ?? (
        <input
          id={name} name={name} type={type} value={value ?? ""}
          onChange={(e) => onChange?.(e.target.value)}
          placeholder={placeholder} autoFocus={autoFocus}
          inputMode={inputMode} step={step}
          aria-invalid={error ? "true" : undefined}
        />
      )}
      {hint && !error && <div className="hint" style={{ marginTop: 6 }}>{hint}</div>}
      {error && <div className="hint" style={{ marginTop: 6, color: "var(--red)" }}>{error}</div>}
    </div>
  );
}
```

- [ ] **Step 3: Create FormPanel and FormSection**

Create `frontend/components/form/FormPanel.jsx`:

```jsx
export default function FormPanel({ children }) {
  return <div className="form-panel">{children}</div>;
}
```

Create `frontend/components/form/FormSection.jsx`:

```jsx
export default function FormSection({ label, sub, children }) {
  return (
    <div className="form-section">
      {label && (
        <div className="form-section-label">
          {label}
          {sub && (
            <span style={{ fontFamily: "inherit", fontWeight: 400, fontSize: 11, textTransform: "none", letterSpacing: 0, color: "var(--text-3)", marginLeft: 4 }}>{sub}</span>
          )}
        </div>
      )}
      {children}
    </div>
  );
}
```

- [ ] **Step 4: Create FormActions**

Create `frontend/components/form/FormActions.jsx`:

```jsx
export default function FormActions({ cancelHref, submitLabel, processing }) {
  return (
    <div className="form-actions">
      <a href={cancelHref} className="btn btn-ghost">Batal</a>
      <button type="submit" className="btn btn-primary" disabled={processing}>
        <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
        {submitLabel}
      </button>
    </div>
  );
}
```

- [ ] **Step 5: Build and check**

Run: `npm run build`
Expected: build succeeds (new components compile; they are unused so far, which is fine).
Run: `.venv\Scripts\python.exe manage.py check`
Expected: no issues.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/form/ hw/templates/hw/base_inertia.html
git commit -m "Feat: reusable Inertia form components + load forms.css"
```

---

### Task 3: Client form (new + edit)

**Files:**
- Create: `frontend/pages/Client/Form.jsx`
- Modify: `hw/views/client_views.py:57-84` (`client_new`, `client_edit`)
- Test: `hw/tests/test_form_views.py`

**Interfaces:**
- Consumes: `FormField`, `FormPanel`, `FormSection`, `FormActions` (Task 2); `flash` share + `<Toast>` (Task 1).
- Produces: Inertia component `Client/Form` with props `{ client: object|null, edit: bool, errors?: {field: msg} }`. View `client_new` accepts GET (render form) + POST (validate → re-render with errors, or save → redirect detail). `client_edit` same with an existing client.

- [ ] **Step 1: Write the failing test**

Append to `hw/tests/test_form_views.py`:

```python
class ClientFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester2", password="pw12345")
        self.client.force_login(self.user)
        s = self.client.session; s["active_company"] = "konoz"; s.save()

    def _inertia(self, url, data, follow=False):
        return self.client.post(url, data, follow=follow,
                                HTTP_X_INERTIA="true", HTTP_X_INERTIA_VERSION="1")

    def test_get_renders_inertia_form(self):
        resp = self.client.get("/clients/new/", HTTP_X_INERTIA="true", HTTP_X_INERTIA_VERSION="1")
        self.assertEqual(resp.json()["component"], "Client/Form")

    def test_missing_name_returns_errors(self):
        resp = self._inertia("/clients/new/", {"name": ""})
        page = resp.json()
        self.assertEqual(page["component"], "Client/Form")
        self.assertIn("name", page["props"]["errors"])

    def test_valid_create_redirects_to_detail(self):
        from hw.models import Client
        resp = self._inertia("/clients/new/", {"name": "PT Sahabat"})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Client.objects.filter(name="PT Sahabat").exists())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test hw.tests.test_form_views.ClientFormTests -v2`
Expected: FAIL — `component` is absent (GET still returns Django template HTML, not Inertia JSON).

- [ ] **Step 3: Update the views**

In `hw/views/client_views.py`, replace `client_new` and `client_edit` (lines 57–84). Add a small validation helper above them:

```python
def _validate_client(data):
    errors = {}
    if not data.get("name", "").strip():
        errors["name"] = "Nama agen wajib diisi."
    return errors


def _client_echo(data):
    """Echo submitted values back to the form on validation error."""
    return {
        "name": data.get("name", ""), "city": data.get("city", ""),
        "province": data.get("province", ""), "pic": data.get("pic", ""),
        "wa": data.get("wa", ""), "email": data.get("email", ""),
        "note": data.get("note", ""), "lat": data.get("lat", ""),
        "lng": data.get("lng", ""), "is_active": data.get("is_active") == "on",
    }


@login_required
def client_new(request):
    company = _company(request)
    if request.method == 'POST':
        errors = _validate_client(request.POST)
        if errors:
            return inertia_render(request, "Client/Form", props={
                "client": _client_echo(request.POST), "edit": False, "errors": errors,
            })
        c = Client(company=company or 'konoz')
        _save_client(c, request.POST)
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'Client', c.name, c.company)
        messages.success(request, f'Client "{c.name}" berhasil ditambahkan.')
        return redirect('client_detail', pk=c.pk)
    return inertia_render(request, "Client/Form", props={"client": None, "edit": False})


@login_required
def client_edit(request, pk):
    company = _company(request)
    filters = {'pk': pk}
    if company:
        filters['company'] = company
    c = get_object_or_404(Client, **filters)
    if request.method == 'POST':
        errors = _validate_client(request.POST)
        if errors:
            echo = _client_echo(request.POST); echo["id"] = c.pk
            return inertia_render(request, "Client/Form", props={
                "client": echo, "edit": True, "errors": errors,
            })
        _before = {'Nama': c.name, 'Kota': c.city, 'Provinsi': c.province, 'PIC': c.pic, 'WhatsApp': c.wa, 'Email': c.email}
        _save_client(c, request.POST)
        _after  = {'Nama': c.name, 'Kota': c.city, 'Provinsi': c.province, 'PIC': c.pic, 'WhatsApp': c.wa, 'Email': c.email}
        changes = [{'label': k, 'before': _before[k], 'after': _after[k]} for k in _before if _before[k] != _after[k]]
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'Client', c.name, c.company, changes)
        messages.success(request, f'Client "{c.name}" berhasil diupdate.')
        return redirect('client_detail', pk=c.pk)
    return inertia_render(request, "Client/Form", props={
        "client": {
            "id": c.pk, "name": c.name, "city": c.city, "province": c.province,
            "pic": c.pic, "wa": c.wa, "email": c.email, "note": c.note,
            "lat": c.lat, "lng": c.lng, "is_active": c.is_active,
        },
        "edit": True,
    })
```

- [ ] **Step 4: Create the Client form component**

Create `frontend/pages/Client/Form.jsx`:

```jsx
import { useForm } from "@inertiajs/react";
import FormPanel from "../../components/form/FormPanel.jsx";
import FormSection from "../../components/form/FormSection.jsx";
import FormField from "../../components/form/FormField.jsx";
import FormActions from "../../components/form/FormActions.jsx";

export default function Form({ client, edit, errors: serverErrors }) {
  const c = client || {};
  const form = useForm({
    name: c.name || "", city: c.city || "", province: c.province || "",
    pic: c.pic || "", wa: c.wa || "", email: c.email || "",
    lat: c.lat ?? "", lng: c.lng ?? "", note: c.note || "",
    is_active: edit ? !!c.is_active : true,
  });
  const errors = { ...serverErrors, ...form.errors };
  const set = (k) => (v) => form.setData(k, v);

  const submit = (e) => {
    e.preventDefault();
    // Django reads checkbox as the string "on".
    form.transform((d) => ({ ...d, is_active: d.is_active ? "on" : "" }));
    const url = edit ? `/clients/${c.id}/edit/` : `/clients/new/`;
    form.post(url);
  };

  return (
    <div className="form-page">
      <div className="page-header" style={{ marginBottom: 16 }}>
        <div>
          <div className="page-title">{edit ? "Edit Client" : "Client Baru"}</div>
          <div className="page-sub">Data agen travel Umrah</div>
        </div>
      </div>

      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label="Identitas">
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField span={2} label="Nama Agen" name="name" required
                value={form.data.name} onChange={set("name")} error={errors.name}
                placeholder="PT. Anugerah Wisata" autoFocus />
              <FormField label="Kota" name="city" value={form.data.city} onChange={set("city")} placeholder="Surabaya" />
              <FormField label="Provinsi" name="province" value={form.data.province} onChange={set("province")} placeholder="Jawa Timur" />
            </div>
            <label className="ff-check">
              <input type="checkbox" checked={form.data.is_active} onChange={(e) => form.setData("is_active", e.target.checked)} />
              <span>Aktif <span className="check-sub">Client dapat dipilih saat membuat dokumen baru</span></span>
            </label>
          </FormSection>

          <FormSection label="Kontak">
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField label="PIC" name="pic" value={form.data.pic} onChange={set("pic")} placeholder="Nama penanggung jawab" />
              <FormField label="WhatsApp" name="wa" value={form.data.wa} onChange={set("wa")} placeholder="628123456789" inputMode="tel" />
            </div>
            <FormField label="Email" name="email" type="email" value={form.data.email} onChange={set("email")} placeholder="email@agen.com" error={errors.email} />
          </FormSection>

          <FormSection label="Lokasi" sub="untuk peta">
            <div className="fg-2">
              <FormField label="Latitude" name="lat" type="number" step="any" value={form.data.lat} onChange={set("lat")} placeholder="-7.2575" />
              <FormField label="Longitude" name="lng" type="number" step="any" value={form.data.lng} onChange={set("lng")} placeholder="112.7521" />
            </div>
            <div className="hint" style={{ marginTop: 8 }}>
              Cari koordinat kota di <a href="https://www.latlong.net/" target="_blank" rel="noreferrer" style={{ color: "var(--accent)", textDecoration: "none" }}>latlong.net ↗</a>
            </div>
          </FormSection>

          <FormSection label="Catatan Internal">
            <FormField name="note">
              <textarea name="note" rows={3} value={form.data.note} onChange={(e) => form.setData("note", e.target.value)} placeholder="Catatan tentang client ini…" />
            </FormField>
          </FormSection>

          <FormActions
            cancelHref={edit ? `/clients/${c.id}/` : "/clients/"}
            submitLabel={edit ? "Simpan Perubahan" : "Tambah Client"}
            processing={form.processing} />
        </FormPanel>
      </form>
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test hw.tests.test_form_views.ClientFormTests hw.tests.test_form_views.FlashShareTests -v2`
Expected: PASS (all 4 tests).

- [ ] **Step 6: Build and check**

Run: `npm run build`
Expected: build succeeds.
Run: `.venv\Scripts\python.exe manage.py check`
Expected: no issues.

- [ ] **Step 7: Manual verification**

Start dev (`npm run dev` + Django runserver). Visit `/clients/new/`: submit empty name → inline "Nama agen wajib diisi." under the Name field, no navigation. Fill name → save → lands on client detail with a green success toast. Edit an existing client → fields prefilled → save → toast.

- [ ] **Step 8: Commit**

```bash
git add frontend/pages/Client/Form.jsx hw/views/client_views.py hw/tests/test_form_views.py
git commit -m "Feat: migrate Client form (new/edit) to React/Inertia with validation"
```

---

### Task 4: Remove old client template

**Files:**
- Delete: `hw/templates/hw/client/client_form.html`

- [ ] **Step 1: Confirm no remaining references**

Run: `grep -rn "client_form.html" hw/`
Expected: no matches (the view no longer renders it after Task 3).

- [ ] **Step 2: Delete the template**

```bash
git rm hw/templates/hw/client/client_form.html
```

- [ ] **Step 3: Check**

Run: `.venv\Scripts\python.exe manage.py check`
Expected: no issues.

- [ ] **Step 4: Commit**

```bash
git commit -m "Chore: remove legacy client_form.html (migrated to React)"
```

---

## SLICE B — Penalty (form + detail)

### Task 5: Penalty detail page

**Files:**
- Create: `frontend/pages/Penalty/Detail.jsx`
- Modify: `hw/views/penalty_views.py:47-50` (`penalty_detail`)
- Test: `hw/tests/test_form_views.py`

**Interfaces:**
- Consumes: existing `.page`, `.card`, `.field`, `.badge` CSS.
- Produces: Inertia component `Penalty/Detail` with prop `penalty` (serialized dict incl. `cl` summary). `penalty_detail` renders it.

- [ ] **Step 1: Write the failing test**

Append to `hw/tests/test_form_views.py`:

```python
class PenaltyViewTests(TestCase):
    def setUp(self):
        from hw.models import ConfirmationLetter
        self.user = User.objects.create_user("tester3", password="pw12345")
        self.client.force_login(self.user)
        s = self.client.session; s["active_company"] = "konoz"; s.save()
        self.cl = ConfirmationLetter.objects.create(company="konoz", guest_name="Budi")

    def _inertia_get(self, url):
        return self.client.get(url, HTTP_X_INERTIA="true", HTTP_X_INERTIA_VERSION="1")

    def test_detail_renders_inertia(self):
        from hw.models import CancellationPenalty
        p = CancellationPenalty.objects.create(cl=self.cl, penalty_number="PN-1")
        resp = self._inertia_get(f"/penalty/{p.pk}/")
        self.assertEqual(resp.json()["component"], "Penalty/Detail")
```

Note: verify the actual `ConfirmationLetter` required fields with `.venv\Scripts\python.exe manage.py shell` if `create()` raises; add the minimum required kwargs.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test hw.tests.test_form_views.PenaltyViewTests -v2`
Expected: FAIL — component absent (still a Django template).

- [ ] **Step 3: Add Inertia import + update penalty_detail**

In `hw/views/penalty_views.py`, add at the top with the other imports:

```python
from inertia import render as inertia_render
```

Replace `penalty_detail` (lines 47–50) with:

```python
def _penalty_props(penalty):
    cl = penalty.cl
    return {
        "id": penalty.pk,
        "penalty_number": penalty.penalty_number,
        "cancellation_date": penalty.cancellation_date.isoformat() if penalty.cancellation_date else None,
        "reason": penalty.reason,
        "penalty_amount": float(penalty.penalty_amount or 0),
        "penalty_currency": penalty.penalty_currency,
        "exchange_rate": float(penalty.exchange_rate or 1),
        "is_paid": penalty.is_paid,
        "payment_date": penalty.payment_date.isoformat() if penalty.payment_date else None,
        "payment_method": penalty.payment_method,
        "payment_note": penalty.payment_note,
        "note": penalty.note,
        "cl": {"id": cl.pk, "confirmation_number": cl.confirmation_number, "guest_name": cl.guest_name},
    }


@login_required
def penalty_detail(request, pk):
    penalty = get_object_or_404(CancellationPenalty.objects.select_related('cl'), pk=pk)
    return inertia_render(request, "Penalty/Detail", props={"penalty": _penalty_props(penalty)})
```

- [ ] **Step 4: Create Penalty/Detail.jsx**

Create `frontend/pages/Penalty/Detail.jsx`. Mirror the structure of `frontend/pages/Client/Detail.jsx` (page-header with Edit + PDF buttons, a `.card` with `.field` rows for each penalty attribute, a delete button posting to `/penalty/<id>/delete/`):

```jsx
import { router } from "@inertiajs/react";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

function Field({ label, children }) {
  return <div className="field"><div className="field-label">{label}</div><div className="field-value">{children}</div></div>;
}

export default function Detail({ penalty: p }) {
  const del = () => { if (confirm(`Hapus dokumen penalti ${p.penalty_number}?`)) router.post(`/penalty/${p.id}/delete/`); };
  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">{p.penalty_number}</div>
          <div className="page-sub">Penalti pembatalan — {p.cl.confirmation_number}</div>
        </div>
        <div className="page-actions">
          <a href={`/penalty/${p.id}/edit/`} className="btn btn-secondary btn-sm">Edit</a>
          <a href={`/penalty/${p.id}/pdf/`} className="btn btn-ghost btn-sm" target="_blank" rel="noreferrer">PDF</a>
        </div>
      </div>

      <div className="detail-grid">
        <div>
          <div className="card">
            <div className="card-header">
              <span className="card-title">Detail Penalti</span>
              <span className={"badge " + (p.is_paid ? "badge-green" : "badge-yellow")}>{p.is_paid ? "Lunas" : "Belum"}</span>
            </div>
            <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <Field label="Tamu / CL">{p.cl.guest_name} — {p.cl.confirmation_number}</Field>
              <Field label="Tanggal Pembatalan">{p.cancellation_date || "—"}</Field>
              <Field label="Jumlah Penalti">{fmt(p.penalty_amount)} {p.penalty_currency}</Field>
              {p.exchange_rate !== 1 && <Field label="Kurs">{p.exchange_rate}</Field>}
              {p.reason && <Field label="Alasan">{p.reason}</Field>}
              {p.is_paid && <Field label="Tanggal Bayar">{p.payment_date || "—"}</Field>}
              {p.payment_method && <Field label="Metode Bayar">{p.payment_method}</Field>}
              {p.payment_note && <Field label="Catatan Bayar">{p.payment_note}</Field>}
              {p.note && (
                <div className="field">
                  <div className="field-label">Catatan</div>
                  <div style={{ fontSize: 13, color: "var(--text-2)", whiteSpace: "pre-wrap" }}>{p.note}</div>
                </div>
              )}
            </div>
            <div style={{ padding: "12px 20px", borderTop: "1px solid var(--border)" }}>
              <button onClick={del} className="btn btn-danger btn-sm btn-full">Hapus Penalti</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test hw.tests.test_form_views.PenaltyViewTests -v2`
Expected: PASS.

- [ ] **Step 6: Build and check**

Run: `npm run build` then `.venv\Scripts\python.exe manage.py check`
Expected: build succeeds; no issues.

- [ ] **Step 7: Commit**

```bash
git add frontend/pages/Penalty/Detail.jsx hw/views/penalty_views.py hw/tests/test_form_views.py
git commit -m "Feat: migrate penalty detail to React/Inertia"
```

---

### Task 6: Penalty form (new + edit)

**Files:**
- Create: `frontend/pages/Penalty/Form.jsx`
- Modify: `hw/views/penalty_views.py` (`penalty_new`, `penalty_edit`)
- Test: `hw/tests/test_form_views.py`

**Interfaces:**
- Consumes: form components (Task 2); `_penalty_props` (Task 5); `inertia_render` (Task 5).
- Produces: Inertia component `Penalty/Form` with props `{ penalty: object|null, cl: {id, confirmation_number, guest_name}, suggested_number, today, edit, errors? }`. `penalty_new(cl_pk)` + `penalty_edit(pk)` handle GET/POST.

- [ ] **Step 1: Write the failing test**

Append to `hw/tests/test_form_views.py` inside `PenaltyViewTests`:

```python
    def test_new_get_renders_form(self):
        resp = self._inertia_get(f"/cl/{self.cl.pk}/penalty/new/")
        self.assertEqual(resp.json()["component"], "Penalty/Form")

    def test_new_post_creates_and_redirects(self):
        from hw.models import CancellationPenalty
        resp = self.client.post(
            f"/cl/{self.cl.pk}/penalty/new/",
            {"penalty_number": "PN-X", "penalty_amount": "500", "penalty_currency": "SAR", "exchange_rate": "1"},
            HTTP_X_INERTIA="true", HTTP_X_INERTIA_VERSION="1",
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(CancellationPenalty.objects.filter(penalty_number="PN-X").exists())
```

Note: confirm the URL names/paths for `penalty_new`/`penalty_edit` in `hw/urls.py`; adjust the test paths if they differ from `/cl/<pk>/penalty/new/` and `/penalty/<pk>/edit/`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test hw.tests.test_form_views.PenaltyViewTests.test_new_get_renders_form -v2`
Expected: FAIL — component absent.

- [ ] **Step 3: Update penalty_new and penalty_edit**

In `hw/views/penalty_views.py`, replace the `render(...'penalty_form.html'...)` calls in `penalty_new` and `penalty_edit` with `inertia_render`, and convert the GET branches. For `penalty_new`, the GET return becomes:

```python
    return inertia_render(request, "Penalty/Form", props={
        "penalty": None,
        "cl": {"id": cl.pk, "confirmation_number": cl.confirmation_number, "guest_name": cl.guest_name},
        "suggested_number": suggested_number,
        "today": date.today().isoformat(),
        "edit": False,
    })
```

Keep the existing POST create logic (it already redirects to `penalty_detail` + flashes a message). For `penalty_edit`, the GET return becomes:

```python
    return inertia_render(request, "Penalty/Form", props={
        "penalty": _penalty_props(penalty),
        "cl": {"id": cl.pk, "confirmation_number": cl.confirmation_number, "guest_name": cl.guest_name},
        "suggested_number": penalty.penalty_number,
        "today": date.today().isoformat(),
        "edit": True,
    })
```

Keep the existing POST update logic (redirects to `penalty_detail` + flash). No new validation is required (all fields optional except number, which has a suggested default), so no `errors` branch is needed here.

- [ ] **Step 4: Create Penalty/Form.jsx**

Create `frontend/pages/Penalty/Form.jsx` using the form components. Fields: penalty_number (default `suggested_number`), cancellation_date (date, default `today`), reason (textarea), penalty_amount (number) + penalty_currency (select SAR/IDR/USD), exchange_rate (number), is_paid (checkbox), and when paid: payment_date, payment_method, payment_note; note (textarea):

```jsx
import { useForm } from "@inertiajs/react";
import FormPanel from "../../components/form/FormPanel.jsx";
import FormSection from "../../components/form/FormSection.jsx";
import FormField from "../../components/form/FormField.jsx";
import FormActions from "../../components/form/FormActions.jsx";

const CURRENCIES = ["SAR", "IDR", "USD"];

export default function Form({ penalty, cl, suggested_number, today, edit, errors: serverErrors }) {
  const p = penalty || {};
  const form = useForm({
    penalty_number: p.penalty_number || suggested_number || "",
    cancellation_date: p.cancellation_date || today || "",
    reason: p.reason || "",
    penalty_amount: p.penalty_amount ?? "",
    penalty_currency: p.penalty_currency || "SAR",
    exchange_rate: p.exchange_rate ?? 1,
    is_paid: edit ? !!p.is_paid : false,
    payment_date: p.payment_date || "",
    payment_method: p.payment_method || "",
    payment_note: p.payment_note || "",
    note: p.note || "",
  });
  const errors = { ...serverErrors, ...form.errors };
  const set = (k) => (v) => form.setData(k, v);

  const submit = (e) => {
    e.preventDefault();
    form.transform((d) => ({ ...d, is_paid: d.is_paid ? "on" : "" }));
    const url = edit ? `/penalty/${p.id}/edit/` : `/cl/${cl.id}/penalty/new/`;
    form.post(url);
  };

  return (
    <div className="form-page">
      <div className="page-header" style={{ marginBottom: 16 }}>
        <div>
          <div className="page-title">{edit ? "Edit Penalti" : "Dokumen Penalti Baru"}</div>
          <div className="page-sub">{cl.guest_name} — {cl.confirmation_number}</div>
        </div>
      </div>

      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label="Informasi Penalti">
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField label="Nomor Penalti" name="penalty_number" value={form.data.penalty_number} onChange={set("penalty_number")} error={errors.penalty_number} />
              <FormField label="Tanggal Pembatalan" name="cancellation_date" type="date" value={form.data.cancellation_date} onChange={set("cancellation_date")} />
            </div>
            <FormField name="reason" label="Alasan">
              <textarea name="reason" rows={2} value={form.data.reason} onChange={(e) => form.setData("reason", e.target.value)} placeholder="Alasan pembatalan…" />
            </FormField>
          </FormSection>

          <FormSection label="Nilai">
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField label="Jumlah" name="penalty_amount" type="number" step="any" value={form.data.penalty_amount} onChange={set("penalty_amount")} error={errors.penalty_amount} />
              <FormField label="Mata Uang" name="penalty_currency">
                <select name="penalty_currency" value={form.data.penalty_currency} onChange={(e) => form.setData("penalty_currency", e.target.value)}>
                  {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </FormField>
            </div>
            <FormField label="Kurs ke SAR" name="exchange_rate" type="number" step="any" value={form.data.exchange_rate} onChange={set("exchange_rate")} />
          </FormSection>

          <FormSection label="Pembayaran">
            <label className="ff-check">
              <input type="checkbox" checked={form.data.is_paid} onChange={(e) => form.setData("is_paid", e.target.checked)} />
              <span>Sudah dibayar</span>
            </label>
            {form.data.is_paid && (
              <div className="fg-2" style={{ marginTop: 12 }}>
                <FormField label="Tanggal Bayar" name="payment_date" type="date" value={form.data.payment_date} onChange={set("payment_date")} />
                <FormField label="Metode" name="payment_method" value={form.data.payment_method} onChange={set("payment_method")} placeholder="Transfer / Tunai" />
                <FormField span={2} name="payment_note" label="Catatan Bayar">
                  <textarea name="payment_note" rows={2} value={form.data.payment_note} onChange={(e) => form.setData("payment_note", e.target.value)} />
                </FormField>
              </div>
            )}
          </FormSection>

          <FormSection label="Catatan Internal">
            <FormField name="note">
              <textarea name="note" rows={3} value={form.data.note} onChange={(e) => form.setData("note", e.target.value)} />
            </FormField>
          </FormSection>

          <FormActions
            cancelHref={edit ? `/penalty/${p.id}/` : `/cl/${cl.id}/`}
            submitLabel={edit ? "Simpan Perubahan" : "Buat Penalti"}
            processing={form.processing} />
        </FormPanel>
      </form>
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test hw.tests.test_form_views.PenaltyViewTests -v2`
Expected: PASS.

- [ ] **Step 6: Build and check**

Run: `npm run build` then `.venv\Scripts\python.exe manage.py check`
Expected: build succeeds; no issues.

- [ ] **Step 7: Manual verification**

From a CL detail page, click "Buat Penalti" → form prefilled with suggested number + today → save → lands on penalty detail with success toast. Edit → fields prefilled → toggle "Sudah dibayar" reveals payment fields → save → toast.

- [ ] **Step 8: Commit**

```bash
git add frontend/pages/Penalty/Form.jsx hw/views/penalty_views.py hw/tests/test_form_views.py
git commit -m "Feat: migrate penalty form (new/edit) to React/Inertia"
```

---

### Task 7: Remove old penalty templates

**Files:**
- Delete: `hw/templates/hw/penalty/penalty_form.html`, `hw/templates/hw/penalty/penalty_detail.html`

- [ ] **Step 1: Confirm no remaining references**

Run: `grep -rn "penalty_form.html\|penalty_detail.html" hw/`
Expected: no matches.

- [ ] **Step 2: Delete the templates**

```bash
git rm hw/templates/hw/penalty/penalty_form.html hw/templates/hw/penalty/penalty_detail.html
```

- [ ] **Step 3: Check + commit**

Run: `.venv\Scripts\python.exe manage.py check` (expect no issues), then:

```bash
git commit -m "Chore: remove legacy penalty templates (migrated to React)"
```

---

## SLICE C — User (list + form)

### Task 8: User list page

**Files:**
- Create: `frontend/pages/User/List.jsx`
- Modify: `hw/views/user_views.py:58-61` (`user_list`) and `user_edit` action handling
- Test: `hw/tests/test_form_views.py`

**Interfaces:**
- Consumes: existing table/badge CSS; `flash`/`Toast` (Task 1).
- Produces: Inertia component `User/List` with prop `users` (list of `{id, username, is_staff, is_superuser, is_active, is_self}`). Per-row action forms post to `user_edit` with `action` ∈ {`reset_password`, `toggle_active`, `toggle_staff`} and `user_delete`.

- [ ] **Step 1: Write the failing test**

Append to `hw/tests/test_form_views.py`:

```python
class UserAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "a@a.com", "pw12345")
        self.client.force_login(self.admin)

    def _inertia_get(self, url):
        return self.client.get(url, HTTP_X_INERTIA="true", HTTP_X_INERTIA_VERSION="1")

    def test_user_list_renders_inertia(self):
        resp = self._inertia_get("/users/")
        page = resp.json()
        self.assertEqual(page["component"], "User/List")
        self.assertTrue(any(u["username"] == "admin" for u in page["props"]["users"]))
```

Note: confirm the `/users/` path in `hw/urls.py`; adjust if different.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test hw.tests.test_form_views.UserAdminTests -v2`
Expected: FAIL — component absent.

- [ ] **Step 3: Add Inertia import + update user_list**

In `hw/views/user_views.py`, add `from inertia import render as inertia_render` at the top. Replace `user_list` (lines 58–61):

```python
@superuser_required
def user_list(request):
    users = User.objects.all().order_by('username')
    data = [{
        "id": u.pk, "username": u.username, "is_staff": u.is_staff,
        "is_superuser": u.is_superuser, "is_active": u.is_active,
        "is_self": u.pk == request.user.pk,
    } for u in users]
    return inertia_render(request, "User/List", props={"users": data})
```

Leave `user_edit`'s POST action handling as-is (it already redirects to `user_list` + flashes). The redirect now lands on the Inertia `User/List`, so the toast shows.

- [ ] **Step 4: Create User/List.jsx**

Create `frontend/pages/User/List.jsx`. Render a table of users; each row has small POST forms for toggle-active, toggle-staff, reset-password (prompt for password via a tiny inline form or a `window.prompt`), and delete. Use a hidden CSRF input via the existing `getCsrf()` util:

```jsx
import { router } from "@inertiajs/react";
import { getCsrf } from "../../utils/csrf.js";

function action(userId, fields) {
  router.post(`/users/${userId}/edit/`, fields);
}

export default function List({ users }) {
  const resetPw = (u) => {
    const pw = window.prompt(`Password baru untuk ${u.username}:`);
    if (!pw) return;
    action(u.id, { action: "reset_password", password: pw, password_confirm: pw });
  };
  const del = (u) => { if (confirm(`Hapus user ${u.username}?`)) router.post(`/users/${u.id}/delete/`); };

  return (
    <div className="page">
      <div className="page-header">
        <div><div className="page-title">Users</div><div className="page-sub">{users.length} akun terdaftar</div></div>
        <div className="page-actions">
          <a href="/users/new/" className="btn btn-primary">
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
            User baru
          </a>
        </div>
      </div>

      <div className="card">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Username</th><th>Role</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td className="col-bold">{u.username}{u.is_self && <span className="badge badge-gray" style={{ marginLeft: 6 }}>Anda</span>}</td>
                  <td>{u.is_superuser ? <span className="badge badge-blue">Admin</span> : u.is_staff ? <span className="badge badge-green">Staff</span> : <span className="badge badge-gray">User</span>}</td>
                  <td>{u.is_active ? <span className="badge badge-green">Aktif</span> : <span className="badge badge-gray">Nonaktif</span>}</td>
                  <td className="col-m-actions" style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                    <button className="btn btn-ghost btn-sm" onClick={() => resetPw(u)}>Reset PW</button>
                    {!u.is_superuser && <button className="btn btn-ghost btn-sm" onClick={() => action(u.id, { action: "toggle_staff" })}>{u.is_staff ? "Cabut Staff" : "Jadikan Staff"}</button>}
                    {!u.is_self && !u.is_superuser && <button className="btn btn-ghost btn-sm" onClick={() => action(u.id, { action: "toggle_active" })}>{u.is_active ? "Nonaktifkan" : "Aktifkan"}</button>}
                    {!u.is_self && !u.is_superuser && <button className="btn btn-danger btn-sm" onClick={() => del(u)}>Hapus</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
```

(`getCsrf` import retained for parity with other shell forms; Inertia's axios already sends the CSRF header, so `router.post` works without an explicit token. Remove the import if your linter flags it as unused.)

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test hw.tests.test_form_views.UserAdminTests -v2`
Expected: PASS.

- [ ] **Step 6: Build and check**

Run: `npm run build` then `.venv\Scripts\python.exe manage.py check`
Expected: build succeeds; no issues.

- [ ] **Step 7: Commit**

```bash
git add frontend/pages/User/List.jsx hw/views/user_views.py hw/tests/test_form_views.py
git commit -m "Feat: migrate user list + row actions to React/Inertia"
```

---

### Task 9: User create form

**Files:**
- Create: `frontend/pages/User/Form.jsx`
- Modify: `hw/views/user_views.py:64-86` (`user_new`)
- Test: `hw/tests/test_form_views.py`

**Interfaces:**
- Consumes: form components (Task 2); `inertia_render` (Task 8).
- Produces: Inertia component `User/Form` with props `{ form_data?: {username}, errors? }`. `user_new` GET renders it; POST validates (username required+unique, password required, confirm match) → errors or create + redirect `user_list`.

- [ ] **Step 1: Write the failing test**

Append to `hw/tests/test_form_views.py` inside `UserAdminTests`:

```python
    def _inertia_post(self, url, data):
        return self.client.post(url, data, HTTP_X_INERTIA="true", HTTP_X_INERTIA_VERSION="1")

    def test_new_get_renders_form(self):
        self.assertEqual(self._inertia_get("/users/new/").json()["component"], "User/Form")

    def test_password_mismatch_returns_error(self):
        resp = self._inertia_post("/users/new/", {"username": "bob", "password": "a", "password_confirm": "b"})
        page = resp.json()
        self.assertEqual(page["component"], "User/Form")
        self.assertIn("password_confirm", page["props"]["errors"])

    def test_duplicate_username_returns_error(self):
        resp = self._inertia_post("/users/new/", {"username": "admin", "password": "x", "password_confirm": "x"})
        self.assertIn("username", resp.json()["props"]["errors"])

    def test_valid_create_redirects(self):
        resp = self._inertia_post("/users/new/", {"username": "carol", "password": "pw", "password_confirm": "pw"})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(username="carol").exists())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test hw.tests.test_form_views.UserAdminTests.test_new_get_renders_form -v2`
Expected: FAIL — component absent.

- [ ] **Step 3: Update user_new**

Replace `user_new` (lines 64–86) in `hw/views/user_views.py`:

```python
@superuser_required
def user_new(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        confirm  = request.POST.get('password_confirm', '')
        is_staff = request.POST.get('is_staff') == 'on'

        errors = {}
        if not username:
            errors['username'] = "Username wajib diisi."
        elif User.objects.filter(username=username).exists():
            errors['username'] = f"Username '{username}' sudah digunakan."
        if not password:
            errors['password'] = "Password wajib diisi."
        elif password != confirm:
            errors['password_confirm'] = "Password tidak cocok."

        if errors:
            return inertia_render(request, "User/Form", props={
                "form_data": {"username": username, "is_staff": is_staff}, "errors": errors,
            })

        user = User.objects.create_user(username=username, password=password, is_staff=is_staff)
        messages.success(request, f"User '{user.username}' berhasil dibuat.")
        return redirect('user_list')

    return inertia_render(request, "User/Form", props={"form_data": None})
```

- [ ] **Step 4: Create User/Form.jsx**

Create `frontend/pages/User/Form.jsx`:

```jsx
import { useForm } from "@inertiajs/react";
import FormPanel from "../../components/form/FormPanel.jsx";
import FormSection from "../../components/form/FormSection.jsx";
import FormField from "../../components/form/FormField.jsx";
import FormActions from "../../components/form/FormActions.jsx";

export default function Form({ form_data, errors: serverErrors }) {
  const fd = form_data || {};
  const form = useForm({
    username: fd.username || "", password: "", password_confirm: "",
    is_staff: !!fd.is_staff,
  });
  const errors = { ...serverErrors, ...form.errors };
  const set = (k) => (v) => form.setData(k, v);

  const submit = (e) => {
    e.preventDefault();
    form.transform((d) => ({ ...d, is_staff: d.is_staff ? "on" : "" }));
    form.post("/users/new/");
  };

  return (
    <div className="form-page">
      <div className="page-header" style={{ marginBottom: 16 }}>
        <div><div className="page-title">User Baru</div><div className="page-sub">Buat akun baru</div></div>
      </div>
      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label="Akun">
            <FormField label="Username" name="username" required value={form.data.username} onChange={set("username")} error={errors.username} autoFocus />
            <div className="fg-2" style={{ marginTop: 12 }}>
              <FormField label="Password" name="password" type="password" required value={form.data.password} onChange={set("password")} error={errors.password} />
              <FormField label="Konfirmasi Password" name="password_confirm" type="password" required value={form.data.password_confirm} onChange={set("password_confirm")} error={errors.password_confirm} />
            </div>
            <label className="ff-check" style={{ marginTop: 12 }}>
              <input type="checkbox" checked={form.data.is_staff} onChange={(e) => form.setData("is_staff", e.target.checked)} />
              <span>Staff <span className="check-sub">Akses ke menu administrasi terbatas</span></span>
            </label>
          </FormSection>
          <FormActions cancelHref="/users/" submitLabel="Buat User" processing={form.processing} />
        </FormPanel>
      </form>
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test hw.tests.test_form_views.UserAdminTests -v2`
Expected: PASS (all User tests).

- [ ] **Step 6: Build and check**

Run: `npm run build` then `.venv\Scripts\python.exe manage.py check`
Expected: build succeeds; no issues.

- [ ] **Step 7: Manual verification**

Visit `/users/new/`: mismatched passwords → "Password tidak cocok." under confirm field; duplicate username → error under username; valid → redirect to user list with success toast.

- [ ] **Step 8: Commit**

```bash
git add frontend/pages/User/Form.jsx hw/views/user_views.py hw/tests/test_form_views.py
git commit -m "Feat: migrate user create form to React/Inertia with validation"
```

---

### Task 10: Remove old user templates

**Files:**
- Delete: `hw/templates/hw/users/user_form.html`, `hw/templates/hw/users/user_list.html`

- [ ] **Step 1: Confirm no remaining references**

Run: `grep -rn "users/user_form.html\|users/user_list.html\|user_form.html\|user_list.html" hw/`
Expected: no matches.

- [ ] **Step 2: Delete + check + commit**

```bash
git rm hw/templates/hw/users/user_form.html hw/templates/hw/users/user_list.html
```

Run: `.venv\Scripts\python.exe manage.py check` (expect no issues), then:

```bash
git commit -m "Chore: remove legacy user templates (migrated to React)"
```

---

## Self-Review Notes

- **Spec coverage:** Foundation (Task 1–2) covers shared form components, forms.css, flash/toast. Slice A (Task 3–4) Client. Slice B (Task 5–7) Penalty form+detail. Slice C (Task 8–10) User list+form. Validation flow, redirect-destination constraint, and cleanup all mapped. `account/profile`, maps, complex forms, and `confirm_delete.html` are explicitly deferred (per spec).
- **user_edit:** No separate "edit form" page — `user_edit` is action-based (reset/toggle), driven from `User/List.jsx` row buttons; its existing POST handling is reused unchanged. This matches the legacy behavior (the old `user_form.html` in edit mode only exposed those actions).
- **Checkbox convention:** All checkboxes use `form.transform` to emit the literal `"on"` so existing `data.get(...) == 'on'` server logic is untouched.
- **Verification reality:** No JS test runner exists; React verified via build + manual. Backend validation covered by Django `TestCase`. This is a deliberate adaptation to the project's existing workflow (smoke + `manage.py check`), not a placeholder.
- **Open items to confirm during implementation (noted inline):** exact URL paths/names in `hw/urls.py` for penalty/user routes; `ConfirmationLetter.create()` required fields for the penalty test fixture.
