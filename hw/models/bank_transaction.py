"""BankTransaction — cash-movement log (Master Architecture v2.0 §25-28, §82).

NOT a second source of truth for the balance: `MoneyAccount.book_balance`
(hw/models/bank.py) stays a pure projection over JournalLine. BankTransaction
is a discrete, traceable record of each movement — created as a side effect
whenever a payment/expense-payment/settlement posts against a concrete
BankAccount/CashAccount — so a bank statement can be reconciled line-by-line
against something narrower than "the whole journal". It is idempotent per
(source_type, source_id): re-confirming the same event never doubles it.

BankStatement/BankStatementLine/Reconciliation (§52) are NOT built yet —
matching + discrepancy UI is its own scoping conversation, deferred.
"""
from django.db import models


class BankTransaction(models.Model):
    DIRECTION_IN  = 'in'
    DIRECTION_OUT = 'out'
    DIRECTION_CHOICES = [
        (DIRECTION_IN,  'Money In'),
        (DIRECTION_OUT, 'Money Out'),
    ]

    STATUS_POSTED     = 'posted'
    STATUS_RECONCILED = 'reconciled'
    # The source document was reversed/voided: the money never really moved
    # (a correction). Kept, not deleted, so the log keeps its audit trail.
    STATUS_VOIDED     = 'voided'
    STATUS_CHOICES = [
        (STATUS_POSTED,     'Posted'),
        (STATUS_RECONCILED, 'Reconciled'),
        (STATUS_VOIDED,     'Voided'),
    ]

    bank_account = models.ForeignKey('BankAccount', null=True, blank=True, on_delete=models.PROTECT, related_name='transactions')
    cash_account = models.ForeignKey('CashAccount', null=True, blank=True, on_delete=models.PROTECT, related_name='transactions')
    transaction_date = models.DateField(db_index=True)
    direction    = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    amount_sar   = models.PositiveIntegerField()
    currency     = models.CharField(max_length=3, default='SAR')
    # Nominal asli dalam `currency` — uang yang benar-benar bergerak di
    # rekening (rupiah/dolar), dasar laporan Arus Dana. `amount_sar` tetap
    # nilai setara jurnal. Null hanya untuk baris lama yang sumbernya tak
    # menyimpan nominal asli.
    amount       = models.BigIntegerField(null=True, blank=True)
    # Sumber asal (PaymentRecord/ExpensePayment/RemittanceSettlement/...) —
    # sama pola reference_type/reference_id yang sudah dipakai JournalEntry.
    source_type  = models.CharField(max_length=40, db_index=True)
    source_id    = models.PositiveIntegerField(db_index=True)
    reference    = models.CharField(max_length=200, blank=True)
    status       = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_POSTED)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-transaction_date', '-id']
        verbose_name = 'Bank Transaction'
        verbose_name_plural = 'Bank Transactions'
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(bank_account__isnull=False, cash_account__isnull=True)
                    | models.Q(bank_account__isnull=True, cash_account__isnull=False)
                ),
                name='banktransaction_exactly_one_account',
            ),
            models.UniqueConstraint(
                fields=['source_type', 'source_id'],
                name='banktransaction_unique_source',
            ),
        ]
        indexes = [
            models.Index(fields=['bank_account', 'transaction_date'], name='banktx_bank_date_idx'),
            models.Index(fields=['cash_account', 'transaction_date'], name='banktx_cash_date_idx'),
        ]

    def __str__(self):
        sign = '+' if self.direction == self.DIRECTION_IN else '-'
        return f'{sign}{self.amount_sar:,} SAR ({self.source_type} #{self.source_id})'

    @property
    def account(self):
        return self.bank_account or self.cash_account
