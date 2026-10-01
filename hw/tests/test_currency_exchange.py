"""Penukaran Valas: a client's USD sold for IDR between our own accounts."""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import exchange_service as fx
from hw.finance.errors import FinanceError
from hw.models import BankAccount, BankTransaction, CurrencyExchange, LedgerAccount
from hw.finance.accounts import cash_ledger_for
from hw.models.journal import JournalEntry
from hw.models.period import FinancialPeriod


class ExchangeBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('fx', password='pw12345')
        FinancialPeriod.objects.create(name='2026', date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        la = LedgerAccount.objects.get(code='1000-KAS-SBY')
        self.usd = BankAccount.objects.create(branch_id='sby', name='USD', currency='USD', ledger_account_id=cash_ledger_for('sby', 'USD'),
                                              bank_name='Mandiri', account_identifier='111')
        self.idr = BankAccount.objects.create(branch_id='sby', name='IDR', currency='IDR', ledger_account_id=cash_ledger_for('sby', 'IDR'),
                                              bank_name='Mandiri', account_identifier='222')

    def _exchange(self, out=2750, inn=48_125_000, day=date(2026, 9, 10)):
        return fx.record_exchange(from_account=self.usd, amount_out=out, to_account=self.idr,
                                  amount_in=inn, exchange_date=day, created_by=self.user)


class RecordExchangeTest(ExchangeBase):
    def test_records_two_cash_rows_in_real_currencies_and_no_journal(self):
        ex = self._exchange()
        self.assertEqual(ex.rate, Decimal('17500.0000'))
        out = BankTransaction.objects.get(source_type=fx.SOURCE_OUT, source_id=ex.pk)
        inn = BankTransaction.objects.get(source_type=fx.SOURCE_IN, source_id=ex.pk)
        self.assertEqual((out.account_id, out.direction, out.currency, out.amount), (self.usd.pk, 'out', 'USD', 2750))
        self.assertEqual((inn.account_id, inn.direction, inn.currency, inn.amount), (self.idr.pk, 'in', 'IDR', 48_125_000))
        self.assertFalse(JournalEntry.objects.exists())  # SAR owed to HQ is unchanged

    def test_rejects_same_currency_same_account_and_zero(self):
        with self.assertRaises(FinanceError):
            fx.record_exchange(from_account=self.idr, amount_out=1, to_account=self.idr, amount_in=1,
                               exchange_date=date(2026, 9, 10), created_by=self.user)
        other_idr = BankAccount.objects.create(branch_id='sby', name='IDR2', currency='IDR',
                                               ledger_account=self.idr.ledger_account, bank_name='BCA', account_identifier='333')
        with self.assertRaises(FinanceError):
            fx.record_exchange(from_account=self.idr, amount_out=1, to_account=other_idr, amount_in=1,
                               exchange_date=date(2026, 9, 10), created_by=self.user)
        with self.assertRaises(FinanceError):
            self._exchange(out=0)
        self.assertFalse(CurrencyExchange.objects.exists())

    def test_void_voids_both_rows_once(self):
        ex = self._exchange()
        fx.void_exchange(ex, reason='typo')
        self.assertEqual(set(BankTransaction.objects.values_list('status', flat=True)), {BankTransaction.STATUS_VOIDED})
        with self.assertRaises(FinanceError):
            fx.void_exchange(ex)

    def test_rate_warning_against_previous_pair(self):
        self._exchange()                                   # 17,500
        prev = fx.previous_rate('USD', 'IDR')
        self.assertEqual(prev, Decimal('17500.0000'))
        self.assertIsNone(fx.rate_warning(Decimal('17800'), prev))      # 1.7% — fine
        self.assertEqual(fx.rate_warning(Decimal('19000'), prev), Decimal('8.6'))


class ExchangeViewTest(ExchangeBase):
    def test_create_via_form_and_list(self):
        self.client.force_login(self.user)
        resp = self.client.post('/finance/exchanges/new/', {
            'from_account': f'bank:{self.usd.pk}', 'amount_out': '2750',
            'to_account': f'bank:{self.idr.pk}', 'amount_in': '48125000', 'exchange_date': '2026-09-10',
        })
        self.assertEqual(resp.status_code, 302)
        rows = self.client.get('/finance/exchanges/', HTTP_X_INERTIA='true').json()['props']['exchanges']
        self.assertEqual((rows[0]['amount_out'], rows[0]['amount_in'], rows[0]['rate']), (2750, 48125000, 17500.0))

    def test_form_error_keeps_input(self):
        self.client.force_login(self.user)
        resp = self.client.post('/finance/exchanges/new/', {
            'from_account': f'bank:{self.idr.pk}', 'amount_out': '10',
            'to_account': f'bank:{self.idr.pk}', 'amount_in': '10', 'exchange_date': '2026-09-10',
        }, HTTP_X_INERTIA='true')
        props = resp.json()['props']
        self.assertTrue(props['error'])
        self.assertEqual(props['form']['amount_out'], '10')

    def test_viewer_cannot_create(self):
        viewer = User.objects.create_user('fxv', password='pw12345')
        viewer.profile.role = 'viewer'
        viewer.profile.save(update_fields=['role'])
        self.client.force_login(viewer)
        resp = self.client.post('/finance/exchanges/new/', {
            'from_account': f'bank:{self.usd.pk}', 'amount_out': '1',
            'to_account': f'bank:{self.idr.pk}', 'amount_in': '1', 'exchange_date': '2026-09-10',
        })
        self.assertRedirects(resp, '/dashboard/', fetch_redirect_response=False)  # _deny bounces home
        self.assertFalse(CurrencyExchange.objects.exists())
