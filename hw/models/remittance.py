"""Remittance & RemittanceLine models.

Pindahan dari models/invoice.py -- dirapikan agar setiap file model selaras
dengan satu fitur. Nama kelas (Remittance, RemittanceLine) tidak berubah,
jadi nama tabel DB (hw_remittance, hw_remittanceline) juga tidak berubah dan
tidak ada migrasi schema yang diperlukan.

Convention: all monetary amounts stored as IntegerField (minor units).
"""
from django.db import models

from .invoice import Invoice


class Remittance(models.Model):
    STATUS_PENDING  = 'pending'
    STATUS_RECEIVED = 'received'
    STATUS_CHOICES  = [(STATUS_PENDING, 'Pending'), (STATUS_RECEIVED, 'Received')]

    remittance_number = models.CharField(max_length=20, unique=True, blank=True)
    date              = models.DateField()
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    receipt_reference = models.CharField(max_length=100, blank=True)

    # Transfer bank fisik: uang IDR keluar dari Surabaya, kurs yang dipakai,
    # dan nominal SAR yang benar-benar diterima pusat (bisa beda karena biaya
    # transfer/pembulatan). Semuanya opsional -- RMT lama hanya punya baris.
    amount_idr         = models.BigIntegerField(null=True, blank=True)
    exchange_rate      = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    received_amount_sar = models.IntegerField(null=True, blank=True)

    note              = models.TextField(blank=True)
    proof             = models.FileField(upload_to='remittance/proof/', null=True, blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['-date', '-created_at']
        verbose_name        = 'Remittance'
        verbose_name_plural = 'Remittances'

    def __str__(self):
        return f"{self.remittance_number} | {self.date} | {self.total_sar} SAR"

    @classmethod
    def generate_number(cls):
        from ..numbering import generate_sequential_number
        return generate_sequential_number(cls, 'RMT', field='remittance_number', padding=3)

    @property
    def total_sar(self):
        from ..finance import queries
        return int(queries.remittance_sent_sar(self.id))

    @property
    def expected_sar(self):
        """SAR teoretis dari amount_idr / kurs (sebelum biaya transfer)."""
        if self.amount_idr is None or not self.exchange_rate:
            return None
        from decimal import Decimal, ROUND_HALF_UP
        return int((Decimal(self.amount_idr) / self.exchange_rate).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

    @property
    def allocated_sar(self):
        """Total SAR yang sudah dibagikan ke reservasi (Σ baris)."""
        return sum(int(l.amount_sar or 0) for l in self.lines.all())

    @property
    def unallocated_sar(self):
        """Sisa transfer yang belum dialokasikan ke reservasi mana pun."""
        if self.received_amount_sar is None:
            return 0
        return int(self.received_amount_sar) - self.allocated_sar

    @property
    def settlement_status(self):
        """Status 5-state v2.0 §90 (sent/partially_settled/fully_settled),
        DITURUNKAN dari RemittanceSettlement (jalur baru — lihat
        hw/models/settlement.py). None kalau remittance ini tak punya
        amount_idr/exchange_rate (expected_sar tak terhitung): berarti masih
        dikelola lewat `status` (pending/received) + jalur lump-sum lama.
        Tidak mencakup draft/cancelled — belum ada sinyal untuk itu di data
        yang ada."""
        expected = self.expected_sar
        if expected is None:
            return None
        received = self.settlements.aggregate(
            t=models.Sum('received_amount_sar'),
        )['t'] or 0
        if received <= 0:
            return 'sent'
        if received >= expected:
            return 'fully_settled'
        return 'partially_settled'


class RemittanceLine(models.Model):
    remittance    = models.ForeignKey(Remittance, on_delete=models.CASCADE, related_name='lines')
    invoice       = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.SET_NULL, related_name='remittance_lines')
    linked_number = models.CharField(max_length=100)
    amount_sar    = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = 'Remittance Line'
        verbose_name_plural = 'Remittance Lines'

    def __str__(self):
        return f"Res {self.linked_number} → {self.amount_sar} SAR"
