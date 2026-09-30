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
    # Akun uang cabang yang mengirim — baris kas keluar di buku kas
    # (BankTransaction). Kosong untuk transfer lama sebelum field ini ada.
    from_account       = models.ForeignKey(
        'MoneyAccount', null=True, blank=True, on_delete=models.PROTECT, related_name='remittances_sent',
    )
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
        """Sisa transfer yang belum dialokasikan ke reservasi mana pun.

        Basis totalnya: received_amount_sar kalau remittance ini masih pakai
        jalur lama (sudah ada nominal diterima manual -- angka itu final,
        dipertahankan apa adanya untuk data lama). Remittance BARU tidak
        pernah lagi mendapat received_amount_sar dari form (2026-09-14 --
        penerimaan HQ sekarang selalu lewat RemittanceSettlement), jadi basis
        totalnya jatuh ke expected_sar (dari amount_idr/exchange_rate) supaya
        alur "declare lump sum dulu, pecah ke reservasi belakangan" tetap
        bisa dilacak progresnya sebelum ada settlement sama sekali."""
        total = self.received_amount_sar if self.received_amount_sar is not None else self.expected_sar
        if total is None:
            return 0
        return int(total) - self.allocated_sar

    @property
    def settled_sar(self):
        """Σ RemittanceSettlement — yang benar-benar sudah diterima pusat."""
        return int(self.settlements.aggregate(t=models.Sum('received_amount_sar'))['t'] or 0)

    @property
    def settlement_basis_sar(self):
        """Nominal yang harus diterima pusat supaya TRANSIT remittance ini nol:
        total kirim yang terposting (total_sar = debit TRANSIT). Bukan
        expected_sar (amount_idr/kurs) -- itu bisa beda dari Σ baris yang
        benar-benar terposting, dan menutup selisih pakai angka itu membuat
        TRANSIT tidak nol. expected_sar hanya jadi fallback kalau sisi kirim
        belum terposting sama sekali. None kalau keduanya tak diketahui."""
        return self.total_sar or self.expected_sar

    @property
    def settlement_status(self):
        """Status v2.0 §90 (sent/partially_settled/fully_settled), DITURUNKAN
        dari RemittanceSettlement terhadap settlement_basis_sar. None kalau
        basisnya tak diketahui. Tidak mencakup draft/cancelled — belum ada
        sinyal untuk itu di data yang ada."""
        basis = self.settlement_basis_sar
        if basis is None:
            return None
        received = self.settled_sar
        if received <= 0:
            return 'sent'
        if received >= basis:
            return 'fully_settled'
        return 'partially_settled'


class RemittanceLine(models.Model):
    remittance    = models.ForeignKey(Remittance, on_delete=models.CASCADE, related_name='lines')
    invoice       = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.SET_NULL, related_name='remittance_lines')
    linked_number = models.CharField(max_length=100)
    amount_sar    = models.PositiveIntegerField(default=0)
    # Terisi = dialokasikan saat Pusat menerima (hw/finance/remittance_allocation.py).
    # Kosong = jalur lama, dialokasikan saat kirim.
    settlement    = models.ForeignKey(
        'RemittanceSettlement', null=True, blank=True, on_delete=models.PROTECT,
        related_name='allocations',
    )

    class Meta:
        verbose_name        = 'Remittance Line'
        verbose_name_plural = 'Remittance Lines'

    def __str__(self):
        return f"Res {self.linked_number} → {self.amount_sar} SAR"
