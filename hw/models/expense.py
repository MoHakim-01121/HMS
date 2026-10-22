"""Expense domain: beban operasional cabang.

Keputusan 2026-10-11: beban selalu dalam rupiah, dicatat oleh Finance, lalu
disetujui (Finance, boleh pencatatnya sendiri; Manager; atau Admin), lalu
dibayar dari rekening IDR cabangnya. Masuk pembukuan saat dibayar, satu
jurnal Dr beban per baris / Cr rekening pembayar, dinilai dengan kurs tercatat
rekening itu (lihat hw/finance/expense_service.py). Sebelum dibayar tidak ada
jurnal, jadi pengajuan yang ditolak tidak meninggalkan apa pun di buku besar.

Nominal dalam rupiah utuh; amount_sar diisi saat dibayar. Expense BUKAN HQ
remittance. Pusat menggantinya lewat ExpenseClaim (keputusan user 2026-10-19).
"""
from django.db import models

from .currency import CURRENCY_CODES
from .uploads import RandomFileName


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
    """Satu beban cabang: diajukan, disetujui, dibayar (atau ditolak), dan
    bila perlu dibatalkan setelah dibayar. Total = jumlah baris."""

    STATUS_SUBMITTED = 'submitted'
    STATUS_APPROVED  = 'approved'
    STATUS_PAID      = 'paid'
    STATUS_REJECTED  = 'rejected'
    STATUS_VOIDED    = 'voided'
    STATUS_CHOICES = [
        (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_APPROVED,  'Approved'),
        (STATUS_PAID,      'Paid'),
        (STATUS_REJECTED,  'Rejected'),
        (STATUS_VOIDED,    'Voided'),
    ]
    # Menunggu keputusan atau pembayaran.
    OPEN_STATUSES = (STATUS_SUBMITTED, STATUS_APPROVED)
    CURRENCY = 'IDR'

    expense_number   = models.CharField(max_length=50, unique=True, db_index=True)
    branch           = models.ForeignKey('Branch', on_delete=models.PROTECT, related_name='expenses')
    # Tanggal biaya terjadi (bukan tanggal dibayar; itu ada di ExpensePayment).
    expense_date     = models.DateField(db_index=True)
    vendor           = models.ForeignKey('Vendor', null=True, blank=True, on_delete=models.PROTECT, related_name='expenses')
    description      = models.CharField(max_length=255, blank=True)
    currency         = models.CharField(max_length=3, default=CURRENCY)

    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUBMITTED, db_index=True)
    note       = models.TextField(blank=True)
    proof      = models.FileField(upload_to=RandomFileName('expenses/proof/'), null=True, blank=True)
    # Siapa yang mengeluarkan uangnya, dan dari mana: uang muka staf (dibayar
    # otomatis saat disetujui, uangnya sudah keluar) atau kosong = rekening
    # kantor, dibayar Finance sesudah disetujui.
    spent_by   = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.PROTECT, related_name='expenses_spent')
    paid_with  = models.ForeignKey('MoneyAccount', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    created_by = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Siapa yang menyetujui atau menolak, kapan, dan alasannya (tolak/batal).
    decided_by    = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    decided_at    = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)

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
                condition=models.Q(status__in=['submitted', 'approved', 'paid', 'rejected', 'voided']),
                name='expense_status_valid',
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
        """Total rupiah."""
        return sum(int(l.amount) for l in self.lines.all())

    @property
    def total_amount_sar(self):
        """Nilai SAR yang dibukukan; 0 sampai dibayar."""
        return sum(int(l.amount_sar) for l in self.lines.all())

    @property
    def payment(self):
        """Pembayaran yang berlaku, atau None."""
        prefetched = getattr(self, '_prefetched_objects_cache', {}).get('payments')
        rows = prefetched if prefetched is not None else self.payments.all()
        return next((p for p in rows if p.status == ExpensePayment.STATUS_PAID), None)

    # Nama lama yang dibaca layar dan export: status kini langsung siklus hidupnya.
    @property
    def display_status(self):
        return self.status

    @property
    def display_status_label(self):
        return self.get_status_display()


