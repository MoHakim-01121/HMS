"""Credit note (Nota Kredit): a formal reduction of what an invoice bills.

An issued invoice is never edited down in silence once money has moved on it;
the reduction is its own numbered document that references the invoice, with
one line per reservation or service it reduces. Posting (credit_note_service):
Dr Pendapatan / Cr Piutang — and when the client has already paid more than
the invoice still bills, the excess goes to the client's deposit (Titipan)
instead, for the existing refund / transfer tools to settle.
"""
from django.db import models


class CreditNote(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_VOIDED = 'voided'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_VOIDED, 'Voided'),
    ]

    credit_note_number = models.CharField(max_length=30, unique=True)
    invoice = models.ForeignKey('Invoice', on_delete=models.PROTECT, related_name='credit_notes')
    client = models.ForeignKey('Client', on_delete=models.PROTECT, related_name='credit_notes')
    issued_date = models.DateField(db_index=True)
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)
    # Part of the credit that went to the client's deposit, not Piutang.
    to_deposit_sar = models.PositiveIntegerField(default=0)
    voided_reason = models.TextField(blank=True)
    voided_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    voided_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issued_date', '-pk']
        verbose_name = 'Credit Note'
        verbose_name_plural = 'Credit Notes'

    def __str__(self):
        return f"{self.credit_note_number} · {self.invoice.invoice_number}"

    @property
    def amount_sar(self):
        return sum(line.amount_sar for line in self.lines.all())

    @classmethod
    def generate_number(cls, issued_date):
        from ..numbering import generate_sequential_number
        return generate_sequential_number(
            cls, f'CN-{issued_date:%Y%m}', field='credit_note_number', padding=3,
        )


class CreditNoteLine(models.Model):
    credit_note = models.ForeignKey(CreditNote, on_delete=models.CASCADE, related_name='lines')
    reservation = models.ForeignKey('Reservation', null=True, blank=True, on_delete=models.PROTECT, related_name='credit_note_lines')
    service_item = models.ForeignKey('ServiceItem', null=True, blank=True, on_delete=models.PROTECT, related_name='credit_note_lines')
    description = models.CharField(max_length=255)
    amount_sar = models.PositiveIntegerField()

    class Meta:
        ordering = ['pk']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(reservation__isnull=False, service_item__isnull=True)
                | models.Q(reservation__isnull=True, service_item__isnull=False),
                name='cn_line_one_target',
            ),
            models.CheckConstraint(condition=models.Q(amount_sar__gt=0), name='cn_line_amount_positive'),
        ]

    def __str__(self):
        return f"{self.description} {self.amount_sar:,}"
