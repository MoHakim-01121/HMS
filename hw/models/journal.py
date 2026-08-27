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


class LedgerAccount(models.Model):
    """Chart of Accounts sebagai tabel — sumber daftar akun untuk jurnal.

    Di-seed lewat `hw.finance.accounts.seed_chart_of_accounts()`. Akun baru
    (mis. kas per-bank) bisa ditambah tanpa migrasi skema.
    """

    NORMAL_DEBIT = "debit"
    NORMAL_CREDIT = "credit"
    NORMAL_CHOICES = [(NORMAL_DEBIT, "Debit"), (NORMAL_CREDIT, "Credit")]

    code = models.CharField(max_length=20, primary_key=True)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=12, choices=AccountType.choices)
    normal_balance = models.CharField(max_length=6, choices=NORMAL_CHOICES)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children",
    )
    is_postable = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    company = models.CharField(
        max_length=20, choices=Company.choices, null=True, blank=True,
        help_text="Kosong = berlaku untuk semua company",
    )

    class Meta:
        ordering = ["code"]
        verbose_name = "Ledger Account"
        verbose_name_plural = "Chart of Accounts"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(type__in=[c[0] for c in AccountType.choices]),
                name="ledgeraccount_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(normal_balance__in=["debit", "credit"]),
                name="ledgeraccount_normal_balance_valid",
            ),
        ]

    def __str__(self):
        return f"{self.code} | {self.name}"


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

    # Nomor urut monoton tanpa gap per company (diisi post_entry()).
    seq            = models.BigIntegerField(null=True, blank=True, db_index=True)

    # Referensi ke sumber data (polymorphic) + idempotency
    reference_type  = models.CharField(max_length=50, blank=True)
    reference_id    = models.PositiveIntegerField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=120, unique=True, null=True, blank=True)

    # Reversal tracking
    is_reversal    = models.BooleanField(default=False)
    reversed_by    = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='reversed_entries')
    reverses       = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='reversals_of')

    # Tamper-evidence: rantai hash antar entry (diisi post_entry()).
    prev_hash      = models.CharField(max_length=64, blank=True)
    entry_hash     = models.CharField(max_length=64, blank=True, db_index=True)

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
            # seq/source uniqueness ditambahkan di Task 2.2 bersama post_entry().
        ]
        indexes = [
            models.Index(fields=['company', 'entry_type'], name='journal_company_type_idx'),
            models.Index(fields=['entry_type', 'entry_date'], name='journal_type_date_idx'),
        ]

    def __str__(self):
        return f"{self.entry_number} | {self.get_entry_type_display()} | {self.description}"

    @property
    def total_debit(self):
        return sum(l.debit for l in self.lines.all())

    @property
    def total_credit(self):
        return sum(l.credit for l in self.lines.all())

    @property
    def is_balanced(self):
        agg = self.lines.aggregate(d=models.Sum('debit'), c=models.Sum('credit'))
        return (agg['d'] or 0) == (agg['c'] or 0)

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
    """Satu kaki dari journal entry — debit XOR credit, non-negatif.

    Invariant per journal_entry per currency: SUM(debit) == SUM(credit).
    `amount_sar` (signed) tersedia sebagai property untuk kode pembaca lama.
    """

    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name='lines')
    line_no       = models.PositiveSmallIntegerField(default=1)
    account       = models.ForeignKey('LedgerAccount', on_delete=models.PROTECT, related_name='+')

    debit         = models.BigIntegerField(default=0)   # SAR minor units, >= 0
    credit        = models.BigIntegerField(default=0)   # SAR minor units, >= 0
    currency      = models.CharField(max_length=3, default='SAR')

    # Jejak mata uang asal (opsional)
    orig_amount   = models.BigIntegerField(null=True, blank=True)
    orig_currency = models.CharField(max_length=3, blank=True)
    fx_rate       = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)

    # Dimensi analitik — snapshot, salah satu atau lebih bisa null
    client        = models.ForeignKey('Client', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    invoice       = models.ForeignKey('Invoice', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    reservation   = models.ForeignKey('Reservation', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    service_item  = models.ForeignKey('ServiceItem', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    penalty       = models.ForeignKey('CancellationPenalty', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    remittance    = models.ForeignKey('Remittance', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')

    note          = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering            = ['journal_entry_id', 'line_no', 'id']
        verbose_name        = 'Journal Line'
        verbose_name_plural = 'Journal Lines'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(debit__gte=0) & models.Q(credit__gte=0),
                name='journal_line_amounts_non_negative',
            ),
            models.CheckConstraint(
                condition=(models.Q(debit__gt=0) & models.Q(credit=0))
                          | (models.Q(debit=0) & models.Q(credit__gt=0)),
                name='journal_line_exactly_one_side',
            ),
            models.UniqueConstraint(
                fields=['journal_entry', 'line_no'], name='journal_line_no_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['account', 'client'], name='journal_acct_client_idx'),
            models.Index(fields=['account', 'invoice'], name='journal_acct_invoice_idx'),
            models.Index(fields=['client', 'account'], name='journal_client_acct_idx'),
            models.Index(fields=['reservation', 'account'], name='journal_res_acct_idx'),
        ]

    def __str__(self):
        return f"{self.account_id}: {self.debit:,} / {self.credit:,}"

    @property
    def amount_sar(self):
        """Signed: +debit / -credit. Kompat dengan pembaca lama."""
        return self.debit - self.credit

    @property
    def is_debit(self):
        return self.debit > 0

    @property
    def is_credit(self):
        return self.credit > 0
