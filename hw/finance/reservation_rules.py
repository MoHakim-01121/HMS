"""Aturan nilai sebuah reservasi (CL) di invoice, satu sumber untuk semua jalur.

Baris hotel di invoice tidak menyimpan nilai: InvoiceLine.amount memanggil
aturan ini setiap kali dibaca, jadi invoice, jurnal charge, dan semua laporan
menagih angka yang sama dengan CL-nya.
"""
from ..utils import round_half_up

CANCELLED = 'CANCELLED'


def is_cancelled(cl):
    return (getattr(cl, 'reservation_status', '') or '').upper() == CANCELLED


def reservation_total_for_cl(cl):
    """Nilai yang ditagih invoice untuk CL ini.

    CL yang dibatalkan bernilai 0: barisnya tetap ada di invoice (jejak audit +
    tautan ke CL), tapi tidak lagi ditagih. Biaya pembatalannya ditagih lewat
    dokumen penalty, bukan lewat baris reservasi ini.
    """
    if cl is None:
        return 0
    if is_cancelled(cl):
        return 0
    return int(round_half_up(cl.total_price or 0))
