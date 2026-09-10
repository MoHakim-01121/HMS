"""Bank & Cash accounts — master rekening operasional (Master Architecture v2.0 §18, §25–28).

Setiap rekening punya SATU native currency. Kalau satu bank punya rekening
multi-currency, itu beberapa baris `BankAccount` yang berbeda.

Saldo BUKAN kolom mutable di sini — `book_balance` diturunkan dari JournalLine
pada `ledger_account` (satu sumber angka: general ledger). `BankTransaction`
(cash-movement ledger terpisah + rekonsiliasi statement) menyusul di fase
rekonsiliasi; sampai saat itu book balance = proyeksi jurnal.
"""
from django.db import models


class MoneyAccount(models.Model):
    """Basis bersama BankAccount & CashAccount."""

    branch = models.ForeignKey('Branch', on_delete=models.PROTECT, related_name='+')
    name = models.CharField(max_length=120)
    currency = models.CharField(max_length=3, default='SAR')
    # Akun buku besar yang mewakili rekening ini. Beberapa rekening operasional
    # boleh memetakan ke satu LedgerAccount (mis. semua kas SBY → 1000-KAS-SBY).
    ledger_account = models.ForeignKey('LedgerAccount', on_delete=models.PROTECT, related_name='+')
    is_active = models.BooleanField(default=True, db_index=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    @property
    def book_balance(self):
        """Saldo buku (native currency) = Σ(debit−credit) baris jurnal pada
        ledger_account. Tanda mengikuti normal balance akun aset (debit +)."""
        from ..finance import queries
        return queries.account_balance(self.ledger_account_id)


class BankAccount(MoneyAccount):
    bank_name = models.CharField(max_length=120)
    account_name = models.CharField(max_length=120, blank=True)       # nama pemilik rekening
    account_identifier = models.CharField(max_length=64, blank=True)  # nomor rekening / IBAN

    class Meta:
        ordering = ['bank_name', 'name']
        verbose_name = 'Bank Account'
        verbose_name_plural = 'Bank Accounts'
        constraints = [
            models.UniqueConstraint(
                fields=['bank_name', 'account_identifier', 'currency'],
                name='uniq_bankaccount_bank_number_currency',
            ),
        ]

    def __str__(self):
        return f"{self.bank_name} {self.name} ({self.currency})"


class CashAccount(MoneyAccount):
    """Kas fisik / brankas cabang. (Berbeda dari enum lama
    hw.models.ledger.CashAccount yang deprecated.)"""

    class Meta:
        ordering = ['branch', 'name']
        verbose_name = 'Cash Account'
        verbose_name_plural = 'Cash Accounts'
        constraints = [
            models.UniqueConstraint(
                fields=['branch', 'name', 'currency'],
                name='uniq_cashaccount_branch_name_currency',
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.currency})"
