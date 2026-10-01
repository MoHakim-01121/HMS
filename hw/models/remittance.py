"""Setoran cabang ke Pusat (skema target 3.6).

Remittance = satu transfer fisik dari rekening cabang ke rekening SAR Pusat:
`amount_sent` keluar dari rekening asal (dalam mata uangnya) dengan kurs
rencana `exchange_rate`, sehingga Pusat mengharapkan `expected_sar`.
Penerimaannya dicatat per tanda terima (RemittanceSettlement), dan setiap
tanda terima membagi uangnya ke reservasi lewat RemittanceLine.

Status tidak disimpan: transfer "received" bila Σ penerimaan mencapai
nominal kirimnya atau selisihnya sudah ditutup (hw.finance.settlement_service).
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db import models


class RemittanceQuerySet(models.QuerySet):
    def pending(self):
        """Transfer yang belum diterima penuh (status dihitung, jadi daftar)."""
        from ..finance.remittance_allocation import annotate_statuses
        return [r for r in annotate_statuses(self) if r.status == Remittance.STATUS_PENDING]


class Remittance(models.Model):
    STATUS_PENDING  = 'pending'
    STATUS_RECEIVED = 'received'

    remittance_number = models.CharField(max_length=20, unique=True, blank=True)
    date              = models.DateField()                       # tanggal kirim
    receipt_reference = models.CharField(max_length=100, blank=True)

    # Rekening cabang asal uang, dan rekening SAR Pusat yang menerimanya.
    from_account = models.ForeignKey('MoneyAccount', on_delete=models.PROTECT, related_name='remittances_sent')
    to_account   = models.ForeignKey('MoneyAccount', on_delete=models.PROTECT, related_name='remittances_received')
    # Nominal yang keluar dari rekening asal, dalam mata uang rekening itu.
    amount_sent   = models.BigIntegerField()
    # Kurs rencana (mata uang asal per 1 SAR); 1 untuk rekening SAR.
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=4)

    note       = models.TextField(blank=True)
    proof      = models.FileField(upload_to='remittance/proof/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = RemittanceQuerySet.as_manager()

    class Meta:
        ordering            = ['-date', '-created_at']
        verbose_name        = 'Remittance'
        verbose_name_plural = 'Remittances'
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_sent__gt=0), name='remittance_amount_positive'),
            models.CheckConstraint(condition=models.Q(exchange_rate__gt=0), name='remittance_rate_positive'),
            models.CheckConstraint(
                condition=~models.Q(from_account=models.F('to_account')), name='remittance_two_accounts',
            ),
        ]

    def __str__(self):
        return f"{self.remittance_number} | {self.date} | {self.expected_sar} SAR"

    @classmethod
    def generate_number(cls):
        from ..numbering import generate_sequential_number
        return generate_sequential_number(cls, 'RMT', field='remittance_number', padding=3)

    # Nama lama kolom nominal kirim (dulu selalu rupiah).
    @property
    def amount_idr(self):
        return self.amount_sent

    @amount_idr.setter
    def amount_idr(self, value):
        self.amount_sent = value

    @property
    def lines(self):
        """Alokasi semua penerimaan transfer ini ke reservasi."""
        return RemittanceLine.objects.filter(settlement__remittance=self)

    @property
    def total_sar(self):
        from ..finance import queries
        return int(queries.remittance_sent_sar(self.id))

    @property
    def expected_sar(self):
        """SAR yang diharapkan Pusat: amount_sent / kurs rencana."""
        if not self.amount_sent or not self.exchange_rate:
            return None
        return int((Decimal(self.amount_sent) / Decimal(self.exchange_rate)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

    @property
    def allocated_sar(self):
        """Total SAR yang sudah dibagikan ke reservasi (Σ alokasi)."""
        return int(self.lines.aggregate(t=models.Sum('amount_sar'))['t'] or 0)

    @property
    def unallocated_sar(self):
        """Sisa transfer yang belum dialokasikan ke reservasi mana pun."""
        return int(self.expected_sar or 0) - self.allocated_sar

    @property
    def settled_sar(self):
        """Σ penerimaan — yang benar-benar sudah diterima Pusat."""
        return int(self.settlements.aggregate(t=models.Sum('received_amount_sar'))['t'] or 0)

    @property
    def settlement_basis_sar(self):
        """Nominal yang harus diterima Pusat supaya Transit remittance ini nol:
        total kirim yang terposting, atau expected_sar bila belum terposting."""
        return self.total_sar or self.expected_sar

    @property
    def settlement_status(self):
        """sent / partially_settled / fully_settled, diturunkan dari penerimaan."""
        basis = self.settlement_basis_sar
        if basis is None:
            return None
        received = self.settled_sar
        if received <= 0:
            return 'sent'
        if received >= basis:
            return 'fully_settled'
        return 'partially_settled'

    @property
    def status(self):
        """received bila diterima penuh atau selisihnya sudah ditutup.
        Untuk daftar, hw.finance.remittance_allocation.annotate_statuses()
        menghitungnya sekaligus untuk banyak transfer."""
        cached = self.__dict__.get('_status_cache')
        if cached is not None:
            return cached
        from ..finance.settlement_service import diff_is_closed
        if self.settlement_status == 'fully_settled' or (self.pk and diff_is_closed(self)):
            return self.STATUS_RECEIVED
        return self.STATUS_PENDING


class RemittanceLine(models.Model):
    """Bagian satu penerimaan Pusat yang melunasi setoran untuk satu reservasi."""
    settlement   = models.ForeignKey(
        'RemittanceSettlement', on_delete=models.PROTECT, related_name='allocations',
    )
    # Baris hotel invoice reservasi itu (bukan lagi nomor CL sebagai teks).
    invoice_line = models.ForeignKey(
        'InvoiceLine', on_delete=models.PROTECT, related_name='remittance_allocations',
    )
    amount_sar   = models.PositiveIntegerField()

    class Meta:
        verbose_name        = 'Remittance Allocation'
        verbose_name_plural = 'Remittance Allocations'
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_sar__gt=0), name='remittance_line_amount_positive'),
        ]

    def __str__(self):
        return f"Res {self.linked_number} → {self.amount_sar} SAR"

    # Dibaca dari penerimaan dan baris invoice-nya.
    @property
    def remittance(self):
        return self.settlement.remittance

    @property
    def remittance_id(self):
        return self.settlement.remittance_id

    @property
    def invoice(self):
        return self.invoice_line.invoice

    @property
    def invoice_id(self):
        return self.invoice_line.invoice_id

    @property
    def linked_number(self):
        return self.invoice_line.reservation_number
