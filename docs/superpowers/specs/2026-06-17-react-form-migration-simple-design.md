# Migrasi Form ke React/Inertia — Fase Form Simpel

**Tanggal:** 2026-06-17
**Branch:** `feat/react-inertia-migration`
**Status:** Disetujui untuk implementasi

## Konteks

Halaman list & detail untuk modul utama HMS sudah dimigrasikan ke React via
Inertia.js. Yang tersisa adalah **form** (tambah/edit), yang masih memakai
Django template + POST biasa (`<form method="post">` → view re-render template
saat gagal, `redirect` + `messages.success` saat sukses). View tidak memakai
Django Forms; mereka mem-parse `request.POST` secara manual.

Fase ini memigrasikan **form simpel** (tanpa baris dinamis): Client, Penalty,
User. Form kompleks (Invoice, CL, Hotel, Services — dengan baris dinamis
kamar/item/pembayaran), halaman peta, dan `account/profile` (upload avatar)
ditunda ke fase berikutnya.

## Keputusan Desain

1. **Submit & validasi: idiomatik Inertia `useForm`.** Form React memakai
   `useForm` dari `@inertiajs/react`. POST lewat Inertia; error validasi
   dikembalikan view sebagai Inertia `errors` dan ditampilkan inline per-field.
2. **Notifikasi sukses: toast via flash.** Django `messages` di-share ke setiap
   response Inertia lewat `InertiaShareMiddleware` yang sudah ada, ditampilkan
   sebagai toast di `AppLayout`.
3. **Urutan: bertahap, simpel dulu** untuk mematangkan pola sebelum form kompleks.

## Batasan Penting: Tujuan Redirect Harus Inertia

Saat request Inertia menerima redirect ke response **bukan-Inertia** (HTML
template Django biasa), Inertia melempar error *"All Inertia requests must
receive a valid Inertia response."* Maka tujuan `redirect` setelah sukses harus
berupa halaman yang sudah dimigrasikan ke Inertia.

Konsekuensi terhadap cakupan:

| Form | Tujuan redirect sukses | Status tujuan | Implikasi |
|------|------------------------|---------------|-----------|
| Client (new/edit) | `client_detail` | ✅ sudah React | Migrasi form bersih total |
| Penalty (new/edit) | `penalty_detail` | ❌ belum React | Bundel migrasi `penalty_detail` |
| User (new) | `user_list` | ❌ belum React | Bundel migrasi `user_list` |
| User (edit aksi) | `user_list` | ❌ belum React | idem |

## Arsitektur

### Fondasi bersama (dibangun sekali di Slice A, dipakai semua)

**Komponen form reusable** — `frontend/components/form/`:

- `FormField.jsx` — membungkus `<div class="ff">` + `<label>` + input/children +
  pesan error. Props: `label`, `name`, `error`, `required`, `hint`, `children`
  (atau render input bawaan via `type`/`value`/`onChange`).
- `FormPanel.jsx` — `<div class="form-panel">`.
- `FormSection.jsx` — `<div class="form-section">` + label seksi
  (`.form-section-label`).
- `FormActions.jsx` — `<div class="form-actions">` dengan tombol Batal + Simpan;
  menerima `cancelHref`, `submitLabel`, `processing`.

Tujuan: tiap komponen punya satu tanggung jawab jelas, dipakai konsisten di
semua form, dan menjaga paritas visual dengan template lama lewat class CSS yang
sama.

**CSS** — Port aturan dari `hw/static/hw/css/forms.css` ke `hw/static/hw/css/shell.css`
(stylesheet yang dimuat `base_inertia.html`), sehingga form React tampil persis
sama tanpa memuat stylesheet terpisah. Class yang dipakai: `.form-page`,
`.form-panel`, `.form-section`, `.form-section-label`, `.ff`, `.fg-2`,
`.ff-check`, `.check-sub`, `.form-actions`, `.hint`.

**Toast** — Dua bagian:

- Backend: `InertiaShareMiddleware` (di `hw/inertia_share.py`) membaca
  `django.contrib.messages` request dan menambahkannya ke share sebagai
  `flash: {"success": "...", "error": "..."}`. Mengkonsumsi messages agar tidak
  dobel dengan template lama.
- Frontend: komponen `Toast.jsx` di `AppLayout` membaca `usePage().props.flash`,
  menampilkan toast yang auto-dismiss (≈3 dtk). Muncul untuk semua aksi
  (simpan/hapus) yang memakai `messages`.

### Pola view (GET & POST)

