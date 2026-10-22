"""Transfer between the organisation's own accounts of one branch — in the
same currency (Kas IDR → Bank IDR), or exchanged (Penukaran Valas).

A same-currency transfer only moves the cash book: both accounts share the
branch's ledger account for that currency, so amount_in = amount_out and no
journal is posted. Money for another branch is a Remittance, not a transfer.

An exchange: a client pays in USD; the branch sells those dollars for rupiah
into an IDR account and later remits the rupiah to HQ. What the branch owes HQ
in SAR is unchanged; a journal moves the SAR value from the USD ledger account
to the IDR one (posting.post_exchange). Both kinds are recorded as two
cash-book rows (BankTransaction): out of the source account and into the
target account, each in its own currency — the fund-flow report and the
branch's realized FX profit read them from there.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db import models

from .uploads import RandomFileName


class CurrencyExchange(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_VOIDED = 'voided'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_VOIDED, 'Voided'),
    ]

    exchange_number = models.CharField(max_length=20, unique=True)
    exchange_date = models.DateField(db_index=True)

    from_account = models.ForeignKey('MoneyAccount', on_delete=models.PROTECT, related_name='+')
    amount_out = models.BigIntegerField()  # in the source account's currency
    to_account = models.ForeignKey('MoneyAccount', on_delete=models.PROTECT, related_name='+')
    amount_in = models.BigIntegerField()   # in the target account's currency

    reference = models.CharField(max_length=200, blank=True)
    note = models.TextField(blank=True)
    proof = models.FileField(upload_to=RandomFileName('exchange/proof/'), null=True, blank=True)
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
                condition=~models.Q(from_account=models.F('to_account')),
                name='fx_accounts_differ',
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
