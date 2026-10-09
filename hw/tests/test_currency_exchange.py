"""Penukaran Valas: a client's USD sold for IDR between our own accounts."""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import accounts as coa, exchange_service as fx, posting
from hw.finance.bank_ledger import record_bank_transaction
from hw.finance.errors import FinanceError, InsufficientFundsError
from hw.finance.hashing import verify_chain
from hw.models import BankAccount, BankTransaction, CurrencyExchange, LedgerAccount
from hw.finance.accounts import cash_ledger_for
from hw.models.journal import JournalEntry, JournalLine
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
        # 5,000 client dollars held, worth 18,750 SAR in the ledger.
        self._fund(self.usd, 5_000, 18_750)

    def _fund(self, account, amount, sar, day=date(2026, 9, 1)):
        posting.post_adjustment(
            lines=[{'account': account.ledger_account_id, 'debit': sar, 'branch': account.branch_id,
                    **posting.native(account, amount)},
                   {'account': coa.OPENING_EQUITY, 'credit': sar, 'branch': account.branch_id}],
            description=f'dana awal {account}', entry_date=day, created_by=self.user,
        )
        record_bank_transaction(account=account, direction='in', amount_sar=sar, currency=account.currency,
                                amount=amount, source_type='TestFunding', source_id=account.pk, transaction_date=day)

    def _ledger(self, account):
        """(saldo asli, saldo SAR) akun buku besar rekening."""
        lines = JournalLine.objects.filter(account_id=account.ledger_account_id)
        native = sum((l.amount_txn or 0) * (1 if l.debit else -1) for l in lines)
        return native, sum(l.debit - l.credit for l in lines)

    def _cash_book(self, account):
        rows = BankTransaction.objects.filter(account=account).exclude(status=BankTransaction.STATUS_VOIDED)
        return sum(r.amount if r.direction == 'in' else -r.amount for r in rows)

    def _exchange(self, out=2750, inn=48_125_000, day=date(2026, 9, 10)):
        return fx.record_exchange(from_account=self.usd, amount_out=out, to_account=self.idr,
                                  amount_in=inn, exchange_date=day, created_by=self.user)


