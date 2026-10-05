"""Currency — master mata uang (skema target §3.1).

Setiap nominal uang di HMS disimpan sebagai bilangan bulat dalam satuan
utuh mata uangnya (riyal, dolar, rupiah) — keputusan 2026-10-05, spec K3.
`minor_digits` (SAR 2 = halala, USD 2 = sen, IDR 0 = rupiah) hanya data
master; tidak dipakai untuk menyimpan nominal. Konversi ke SAR dan
pembulatannya lewat `hw.utils.convert_to_sar`.
"""
from django.db import models

# Kode yang dipakai CHECK constraint kolom mata uang (baris master-nya disemai
# migrasi). Menambah mata uang = menambah baris Currency dan kode di sini.
CURRENCY_CODES = ['SAR', 'USD', 'IDR']


class Currency(models.Model):
    code = models.CharField(max_length=3, primary_key=True)
    name = models.CharField(max_length=50)
    minor_digits = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ['code']
        verbose_name = 'Currency'
        verbose_name_plural = 'Currencies'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(minor_digits__lte=3),
                name='currency_minor_digits_range',
            ),
            models.CheckConstraint(
                condition=models.Q(code__regex=r'^[A-Z]{3}$'),
                name='currency_code_iso',
            ),
        ]

    def __str__(self):
        return self.code