```python
# GET → render komponen form Inertia
def client_new(request):
    if request.method == 'POST':
        errors = _validate_client(request.POST)
        if errors:
            return inertia_render(request, "Client/Form",
                                  props={"edit": False, "client": _form_echo(request.POST), "errors": errors})
        c = _save_client(Client(), request.POST)
        messages.success(request, f'Client "{c.name}" berhasil ditambahkan.')
        return redirect('client_detail', pk=c.pk)
    return inertia_render(request, "Client/Form", props={"edit": False, "client": None})
```

- `errors` adalah dict `{field_name: pesan}`. Inertia menaruhnya di
  `page.props.errors`; `useForm` otomatis mengisi `form.errors`.
- Saat gagal, view re-render komponen **yang sama** (`Client/Form`) sehingga
  bukan redirect → tidak melanggar batasan Inertia.
- Validasi diekstrak ke helper kecil (`_validate_*`) terpisah dari penyimpanan.

### Pola komponen form (React)

```jsx
import { useForm } from "@inertiajs/react";

export default function Form({ client, edit }) {
  const form = useForm({
    name: client?.name || "", city: client?.city || "", /* ... */
    is_active: client ? client.is_active : true,
  });
  const submit = (e) => {
    e.preventDefault();
    if (edit) form.post(`/clients/${client.id}/edit/`);
    else form.post(`/clients/new/`);
  };
  return (
    <form onSubmit={submit} className="form-page"> {/* FormPanel/FormSection/FormField */} </form>
  );
}
```

- Satu komponen `Form.jsx` per modul menangani **new & edit** (`edit` prop +
  ada/tidaknya objek).
- Method HTTP: gunakan POST untuk create. Untuk edit, gunakan POST juga (view
  Django saat ini menangani POST untuk edit; tidak perlu menambah dukungan PUT).
  → **Edit memakai `form.post(editUrl)`** agar selaras dengan routing/CSRF yang ada.

## Slice (unit implementasi)

### Slice A — Fondasi + Client form
- Bangun `frontend/components/form/*`, port `forms.css` → `shell.css`, buat
  `Toast.jsx` + share `flash` di middleware.
- `Client/Form.jsx` (new+edit).
- Ubah `client_new`, `client_edit` di `client_views.py` → `inertia_render` +
  validasi + flash. Pertahankan `_save_client` yang ada.
- Field: name (wajib), city, province, is_active, pic, wa, email, lat, lng, note.

### Slice B — Penalty (form + detail)
- `Penalty/Form.jsx` (new+edit) + `Penalty/Detail.jsx`.
- Ubah `penalty_new`, `penalty_edit`, `penalty_detail` → `inertia_render`.
- Field: penalty_number, cancellation_date, reason, penalty_amount,
  penalty_currency, exchange_rate, is_paid, payment_date, payment_method,
  payment_note, note. Sediakan `suggested_number` & `today` sebagai props.

### Slice C — User (list + form)
- `User/List.jsx` + `User/Form.jsx`.
- Ubah `user_list`, `user_new`, `user_edit` → `inertia_render`.
- `user_new`: username (wajib), password (wajib), password_confirm (harus cocok),
  is_staff. Validasi unik username.
- `user_edit`: aksi berbasis tombol (reset_password, toggle_active,
  toggle_staff) — tetap POST dengan field `action`; tampilkan via komponen yang
  sesuai. Aksi toggle bisa tetap berupa form-button kecil di `User/List.jsx`.

## Penanganan Error

- Validasi server mengembalikan dict `errors` → ditampilkan inline di
  `FormField` per-field. Pesan non-field (mis. "Password tidak cocok") dipetakan
  ke field terkait (`password_confirm`) atau ke flash error → toast.
- Network/5xx ditangani Inertia default (event `onError`).

## Testing

Per slice:
1. `npm run build` sukses (Vite).
2. `python manage.py check` lolos.
3. Smoke test render Inertia (pola skrip yang sudah dipakai pada migrasi
   sebelumnya) untuk komponen baru.
4. Verifikasi manual: create sukses → redirect + toast; submit invalid → error
   inline; edit → tersimpan.

## Cleanup

Template lama (`client_form.html`, `penalty_form.html`, `penalty_detail.html`,
`user_form.html`, `user_list.html`) dihapus setelah slice terkait diverifikasi
bekerja, agar tidak ada dua sumber kebenaran.

## Di Luar Cakupan (Fase Berikutnya)

- Form kompleks dengan baris dinamis: Invoice, CL, Hotel, Services
  (menggantikan `invoice_form.js` ~12KB dan logika serupa).
- Halaman peta (`hotel_map`, `client_map`).
- `account/profile` (upload/hapus avatar).
- Konfirmasi hapus (`confirm_delete.html`).
