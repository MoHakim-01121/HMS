# CL Form React Migration + Form Transport Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the Confirmation Letter (CL) new/edit form to React/Inertia with dynamic room rows, and fix the Inertia→Django form transport so React forms actually post readable data in the browser (retrofitting the simple forms).

**Architecture:** A shared `postForm` helper submits with `forceFormData: true` (multipart, so Django `request.POST`/`request.FILES` populate) and serializes collection fields (rooms) to a JSON string the backend parses with `json.loads`. CL views switch GET to `inertia_render("Cl/Form")` and return field-level Inertia `errors` on validation failure; `Cl/Form.jsx` + `RoomRows.jsx` render the form with add/remove rooms and a live total preview.

**Tech Stack:** Django + inertia-django, `@inertiajs/react` v1.3, React 18, Vite.

## Global Constraints

- All React form submits MUST send multipart (`forceFormData: true`), because Inertia v1.3 otherwise sends JSON and Django `request.POST` stays empty. Verified in `@inertiajs/core`: `if ((hasFiles(r) || forceFormData) && !(r instanceof FormData) && (r = objectToFormData(r)))`.
- Dynamic collections are sent as ONE JSON string field (e.g. `rooms`), parsed with `json.loads`. Do NOT rely on `request.POST.getlist` with `forceFormData` (it serializes arrays as `rooms[0][...]`).
- Checkboxes are sent as the literal string `"on"` (existing `data.get(...) == 'on'` server logic is unchanged).
- Inertia redirect targets must be Inertia pages (CL detail/list already are).
- No `Co-Authored-By: Claude` trailer in any commit.
- Do NOT commit per-task in this session — the user commits at the end. Each task still ends with build + check + tests as its gate; the "Commit" step is deferred/skipped until the user asks.
- Reuse existing form components (`frontend/components/form/`) and CSS classes verbatim.
- Commands: repo root `C:\Users\konoz\OneDrive\Desktop\HMS`, PowerShell. Python: `.venv\Scripts\python.exe`. Build: `npm run build`. Test: `.venv\Scripts\python.exe manage.py test hw.tests.test_form_views -v1`.

---

## File Structure

**New (frontend):**
- `frontend/utils/inertiaForm.js` — `postForm(form, url, { json })` helper.
- `frontend/pages/Cl/Form.jsx` — CL new/edit form.
- `frontend/pages/Cl/RoomRows.jsx` — dynamic room rows sub-component.

**Modified (frontend):**
- `frontend/pages/Client/Form.jsx`, `frontend/pages/Penalty/Form.jsx`, `frontend/pages/User/Form.jsx` — add `forceFormData: true` to submit.

**Modified (backend):**
- `hw/views/cl_views.py` — `cl_new`, `cl_edit`, `_save_cl_rooms`.

**Modified (tests):**
- `hw/tests/test_form_views.py` — add `ClFormTests`.

**Deleted after verification:**
- `hw/templates/hw/cl/cl_form.html`.

---

## Task 1: Transport helper + retrofit simple forms

**Files:**
- Create: `frontend/utils/inertiaForm.js`
- Modify: `frontend/pages/Client/Form.jsx` (submit), `frontend/pages/Penalty/Form.jsx` (submit), `frontend/pages/User/Form.jsx` (submit)

**Interfaces:**
- Produces: `postForm(form, url, { json = [] } = {})` — sets a transform that JSON-stringifies each key in `json`, then calls `form.post(url, { forceFormData: true })`. Returns the `form.post` result.

- [ ] **Step 1: Create the helper**

Create `frontend/utils/inertiaForm.js`:

```js
// Submit an Inertia useForm as multipart so Django request.POST/FILES populate
// (Inertia sends JSON by default, which Django does not parse). Collection
// fields named in `json` are stringified into a single JSON field each.
export function postForm(form, url, { json = [] } = {}) {
  form.transform((data) => {
    const out = { ...data };
    for (const key of json) out[key] = JSON.stringify(data[key] ?? []);
    return out;
  });
  return form.post(url, { forceFormData: true });
}
```

