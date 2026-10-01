"""Schema v2 F2c — rekening bank dan kas dalam satu tabel MoneyAccount."""
from django.db import IntegrityError, transaction
from django.test import TestCase

from hw.db_pg import pg_only
from hw.models import BankAccount, Branch, CashAccount, MoneyAccount
from hw.finance.accounts import cash_ledger_for
from hw.models.journal import LedgerAccount
from hw.views.helpers import money_account_choices, resolve_money_account


class MoneyAccountTest(TestCase):
    def setUp(self):
        self.sby = Branch.objects.get(code='sby')
        self.ledger = LedgerAccount.objects.get(code='1000-KAS-SBY')

    def _bank(self, **kw):
        defaults = dict(branch=self.sby, name='Ops', currency='IDR', ledger_account_id=cash_ledger_for('sby', 'IDR'),
                        bank_name='Mandiri', account_identifier='111')
        defaults.update(kw)
        return BankAccount.objects.create(**defaults)

    def test_proxies_share_one_table_and_filter_by_kind(self):
        bank = self._bank()
        self.assertEqual(bank.kind, 'bank')
        self.assertEqual(BankAccount._meta.db_table, CashAccount._meta.db_table)
        self.assertIn(bank.pk, MoneyAccount.objects.values_list('pk', flat=True))
        self.assertNotIn(bank.pk, CashAccount.objects.values_list('pk', flat=True))
        cash = CashAccount.objects.get(branch_id='sby')
        self.assertEqual(cash.kind, 'cash')
        self.assertNotIn(cash.pk, BankAccount.objects.values_list('pk', flat=True))

    def test_ids_never_collide_between_bank_and_cash(self):
        bank = self._bank()
        self.assertFalse(CashAccount.objects.filter(pk=bank.pk).exists())

    def test_bank_needs_bank_name(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._bank(bank_name='')

    def test_same_account_number_refused_only_when_filled(self):
        self._bank()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._bank(name='Dup')
        # Dua rekening tanpa nomor di bank yang sama boleh (dulu ditolak).
        self._bank(name='A', account_identifier='')
        self._bank(name='B', account_identifier='')

    def test_cash_name_unique_per_branch_and_currency(self):
        existing = CashAccount.objects.get(branch_id='sby')
        with self.assertRaises(IntegrityError), transaction.atomic():
            CashAccount.objects.create(branch=self.sby, name=existing.name, currency=existing.currency,
                                       ledger_account=self.ledger)

    def test_currency_and_kind_are_checked(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._bank(currency='EUR', account_identifier='222', ledger_account_id=cash_ledger_for('sby', 'EUR'))
        with self.assertRaises(IntegrityError), transaction.atomic():
            MoneyAccount.objects.create(kind='card', branch=self.sby, name='X', currency='SAR',
                                        ledger_account=self.ledger, bank_name='B')

    def test_picker_tokens_round_trip(self):
        bank = self._bank()
        tokens = {c['value'] for c in money_account_choices()}
        self.assertIn(f'bank:{bank.pk}', tokens)
        cash = CashAccount.objects.get(branch_id='sby')
        self.assertIn(f'cash:{cash.pk}', tokens)
        self.assertEqual(resolve_money_account(f'cash:{cash.pk}'), cash)
        self.assertIsNone(resolve_money_account('bank:abc'))
        self.assertIsNone(resolve_money_account('card:1'))


@pg_only
class MoneyAccountPostgresRuleTest(TestCase):
    def test_head_office_account_must_be_sar(self):
        pusat = Branch.objects.get(code='pusat')
        with self.assertRaises(IntegrityError), transaction.atomic():
            BankAccount.objects.create(branch=pusat, name='IDR HQ', currency='IDR',
                                       ledger_account_id=cash_ledger_for('sby', 'IDR'),
                                       bank_name='Mandiri', account_identifier='999')
