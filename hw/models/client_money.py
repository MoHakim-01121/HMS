"""Uang deposit client yang keluar: refund dan transfer ke client lain (skema target 3.5).

Deposit client (akun Titipan) bertambah ketika kelebihan bayar dipindahkan ke
sana. Ia berkurang lewat dua dokumen bernomor di sini, masing-masing dengan
satu entry jurnalnya: refund (uang dikembalikan dari sebuah rekening) dan
transfer (deposit pindah ke client lain).

Keduanya butuh dua orang: dokumen dicatat `pending` tanpa jurnal, lalu
dikonfirmasi user lain (admin boleh menyetujui catatannya sendiri) -- baru
saat itu jurnal diposting. Lihat hw.finance.deposit.
"""
from django.db import models

from .uploads import RandomFileName


class ApprovalStatus(models.TextChoices):
    PENDING   = 'pending', 'Awaiting approval'
    CONFIRMED = 'confirmed', 'Confirmed'
    REJECTED  = 'rejected', 'Rejected'


class Approvable(models.Model):
    """Status persetujuan dokumen uang keluar. Jurnal hanya ada bila confirmed."""
    status          = models.CharField(max_length=10, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING)
    confirmed_by    = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    confirmed_at    = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True)

    class Meta:
        abstract = True

    @property
    def is_pending(self):
        return self.status == ApprovalStatus.PENDING


class ClientRefund(Approvable):
    refund_number = models.CharField(max_length=30, unique=True)
    client        = models.ForeignKey('Client', on_delete=models.PROTECT, related_name='refunds')
    # Rekening yang mengeluarkan uangnya; mata uang `amount_paid` = mata uangnya.
    money_account = models.ForeignKey('MoneyAccount', on_delete=models.PROTECT, related_name='client_refunds')
    refund_date   = models.DateField()
    amount_sar    = models.PositiveIntegerField()      # yang diambil dari deposit client
    amount_paid   = models.PositiveIntegerField()      # yang benar-benar keluar dari rekening
    note          = models.TextField(blank=True)
    proof         = models.FileField(upload_to=RandomFileName('refunds/proof/'), null=True, blank=True)
    created_by    = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='+')
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-refund_date', '-pk']
        verbose_name = 'Client Refund'
        verbose_name_plural = 'Client Refunds'
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_sar__gt=0), name='client_refund_amount_positive'),
            models.CheckConstraint(condition=models.Q(amount_paid__gt=0), name='client_refund_paid_positive'),
            models.CheckConstraint(condition=models.Q(status__in=ApprovalStatus.values), name='client_refund_status_valid'),
        ]

    def __str__(self):
        return f"{self.refund_number} · {self.client}"

    @classmethod
    def generate_number(cls, on_date):
        from ..numbering import generate_sequential_number
        return generate_sequential_number(cls, f'RFD-{on_date:%Y%m}', field='refund_number', padding=3)


class ClientTransfer(Approvable):
    """Deposit satu client dipindahkan ke client lain."""
    transfer_number = models.CharField(max_length=30, unique=True)
    from_client     = models.ForeignKey('Client', on_delete=models.PROTECT, related_name='deposit_transfers_out')
    to_client       = models.ForeignKey('Client', on_delete=models.PROTECT, related_name='deposit_transfers_in')
    transfer_date   = models.DateField()
    amount_sar      = models.PositiveIntegerField()
    note            = models.TextField(blank=True)
    created_by      = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='+')
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-transfer_date', '-pk']
        verbose_name = 'Client Deposit Transfer'
        verbose_name_plural = 'Client Deposit Transfers'
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_sar__gt=0), name='client_transfer_amount_positive'),
            models.CheckConstraint(
                condition=~models.Q(from_client=models.F('to_client')), name='client_transfer_two_clients',
            ),
            models.CheckConstraint(condition=models.Q(status__in=ApprovalStatus.values), name='client_transfer_status_valid'),
        ]

    def __str__(self):
        return f"{self.transfer_number} · {self.from_client} → {self.to_client}"

    @classmethod
    def generate_number(cls, on_date):
        from ..numbering import generate_sequential_number
        return generate_sequential_number(cls, f'DTR-{on_date:%Y%m}', field='transfer_number', padding=3)