- [ ] **Step 2: Retrofit Client/Form.jsx submit**

In `frontend/pages/Client/Form.jsx`, the submit handler currently ends with `form.post(url);`. Change ONLY that call to pass the option (keep the existing `form.transform` checkbox line above it):

```jsx
    form.post(url, { forceFormData: true });
```

- [ ] **Step 3: Retrofit Penalty/Form.jsx submit**

In `frontend/pages/Penalty/Form.jsx`, change `form.post(url);` to:

```jsx
    form.post(url, { forceFormData: true });
```

- [ ] **Step 4: Retrofit User/Form.jsx submit**

In `frontend/pages/User/Form.jsx`, change `form.post("/users/new/");` to:

```jsx
    form.post("/users/new/", { forceFormData: true });
```

- [ ] **Step 5: Build and verify existing tests still pass**

Run: `npm run build`
Expected: build succeeds.
Run: `.venv\Scripts\python.exe manage.py test hw.tests.test_form_views -v1`
Expected: all existing tests still PASS (the Django test client posts form-encoded, unaffected by the client-side change). This confirms no regression; the browser fix is verified manually.

- [ ] **Step 6: Commit** (deferred — skip until user asks)

```bash
git add frontend/utils/inertiaForm.js frontend/pages/Client/Form.jsx frontend/pages/Penalty/Form.jsx frontend/pages/User/Form.jsx
git commit -m "Fix: submit React forms as multipart (forceFormData) so Django reads POST"
```

---

## Task 2: CL view migration + room JSON parsing + tests

**Files:**
- Modify: `hw/views/cl_views.py` (`cl_new`, `cl_edit`, `_save_cl_rooms`)
- Test: `hw/tests/test_form_views.py` (add `ClFormTests`)

**Interfaces:**
- Consumes: `inertia_render` (already imported in `cl_views.py`), existing `_form_context_data()`, `_parse_date`, `ConfirmationLetter`, `Room`, `Client`, `log_activity`, `ActivityLog`.
- Produces: Inertia component `Cl/Form` with props `{ suggested_number, default_company, hotels, clients, cl, edit, errors? }`. `_save_cl_rooms(cl, request)` parses `request.POST.get("rooms")` as a JSON array of `{room_type, meals, quantity, price}`.

- [ ] **Step 1: Write the failing tests**

Append to `hw/tests/test_form_views.py`:

```python
class ClFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester4", password="pw12345")
        self.client.force_login(self.user)
        s = self.client.session; s["active_company"] = "konoz"; s.save()

    def _post(self, url, data):
        return self.client.post(url, data, HTTP_X_INERTIA="true")

    def test_get_renders_inertia_form(self):
        resp = self.client.get("/cl/new/", HTTP_X_INERTIA="true")
        self.assertEqual(resp.json()["component"], "Cl/Form")

    def test_checkout_before_checkin_returns_error(self):
        page = self._post("/cl/new/", {
            "confirmation_number": "CLX-1", "company": "konoz",
            "check_in": "2026-06-10", "check_out": "2026-06-05", "rooms": "[]",
        }).json()
        self.assertEqual(page["component"], "Cl/Form")
        self.assertIn("check_out", page["props"]["errors"])

    def test_duplicate_number_returns_error(self):
        from hw.models import ConfirmationLetter
        ConfirmationLetter.objects.create(company="konoz", confirmation_number="CLX-DUP")
        page = self._post("/cl/new/", {"confirmation_number": "CLX-DUP", "company": "konoz", "rooms": "[]"}).json()
        self.assertIn("confirmation_number", page["props"]["errors"])

    def test_valid_create_with_rooms(self):
        from hw.models import ConfirmationLetter, Room
        resp = self._post("/cl/new/", {
            "confirmation_number": "CLX-OK", "company": "konoz",
            "guest_name": "Budi", "hotel_name": "Hilton",
            "reservation_status": "DEFINITE",
            "rooms": '[{"room_type":"Double","meals":"BB","quantity":2,"price":300}]',
        })
        self.assertEqual(resp.status_code, 302)
        cl = ConfirmationLetter.objects.get(confirmation_number="CLX-OK")
        rooms = Room.objects.filter(cl=cl)
        self.assertEqual(rooms.count(), 1)
        self.assertEqual(rooms.first().quantity, 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe manage.py test hw.tests.test_form_views.ClFormTests -v2`
