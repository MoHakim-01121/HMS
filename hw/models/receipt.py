"""Receipt (Kwitansi) — bukti pembayaran untuk reservasi.

Receipt di-generate dari PaymentRecord sebagai dokumen terpisah.
Convention: all monetary amounts stored as IntegerField (minor units).
"""
from django.db import models
from django.urls import reverse


class Receipt(models.Model):
    """Kwitansi pembayaran — dokumen bukti bahwa klien telah membayar."""

    STATUS_ACTIVE  = 'active'
    STATUS_VOIDED  = 'voided'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_VOIDED, 'Voided'),
    ]

    # Identitas
    receipt_number = models.CharField(max_length=50, unique=True, db_index=True)
    receipt_date   = models.DateField()

    # Relasi ke data existing
    payment        = models.ForeignKey(
        'PaymentRecord', on_delete=models.PROTECT, related_name='receipts',
    )
    # Nullable: pembayaran tanpa invoice (deposit) tetap dapat kwitansi —
    # PDF menampilkan tanpa blok invoice ("Paid for") dan tanpa rincian alokasi.
    invoice        = models.ForeignKey(
        'Invoice', null=True, blank=True, on_delete=models.PROTECT, related_name='receipts',
    )
    client         = models.ForeignKey(
        'Client', on_delete=models.PROTECT, related_name='receipts',
    )
    confirmation_letter = models.ForeignKey(
        'ConfirmationLetter', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='receipts',
    )

    # Data pembayaran
    amount_sar     = models.PositiveIntegerField()
    payment_method = models.CharField(max_length=50)
    payment_note   = models.TextField(blank=True)

    # Status
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    voided_reason  = models.TextField(blank=True)

    # Audit
    created_by     = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='+')
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['-created_at']
        verbose_name        = 'Receipt'
        verbose_name_plural = 'Receipts'
        indexes = [
            models.Index(fields=['status'], name='receipt_status_idx'),
            models.Index(fields=['client', 'status'], name='receipt_client_status_idx'),
        ]

    def __str__(self):
        return f"{self.receipt_number} | {self.amount_sar:,} SAR"

    def get_absolute_url(self):
        if self.payment_id:
            return reverse('payment_detail', args=[self.payment_id])
        return reverse('receipt_pdf', args=[self.pk])

    @staticmethod
    def generate_number():
        from ..numbering import generate_sequential_number
        return generate_sequential_number(Receipt, 'RCP', field='receipt_number', padding=4)
