"""FASE I follow-up — bank account transaction drill-down (v2.0 §64)."""
from datetime import date

from django.contrib.auth.models import User
from django.test import Client as HttpClient
from django.test import TestCase

from hw.finance import queries as finance_queries
from hw.finance_helpers import confirm_payment, create_payment_record
from hw.models import Branch, CashAccount, Client
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_invoice


class AccountTransactionsQueryTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('drilldown', password='pw12345')
        FinancialPeriod.objects.create(
            name='2020-2030',            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.sby = Branch.objects.get(code='sby')
        self.cash_sby = CashAccount.objects.get(branch_id='sby')

    def test_unknown_account_returns_none(self):
        self.assertIsNone(finance_queries.account_transactions('cash', 999999))

    def test_running_balance_accumulates_in_chronological_order(self):
        client_obj = Client.objects.create( name='PT DD')
        inv = make_invoice(invoice_number='INV-DD-1', customer_name='PT DD', client=client_obj)
        pr1 = create_payment_record(
            inv, client_obj, date(2026, 7, 1), 5000, method='Transfer',
            receiving_account=self.cash_sby, created_by=self.user,
        )
        confirm_payment(pr1, confirmed_by=self.user)
        pr2 = create_payment_record(
            inv, client_obj, date(2026, 7, 2), 3000, method='Transfer',
            receiving_account=self.cash_sby, created_by=self.user,
        )
        confirm_payment(pr2, confirmed_by=self.user)

        data = finance_queries.account_transactions('cash', self.cash_sby.pk)
        self.assertEqual(data['account']['kind'], 'cash')
        # Most-recent-first output, but balance itself accumulates forward in time.
        dates = [r['transaction_date'] for r in data['rows']]
        self.assertEqual(dates, sorted(dates, reverse=True))
        newest, oldest = data['rows'][0], data['rows'][-1]
        self.assertEqual(oldest['running_balance_sar'], 5000)
        self.assertEqual(newest['running_balance_sar'], 8000)
        self.assertFalse(newest['matched'])


class BankAccountTransactionsViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('viewdd', password='pw12345', is_staff=True, is_superuser=True)
        FinancialPeriod.objects.create(
            name='2020-2030',            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.cash_sby = CashAccount.objects.get(branch_id='sby')
        self.http = HttpClient()
        self.http.force_login(self.user)

    def test_view_renders_for_valid_account(self):
        resp = self.http.get(f'/finance/bank-accounts/cash/{self.cash_sby.pk}/')
        self.assertEqual(resp.status_code, 200)

    def test_view_404s_for_unknown_kind(self):
        resp = self.http.get(f'/finance/bank-accounts/bogus/{self.cash_sby.pk}/')
        self.assertEqual(resp.status_code, 404)

    def test_view_404s_for_unknown_id(self):
        resp = self.http.get('/finance/bank-accounts/cash/999999/')
        self.assertEqual(resp.status_code, 404)