Expected: FAIL — `test_get_renders_inertia_form` errors because GET still returns a Django template (no `component` key).

- [ ] **Step 3: Rewrite `_save_cl_rooms` to parse JSON**

In `hw/views/cl_views.py`, replace the existing `_save_cl_rooms` function:

```python
def _save_cl_rooms(cl, request):
    import json
    try:
        rooms = json.loads(request.POST.get("rooms", "[]") or "[]")
    except (ValueError, TypeError):
        rooms = []
    for r in rooms:
        rt = (r.get("room_type") or "").strip()
        if not rt:
            continue
        try:
            qty = max(1, int(r.get("quantity") or 1))
        except (ValueError, TypeError):
            qty = 1
        try:
            price = max(0, float(r.get("price") or 0))
        except (ValueError, TypeError):
            price = 0
        Room.objects.create(cl=cl, room_type=rt, meals=(r.get("meals") or ""), quantity=qty, price=price)
```

- [ ] **Step 4: Add the validation + echo helpers**

In `hw/views/cl_views.py`, add above `cl_new` (after `_form_context_data`):

```python
def _validate_cl(data, exclude_pk=None):
    errors = {}
    check_in = _parse_date(data.get("check_in"))
    check_out = _parse_date(data.get("check_out"))
    if check_in and check_out and check_out < check_in:
        errors["check_out"] = "Check-out tidak boleh sebelum check-in."
    number = data.get("confirmation_number", "")
    qs = ConfirmationLetter.objects.filter(confirmation_number=number)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    if number and qs.exists():
        errors["confirmation_number"] = f"Nomor CL '{number}' sudah digunakan."
    return errors


def _cl_echo(data):
    import json
    try:
        rooms = json.loads(data.get("rooms", "[]") or "[]")
    except (ValueError, TypeError):
        rooms = []
    return {
        "company": data.get("company", "konoz"),
        "client_id": data.get("client_id", ""),
        "hotel_name": data.get("hotel_name", ""),
        "guest_name": data.get("guest_name", ""),
        "guest_phone": data.get("guest_phone", ""),
        "check_in": data.get("check_in", ""),
        "check_out": data.get("check_out", ""),
        "confirmation_number": data.get("confirmation_number", ""),
        "reservation_status": data.get("reservation_status", "DEFINITE"),
        "note": data.get("note", ""),
        "rooms": rooms,
    }
```

- [ ] **Step 5: Rewrite `cl_new`**

Replace `cl_new` in `hw/views/cl_views.py` with:

```python
def cl_new(request):
    suggested_number = ConfirmationLetter.generate_number()
    default_company = request.session.get("active_company", "konoz")
    if request.method == "POST":
        errors = _validate_cl(request.POST)
        if errors:
            return inertia_render(request, "Cl/Form", props={
                "cl": _cl_echo(request.POST), "edit": False, "errors": errors,
                "suggested_number": request.POST.get("confirmation_number", suggested_number),
                "default_company": default_company, **_form_context_data(),
            })
        client_id = request.POST.get("client_id") or None
        guest_name = request.POST.get("guest_name", "").strip()
        if not guest_name and client_id:
            guest_name = Client.objects.filter(pk=client_id).values_list("name", flat=True).first() or ""
        cl = ConfirmationLetter.objects.create(
            company=request.POST.get("company", "konoz"),
            client_id=client_id,
            hotel_name=request.POST.get("hotel_name", ""),
            guest_name=guest_name,
            guest_phone=request.POST.get("guest_phone", ""),
            check_in=_parse_date(request.POST.get("check_in")),
            check_out=_parse_date(request.POST.get("check_out")),
            confirmation_number=request.POST.get("confirmation_number", ""),
            reservation_status=request.POST.get("reservation_status", "DEFINITE"),
            note=request.POST.get("note", ""),
        )
        _save_cl_rooms(cl, request)
        log_activity(request.user, ActivityLog.ACTION_CREATE, 'CL', cl.confirmation_number, cl.company)
        messages.success(request, f"Confirmation Letter {cl.confirmation_number} berhasil dibuat.")
        return redirect("cl_detail", pk=cl.pk)
    return inertia_render(request, "Cl/Form", props={
        "cl": None, "edit": False,
        "suggested_number": suggested_number, "default_company": default_company,
        **_form_context_data(),
    })
```

