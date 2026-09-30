"""Money accounts — rekening bank dan kas cabang dalam SATU tabel (skema target §3.1).

Setiap akun punya satu mata uang. Rekening multi-mata-uang di satu bank =
beberapa baris. `kind` membedakan rekening bank dari kas fisik; sebelumnya
keduanya tabel terpisah, sehingga setiap tabel yang menunjuk "sebuah akun"
perlu sepasang kolom (bank_account, cash_account) dengan CHECK "tepat satu
terisi". Sekarang cukup satu foreign key ke MoneyAccount.

`BankAccount` dan `CashAccount` adalah proxy: baris yang sama, disaring per
`kind` — dipakai di tempat yang memang hanya berurusan dengan salah satunya
(halaman kelola rekening bank, kas default cabang).

Saldo BUKAN kolom di sini: `book_balance` diturunkan dari JournalLine pada
`ledger_account`; buku kas per akun ada di BankTransaction.
"""
from django.db import models

from .currency import CURRENCY_CODES  # noqa: E402,F401  (nama lama tetap diekspor dari sini)


class MoneyAccount(models.Model):
    KIND_BANK = 'bank'
    KIND_CASH = 'cash'
    KIND_CHOICES = [(KIND_BANK, 'Bank'), (KIND_CASH, 'Cash')]

    kind = models.CharField(max_length=4, choices=KIND_CHOICES, default=KIND_BANK)
    branch = models.ForeignKey('Branch', on_delete=models.PROTECT, related_name='money_accounts')
    name = models.CharField(max_length=120)
    # Mata uang akun. Di PostgreSQL kolom ini ber-FOREIGN KEY ke hw_currency
    # (lihat migrasi); di Django tetap teks supaya `acc.currency == 'IDR'`.
    currency = models.CharField(max_length=3, default='SAR')
    # Akun buku besar yang mewakili rekening ini. Beberapa rekening operasional
    # boleh memetakan ke satu LedgerAccount (mis. semua kas SBY → 1000-KAS-SBY).
    ledger_account = models.ForeignKey('LedgerAccount', on_delete=models.PROTECT, related_name='+')
    is_active = models.BooleanField(default=True, db_index=True)
    note = models.TextField(blank=True)
    # Saldo nyata (dalam `currency`) pada `opening_date`, sebelum pergerakan
    # pertama yang dicatat sistem ini — dicerminkan sebagai satu baris
    # "opening balance" di buku kas.
    opening_balance = models.BigIntegerField(default=0)
    opening_date = models.DateField(null=True, blank=True)

    # Hanya untuk rekening bank.
    bank_name = models.CharField(max_length=120, blank=True)
    account_name = models.CharField(max_length=120, blank=True)       # nama pemilik rekening
    account_identifier = models.CharField(max_length=64, blank=True)  # nomor rekening / IBAN
    # Tampil sebagai rekening tujuan ("Pay to") di detail invoice cabang ini.
    show_on_invoice = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['kind', 'bank_name', 'name']
        verbose_name = 'Money Account'
        verbose_name_plural = 'Money Accounts'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=['bank', 'cash']), name='moneyaccount_kind_valid',
            ),
            models.CheckConstraint(
                condition=models.Q(currency__in=CURRENCY_CODES), name='moneyaccount_currency_valid',
            ),
            models.CheckConstraint(
                condition=models.Q(kind='cash') | ~models.Q(bank_name=''),
                name='moneyaccount_bank_needs_bank_name',
            ),
            # Satu nomor rekening satu baris. Hanya berlaku bila nomornya diisi —
            # versi lama ikut menganggap nomor kosong sebagai "sama".
            models.UniqueConstraint(
                fields=['bank_name', 'account_identifier', 'currency'],
                condition=models.Q(kind='bank') & ~models.Q(account_identifier=''),
                name='uniq_moneyaccount_bank_number_currency',
            ),
            models.UniqueConstraint(
                fields=['branch', 'name', 'currency'],
                condition=models.Q(kind='cash'),
                name='uniq_moneyaccount_cash_branch_name_currency',
            ),
        ]

    def __str__(self):
        if self.kind == self.KIND_BANK:
            return f"{self.bank_name} {self.name} ({self.currency})"
        return f"{self.name} ({self.currency})"

    @property
    def is_bank(self):
        return self.kind == self.KIND_BANK

    @property
    def token(self):
        """Nilai picker di form: "bank:<id>" / "cash:<id>"."""
        return f'{self.kind}:{self.pk}'

    @property
    def book_balance(self):
        """Saldo buku = Σ(debit−credit) baris jurnal pada ledger_account.
        Tanda mengikuti normal balance akun aset (debit +)."""
        from ..finance import queries
        return queries.account_balance(self.ledger_account_id)


class _KindManager(models.Manager):
    def __init__(self, kind):
        super().__init__()
        self._kind = kind

    def get_queryset(self):
        return super().get_queryset().filter(kind=self._kind)


class BankAccount(MoneyAccount):
    objects = _KindManager(MoneyAccount.KIND_BANK)

    class Meta:
        proxy = True
        ordering = ['bank_name', 'name']
        verbose_name = 'Bank Account'
        verbose_name_plural = 'Bank Accounts'

    def save(self, *args, **kwargs):
        self.kind = MoneyAccount.KIND_BANK
        super().save(*args, **kwargs)


class CashAccount(MoneyAccount):
    """Kas fisik / brankas cabang."""

    objects = _KindManager(MoneyAccount.KIND_CASH)

    class Meta:
        proxy = True
        ordering = ['branch', 'name']
        verbose_name = 'Cash Account'
        verbose_name_plural = 'Cash Accounts'

    def save(self, *args, **kwargs):
        self.kind = MoneyAccount.KIND_CASH
        super().save(*args, **kwargs)
