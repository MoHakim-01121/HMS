"""Month-end close checklist: what must be settled before a period is locked."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import period_checklist as pc
from hw.finance import reconciliation_service as rs
from hw.finance_helpers import confirm_payment, create_payment_record
from hw.models import BankAccount, Client, LedgerAccount
from hw.finance.accounts import cash_ledger_for
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_invoice


class PeriodChecklistTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('pc', password='pw12345')
        self.sep = FinancialPeriod.objects.create(name='2026-09', date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))
        self.idr = BankAccount.objects.create(
            branch_id='sby', name='IDR', currency='IDR', ledger_account_id=cash_ledger_for('sby', 'IDR'),
            bank_name='Mandiri', account_identifier='1')
        self.cl = Client.objects.create(name='PT Close')
        self.inv = make_invoice(invoice_number='INV-PC', customer_name='x', client=self.cl)
        self.client.force_login(self.user)

    def _pay(self, confirm=True):
        p = create_payment_record(self.inv, self.cl, date(2026, 9, 5), 4_900_000, currency='IDR', exchange_rate=4900,
                                  method='Transfer', receiving_account=self.idr, created_by=self.user)
        if confirm:
            confirm_payment(p, self.user)
        return p

    def _status(self, key):
        return next(i for i in pc.checklist(self.sep)['items'] if i['key'] == key)

    def test_clean_period(self):
        c = pc.checklist(self.sep)
        self.assertTrue(c['can_lock'])
        self.assertEqual({i['status'] for i in c['items']}, {pc.OK})

    def test_pending_payment_blocks_lock(self):
        self._pay(confirm=False)
        item = self._status('pending_payments')
        self.assertEqual((item['status'], item['params']['n']), (pc.FAIL, 1))
        self.assertFalse(pc.checklist(self.sep)['can_lock'])

    def test_unallocated_payment_and_unreconciled_bank_warn(self):
        self._pay()
        self.assertEqual(self._status('unallocated_payments')['status'], pc.WARN)
        bank = self._status('bank_statements')
        self.assertEqual(bank['status'], pc.WARN)
        self.assertIn('no statement', bank['rows'][0])
        self.assertTrue(pc.checklist(self.sep)['can_lock'])            # warnings don't block

        st = rs.create_statement(account=self.idr, period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
                                 opening_balance=0, closing_balance=4_900_000,
                                 lines=[{'line_date': date(2026, 9, 5), 'direction': 'in', 'amount': 4_900_000}])
        rs.match_suggested(st)
        self.assertEqual(self._status('bank_statements')['status'], pc.OK)

    def test_lock_view_refuses_with_blocking_item(self):
        self._pay(confirm=False)
        self.sep.close(self.user)
        props = self.client.get(f'/finance/periods/{self.sep.pk}/', HTTP_X_INERTIA='true').json()['props']
        self.assertFalse(props['checklist']['can_lock'])
        self.client.post(f'/finance/periods/{self.sep.pk}/lock/')
        self.sep.refresh_from_db()
        self.assertEqual(self.sep.status, FinancialPeriod.STATUS_CLOSED)
