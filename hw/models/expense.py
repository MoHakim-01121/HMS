"""Expense domain — beban operasional cabang (Master Architecture v2.0 §29–31, §63, §77).

Expense = biaya (accrual). ExpensePayment = pergerakan kas. Keduanya terpisah:
sebuah Expense bisa POSTED tapi belum dibayar (utang / Accounts Payable).

Konvensi: semua nominal IntegerField dalam satuan utuh mata uangnya (riyal,
rupiah, dolar). amount_sar via convert_to_sar (Decimal, setengah ke atas).
Expense BUKAN HQ remittance dan BUKAN obligation pusat.
"""
from django.db import models

from .currency import CURRENCY_CODES



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
    """Biaya cabang (accrual): Dr beban per baris / Cr Utang Usaha.

    Total dan status bayar tidak disimpan: total = Σ baris, status bayar dari
    Σ pembayaran. Yang disimpan hanya siklus hidup dokumen (draft / posted /
    voided)."""

    STATUS_DRAFT          = 'draft'
    STATUS_POSTED         = 'posted'
    STATUS_VOIDED         = 'voided'
    # Keadaan bayar (diturunkan), untuk layar dan filter.
    STATUS_PARTIALLY_PAID = 'partially_paid'
    STATUS_PAID           = 'paid'
    STATUS_CHOICES = [
        (STATUS_DRAFT,  'Draft'),
        (STATUS_POSTED, 'Posted'),
        (STATUS_VOIDED, 'Voided'),
    ]
    DISPLAY_CHOICES = [
        (STATUS_DRAFT,          'Draft'),
        (STATUS_POSTED,         'Posted'),
        (STATUS_PARTIALLY_PAID, 'Partially Paid'),
        (STATUS_PAID,           'Paid'),
        (STATUS_VOIDED,         'Voided'),
    ]

    expense_number   = models.CharField(max_length=50, unique=True, db_index=True)
    branch           = models.ForeignKey('Branch', on_delete=models.PROTECT, related_name='expenses')
    expense_date     = models.DateField(db_index=True)
    vendor           = models.ForeignKey('Vendor', null=True, blank=True, on_delete=models.PROTECT, related_name='expenses')
    description      = models.CharField(max_length=255, blank=True)
    currency         = models.CharField(max_length=3, default='SAR')

    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
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
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=['draft', 'posted', 'voided']), name='expense_status_valid',
            ),
            models.CheckConstraint(condition=models.Q(currency__in=CURRENCY_CODES), name='expense_currency_valid'),
        ]

    def __str__(self):
        return f"{self.expense_number} | {self.vendor or self.description}"

    @staticmethod
    def generate_number():
        from ..numbering import generate_sequential_number
        return generate_sequential_number(Expense, 'EXP', field='expense_number', padding=4)

    @property
    def period(self):
        from .period import FinancialPeriod
        return FinancialPeriod.objects.filter(
            date_from__lte=self.expense_date, date_to__gte=self.expense_date,
        ).first()

    @property
    def total_amount(self):
        return sum(int(l.amount) for l in self.lines.all())

    @property
    def total_amount_sar(self):
        return sum(int(l.amount_sar) for l in self.lines.all())

    @property
    def paid_sar(self):
        prefetched = getattr(self, '_prefetched_objects_cache', {}).get('payments')
        if prefetched is not None:
            return sum(p.amount_sar for p in prefetched if p.status == ExpensePayment.STATUS_PAID)
        return self.payments.filter(
            status=ExpensePayment.STATUS_PAID,
        ).aggregate(t=models.Sum('amount_sar'))['t'] or 0

    @property
    def outstanding_sar(self):
        return max(0, self.total_amount_sar - self.paid_sar)

    @property
    def display_status(self):
        """Siklus hidup, dan untuk beban yang sudah diposting keadaan bayarnya."""
        if self.status != self.STATUS_POSTED:
            return self.status
        total, paid = self.total_amount_sar, self.paid_sar
        if total > 0 and paid >= total:
            return self.STATUS_PAID
        return self.STATUS_PARTIALLY_PAID if paid > 0 else self.STATUS_POSTED

    @property
    def display_status_label(self):
        return dict(self.DISPLAY_CHOICES)[self.display_status]


class ExpenseLine(models.Model):
    expense       = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='lines')
    category      = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name='+')
    # Override akun buku besar (default: category.ledger_account).
    ledger_account = models.ForeignKey('LedgerAccount', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    # Biaya vendor untuk satu baris Services yang dijual cabang ini (B13):
    # jumlah pax-nya adalah jumlah baris Services itu, jadi tidak disimpan lagi.
    service_line  = models.ForeignKey(
        'InvoiceLine', null=True, blank=True, on_delete=models.PROTECT, related_name='vendor_costs',
    )
    description   = models.CharField(max_length=255, blank=True)
    amount        = models.PositiveIntegerField()
    amount_sar    = models.PositiveIntegerField()     # nilai SAR yang dibukukan

    class Meta:
        verbose_name = 'Expense Line'
        verbose_name_plural = 'Expense Lines'
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='expense_line_amount_positive'),
        ]

    def __str__(self):
        return f"{self.category_id}: {self.amount_sar:,}"

    @property
    def account_code(self):
        return self.ledger_account_id or self.category.ledger_account_id

    @property
    def unit_cost(self):
        """Harga beli per pax untuk biaya vendor Services."""
        if self.service_line_id and self.service_line.quantity:
            return self.amount / self.service_line.quantity
        return None


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
    amount       = models.PositiveIntegerField()        # mata uang rekening pembayar
    amount_sar   = models.PositiveIntegerField()
    # Akun uang (rekening bank atau kas) yang membayar; mata uangnya = mata uang `amount`.
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
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='expense_payment_amount_positive'),
        ]

    def __str__(self):
        return f"{self.expense.expense_number} pay {self.amount_sar:,}"

    @property
    def currency(self):
        return self.source_account.currency
