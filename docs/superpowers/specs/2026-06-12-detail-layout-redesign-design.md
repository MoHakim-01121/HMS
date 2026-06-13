# Redesign Layout Halaman Detail (CL & Invoice)

**Tanggal:** 2026-06-12
**Tipe:** Refactor UI/layout (tanpa perubahan data, URL, atau logika Django)

## Latar Belakang

Halaman `cl_detail.html` dan `invoice_detail.html` terasa tidak rapi. Keluhan user:

1. Hero (`dhero`) terlalu ramai — nomor, badge, sub-judul, tombol menumpuk.
2. Hirarki informasi kurang jelas — tidak ada urutan baca yang menonjolkan angka penting.
3. Banyak `style="..."` inline yang berulang & tidak konsisten.
4. Layout 2 kolom terasa timpang; invoice malah tanpa rail.

Selain itu tombol PDF/Edit muncul **dobel** (di topbar atas dan di hero).

## Tujuan

Layout yang bersih dengan hirarki baca jelas:
**Hero ramping → Summary bar angka penting → konten.**

Murni layout & CSS. **Tidak mengubah:** isi data, context Django, URL/route, atau tampilan PDF.

## Keputusan Desain (disetujui user)

- **Arah:** Summary bar + struktur rail-kiri.
- **Tombol PDF/Edit:** hanya di **hero** (dibuang dari `topbar_actions`).
- **CL detail:** rail **kiri sempit** "Detail Properti" + konten **kanan lebar** (tabel Kamar, Lampiran).
- **Invoice detail:** tidak punya field detail seperti CL, jadi tetap **satu kolom full-width** di bawah summary (hero + stats sudah jadi summary bar).

## Struktur Akhir

### CL detail (`cl_detail.html`)

```
┌──────────────────────────────────────┐
│ CONFIRMATION LETTER                   │  kicker
│ KNZ-00123         [Konoz][Definite]   │  judul + badge
│ Ahmad · 12–15 Jun        [PDF][Edit]  │  sub + aksi
├──────────┬──────────┬─────────────────┤
│  Total   │  Malam   │  Tamu           │  summary bar (full-width)
│ 9.000 SAR│    3     │   2 orang       │
├──────────┴────┬─────┴─────────────────┤
│ DETAIL        │ ▢ Kamar (tabel)       │
│ PROPERTI      │                       │
│ Hotel         │ ▢ Lampiran            │
│ Agen Travel   │                       │
│ Telepon       │                       │
│ Check-in/out  │                       │
│ Catatan       │                       │
└───────────────┴───────────────────────┘
```

- **Hero:** kicker, baris judul (nomor copyable + badge status/company di kanan), baris sub (tamu · tanggal di kiri, tombol PDF/Edit di kanan).
- **Summary bar:** 3 sel — Total (SAR), Malam, Tamu.
- **Rail kiri "Detail Properti":** isi meta rail lama (Hotel, Agen Travel→link client, Telepon, Check-in, Check-out, Total, Catatan).
- **Konten kanan:** card Penalti (hanya bila `CANCELLED`), card Kamar, Lampiran.
- **Mobile:** rail kiri pindah ke atas konten (stack vertikal).

### Invoice detail (`invoice_detail.html`)

```
┌──────────────────────────────────────┐
│ INVOICE HOTEL                         │
│ INV-00045          [Konoz][Paid]      │
│ Ahmad · 12 Jun           [PDF][Edit]  │
├──────────┬──────────┬─────────────────┤
│ Total Res│  Paid    │  Remaining      │  stats = summary bar
├──────────┴──────────┴─────────────────┤
│ ▢ Reservations (tabel)                │
│ ▢ Payments (tabel)                    │
└──────────────────────────────────────┘
```

- Hero diramping sama seperti CL.
- `stats` (Total Reservation / Paid / Remaining) berperan sebagai summary bar — dirapikan, dikonsistenkan dengan style summary CL.
- Konten full-width: Reservations, Payments. Alert jatuh tempo tetap di atas konten.

## Perubahan CSS (`design.css`)

Pindahkan inline-style berulang jadi class reusable:

- **Summary bar:** kelas `.dsummary` + `.dsummary-cell` (label kecil + nilai besar mono). Samakan untuk CL & invoice; `stats`/`stat` lama disesuaikan/di-alias.
- **Rail kiri CL:** `.dlayout` dibalik jadi rail-kiri (`grid-template-columns: <rail> 1fr`). Pertahankan `.dmeta*` untuk isi rail, atau ganti nama agar jelas (mis. tetap `.dmeta` tapi diposisikan kiri).
- **Hero:** rapikan `.dhero`, `.dhero-main`, `.dhero-side`, `.dhero-actions` agar baris konsisten; tombol selalu di kanan.
- **Field grid** (untuk rail / detail): pakai pola field-label + field-value yang sudah ada.
- Buang `style="height:28px;padding:0 12px;..."` berulang pada tombol → andalkan `.btn-sm`/`.btn-ghost`.
- Responsif: di ≤700px rail kiri jadi block penuh di atas konten; summary bar tetap 3 kolom rapat (sudah ada pola di invoice `@media`).

## Yang TIDAK dikerjakan (YAGNI)

- Tidak mengubah skema warna / token desain global.
- Tidak menyentuh template PDF.
- Tidak mengubah view/context/URL.
- Tidak menambah fitur baru — hanya menata ulang elemen yang sudah ada.

## Kriteria Selesai

- Tombol PDF/Edit tidak dobel (hanya di hero).
- CL: rail kiri + konten kanan; Invoice: hero + summary + konten full-width.
- Tidak ada `style="..."` inline berulang untuk summary/hero/tombol (dipindah ke `design.css`).
- Tampilan tetap benar di mobile (≤700px) — rail nge-stack, summary tetap terbaca.
- Tidak ada perubahan data/perilaku; halaman tetap render tanpa error.
