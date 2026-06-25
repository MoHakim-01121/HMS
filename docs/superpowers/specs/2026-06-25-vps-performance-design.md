# VPS Performance Optimization — Design Spec

**Date:** 2026-06-25  
**Scope:** Aplikasi HMS (Django 5.2 + React/Inertia + Gunicorn + WhiteNoise) di VPS Hostinger  
**Goal:** Mengurangi latency halaman, memory usage, dan beban DB tanpa infrastruktur baru

---

## Konteks & Audit

Stack produksi saat ini:
- Django 5.2.8 + PostgreSQL via psycopg2
- React/Inertia.js (Vite build, single bundle)
- Gunicorn 2 sync workers, `--preload`
- WhiteNoise 6.6 untuk static files
- Tidak ada Django cache backend
- Session: default DB-backed

Yang sudah baik (tidak diubah):
- `db_index=True` pada semua field yang sering di-filter (`company`, `check_in`, `check_out`, `reservation_status`, `confirmation_number`)
- `select_related` + `prefetch_related` sudah dipakai di calendar dan CL list
- `CONN_MAX_AGE=600` — koneksi DB di-reuse
- `--preload` di Gunicorn

Gap yang ditemukan:
1. Tidak ada GZipMiddleware — Inertia JSON props dikirim tanpa kompresi
2. Gunicorn sync workers terlalu sedikit, tidak ada `--max-requests` (memory leak WeasyPrint)
3. Vite single bundle — React + app code jadi 1 file, re-download tiap deploy
4. Tidak ada Django cache — MessageTemplate & WATarget di-query tiap request kalender
5. WhiteNoise `MAX_AGE` tidak di-set — browser tidak cache static secara agresif
6. Field `ai_summary` dead code di `ConfirmationLetter` dan `Invoice` — ikut di-load tapi tidak dipakai
7. CL list load `note` (TextField) padahal tidak ditampilkan

---

## Perubahan yang Disetujui

### 1. GZipMiddleware

Tambah ke `config/settings.py` di posisi tepat setelah `SecurityMiddleware`:

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.gzip.GZipMiddleware',       # ← tambah
    'whitenoise.middleware.WhiteNoiseMiddleware',
    ...
]
```

Semua response Django (HTML + Inertia JSON props) dikompres. Payload navigasi turun ~70-80% untuk halaman dengan banyak data.

Tidak ada risiko BREACH: semua halaman HMS butuh autentikasi.

### 2. Gunicorn — gthread + max-requests

Ganti `bin/startup.sh`:

```bash
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:${PORT:-8000} \
  --worker-class gthread \
  --workers ${GUNICORN_WORKERS:-3} \
  --threads ${GUNICORN_THREADS:-4} \
  --timeout 120 \
  --max-requests 1000 \
  --max-requests-jitter 100 \
  --preload
```

Perubahan dari sebelumnya:
- `--worker-class gthread` — tiap worker handle 4 request concurrent via thread. Saat Fonnte API lambat, thread lain tetap melayani.
- Default `--workers 3` (dari 2) — aman untuk VPS 1-2 core. Override via `.env` dengan `GUNICORN_WORKERS=5` jika RAM cukup.
- `--max-requests 1000 --max-requests-jitter 100` — worker restart setelah 1000 request. Wajib ada karena WeasyPrint (PDF) punya memory leak. Jitter supaya semua worker tidak restart bersamaan.

### 3. Vite Code Splitting

Update `vite.config.js` untuk pisah vendor chunk:

```js
rollupOptions: {
  input: resolve("./frontend/main.jsx"),
  output: {
    manualChunks: {
      vendor: ['react', 'react-dom', '@inertiajs/react'],
    },
  },
},
```

Hasil build: dua file — `vendor-[hash].js` (React, tidak berubah antar deploy) dan `main-[hash].js` (app code). Browser cache vendor chunk permanen. Setelah deploy, user hanya download ulang `main-[hash].js` yang lebih kecil.

### 4. Django Cache (locmem) + Session Cache

Tambah ke `config/settings.py`:

```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'TIMEOUT': 300,
    }
}

SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
```

`SESSION_ENGINE = cached_db` — session dibaca dari memori, hanya fallback ke DB jika tidak ada di cache. Hemat 1 DB query per request.

Cache `_get_message_templates()` dan `_get_last_recap()` di `hw/views/calendar_views.py` menggunakan `cache.get_or_set()`:

```python
from django.core.cache import cache

def _get_message_templates():
    def _fetch():
        rows = {r.template_type: r.body for r in MessageTemplate.objects.all()}
        return {
            'h1_template':    rows.get('H1_GUEST',  TEMPLATE_H1),
            'h0_template':    rows.get('H0_GUEST',  TEMPLATE_H0),
            'recap_template': rows.get('RECAP_OPS', TEMPLATE_RECAP),
        }
    return cache.get_or_set('message_templates', _fetch, 300)

def _get_last_recap():
    def _fetch():
        log = RecapLog.objects.filter(status='SENT').order_by('-sent_at').first()
        if not log:
            return None
        return {
            'sent_at': log.sent_at.strftime('%d %b %Y %H:%M'),
            'target': log.target,
            'cl_count': log.cl_count,
            'triggered_by': log.triggered_by,
        }
    return cache.get_or_set('last_recap', _fetch, 60)
```

Invalidate `message_templates` setelah user save template di `message_template_save` view:

```python
cache.delete('message_templates')
```

**Catatan:** locmem adalah per-process. Dengan 3 Gunicorn workers, ada 3 cache terpisah. `cache.delete()` hanya clear 1 worker; worker lain serve stale sampai TTL habis (5 menit). Ini acceptable untuk data semi-statis.

### 5. WhiteNoise Max-Age

Tambah ke `config/settings.py`:

```python
WHITENOISE_MAX_AGE = 31536000  # 1 tahun
```

WhiteNoise sudah pakai content-hash di nama file (e.g. `vendor-Cx3bXh9p.js`), sehingga 1 tahun cache aman — file baru otomatis dapat nama baru.

### 6. Hapus Field `ai_summary` (Dead Code)

Field `ai_summary = models.TextField(blank=True)` di `ConfirmationLetter` dan `Invoice` tidak pernah dibaca atau diisi di mana pun. Fitur AI summary dibatalkan. AI hanya dipakai di halaman utama via chat (GROQ/Gemini API langsung), tidak melalui field ini.

Langkah:
1. Hapus `ai_summary` dari `hw/models/confirmation.py`
2. Hapus `ai_summary` dari `hw/models/invoice.py`
3. Jalankan `python manage.py makemigrations` → buat migration drop column
4. Jalankan `python manage.py migrate` di VPS

### 7. Defer `note` di CL List

CL list tidak menampilkan `note` tapi ORM tetap load field ini (TextField). Tambah `.defer('note')` ke queryset di `hw/views/cl_views.py`:

```python
base_qs = (
    ConfirmationLetter.objects
    .filter(company=active_company) if active_company
    else ConfirmationLetter.objects.all()
).defer('note') \
 .select_related('invoice') \
 .prefetch_related('rooms')
```

Hanya di `cl_list` — jangan di `_filter_cl_qs()` atau `cl_export_csv()` karena keduanya membutuhkan `note` (CSV export menulis `cl.note` ke output).

---

## File yang Berubah

| File | Perubahan |
|------|-----------|
| `config/settings.py` | GZipMiddleware, CACHES, SESSION_ENGINE, WHITENOISE_MAX_AGE |
| `bin/startup.sh` | gthread, max-requests, default workers 3 |
| `vite.config.js` | manualChunks vendor split |
| `hw/views/calendar_views.py` | cache.get_or_set untuk templates & last_recap |
| `hw/views/cl_views.py` | defer('note') di base_qs cl_list saja |
| `hw/models/confirmation.py` | hapus ai_summary |
| `hw/models/invoice.py` | hapus ai_summary |
| `hw/migrations/XXXX_remove_ai_summary.py` | migration baru (auto-generated) |

---

## Tidak Termasuk dalam Scope

- Redis cache (tidak perlu install software baru)
- Nginx-level gzip (butuh akses edit config Nginx)
- Database indexes tambahan (sudah adequate)
- CDN untuk static files
