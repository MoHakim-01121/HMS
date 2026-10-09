"""Reconciliation UI wiring — list/new/detail/match/unmatch + RBAC."""
import json
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import BankTransaction, CashAccount, Client
from hw.models.reconciliation import BankStatement
from hw.models.period import FinancialPeriod
from hw.finance_helpers import create_payment_record, confirm_payment
from hw.tests.factories import make_invoice


def make_user(username, role):
    u = User.objects.create_user(username, password='pw12345')
    u.profile.role = role
    u.profile.save(update_fields=['role'])
    return u


class ReconciliationViewsBase(TestCase):
    def setUp(self):
        FinancialPeriod.objects.create(
            name='2020-2030',            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        # Reconciling is Finance's (and the admin's); Manager reads it (2026-10-09).
        self.finance = make_user('rv_fin', 'finance')
        self.manager = make_user('rv_mgr', 'manager')
        self.staff = make_user('rv_staff', 'staff')
        self.cash_sby = CashAccount.objects.get(branch_id='sby')
        self.client_obj = Client.objects.create( name='PT RV')
        self.inv = make_invoice(invoice_number='INV-RV-1', customer_name='PT RV', client=self.client_obj)


class ReconciliationListViewTest(ReconciliationViewsBase):
    def test_manager_can_view_list(self):
        self.client.force_login(self.manager)
        resp = self.client.get('/finance/reconciliation/')
        self.assertEqual(resp.status_code, 200)


class ReconciliationNewViewTest(ReconciliationViewsBase):
    def test_finance_can_create_statement(self):
        self.client.force_login(self.finance)
        resp = self.client.post('/finance/reconciliation/new/', {
            'account': f'cash:{self.cash_sby.pk}',
            'period_start': '2026-08-01', 'period_end': '2026-08-31',
            'opening_balance': '0', 'closing_balance': '5000',
            'lines': json.dumps([{'line_date': '2026-08-05', 'direction': 'in', 'amount': 5000, 'description': 'x'}]),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(BankStatement.objects.count(), 1)

    def test_staff_and_manager_cannot_create_statement(self):
        for user in (self.staff, self.manager):
            self.client.force_login(user)
            resp = self.client.post('/finance/reconciliation/new/', {
                'account': f'cash:{self.cash_sby.pk}',
                'period_start': '2026-08-01', 'period_end': '2026-08-31',
                'closing_balance': '5000',
            })
            self.assertEqual(resp.status_code, 302)
        self.assertEqual(BankStatement.objects.count(), 0)


class ReconciliationMatchViewTest(ReconciliationViewsBase):
    def setUp(self):
        super().setUp()
        pr = create_payment_record(
            self.inv, self.client_obj, date(2026, 8, 5), 5000, method='Transfer',
            receiving_account=self.cash_sby, created_by=self.finance,
        )
        confirm_payment(pr, self.finance)
        self.tx = BankTransaction.objects.get(source_type='PaymentRecord', source_id=pr.pk)
        self.client.force_login(self.finance)
        self.client.post('/finance/reconciliation/new/', {
            'account': f'cash:{self.cash_sby.pk}',
            'period_start': '2026-08-01', 'period_end': '2026-08-31',
            'opening_balance': '0', 'closing_balance': '5000',
            'lines': json.dumps([{'line_date': '2026-08-05', 'direction': 'in', 'amount': 5000, 'description': 'x'}]),
        })
        self.statement = BankStatement.objects.get()
        self.line = self.statement.lines.get()

    def test_detail_shows_candidates(self):
        resp = self.client.get(f'/finance/reconciliation/{self.statement.pk}/', HTTP_X_INERTIA='true')
        line = resp.json()['props']['statement']['lines'][0]
        self.assertEqual(len(line['candidates']), 1)

    def test_finance_can_match_and_unmatch(self):
        resp = self.client.post(f'/finance/reconciliation/lines/{self.line.pk}/match/', {
            'transaction_id': str(self.tx.pk),
        })
        self.assertEqual(resp.status_code, 302)
        self.line.refresh_from_db()
        self.assertEqual(self.line.matched_transaction_id, self.tx.pk)

        resp = self.client.post(f'/finance/reconciliation/lines/{self.line.pk}/unmatch/')
        self.assertEqual(resp.status_code, 302)
        self.line.refresh_from_db()
        self.assertIsNone(self.line.matched_transaction_id)

    def test_staff_and_manager_cannot_match(self):
        for user in (self.staff, self.manager):
            self.client.force_login(user)
            resp = self.client.post(f'/finance/reconciliation/lines/{self.line.pk}/match/', {
                'transaction_id': str(self.tx.pk),
            })
            self.assertEqual(resp.status_code, 302)
        self.line.refresh_from_db()
        self.assertIsNone(self.line.matched_transaction_id)
