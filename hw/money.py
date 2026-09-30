"""Uang: satuan terkecil, konversi, dan pembulatan — satu tempat untuk semua.

Konvensi skema target (spec §2 K3–K4):

* Nominal disimpan sebagai ``int`` dalam satuan terkecil mata uangnya
  (SAR → halala, USD → sen, IDR → rupiah). Jumlah digit desimal tiap mata
  uang ada di ``MINOR_DIGITS`` (cermin tabel ``Currency``).
* Kurs disimpan **seperti dikutip pasar**, bukan sebagai pengali terbalik.
  Rupiah dikutip per satu unit mata uang lain (4.900 IDR per SAR), SAR per USD
  (3,75). Menyimpan kebalikannya (1/4900 = 0,00020408) kehilangan presisi:
  Rp35.280.000 × 0,00020408 = SAR 7.199,94, bukan 7.200.
* Hasil konversi dibulatkan **setengah ke atas** pada satuan terkecil mata uang
  tujuan. Tidak ada float di jalur uang.
"""
from decimal import ROUND_HALF_UP, Decimal

MINOR_DIGITS = {'SAR': 2, 'USD': 2, 'IDR': 0}

TO_PER_FROM = 'to_per_from'   # rate = berapa unit mata uang tujuan per 1 unit asal (dikali)
FROM_PER_TO = 'from_per_to'   # rate = berapa unit mata uang asal per 1 unit tujuan (dibagi)


class MoneyError(ValueError):
    pass


def minor_digits(code):
    try:
        return MINOR_DIGITS[code]
    except KeyError:
        raise MoneyError(f"Mata uang tidak dikenal: {code!r}") from None


def to_minor(amount, code):
    """Nominal utuh/desimal (mis. Decimal('7200.50')) → int satuan terkecil."""
    scale = Decimal(10) ** minor_digits(code)
    return int((Decimal(str(amount)) * scale).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def from_minor(amount_minor, code):
    """int satuan terkecil → Decimal nominal (untuk tampilan)."""
    return Decimal(amount_minor) / (Decimal(10) ** minor_digits(code))


def market_quote(from_code, to_code):
    """Arah kutipan kurs yang dipakai pasar/form untuk pasangan ini.

    Rupiah selalu dikutip per satu unit mata uang lain; pasangan lain dikutip
    sebagai unit SAR per satu unit asing (SAR per USD).
    """
    if from_code == to_code:
        return TO_PER_FROM
    if from_code == 'IDR':
        return FROM_PER_TO          # 4.900 IDR per 1 SAR → dibagi
    if to_code == 'IDR':
        return TO_PER_FROM          # 17.500 IDR per 1 USD → dikali
    if to_code == 'SAR':
        return TO_PER_FROM          # 3,75 SAR per 1 USD → dikali
    return FROM_PER_TO              # SAR → USD dikutip 3,75 SAR per 1 USD → dibagi


def convert(amount_minor, from_code, to_code, *, rate, rate_is=None):
    """Konversi nominal satuan terkecil `from_code` → satuan terkecil `to_code`.

    `rate_is` menyatakan arti `rate` (TO_PER_FROM atau FROM_PER_TO). Bila tidak
    diisi, dipakai `market_quote(from_code, to_code)`.
    """
    if not isinstance(amount_minor, int):
        raise MoneyError("amount_minor harus int (satuan terkecil)")
    rate = Decimal(str(rate))
    if rate <= 0:
        raise MoneyError("Kurs harus lebih dari 0")
    if from_code == to_code:
        if rate != 1:
            raise MoneyError("Kurs untuk mata uang yang sama harus 1")
        return amount_minor
    rate_is = rate_is or market_quote(from_code, to_code)
    major = from_minor(amount_minor, from_code)
    if rate_is == TO_PER_FROM:
        converted = major * rate
    elif rate_is == FROM_PER_TO:
        converted = major / rate
    else:
        raise MoneyError(f"rate_is tidak dikenal: {rate_is!r}")
    return to_minor(converted, to_code)
