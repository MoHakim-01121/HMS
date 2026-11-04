"""Credit note (Nota Kredit): a formal reduction of what an invoice bills.

An issued invoice is never edited down in silence once money has moved on it;
the reduction is its own numbered document that references the invoice, with
one line per invoice line it reduces. Posting (credit_note_service):
Dr Pendapatan / Cr Piutang — and when the client has already paid more than
the invoice still bills, the excess goes to the client's deposit (Titipan)
instead, for the existing refund / transfer tools to settle.

Who bears it (user, 2026-11-04): by default head office, whose revenue it
reduces. When the branch that sold the invoice gave the discount, the branch
bears it: Dr Beban Diskon Cabang on that branch instead of Pendapatan, so head
office keeps its revenue and the branch still owes it the full SAR.
"""
from django.db import models


class CreditNote(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_VOIDED = 'voided'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_VOIDED, 'Voided'),
    ]
    BORNE_HQ = 'hq'
    BORNE_BRANCH = 'branch'
    BORNE_CHOICES = [
        (BORNE_HQ, 'Head office'),
        (BORNE_BRANCH, 'Branch'),
    ]

    credit_note_number = models.CharField(max_length=30, unique=True)
    invoice = models.ForeignKey('Invoice', on_delete=models.PROTECT, related_name='credit_notes')
    client = models.ForeignKey('Client', on_delete=models.PROTECT, related_name='credit_notes')
    issued_date = models.DateField(db_index=True)
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)
    borne_by = models.CharField(max_length=10, choices=BORNE_CHOICES, default=BORNE_HQ, db_index=True)
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
    def is_branch_borne(self):
        return self.borne_by == self.BORNE_BRANCH

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
    invoice_line = models.ForeignKey('InvoiceLine', on_delete=models.PROTECT, related_name='credit_note_lines')
    description = models.CharField(max_length=255)
    amount_sar = models.PositiveIntegerField()

    class Meta:
        ordering = ['pk']
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_sar__gt=0), name='cn_line_amount_positive'),
        ]

    def __str__(self):
        return f"{self.description} {self.amount_sar:,}"
