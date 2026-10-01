"""FASE B — Bank & Cash account masters + book-balance projection."""
from datetime import date

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase

from hw.models import BankAccount, Branch, CashAccount, Client
from hw.finance.accounts import cash_ledger_for
from hw.models.journal import LedgerAccount
from hw.models.period import FinancialPeriod
from hw.finance import posting


class CashAccountSeedTest(TestCase):
    def test_migration_seeded_one_cash_account_per_branch(self):
        self.assertEqual(CashAccount.objects.count(), 3)
        sby = CashAccount.objects.get(branch_id='sby')
        self.assertEqual(sby.currency, 'SAR')
        self.assertEqual(sby.ledger_account_id, '1000-KAS-SBY')


class MoneyAccountConstraintTest(TestCase):
    def test_bank_account_unique_on_bank_number_currency(self):
        la = LedgerAccount.objects.get(code='1000-KAS-SBY')
        sby = Branch.objects.get(code='sby')
        BankAccount.objects.create(
            branch=sby, name='Ops', currency='USD', ledger_account_id=cash_ledger_for('sby', 'USD'),
            bank_name='BCA', account_identifier='123',
        )
        with self.assertRaises(IntegrityError):
            BankAccount.objects.create(
                branch=sby, name='Ops 2', currency='USD', ledger_account_id=cash_ledger_for('sby', 'USD'),
                bank_name='BCA', account_identifier='123',
            )

    def test_same_bank_different_currency_is_allowed(self):
        la = LedgerAccount.objects.get(code='1000-KAS-JKT')
        jkt = Branch.objects.get(code='jkt')
        BankAccount.objects.create(branch=jkt, name='IDR', currency='IDR',
                                   ledger_account_id=cash_ledger_for('sby', 'IDR'), bank_name='BCA', account_identifier='999')
        BankAccount.objects.create(branch=jkt, name='USD', currency='USD',
                                   ledger_account_id=cash_ledger_for('sby', 'USD'), bank_name='BCA', account_identifier='999')
        self.assertEqual(BankAccount.objects.filter(account_identifier='999').count(), 2)


class BookBalanceProjectionTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('bankt', password='pw12345')
        FinancialPeriod.objects.create(
            name='2020-2030',            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        Client.objects.create( name='PT Bank')

    def test_book_balance_tracks_journal_lines_on_ledger_account(self):
        sby = CashAccount.objects.get(branch_id='sby')
        self.assertEqual(sby.book_balance, 0)
        posting.post_entry(
            entry_type=posting.JournalEntry.TYPE_ADJUSTMENT,
            description='cash in',
            entry_date=date(2026, 1, 5),
            lines=[
                {'account': '1000-KAS-SBY', 'debit': 7500},
                {'account': 'equity', 'credit': 7500},
            ],
            created_by=self.user,
        )
        self.assertEqual(sby.book_balance, 7500)
