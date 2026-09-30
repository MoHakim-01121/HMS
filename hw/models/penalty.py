"""CancellationPenalty: denda pembatalan sebuah reservasi (skema target 3.2).

Ditetapkan Pusat, selalu dalam SAR, dan ditagih di invoice hotel (yang juga
selalu SAR) sebagai satu baris invoice: dokumen ini menjelaskan dendanya,
invoice yang menagihnya. Denda tidak menyimpan invoice maupun status bayarnya:
invoice-nya adalah baris invoice yang menunjuk denda ini, dan lunas-tidaknya
dihitung dari uang yang diterima untuk reservasi itu (hw.finance.
penalty_billing).
"""
from django.db import models


class CancellationPenalty(models.Model):
    # PROTECT: reservasi yang sudah dikenai denda tidak boleh hilang.
    cl              = models.OneToOneField('ConfirmationLetter', on_delete=models.PROTECT, related_name='penalty')
    penalty_number  = models.CharField(max_length=50, unique=True)
    cancellation_date = models.DateField()
    reason          = models.TextField(blank=True)

    # Nominal denda dalam SAR.
    penalty_amount   = models.PositiveIntegerField()

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
    def invoice_line(self):
        """Baris invoice yang sedang menagih denda ini (None bila belum ditagih)."""
        from .invoice import InvoiceLine
        if not self.pk:
            return None
        return InvoiceLine.objects.filter(
            kind=InvoiceLine.KIND_PENALTY, penalty_id=self.pk, voided_at__isnull=True,
        ).select_related('invoice').first()

    @property
    def invoice(self):
        line = self.invoice_line
        return line.invoice if line else None

    # Dibaca PDF denda. Keduanya turunan: denda lunas bila uang yang diterima
    # untuk reservasinya sudah menutup nominal denda.
    @property
    def is_paid(self):
        from ..finance.penalty_billing import penalty_state
        return penalty_state(self)['is_paid']

    @property
    def payment_date(self):
        from ..finance.penalty_billing import penalty_state
        return penalty_state(self)['paid_on']

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