- [ ] **Step 6: Rewrite `cl_edit`**

Replace the body of `cl_edit` in `hw/views/cl_views.py` with (keeps `log_activity` diff snapshot):

```python
@login_required
def cl_edit(request, pk):
    cl = get_object_or_404(ConfirmationLetter, pk=pk)

    def _room_snapshot(rooms_qs):
        rows = [f"{r.room_type} x{r.quantity} @ {int(r.price or 0)}" for r in rooms_qs.order_by('id')]
        return ' | '.join(rows) if rows else '—'

    if request.method == "POST":
        errors = _validate_cl(request.POST, exclude_pk=cl.pk)
        if errors:
            echo = _cl_echo(request.POST); echo["id"] = cl.pk
            return inertia_render(request, "Cl/Form", props={
                "cl": echo, "edit": True, "errors": errors,
                "suggested_number": request.POST.get("confirmation_number", cl.confirmation_number),
                "default_company": cl.company, **_form_context_data(),
            })
        _before = {
            'Hotel': cl.hotel_name, 'Tamu': cl.guest_name, 'No. Telp': cl.guest_phone,
            'Check-in': str(cl.check_in or ''), 'Check-out': str(cl.check_out or ''),
            'Status': cl.reservation_status, 'Company': cl.company, 'Kamar': _room_snapshot(cl.rooms.all()),
        }
        cl.company = request.POST.get("company", "konoz")
        cl.client_id = request.POST.get("client_id") or None
        cl.hotel_name = request.POST.get("hotel_name", "")
        guest_name = request.POST.get("guest_name", "").strip()
        if not guest_name and cl.client_id:
            guest_name = Client.objects.filter(pk=cl.client_id).values_list("name", flat=True).first() or ""
        cl.guest_name = guest_name
        cl.guest_phone = request.POST.get("guest_phone", "")
        cl.check_in = _parse_date(request.POST.get("check_in"))
        cl.check_out = _parse_date(request.POST.get("check_out"))
        cl.confirmation_number = request.POST.get("confirmation_number", "")
        cl.reservation_status = request.POST.get("reservation_status", "DEFINITE")
        cl.note = request.POST.get("note", "")
        cl.save()
        cl.rooms.all().delete()
        _save_cl_rooms(cl, request)
        _after = {
            'Hotel': cl.hotel_name, 'Tamu': cl.guest_name, 'No. Telp': cl.guest_phone,
            'Check-in': str(cl.check_in or ''), 'Check-out': str(cl.check_out or ''),
            'Status': cl.reservation_status, 'Company': cl.company, 'Kamar': _room_snapshot(cl.rooms.all()),
        }
        changes = [{'label': k, 'before': _before[k], 'after': _after[k]} for k in _before if _before[k] != _after[k]]
        log_activity(request.user, ActivityLog.ACTION_EDIT, 'CL', cl.confirmation_number, cl.company, changes)
        messages.success(request, f"Confirmation Letter {cl.confirmation_number} berhasil diperbarui.")
        return redirect("cl_detail", pk=cl.pk)

    rooms = [{
        "room_type": r.room_type, "meals": r.meals,
        "quantity": r.quantity, "price": int(round(float(r.price))),
    } for r in cl.rooms.all()]
    return inertia_render(request, "Cl/Form", props={
        "cl": {
            "id": cl.pk, "company": cl.company,
            "client_id": cl.client_id or "", "hotel_name": cl.hotel_name,
            "guest_name": cl.guest_name, "guest_phone": cl.guest_phone,
            "check_in": cl.check_in.isoformat() if cl.check_in else "",
            "check_out": cl.check_out.isoformat() if cl.check_out else "",
            "confirmation_number": cl.confirmation_number,
            "reservation_status": cl.reservation_status, "note": cl.note,
            "rooms": rooms,
        },
        "edit": True, "suggested_number": cl.confirmation_number,
        "default_company": cl.company, **_form_context_data(),
    })
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test hw.tests.test_form_views.ClFormTests -v2`
Expected: PASS (4 tests). Note: the `_save_cl_rooms` `import json` is function-local to avoid touching the module's existing top-of-file imports; this is intentional.

