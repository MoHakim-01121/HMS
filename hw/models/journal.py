from django.db import models

from .choices import Company


class AccountType(models.TextChoices):
    """Tipe akun untuk Chart of Accounts."""
    ASSET     = 'asset',     'Asset'
    LIABILITY = 'liability', 'Liability'
    INCOME    = 'income',    'Income'
    EXPENSE   = 'expense',   'Expense'
    EQUITY    = 'equity',    'Equity'


class Account(models.TextChoices):
    """Chart of Accounts —irtual accounts untuk tracking arus kas.

    SETIAP transaksi harus menyentuh minimal 2 account dengan
    jumlah yang balance (debit + credit = 0).
    """
    # Kas / Asset
    CASH_SBY   = 'cash_sby',   'Kas Surabaya'
    CASH_JKT   = 'cash_jkt',   'Kas Jakarta'
    CASH_PUSAT = 'cash_pusat', 'Kas Pusat (HQ)'
    FX         = 'fx',         'Selisih Kurs'

    # Piutang / Receivable
    RECEIVABLE = 'receivable', 'Piutang Client'

    # Pendapatan
    INCOME_HOTEL   = 'income_hotel',   'Pendapatan Hotel'
    INCOME_SERVICE = 'income_service', 'Pendapatan Visa/Services'
    INCOME_PENALTY = 'income_penalty', 'Pendapatan Penalty'

    # Biaya
    EXPENSE_PENALTY = 'expense_penalty', 'Beban Penalty'

    # Equity
    EQUITY = 'equity', 'Modal'


ACCOUNT_TYPE_MAP = {
    Account.CASH_SBY:     AccountType.ASSET,
    Account.CASH_JKT:     AccountType.ASSET,
    Account.CASH_PUSAT:   AccountType.ASSET,
    Account.FX:           AccountType.ASSET,
    Account.RECEIVABLE:   AccountType.ASSET,
    Account.INCOME_HOTEL: AccountType.INCOME,
    Account.INCOME_SERVICE: AccountType.INCOME,
    Account.INCOME_PENALTY: AccountType.INCOME,
    Account.EXPENSE_PENALTY: AccountType.EXPENSE,
    Account.EQUITY:       AccountType.EQUITY,
}


class JournalEntry(models.Model):
    """Immutable journal entry. Setiap entry harus balance: SUM(lines) = 0.

    Tidak ada UPDATE atau DELETE. Koreksi dilakukan via reversal entry.
    """

    TYPE_CHARGE     = 'charge'
    TYPE_PAYMENT    = 'payment'
    TYPE_ALLOCATE   = 'allocate'
    TYPE_TRANSFER   = 'transfer'
    TYPE_REFUND     = 'refund'
    TYPE_PENALTY    = 'penalty'
    TYPE_REVERSAL   = 'reversal'
    TYPE_ADJUSTMENT = 'adjustment'
    TYPE_CHOICES = [
        (TYPE_CHARGE,     'Charge'),
        (TYPE_PAYMENT,    'Payment'),
        (TYPE_ALLOCATE,   'Allocation'),
        (TYPE_TRANSFER,   'Transfer'),
        (TYPE_REFUND,     'Refund'),
        (TYPE_PENALTY,    'Penalty'),
        (TYPE_REVERSAL,   'Reversal'),
        (TYPE_ADJUSTMENT, 'Adjustment'),
    ]

    entry_number   = models.CharField(max_length=50, unique=True, db_index=True)
    entry_type     = models.CharField(max_length=20, choices=TYPE_CHOICES)
    description    = models.CharField(max_length=255)
    entry_date     = models.DateField(db_index=True)

    # Referensi ke sumber data (polymorphic)
    reference_type = models.CharField(max_length=50, blank=True)
    reference_id   = models.PositiveIntegerField(null=True, blank=True)

    # Reversal tracking
    is_reversal    = models.BooleanField(default=False)
    reversed_by    = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='reversed_entries')
    reverses       = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='reversals_of')

    # Scope
    period   = models.ForeignKey('FinancialPeriod', on_delete=models.PROTECT, related_name='journal_entries')
    company  = models.CharField(max_length=20, choices=Company.choices, default=Company.KONOZ)

    # Audit
    created_by = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering            = ['entry_date', 'created_at']
        verbose_name        = 'Journal Entry'
        verbose_name_plural = 'Journal Entries'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(reference_type='') | models.Q(reference_id__isnull=False),
                name='journal_entry_ref_requires_id',
            ),
        ]
        indexes = [
            models.Index(fields=['company', 'entry_type'], name='journal_company_type_idx'),
            models.Index(fields=['entry_type', 'entry_date'], name='journal_type_date_idx'),
        ]

    def __str__(self):
        return f"{self.entry_number} | {self.get_entry_type_display()} | {self.description}"

    @property
    def total_debit(self):
        return sum(l.amount_sar for l in self.lines.all() if l.amount_sar > 0)

    @property
    def total_credit(self):
        return abs(sum(l.amount_sar for l in self.lines.all() if l.amount_sar < 0))

    @property
    def is_balanced(self):
        return self.lines.aggregate(total=models.Sum('amount_sar'))['total'] == 0

    @staticmethod
    def generate_number():
        from django.db import transaction
        with transaction.atomic():
            nums = []
            for num_str in JournalEntry.objects.select_for_update().filter(
                entry_number__startswith='JE-',
            ).values_list('entry_number', flat=True):
                parts = num_str.split('-')
                if len(parts) == 2:
                    try:
                        nums.append(int(parts[1]))
                    except ValueError:
                        pass
            return f"JE-{(max(nums) + 1 if nums else 1):06d}"


class JournalLine(models.Model):
    """Single leg of a journal entry.

    Positive amount = debit (money masuk / aset naik / pendapatan)
    Negative amount = credit (money keluar / utang naik / beban naik)

    Invariant: SUM(lines untuk satu journal_entry) = 0
    """

    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account       = models.CharField(max_length=50, choices=Account.choices)

    # Dimensi — salah satu atau lebih bisa null
    client        = models.ForeignKey('Client', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    invoice       = models.ForeignKey('Invoice', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    reservation   = models.ForeignKey('Reservation', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    service_item  = models.ForeignKey('ServiceItem', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    penalty       = models.ForeignKey('CancellationPenalty', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')

    amount_sar    = models.IntegerField()
    note          = models.TextField(blank=True)

    class Meta:
        ordering            = ['id']
        verbose_name        = 'Journal Line'
        verbose_name_plural = 'Journal Lines'
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(amount_sar=0),
                name='journal_line_amount_nonzero',
            ),
        ]
        indexes = [
            models.Index(fields=['account', 'client'], name='journal_acct_client_idx'),
            models.Index(fields=['account', 'invoice'], name='journal_acct_invoice_idx'),
            models.Index(fields=['client', 'account'], name='journal_client_acct_idx'),
        ]

    def __str__(self):
        sign = '+' if self.amount_sar > 0 else ''
        return f"{self.get_account_display()}: {sign}{self.amount_sar:,}"

    @property
    def is_debit(self):
        return self.amount_sar > 0

    @property
    def is_credit(self):
        return self.amount_sar < 0
