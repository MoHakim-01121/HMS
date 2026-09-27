"""Currency exchange between the organisation's own accounts (Penukaran Valas).

A client pays in USD; the branch sells those dollars for rupiah into an IDR
account and later remits the rupiah to HQ. The exchange moves money between
two of our own accounts in different currencies, so it changes nothing in the
SAR journal (what the branch owes HQ is unchanged). It is recorded as two
cash-book rows (BankTransaction): out of the source account and into the
target account, each in its own currency — the fund-flow report and the
branch's realized FX profit read them from there.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db import models


class CurrencyExchange(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_VOIDED = 'voided'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_VOIDED, 'Voided'),
    ]

    exchange_number = models.CharField(max_length=20, unique=True)
    exchange_date = models.DateField(db_index=True)

    # Exactly one account per side (bank or cash), same pattern as PaymentRecord.
    from_bank_account = models.ForeignKey('BankAccount', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    from_cash_account = models.ForeignKey('CashAccount', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    amount_out = models.BigIntegerField()  # in the source account's currency
    to_bank_account = models.ForeignKey('BankAccount', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    to_cash_account = models.ForeignKey('CashAccount', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    amount_in = models.BigIntegerField()   # in the target account's currency

    reference = models.CharField(max_length=200, blank=True)
    note = models.TextField(blank=True)
    proof = models.FileField(upload_to='exchange/proof/', null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)
    voided_reason = models.TextField(blank=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-exchange_date', '-pk']
        verbose_name = 'Currency Exchange'
        verbose_name_plural = 'Currency Exchanges'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(from_bank_account__isnull=False, from_cash_account__isnull=True)
                | models.Q(from_bank_account__isnull=True, from_cash_account__isnull=False),
                name='fx_exactly_one_from_account',
            ),
            models.CheckConstraint(
                condition=models.Q(to_bank_account__isnull=False, to_cash_account__isnull=True)
                | models.Q(to_bank_account__isnull=True, to_cash_account__isnull=False),
                name='fx_exactly_one_to_account',
            ),
            models.CheckConstraint(condition=models.Q(amount_out__gt=0, amount_in__gt=0), name='fx_amounts_positive'),
        ]

    def __str__(self):
        return f"{self.exchange_number} {self.amount_out:,} {self.from_currency} → {self.amount_in:,} {self.to_currency}"

    @classmethod
    def generate_number(cls):
        from ..numbering import generate_sequential_number
        return generate_sequential_number(cls, 'FX', field='exchange_number', padding=4)

    @property
    def from_account(self):
        return self.from_bank_account or self.from_cash_account

    @property
    def to_account(self):
        return self.to_bank_account or self.to_cash_account

    @property
    def from_currency(self):
        return self.from_account.currency

    @property
    def to_currency(self):
        return self.to_account.currency

    @property
    def rate(self):
        """Units of the target currency received per unit of the source
        currency (e.g. 17,500 IDR per USD)."""
        return (Decimal(self.amount_in) / Decimal(self.amount_out)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