- [ ] **Step 8: Check**

Run: `.venv\Scripts\python.exe manage.py check`
Expected: no issues.

- [ ] **Step 9: Commit** (deferred — skip until user asks)

```bash
git add hw/views/cl_views.py hw/tests/test_form_views.py
git commit -m "Feat: migrate CL views to Inertia with JSON room parsing + validation"
```

---

## Task 3: Cl/Form.jsx + RoomRows.jsx

**Files:**
- Create: `frontend/pages/Cl/RoomRows.jsx`
- Create: `frontend/pages/Cl/Form.jsx`

**Interfaces:**
- Consumes: `postForm` (Task 1); `FormPanel/FormSection/FormField/FormActions`; backend `Cl/Form` props (Task 2).
- Produces: Inertia page component `Cl/Form`.

- [ ] **Step 1: Create RoomRows.jsx**

Create `frontend/pages/Cl/RoomRows.jsx`:

```jsx
const ROOM_TYPES = ["Double", "Triple", "Quad", "Quint"];
const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

export default function RoomRows({ rooms, onChange, nights }) {
  const update = (i, key, val) => {
    const next = rooms.map((r, idx) => (idx === i ? { ...r, [key]: val } : r));
    onChange(next);
  };
  const add = () => onChange([...rooms, { room_type: "", meals: "", quantity: 1, price: "" }]);
  const remove = (i) => onChange(rooms.filter((_, idx) => idx !== i));

  return (
    <div>
      {rooms.map((r, i) => {
        const sub = (nights || 1) * (Number(r.quantity) || 0) * (Number(r.price) || 0);
        return (
          <div key={i} className="fg-2" style={{ gridTemplateColumns: "1.2fr 1fr .7fr 1fr auto", alignItems: "end", gap: 8, marginBottom: 8 }}>
            <div className="ff">
              <label>Tipe Kamar</label>
              <select value={r.room_type} onChange={(e) => update(i, "room_type", e.target.value)}>
                <option value="">— Pilih —</option>
                {ROOM_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className="ff"><label>Makan</label><input type="text" value={r.meals} onChange={(e) => update(i, "meals", e.target.value)} placeholder="BB, HB…" /></div>
            <div className="ff"><label>Jml</label><input type="number" min="1" value={r.quantity} onChange={(e) => update(i, "quantity", e.target.value)} /></div>
            <div className="ff"><label>Harga/malam</label><input type="number" min="0" step="0.01" value={r.price} onChange={(e) => update(i, "price", e.target.value)} placeholder="0.00" /></div>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => remove(i)} title="Hapus" style={{ marginBottom: 2 }}>×</button>
            <div style={{ gridColumn: "1 / -1", fontSize: 11, color: "var(--text-3)", marginTop: -2 }}>Subtotal: {fmt(sub)} SAR</div>
          </div>
        );
      })}
      <button type="button" className="btn btn-secondary btn-sm" onClick={add} style={{ marginTop: 4 }}>
        <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
        Tambah kamar
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Create Cl/Form.jsx**

Create `frontend/pages/Cl/Form.jsx`:

```jsx
import { useForm } from "@inertiajs/react";
import FormPanel from "../../components/form/FormPanel.jsx";
import FormSection from "../../components/form/FormSection.jsx";
import FormField from "../../components/form/FormField.jsx";
import FormActions from "../../components/form/FormActions.jsx";
import { postForm } from "../../utils/inertiaForm.js";
import RoomRows from "./RoomRows.jsx";