class ExpenseLine(models.Model):
    expense       = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='lines')
    category      = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name='+')
    # Override akun buku besar (default: category.ledger_account).
    ledger_account = models.ForeignKey('LedgerAccount', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    description   = models.CharField(max_length=255, blank=True)
    # Kosong bila baris ini punya struk (ExpenseReceipt); diisi bila tidak ada
    # struk sama sekali, untuk diperiksa penyetuju.
    no_receipt_reason = models.CharField(max_length=255, blank=True)
    amount        = models.PositiveIntegerField()     # rupiah
    amount_sar    = models.PositiveIntegerField(default=0)  # nilai SAR yang dibukukan, diisi saat dibayar

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


class ExpenseReceipt(models.Model):
    """Satu file struk untuk satu baris beban (foto atau PDF)."""
    line = models.ForeignKey(ExpenseLine, on_delete=models.CASCADE, related_name='receipts')
    file = models.FileField(upload_to=RandomFileName('expenses/receipts/'))
    name = models.CharField(max_length=255, blank=True)   # nama asli, untuk ditampilkan
    size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'Expense Receipt'
        verbose_name_plural = 'Expense Receipts'

    def __str__(self):
        return self.name or self.file.name


class ExpensePayment(models.Model):
    STATUS_PAID    = 'paid'
    STATUS_VOID    = 'void'
    STATUS_CHOICES = [
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


class ExpenseClaim(models.Model):
    """Klaim penggantian: cabang meminta Pusat mengganti beban yang sudah ia
    bayar dalam satu rentang tanggal (keputusan user 2026-10-19). Pusat
    mengganti dengan rupiah persis sebesar klaim; saat itu klaim lunas dan
    rupiahnya masuk rekening IDR cabang, lawan Rekening Antar Kantor – Pusat."""
    STATUS_DRAFT     = 'draft'
    STATUS_SUBMITTED = 'submitted'
    STATUS_PAID      = 'paid'
    STATUS_REJECTED  = 'rejected'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_DRAFT,     'Draft'),
        (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_PAID,      'Paid'),
        (STATUS_REJECTED,  'Rejected'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]
    ACTIVE_STATUSES = (STATUS_DRAFT, STATUS_SUBMITTED, STATUS_PAID)

    claim_number = models.CharField(max_length=50, unique=True, db_index=True)
    branch       = models.ForeignKey('Branch', on_delete=models.PROTECT, related_name='expense_claims')
    date_from    = models.DateField()
    date_to      = models.DateField()
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    total_amount = models.BigIntegerField(default=0)   # rupiah
    total_sar    = models.BigIntegerField(default=0)   # nilai SAR beban saat dibayar
    note          = models.TextField(blank=True)
    decision_note = models.TextField(blank=True)

    paid_date = models.DateField(null=True, blank=True)
    paid_to   = models.ForeignKey('MoneyAccount', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    reference = models.CharField(max_length=200, blank=True)
    proof     = models.FileField(upload_to=RandomFileName('expenses/claims/'), null=True, blank=True)

    created_by   = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='+')
    created_at   = models.DateTimeField(auto_now_add=True, db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_by   = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    decided_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Expense Claim'
        verbose_name_plural = 'Expense Claims'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=['draft', 'submitted', 'paid', 'rejected', 'cancelled']),
                name='expense_claim_status_valid',
            ),
            models.CheckConstraint(condition=models.Q(date_from__lte=models.F('date_to')),
                                   name='expense_claim_range_ordered'),
        ]

    def __str__(self):
        return f"{self.claim_number} | {self.branch_id}"

    @staticmethod
    def generate_number():
        from ..numbering import generate_sequential_number
        return generate_sequential_number(ExpenseClaim, 'CLM', field='claim_number', padding=4)


class ExpenseClaimItem(models.Model):
    """Satu beban di dalam klaim. `amount`/`amount_sar` disalin saat diklaim.
    Item klaim yang ditolak atau dibatalkan tidak aktif lagi, sehingga bebannya
    bisa diklaim ulang; satu beban punya paling banyak satu item aktif."""
    claim      = models.ForeignKey(ExpenseClaim, on_delete=models.CASCADE, related_name='items')
    expense    = models.ForeignKey(Expense, on_delete=models.PROTECT, related_name='claim_items')
    amount     = models.BigIntegerField()
    amount_sar = models.BigIntegerField()
    is_active  = models.BooleanField(default=True)

    class Meta:
        ordering = ['expense__expense_date', 'expense_id']
        constraints = [
            models.UniqueConstraint(fields=['expense'], condition=models.Q(is_active=True),
                                    name='expense_one_active_claim'),
        ]

    def __str__(self):
        return f"{self.claim.claim_number} · {self.expense.expense_number}"
