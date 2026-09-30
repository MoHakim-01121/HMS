"""CancellationPenalty: denda pembatalan sebuah reservasi (skema target 3.2).

Ditetapkan Pusat, selalu dalam SAR, dan ditagih di invoice hotel (yang juga
selalu SAR). Client yang membayar denda dalam rupiah atau dolar dicatat sebagai
pembayaran dengan kursnya; dokumen dendanya sendiri tetap SAR.
"""
from django.db import models


class CancellationPenalty(models.Model):
    # PROTECT: reservasi yang sudah dikenai denda tidak boleh hilang.
    cl              = models.OneToOneField('ConfirmationLetter', on_delete=models.PROTECT, related_name='penalty')
    invoice         = models.ForeignKey('Invoice', null=True, blank=True, on_delete=models.SET_NULL, related_name='penalties')
    penalty_number  = models.CharField(max_length=50, unique=True)
    cancellation_date = models.DateField()
    reason          = models.TextField(blank=True)

    # Nominal denda dalam SAR.
    penalty_amount   = models.PositiveIntegerField()

    # Status bayar lama. Masih memicu jurnal pembayaran denda (posting.
    # resync_penalty); dipindahkan ke modul Payment di fase pembayaran (F5).
    is_paid        = models.BooleanField(default=False)
    payment_date   = models.DateField(null=True, blank=True)
    payment_method = models.CharField(max_length=100, blank=True)
    payment_note   = models.TextField(blank=True)

    note       = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['-created_at']
        verbose_name        = 'Cancellation Penalty'
        verbose_name_plural = 'Cancellation Penalties'
        constraints = [
            models.CheckConstraint(condition=models.Q(penalty_amount__gt=0), name='penalty_amount_positive'),
        ]

    def __str__(self):
        return f"{self.penalty_number} — {self.cl.confirmation_number}"

    # Denda selalu SAR: nilai-nilai ini tetap tersedia dengan nama lamanya
    # untuk PDF dan kode pembaca, tapi bukan lagi kolom yang bisa berbeda.
    penalty_currency = 'SAR'
    exchange_rate = 1

    @property
    def amount_sar(self):
        return self.penalty_amount

    @property
    def penalty_amount_sar(self):
        return self.penalty_amount

    @classmethod
    def generate_number(cls):
        from ..numbering import generate_sequential_number
        return generate_sequential_number(cls, 'PNL', field='penalty_number', padding=3)

    @classmethod
    def suggest_number(cls):
        from ..numbering import peek_number
        return peek_number(cls, 'PNL', field='penalty_number', padding=3)

    @classmethod
    def claim_number(cls, number):
        """Counter mengikuti nomor yang diketik user."""
        from ..numbering import advance_number
        advance_number(cls, 'PNL', number, field='penalty_number')
