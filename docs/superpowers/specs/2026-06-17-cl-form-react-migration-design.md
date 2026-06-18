# CL Form → React/Inertia + Form Transport Fix — Design

**Tanggal:** 2026-06-17
**Branch:** `feat/react-inertia-migration`
**Status:** Disetujui untuk implementasi

## Konteks

Form simpel (Client, Penalty, User) sudah dimigrasikan ke React/Inertia. Tahap
berikutnya adalah form kompleks dengan baris dinamis. Sub-proyek pertama:
**Confirmation Letter (CL) form** — baris dinamis paling sederhana (hanya kamar),
untuk mematangkan pola "dynamic rows + useForm" sebelum Invoice/Services.

Spec ini juga memuat **perbaikan transport** yang menjadi prasyarat semua form
React (termasuk retrofit form simpel).

## Temuan Kritis: Transport Inertia

Inertia core v1.3.0 hanya mengubah payload menjadi `FormData` bila ada file atau
`forceFormData: true`:

```js
if ((hasFiles(r) || forceFormData) && !(r instanceof FormData) && (r = objectToFormData(r)) ...
```

Tanpa itu, `form.post` mengirim **JSON** (via axios). Django `request.POST` hanya
mem-parse `application/x-www-form-urlencoded`/`multipart` — **bukan JSON body**.
Maka view yang membaca `request.POST.get(...)` akan kosong di browser asli. Test
form simpel lolos hanya karena Django test client mengirim form-encoded.

**Keputusan:** semua submit form React memakai `forceFormData: true` (multipart),
sehingga `request.POST` dan `request.FILES` terisi seperti form Django lama.
Koleksi (array baris dinamis) dikirim sebagai **satu field string JSON**, di-parse
backend dengan `json.loads` — menghindari serialisasi bracket (`rooms[0][...]`)
yang tidak cocok dengan `request.POST.getlist`.

## Arsitektur

### 1. Helper transport bersama

**`frontend/utils/inertiaForm.js`** — `postForm(form, url, { json } = {})`:
- Untuk tiap key di `json` (mis. `rooms`), set `form.transform` agar mengganti
  nilai array dengan `JSON.stringify(value)`.
- Memanggil `form.post(url, { forceFormData: true })`.
- Mengembalikan apa yang dikembalikan `form.post`.

Bentuk yang diharapkan:
```js
export function postForm(form, url, { json = [] } = {}) {
  form.transform((data) => {
    const out = { ...data };
    for (const key of json) out[key] = JSON.stringify(data[key] ?? []);
    return out;
  });
  return form.post(url, { forceFormData: true });
}
```

### 2. Retrofit form simpel

Client/Penalty/User TIDAK dirutekan lewat `postForm` (tak punya koleksi). Cukup
ubah pemanggilan submit mereka dari `form.post(url)` menjadi
`form.post(url, { forceFormData: true })`, dan **pertahankan** `form.transform`
checkbox→`"on"` yang sudah ada (transform dan opsi `forceFormData` tidak saling
menimpa: transform mengubah data, `forceFormData` adalah opsi `post`). Tidak ada
perubahan backend untuk form simpel.

### 3. View CL (`hw/views/cl_views.py`)

- `cl_new`/`cl_edit` GET → `inertia_render("Cl/Form", props={...})` dengan
  `suggested_number`, `default_company`, `hotels`, `clients`, (`cl` pada edit),
  `edit`.
- POST: kumpulkan `errors` dict:
  - `check_out` bila `check_out < check_in`.
  - `confirmation_number` bila nomor sudah dipakai (exclude diri sendiri saat edit).
  - Jika ada error → `inertia_render("Cl/Form", props={..., "errors": errors,
    "cl"/"form_data": echo})`.
  - Jika valid → buat/update CL, `_save_cl_rooms`, `log_activity`,
    `messages.success`, `redirect("cl_detail")`.
- `_save_cl_rooms(cl, request)` ditulis ulang:
  ```python
  import json
  rooms = json.loads(request.POST.get("rooms", "[]") or "[]")
  for r in rooms:
      rt = (r.get("room_type") or "").strip()
      if not rt:
          continue
      Room.objects.create(
          cl=cl, room_type=rt, meals=r.get("meals", "") or "",
          quantity=max(1, int(r.get("quantity") or 1)),
          price=max(0, float(r.get("price") or 0)),
      )
  ```
- Echo helper mengembalikan field skalar + daftar `rooms` agar form tetap terisi
  saat error.

### 4. Komponen `Cl/Form.jsx` + `RoomRows`

- `useForm` dengan field skalar + `rooms: cl?.rooms || []` (tiap item
  `{room_type, meals, quantity, price}`).
- Reuse `FormPanel/FormSection/FormField/FormActions`.
- Sub-komponen **`RoomRows`** (file `frontend/pages/Cl/RoomRows.jsx`):
  props `rooms`, `onChange(nextRooms)`, `nights`. Render tiap baris (room_type,
  meals, quantity number, price number) dengan tombol hapus; tombol "Tambah kamar"
  menambah baris kosong; menampilkan subtotal per baris (`nights*qty*price`).
- `company` & `reservation_status` sebagai `<select>`, `client_id` dropdown dari
  `clients`, `hotel_name` `<input list>` dengan `<datalist>` dari `hotels`.
- **Preview total** read-only: `nights × Σ(qty×price)`, dihitung di React;
  `nights` dari selisih check_in/check_out (default 1 bila belum lengkap).
- Submit: `postForm(form, edit ? "/cl/<id>/edit/" : "/cl/new/", { json: ["rooms"] })`.
- Cancel → `cl_detail` (edit) atau `cl_list` (new).

### 5. Error handling

Error validasi server dikembalikan sebagai inertia `errors` dan ditampilkan inline
di `FormField` (`check_out`, `confirmation_number`). Error non-field lain (tak ada
untuk CL) akan jatuh ke flash toast.

## Testing

Django `TestCase` di `hw/tests/test_form_views.py` (test client mengirim multipart;
`rooms` sebagai string JSON), kelas `ClFormTests`:
1. GET `/cl/new/` (header `X-Inertia`) → `component == "Cl/Form"`.
2. POST check_out < check_in → `errors.check_out` ada, `component == "Cl/Form"`.
3. POST nomor duplikat → `errors.confirmation_number` ada.
4. POST valid dengan `rooms='[{"room_type":"Double","quantity":2,"price":300}]'`
   → 302, CL tercipta, 1 Room tercipta dengan quantity 2.

Plus `npm run build` sukses, `manage.py check` bersih, verifikasi manual
(create/edit/tambah-hapus kamar/preview total/error inline/toast).

## Cleanup

Hapus `hw/templates/hw/cl/cl_form.html` setelah slice terverifikasi.

## Di Luar Cakupan (Sub-Proyek Berikutnya)

Invoice form (reservasi + pembayaran + drag-sort + upload bukti), Services form,
Hotel form, halaman peta (`hotel_map`/`client_map`), `account/profile` (avatar),
dan `confirm_delete.html`. Masing-masing mendapat siklus spec → plan tersendiri.
Transport fix di spec ini menjadi fondasi semua form berikutnya.
