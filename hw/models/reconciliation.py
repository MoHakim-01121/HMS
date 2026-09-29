"""Bank reconciliation (Master Architecture v2.0 §52).

BankStatement/BankStatementLine hold what the BANK says happened (external
truth — typed in, or imported from the bank's CSV export). Amounts are in the
account's own currency, exactly as the bank prints them: a Mandiri IDR
statement is compared in rupiah against the cash book (BankTransaction.amount),
never through a SAR conversion. Differences are surfaced, never silently
overwritten (v2.0 §52: "Jangan otomatis menimpa fakta internal dengan data
statement").
"""
from django.db import models


class BankStatement(models.Model):
    bank_account = models.ForeignKey('BankAccount', null=True, blank=True, on_delete=models.PROTECT, related_name='statements')
    cash_account = models.ForeignKey('CashAccount', null=True, blank=True, on_delete=models.PROTECT, related_name='statements')
    currency     = models.CharField(max_length=3, default='SAR')
    period_start = models.DateField()
    period_end   = models.DateField()
    opening_balance = models.BigIntegerField()
    closing_balance = models.BigIntegerField()
    note       = models.TextField(blank=True)
    # Set when the lines came from an uploaded bank export.
    source_filename = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period_end', '-id']
        verbose_name = 'Bank Statement'
        verbose_name_plural = 'Bank Statements'
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(bank_account__isnull=False, cash_account__isnull=True)
                    | models.Q(bank_account__isnull=True, cash_account__isnull=False)
                ),
                name='bankstatement_exactly_one_account',
            ),
        ]

    def __str__(self):
        return f'{self.account} {self.period_start}–{self.period_end}'

    @property
    def account(self):
        return self.bank_account or self.cash_account

    @property
    def is_fully_matched(self):
        return not self.lines.filter(matched_transaction__isnull=True).exists()


class BankStatementLine(models.Model):
    statement   = models.ForeignKey(BankStatement, on_delete=models.CASCADE, related_name='lines')
    line_date   = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    direction   = models.CharField(max_length=3, choices=[('in', 'Money In'), ('out', 'Money Out')])
    amount      = models.PositiveBigIntegerField()   # in the statement's currency
    reference   = models.CharField(max_length=200, blank=True)
    # Set once matched to a BankTransaction — the whole point of this table.
    # Null means still unreconciled.
    matched_transaction = models.ForeignKey(
        'BankTransaction', null=True, blank=True, on_delete=models.SET_NULL, related_name='statement_lines',
    )

    class Meta:
        ordering = ['line_date', 'id']
        verbose_name = 'Bank Statement Line'
        verbose_name_plural = 'Bank Statement Lines'

    def __str__(self):
        sign = '+' if self.direction == 'in' else '-'
        return f'{sign}{self.amount:,} {self.statement.currency} — {self.description or self.reference}'
