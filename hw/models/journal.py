from django.db import models

from .currency import CURRENCY_CODES
from .uploads import RandomFileName


class ImmutableLedgerError(Exception):
    """Percobaan UPDATE/DELETE pada baris ledger append-only."""


class AppendOnlyModel(models.Model):
    """Baris hanya boleh di-INSERT. Koreksi lewat reversal entry.

    Ditegakkan di app layer di sini + trigger Postgres (migrasi). Queryset
    .delete()/.update() massal tetap bisa lolos di app layer — trigger PG
    yang menutupnya di produksi; migrasi data pakai historical model tanpa
    override ini (mis. purge di 0067)."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk is not None and not self._state.adding:
            raise ImmutableLedgerError(
                f"{type(self).__name__} bersifat append-only — tidak bisa di-UPDATE "
                f"(pk={self.pk}). Buat reversal entry untuk koreksi."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableLedgerError(
            f"{type(self).__name__} bersifat append-only — tidak bisa di-DELETE "
            f"(pk={self.pk}). Buat reversal entry untuk koreksi."
        )


class AccountType(models.TextChoices):
    """Tipe akun untuk Chart of Accounts."""
    ASSET     = 'asset',     'Asset'
    LIABILITY = 'liability', 'Liability'
    INCOME    = 'income',    'Income'
    EXPENSE   = 'expense',   'Expense'
    EQUITY    = 'equity',    'Equity'


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


SOURCE_COLUMNS = (
    'source_invoice', 'source_credit_note', 'source_payment', 'source_remittance',
    'source_remittance_settlement', 'source_expense', 'source_expense_payment',
    'source_client_refund', 'source_client_transfer', 'source_currency_exchange', 'source_expense_claim',
    'reverses',
)


def _at_most_one_source():
    condition = models.Q(**{f'{f}__isnull': True for f in SOURCE_COLUMNS})
    for f in SOURCE_COLUMNS:
        condition |= models.Q(**{f'{f}__isnull': False}) & models.Q(
            **{f'{o}__isnull': True for o in SOURCE_COLUMNS if o != f}
        )
    return condition


class JournalEntryQuerySet(models.QuerySet):
    def for_source(self, source_type, source_id):
        """Entry yang bersumber dari dokumen ini. `source_id` boleh daftar id."""
        name, entry_type = JournalEntry.SOURCE_ALIASES.get(source_type, (source_type, None))
        field = JournalEntry.SOURCE_FIELDS[name]
        if isinstance(source_id, (list, tuple, set, models.QuerySet)):
            qs = self.filter(**{f'{field}_id__in': source_id})
        else:
            qs = self.filter(**{f'{field}_id': source_id})
        if entry_type is not None:
            return qs.filter(entry_type=entry_type)
        aliased = [t for base, t in JournalEntry.SOURCE_ALIASES.values() if base == name]
        return qs.exclude(entry_type__in=aliased) if aliased else qs

    def live(self):
        """Bukan pembalik dan belum dibalik."""
        return self.filter(reverses__isnull=True, reversed_by__isnull=True)


class JournalEntry(AppendOnlyModel):
    """Immutable journal entry. Setiap entry harus balance: SUM(lines) = 0.

    Tidak ada UPDATE atau DELETE. Koreksi dilakukan via reversal entry.
    """

    TYPE_CHARGE     = 'charge'
    TYPE_PAYMENT    = 'payment'
    TYPE_ALLOCATE   = 'allocate'
    TYPE_TRANSFER   = 'transfer'
    TYPE_REFUND     = 'refund'
    TYPE_PENALTY    = 'penalty'
    TYPE_REMITTANCE = 'remittance'
    TYPE_EXPENSE    = 'expense'
    TYPE_REVERSAL   = 'reversal'
    TYPE_ADJUSTMENT = 'adjustment'
    TYPE_CREDIT_NOTE = 'credit_note'
    TYPE_REMITTANCE_DIFF = 'remittance_diff'
    TYPE_EXCHANGE   = 'exchange'
    TYPE_REIMBURSEMENT = 'reimbursement'
    TYPE_CHOICES = [
        (TYPE_CHARGE,     'Charge'),
        (TYPE_PAYMENT,    'Payment'),
        (TYPE_ALLOCATE,   'Allocation'),
        (TYPE_TRANSFER,   'Transfer'),
        (TYPE_REFUND,     'Refund'),
        (TYPE_PENALTY,    'Penalty'),
        (TYPE_REMITTANCE, 'Remittance'),
        (TYPE_EXPENSE,    'Expense'),
        (TYPE_REVERSAL,   'Reversal'),
        (TYPE_ADJUSTMENT, 'Adjustment'),
        (TYPE_CREDIT_NOTE, 'Credit note'),
        (TYPE_REMITTANCE_DIFF, 'Remittance difference'),
        (TYPE_EXCHANGE,   'Currency exchange'),
        (TYPE_REIMBURSEMENT, 'Reimbursement'),
    ]

    # Dokumen sumber -> kolom FK-nya. Satu entry punya paling banyak satu
    # sumber; entry pembalik tidak punya sumber (ia menunjuk `reverses`).
    SOURCE_FIELDS = {
        'Invoice':              'source_invoice',
        'CreditNote':           'source_credit_note',
        'PaymentRecord':        'source_payment',
        'Remittance':           'source_remittance',
        'RemittanceSettlement': 'source_remittance_settlement',
        'Expense':              'source_expense',
        'ExpensePayment':       'source_expense_payment',
        'ClientRefund':         'source_client_refund',
        'ClientTransfer':       'source_client_transfer',
        'CurrencyExchange':     'source_currency_exchange',
        'ExpenseClaim':         'source_expense_claim',
    }
    # Jenis entry yang punya nama sumber sendiri walau dokumennya sama:
    # selisih penerimaan transfer (sumber Remittance) dan alokasi penerimaan
    # Pusat ke reservasi (sumber RemittanceSettlement).
    SOURCE_ALIASES = {
        'RemittanceDiff':       ('Remittance', TYPE_REMITTANCE_DIFF),
        'RemittanceAllocation': ('RemittanceSettlement', TYPE_ALLOCATE),
    }

    entry_number   = models.CharField(max_length=50, unique=True, db_index=True)
    entry_type     = models.CharField(max_length=20, choices=TYPE_CHOICES)
    description    = models.CharField(max_length=255)
    entry_date     = models.DateField(db_index=True)

    # Nomor urut monoton tanpa gap (diisi post_entry()).
    seq            = models.BigIntegerField(null=True, blank=True, db_index=True)

    idempotency_key = models.CharField(max_length=120, unique=True, null=True, blank=True)

    # Dokumen sumber (paling banyak satu terisi), lihat SOURCE_FIELDS.
    source_invoice               = models.ForeignKey('Invoice', null=True, blank=True, on_delete=models.PROTECT, related_name='journal_entries')
    source_credit_note           = models.ForeignKey('CreditNote', null=True, blank=True, on_delete=models.PROTECT, related_name='journal_entries')
    source_payment               = models.ForeignKey('PaymentRecord', null=True, blank=True, on_delete=models.PROTECT, related_name='journal_entries')
    source_remittance            = models.ForeignKey('Remittance', null=True, blank=True, on_delete=models.PROTECT, related_name='journal_entries')
    source_remittance_settlement = models.ForeignKey('RemittanceSettlement', null=True, blank=True, on_delete=models.PROTECT, related_name='journal_entries')
    source_expense               = models.ForeignKey('Expense', null=True, blank=True, on_delete=models.PROTECT, related_name='journal_entries')
    source_expense_payment       = models.ForeignKey('ExpensePayment', null=True, blank=True, on_delete=models.PROTECT, related_name='journal_entries')
    source_client_refund         = models.OneToOneField('ClientRefund', null=True, blank=True, on_delete=models.PROTECT, related_name='journal_entry')
    source_client_transfer       = models.OneToOneField('ClientTransfer', null=True, blank=True, on_delete=models.PROTECT, related_name='journal_entry')
    # Penukaran valas memindahkan nilai antar rekening mata uang cabang.
    source_currency_exchange     = models.OneToOneField('CurrencyExchange', null=True, blank=True, on_delete=models.PROTECT, related_name='journal_entry')
    # Penggantian beban cabang oleh Pusat (lunas; pembaliknya saat dibatalkan).
    source_expense_claim         = models.ForeignKey('ExpenseClaim', null=True, blank=True, on_delete=models.PROTECT, related_name='journal_entries')

    # Entry pembalik menunjuk entry yang dibaliknya; dibalik paling banyak sekali.
    reverses       = models.OneToOneField('self', null=True, blank=True, on_delete=models.PROTECT, related_name='reversed_by')

    # Tamper-evidence: rantai hash antar entry (diisi post_entry()).
    prev_hash      = models.CharField(max_length=64, blank=True)
    entry_hash     = models.CharField(max_length=64, blank=True, db_index=True)

    # Scope
    period   = models.ForeignKey('FinancialPeriod', on_delete=models.PROTECT, related_name='journal_entries')

    # Audit
    created_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Lampiran dokumen sumber (mis. bukti transfer refund). Metadata saja --
    # tidak ikut entry_hash, jadi append-only tetap berlaku.
    proof = models.FileField(upload_to=RandomFileName('ledger/proof/'), null=True, blank=True)

    objects = JournalEntryQuerySet.as_manager()

    class Meta:
        ordering            = ['entry_date', 'created_at']
        verbose_name        = 'Journal Entry'
        verbose_name_plural = 'Journal Entries'
        constraints = [
            models.CheckConstraint(condition=_at_most_one_source(), name='journal_entry_one_source'),
            models.CheckConstraint(
                condition=models.Q(entry_type__in=[
                    'charge', 'payment', 'allocate', 'transfer', 'refund', 'penalty', 'remittance',
                    'expense', 'reversal', 'adjustment', 'credit_note', 'remittance_diff', 'exchange',
                    'reimbursement',
                ]),
                name='journal_entry_type_valid',
            ),
            models.UniqueConstraint(
                fields=['seq'], name='journal_entry_seq_uniq',
                condition=models.Q(seq__isnull=False),
            ),
        ]
        indexes = [
            models.Index(fields=['entry_type', 'entry_date'], name='journal_type_date_idx'),
        ]

    def __str__(self):
        return f"{self.entry_number} | {self.get_entry_type_display()} | {self.description}"

    @property
    def is_reversal(self):
        return self.reverses_id is not None

    @property
    def source_type(self):
        """Nama sumber ('Invoice', 'RemittanceDiff', ...), 'JournalEntry' untuk
        entry pembalik, '' untuk jurnal manual."""
        if self.reverses_id is not None:
            return 'JournalEntry'
        for name, field in self.SOURCE_FIELDS.items():
            if getattr(self, f'{field}_id') is not None:
                for alias, (base, entry_type) in self.SOURCE_ALIASES.items():
                    if base == name and self.entry_type == entry_type:
                        return alias
                return name
        return ''

    @property
    def source_id(self):
        if self.reverses_id is not None:
            return self.reverses_id
        for field in self.SOURCE_FIELDS.values():
            value = getattr(self, f'{field}_id')
            if value is not None:
                return value
        return None

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


class JournalLine(AppendOnlyModel):
    """Satu kaki dari journal entry — debit XOR credit, non-negatif.

    Invariant per journal_entry: SUM(debit) == SUM(credit), dalam SAR.
    `currency` adalah mata uang transaksi; `amount_txn` nominal aslinya.
    `amount_sar` (signed) tersedia sebagai property untuk kode pembaca lama.
    """

    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name='lines')
    line_no       = models.PositiveSmallIntegerField(default=1)
    account       = models.ForeignKey('LedgerAccount', on_delete=models.PROTECT, related_name='+')

    debit         = models.BigIntegerField(default=0)   # SAR utuh (riyal), >= 0
    credit        = models.BigIntegerField(default=0)   # SAR utuh (riyal), >= 0
    currency      = models.CharField(max_length=3, default='SAR')   # mata uang transaksi

    # Nominal asli dalam `currency` dan kursnya (baris kas/bank non-SAR).
    amount_txn    = models.BigIntegerField(null=True, blank=True)
    fx_rate       = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)

    # Dimensi analitik — snapshot, salah satu atau lebih bisa null
    branch        = models.ForeignKey('Branch', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    client        = models.ForeignKey('Client', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    invoice       = models.ForeignKey('Invoice', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    # Baris invoice yang ditagih / dibayar: baris hotel (reservasi) atau
    # baris Services. Denda dicatat di baris hotel reservasinya, ditandai
    # `penalty` (uang reservasi menutup dendanya lebih dulu).
    invoice_line  = models.ForeignKey('InvoiceLine', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    penalty       = models.ForeignKey('CancellationPenalty', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    remittance    = models.ForeignKey('Remittance', null=True, blank=True, on_delete=models.PROTECT, related_name='+')

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
            models.CheckConstraint(
                condition=models.Q(amount_txn__isnull=True) | models.Q(amount_txn__gt=0),
                name='journal_line_amount_txn_positive',
            ),
            models.CheckConstraint(condition=models.Q(currency__in=CURRENCY_CODES), name='journal_line_currency_valid'),
            models.CheckConstraint(
                condition=models.Q(penalty__isnull=True) | models.Q(invoice_line__isnull=False),
                name='journal_line_penalty_on_line',
            ),
        ]
        indexes = [
            models.Index(fields=['account', 'client'], name='journal_acct_client_idx'),
            models.Index(fields=['branch', 'account'], name='journal_branch_acct_idx'),
            models.Index(fields=['account', 'invoice'], name='journal_acct_invoice_idx'),
            models.Index(fields=['client', 'account'], name='journal_client_acct_idx'),
            models.Index(fields=['invoice_line', 'account'], name='journal_line_acct_idx'),
        ]

    def __str__(self):
        return f"{self.account_id}: {self.debit:,} / {self.credit:,}"

    @property
    def amount_sar(self):
        """Signed: +debit / -credit. Kompat dengan pembaca lama."""
        return self.debit - self.credit