const STATUS = [["DEFINITE", "Definite"], ["TENTATIVE", "Tentative"], ["CANCELLED", "Cancelled"]];
const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

function nightsBetween(ci, co) {
  if (!ci || !co) return 1;
  const d = (new Date(co) - new Date(ci)) / 86400000;
  return d > 0 ? d : 1;
}

export default function Form({ cl, edit, errors: serverErrors, suggested_number, default_company, hotels, clients }) {
  const c = cl || {};
  const form = useForm({
    company: c.company || default_company || "konoz",
    client_id: c.client_id || "",
    hotel_name: c.hotel_name || "",
    guest_name: c.guest_name || "",
    guest_phone: c.guest_phone || "",
    check_in: c.check_in || "",
    check_out: c.check_out || "",
    confirmation_number: c.confirmation_number || suggested_number || "",
    reservation_status: c.reservation_status || "DEFINITE",
    note: c.note || "",
    rooms: c.rooms || [],
  });
  const errors = { ...serverErrors, ...form.errors };
  const set = (k) => (v) => form.setData(k, v);
  const nights = nightsBetween(form.data.check_in, form.data.check_out);
  const total = nights * form.data.rooms.reduce((s, r) => s + (Number(r.quantity) || 0) * (Number(r.price) || 0), 0);

  const submit = (e) => {
    e.preventDefault();
    postForm(form, edit ? `/cl/${c.id}/edit/` : "/cl/new/", { json: ["rooms"] });
  };

  return (
    <div className="form-page">
      <div className="page-header" style={{ marginBottom: 16 }}>
        <div>
          <div className="page-title">{edit ? "Edit Confirmation Letter" : "Confirmation Letter Baru"}</div>
          <div className="page-sub">Detail reservasi hotel</div>
        </div>
      </div>

      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label="Company & Status">
            <div className="fg-2">
              <FormField label="Company" name="company">
                <select name="company" value={form.data.company} onChange={(e) => form.setData("company", e.target.value)}>
                  <option value="konoz">Konoz United</option>
                  <option value="ijabah">Ijabah</option>
                </select>
              </FormField>
              <FormField label="Reservation Status" name="reservation_status">
                <select name="reservation_status" value={form.data.reservation_status} onChange={(e) => form.setData("reservation_status", e.target.value)}>
                  {STATUS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </FormField>
            </div>
          </FormSection>

          <FormSection label="Reservasi">
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField label="Nomor CL" name="confirmation_number" required value={form.data.confirmation_number} onChange={set("confirmation_number")} error={errors.confirmation_number} />
              <FormField label="Hotel" name="hotel_name">
                <input list="cl-hotels" name="hotel_name" value={form.data.hotel_name} onChange={(e) => form.setData("hotel_name", e.target.value)} placeholder="Nama hotel" />
                <datalist id="cl-hotels">
                  {(hotels || []).map((h, i) => <option key={i} value={h.name} />)}
                </datalist>
              </FormField>
            </div>
            <div className="fg-2">
              <FormField label="Check-in" name="check_in" type="date" value={form.data.check_in} onChange={set("check_in")} />
              <FormField label="Check-out" name="check_out" type="date" value={form.data.check_out} onChange={set("check_out")} error={errors.check_out} />
            </div>
          </FormSection>

          <FormSection label="Tamu">
            <div className="fg-2" style={{ marginBottom: 12 }}>
              <FormField label="Client (Agen)" name="client_id">
                <select name="client_id" value={form.data.client_id} onChange={(e) => form.setData("client_id", e.target.value)}>
                  <option value="">— Tanpa client —</option>
                  {(clients || []).map((cl2) => <option key={cl2.id} value={cl2.id}>{cl2.name}</option>)}
                </select>
              </FormField>
              <FormField label="Nama Tamu" name="guest_name" value={form.data.guest_name} onChange={set("guest_name")} placeholder="Kosongkan untuk pakai nama client" />
            </div>
            <FormField label="No. Telepon" name="guest_phone" value={form.data.guest_phone} onChange={set("guest_phone")} inputMode="tel" />
          </FormSection>

          <FormSection label="Kamar">
            <RoomRows rooms={form.data.rooms} onChange={(next) => form.setData("rooms", next)} nights={nights} />
            <div style={{ marginTop: 12, textAlign: "right", fontWeight: 600 }}>
              Total: {fmt(total)} SAR <span style={{ fontWeight: 400, fontSize: 12, color: "var(--text-3)" }}>({nights} malam)</span>
            </div>
          </FormSection>

          <FormSection label="Catatan">
            <FormField name="note">
              <textarea name="note" rows={3} value={form.data.note} onChange={(e) => form.setData("note", e.target.value)} placeholder="Catatan internal…" />
            </FormField>
          </FormSection>

          <FormActions
            cancelHref={edit ? `/cl/${c.id}/` : "/cl/"}
            submitLabel={edit ? "Simpan Perubahan" : "Buat CL"}
            processing={form.processing} />
        </FormPanel>
      </form>
    </div>
  );
}
```

- [ ] **Step 3: Build**

Run: `npm run build`
Expected: build succeeds; bundle includes `Cl/Form`.

- [ ] **Step 4: Manual verification**

`npm run dev` + runserver. `/cl/new/`: add 2 rooms, set qty/price → total preview updates; remove a room; submit check_out before check_in → inline error on Check-out; valid submit → CL detail with rooms + success toast. Edit an existing CL → fields + rooms prefilled → save.

- [ ] **Step 5: Commit** (deferred — skip until user asks)

```bash
git add frontend/pages/Cl/Form.jsx frontend/pages/Cl/RoomRows.jsx
git commit -m "Feat: CL form (new/edit) React component with dynamic room rows"
```

---

## Task 4: Remove legacy CL form template

**Files:**
- Delete: `hw/templates/hw/cl/cl_form.html`

- [ ] **Step 1: Confirm no remaining references**

Run: `grep -rn "cl_form.html" hw/ --include=*.py`
Expected: no matches.

- [ ] **Step 2: Delete the template**

```bash
rm hw/templates/hw/cl/cl_form.html
```

- [ ] **Step 3: Check**

Run: `.venv\Scripts\python.exe manage.py check`
Expected: no issues.

- [ ] **Step 4: Commit** (deferred — skip until user asks)

```bash
git rm hw/templates/hw/cl/cl_form.html
git commit -m "Chore: remove legacy cl_form.html (migrated to React)"
```

---

## Self-Review Notes

- **Spec coverage:** Transport helper + retrofit (Task 1) = spec §1–2. CL views + room JSON (Task 2) = spec §3. Cl/Form + RoomRows (Task 3) = spec §4 incl. datalist hotels, client dropdown, live total. Validation errors (Task 2/3) = spec §5. Tests (Task 2) = spec Testing. Cleanup (Task 4) = spec Cleanup.
- **Type consistency:** `_cl_echo`/edit-GET both produce `rooms` as a list of `{room_type, meals, quantity, price}`; `Cl/Form` reads `c.rooms`; `RoomRows` mutates the same shape; `postForm({json:["rooms"]})` stringifies it; `_save_cl_rooms` parses the same keys. `check_in`/`check_out` are ISO strings both ways (`<input type=date>` uses `YYYY-MM-DD`, `_parse_date` accepts it).
- **forceFormData reality:** retrofit confirmed against Inertia core source quoted in Global Constraints.
- **Deferred commits:** per user preference, "Commit" steps are documented but skipped this session; task gates are build + check + tests.
- **Confirm during implementation:** `_parse_date` accepts `YYYY-MM-DD` (used by date inputs) — verify in `hw/views/helpers.py`; the legacy form posted the same format so this should hold.