class RecordExchangeTest(ExchangeBase):
    def test_records_two_cash_rows_in_real_currencies(self):
        ex = self._exchange()
        self.assertEqual(ex.rate, Decimal('17500.0000'))
        out = BankTransaction.objects.get(source_type=fx.SOURCE_OUT, source_id=ex.pk)
        inn = BankTransaction.objects.get(source_type=fx.SOURCE_IN, source_id=ex.pk)
        self.assertEqual((out.account_id, out.direction, out.currency, out.amount), (self.usd.pk, 'out', 'USD', 2750))
        self.assertEqual((inn.account_id, inn.direction, inn.currency, inn.amount), (self.idr.pk, 'in', 'IDR', 48_125_000))

    def test_journal_moves_the_carrying_value_between_currency_accounts(self):
        # 2,750 of 5,000 dollars carried at 18,750 SAR -> 10,313 SAR moves to rupiah;
        # the SAR value held (and owed to HQ) does not change.
        ex = self._exchange()
        entry = JournalEntry.objects.get(source_currency_exchange=ex)
        self.assertEqual(entry.entry_type, JournalEntry.TYPE_EXCHANGE)
        self.assertEqual(self._ledger(self.usd), (2_250, 8_437))
        self.assertEqual(self._ledger(self.idr), (48_125_000, 10_313))
        self.assertEqual(verify_chain(), [])

    def test_ledger_and_cash_book_agree_after_an_exchange(self):
        self._exchange()
        for account in (self.usd, self.idr):
            self.assertEqual(self._ledger(account)[0], self._cash_book(account), str(account))

    def test_exchange_into_riyal_books_the_difference_as_fx_result(self):
        sar = BankAccount.objects.create(branch_id='sby', name='SAR', currency='SAR', bank_name='Mandiri',
                                         account_identifier='444', ledger_account_id=cash_ledger_for('sby', 'SAR'))
        self._fund(self.idr, 47_000_000, 10_000)
        # 4,700,000 rupiah carried at 1,000 SAR bring 1,050 real riyal: 50 SAR gain.
        fx.record_exchange(from_account=self.idr, amount_out=4_700_000, to_account=sar, amount_in=1_050,
                           exchange_date=date(2026, 9, 10), created_by=self.user)
        self.assertEqual(self._ledger(sar), (0, 1_050))
        gain = JournalLine.objects.filter(account_id=coa.INC_FX_GAIN).values_list('credit', flat=True)
        self.assertEqual(list(gain), [50])

    def test_cannot_exchange_money_the_account_does_not_hold(self):
        with self.assertRaises(InsufficientFundsError):
            self._exchange(out=6_000)
        self.assertFalse(CurrencyExchange.objects.exists())

    def test_rejects_same_account_other_branch_and_zero(self):
        with self.assertRaises(FinanceError):
            fx.record_exchange(from_account=self.idr, amount_out=1, to_account=self.idr, amount_in=1,
                               exchange_date=date(2026, 9, 10), created_by=self.user)
        # Money for another branch travels as a Remittance, not a transfer.
        hq_usd = BankAccount.objects.create(branch_id='pusat', name='USD HQ', currency='USD', bank_name='BCA',
                                            account_identifier='555', ledger_account_id=cash_ledger_for('pusat', 'USD'))
        with self.assertRaisesMessage(FinanceError, 'Remittance'):
            fx.record_exchange(from_account=self.usd, amount_out=100, to_account=hq_usd, amount_in=100,
                               exchange_date=date(2026, 9, 10), created_by=self.user)
        with self.assertRaises(FinanceError):
            self._exchange(out=0)
        self.assertFalse(CurrencyExchange.objects.exists())

    def _other_usd(self):
        return BankAccount.objects.create(branch_id='sby', name='USD2', currency='USD', bank_name='BCA',
                                          account_identifier='333', ledger_account=self.usd.ledger_account)

    def test_same_currency_transfer_moves_cash_only(self):
        other_usd = self._other_usd()
        # amount_in follows amount_out whatever the form sent.
        ex = fx.record_exchange(from_account=self.usd, amount_out=1_350, to_account=other_usd, amount_in=None,
                                exchange_date=date(2026, 9, 10), created_by=self.user)
        self.assertEqual((ex.amount_out, ex.amount_in, ex.rate), (1_350, 1_350, Decimal('1.0000')))
        self.assertEqual((self._cash_book(self.usd), self._cash_book(other_usd)), (3_650, 1_350))
        # One ledger account per branch and currency: nothing to journal, value unchanged.
        self.assertFalse(JournalEntry.objects.for_source('CurrencyExchange', ex.pk).exists())
        self.assertEqual(self._ledger(self.usd), (5_000, 18_750))
        fx.void_exchange(ex, reason='typo')
        self.assertEqual((self._cash_book(self.usd), self._cash_book(other_usd)), (5_000, 0))

    def test_same_currency_transfer_cannot_overdraw(self):
        with self.assertRaises(InsufficientFundsError):
            fx.record_exchange(from_account=self.usd, amount_out=6_000, to_account=self._other_usd(), amount_in=6_000,
                               exchange_date=date(2026, 9, 10), created_by=self.user)
        self.assertFalse(CurrencyExchange.objects.exists())

    def test_cutover_replay_books_no_journal_for_same_currency_transfer(self):
        from io import StringIO
        from django.core.management import call_command
        same = fx.record_exchange(from_account=self.usd, amount_out=100, to_account=self._other_usd(), amount_in=100,
                                  exchange_date=date(2026, 9, 10), created_by=self.user)
        call_command('cutover_journal', '--commit', stdout=StringIO())
        self.assertFalse(JournalEntry.objects.for_source('CurrencyExchange', same.pk).exists())
        self.assertEqual(self._ledger(self.usd), (5_000, 18_750))

    def test_fund_flow_ignores_same_currency_transfer(self):
        from hw.finance.fund_flow import _branch_events
        fx.record_exchange(from_account=self.usd, amount_out=100, to_account=self._other_usd(), amount_in=100,
                           exchange_date=date(2026, 9, 10), created_by=self.user)
        ex = self._exchange()
        kinds = [(e[3], e[2]) for e in _branch_events('sby', None)]
        self.assertEqual(kinds, [('exchange', ex.pk)])

    def test_void_voids_both_rows_once(self):
        ex = self._exchange()
        fx.void_exchange(ex, reason='typo')
        rows = BankTransaction.objects.filter(source_type__in=(fx.SOURCE_OUT, fx.SOURCE_IN))
        self.assertEqual(set(rows.values_list('status', flat=True)), {BankTransaction.STATUS_VOIDED})
        self.assertEqual(self._ledger(self.usd), (5_000, 18_750))
        self.assertEqual(self._ledger(self.idr), (0, 0))
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
