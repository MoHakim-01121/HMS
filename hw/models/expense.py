"""Expense domain — beban operasional cabang (Master Architecture v2.0 §29–31, §63, §77).

Expense = biaya (accrual). ExpensePayment = pergerakan kas. Keduanya terpisah:
sebuah Expense bisa POSTED tapi belum dibayar (utang / Accounts Payable).

Konvensi: semua nominal IntegerField (minor units). amount_sar via convert_to_sar.
Expense BUKAN HQ remittance dan BUKAN obligation pusat.
"""
from django.db import models



class ExpenseCategory(models.Model):
    """Master kategori beban — dikelola bisnis, memetakan ke satu LedgerAccount."""

    code = models.CharField(max_length=20, primary_key=True)
    name = models.CharField(max_length=100)
    ledger_account = models.ForeignKey('LedgerAccount', on_delete=models.PROTECT, related_name='+')
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'Expense Category'
        verbose_name_plural = 'Expense Categories'

    def __str__(self):
        return f"{self.code} | {self.name}"


class Expense(models.Model):
    STATUS_DRAFT         = 'draft'
    STATUS_POSTED        = 'posted'
    STATUS_PARTIALLY_PAID = 'partially_paid'
    STATUS_PAID          = 'paid'
    STATUS_VOIDED        = 'voided'
    STATUS_CHOICES = [
        (STATUS_DRAFT,          'Draft'),
        (STATUS_POSTED,         'Posted'),
        (STATUS_PARTIALLY_PAID, 'Partially Paid'),
        (STATUS_PAID,           'Paid'),
        (STATUS_VOIDED,         'Voided'),
    ]

    expense_number   = models.CharField(max_length=50, unique=True, db_index=True)
    branch           = models.ForeignKey('Branch', on_delete=models.PROTECT, related_name='expenses')
    expense_date     = models.DateField(db_index=True)
    vendor           = models.CharField(max_length=200, blank=True)
    description      = models.CharField(max_length=255, blank=True)
    currency         = models.CharField(max_length=10, default='SAR')
    total_amount     = models.PositiveIntegerField(default=0)
    total_amount_sar = models.PositiveIntegerField(default=0)

    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    period     = models.ForeignKey('FinancialPeriod', on_delete=models.PROTECT, related_name='expenses')
    note       = models.TextField(blank=True)
    proof      = models.FileField(upload_to='expenses/proof/', null=True, blank=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-expense_date', '-created_at']
        verbose_name = 'Expense'
        verbose_name_plural = 'Expenses'
        indexes = [
            models.Index(fields=['branch', 'expense_date'], name='expense_branch_date_idx'),
            models.Index(fields=['status', 'expense_date'], name='expense_status_date_idx'),
        ]

    def __str__(self):
        return f"{self.expense_number} | {self.vendor or self.description}"

    @staticmethod
    def generate_number():
        from ..numbering import generate_sequential_number
        return generate_sequential_number(Expense, 'EXP', field='expense_number', padding=4)

    @property
    def paid_sar(self):
        return self.payments.filter(
            status=ExpensePayment.STATUS_PAID,
        ).aggregate(t=models.Sum('amount_sar'))['t'] or 0

    @property
    def outstanding_sar(self):
        return max(0, self.total_amount_sar - self.paid_sar)

    def derive_status(self):
        """Status bayar dari Σ ExpensePayment vs total. Tidak menyentuh
        draft/voided (lifecycle dokumen)."""
        if self.status in (self.STATUS_DRAFT, self.STATUS_VOIDED):
            return self.status
        paid = self.paid_sar
        if paid >= self.total_amount_sar and self.total_amount_sar > 0:
            return self.STATUS_PAID
        if paid > 0:
            return self.STATUS_PARTIALLY_PAID
        return self.STATUS_POSTED


class ExpenseLine(models.Model):
    expense       = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='lines')
    category      = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name='+')
    # Override akun buku besar (default: category.ledger_account).
    ledger_account = models.ForeignKey('LedgerAccount', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    description   = models.CharField(max_length=255, blank=True)
    amount        = models.PositiveIntegerField(default=0)
    amount_sar    = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Expense Line'
        verbose_name_plural = 'Expense Lines'

    def __str__(self):
        return f"{self.category_id}: {self.amount_sar:,}"

    @property
    def account_code(self):
        return self.ledger_account_id or self.category.ledger_account_id


class ExpensePayment(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_PAID    = 'paid'
    STATUS_VOID    = 'void'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PAID,    'Paid'),
        (STATUS_VOID,    'Void'),
    ]

    expense      = models.ForeignKey(Expense, on_delete=models.PROTECT, related_name='payments')
    payment_date = models.DateField()
    amount       = models.PositiveIntegerField()
    currency     = models.CharField(max_length=10, default='SAR')
    amount_sar   = models.PositiveIntegerField()
    # Akun uang (rekening bank atau kas) yang membayar.
    source_account = models.ForeignKey('MoneyAccount', on_delete=models.PROTECT, related_name='expense_payments')
    reference    = models.CharField(max_length=200, blank=True)
    status       = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PAID)
    note         = models.TextField(blank=True)
    created_by   = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='+')
    created_at   = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['payment_date', 'id']
        verbose_name = 'Expense Payment'
        verbose_name_plural = 'Expense Payments'

    def __str__(self):
        return f"{self.expense.expense_number} pay {self.amount_sar:,}"
