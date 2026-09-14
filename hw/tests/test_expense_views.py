"""FASE D UI — expense_views wiring (list/detail/record/pay/void + RBAC)."""
import json
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Branch, CashAccount, Expense, ExpenseCategory
from hw.models.period import FinancialPeriod


def make_user(username, role):
    u = User.objects.create_user(username, password='pw12345')
    u.profile.role = role
    u.profile.save(update_fields=['role'])
    return u


class ExpenseViewsBase(TestCase):
    def setUp(self):
        FinancialPeriod.objects.create(
            name='2020-2030',            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.manager = make_user('exp_mgr', 'manager')
        self.staff = make_user('exp_staff', 'staff')
        self.viewer = make_user('exp_viewer', 'viewer')
        self.sby = Branch.objects.get(code='sby')
        self.cash = CashAccount.objects.get(branch_id='sby')
        self.util = ExpenseCategory.objects.get(code='UTIL')


class ExpenseListViewTest(ExpenseViewsBase):
    def test_manager_can_view_list(self):
        self.client.force_login(self.manager)
        resp = self.client.get('/finance/expenses/')
        self.assertEqual(resp.status_code, 200)

    def test_anonymous_redirected(self):
        resp = self.client.get('/finance/expenses/')
        self.assertEqual(resp.status_code, 302)


class ExpenseRecordViewTest(ExpenseViewsBase):
    def test_manager_can_record_expense(self):
        self.client.force_login(self.manager)
        resp = self.client.post('/finance/expenses/record/', {
            'branch': 'sby', 'expense_date': '2026-05-01', 'vendor': 'PLN',
            'currency': 'SAR', 'exchange_rate': '1',
            'lines': json.dumps([{'category': 'UTIL', 'amount': 1200}]),
        })
        self.assertEqual(resp.status_code, 302)
        exp = Expense.objects.get(vendor='PLN')
        self.assertEqual(exp.status, Expense.STATUS_POSTED)
        self.assertEqual(exp.total_amount_sar, 1200)

    def test_pay_now_settles_immediately(self):
        self.client.force_login(self.manager)
        self.client.post('/finance/expenses/record/', {
            'branch': 'sby', 'expense_date': '2026-05-02', 'vendor': 'PDAM',
            'currency': 'SAR', 'exchange_rate': '1',
            'lines': json.dumps([{'category': 'UTIL', 'amount': 800}]),
            'pay_now_account': f'cash:{self.cash.pk}',
        })
        exp = Expense.objects.get(vendor='PDAM')
        self.assertEqual(exp.status, Expense.STATUS_PAID)
        self.assertEqual(exp.outstanding_sar, 0)

    def test_staff_can_record_expense(self):
        self.client.force_login(self.staff)
        resp = self.client.post('/finance/expenses/record/', {
            'branch': 'sby', 'expense_date': '2026-05-03', 'vendor': 'Telkom',
            'currency': 'SAR', 'exchange_rate': '1',
            'lines': json.dumps([{'category': 'TELECOM', 'amount': 300}]),
        })
        self.assertEqual(resp.status_code, 302)

    def test_viewer_cannot_record_expense(self):
        self.client.force_login(self.viewer)
        resp = self.client.post('/finance/expenses/record/', {
            'branch': 'sby', 'expense_date': '2026-05-04',
            'lines': json.dumps([{'category': 'UTIL', 'amount': 100}]),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Expense.objects.filter(expense_date='2026-05-04').exists())


class ExpenseDetailPayVoidTest(ExpenseViewsBase):
    def setUp(self):
        super().setUp()
        from hw.finance import expense_service
        self.exp = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 5, 5), created_by=self.manager,
            vendor='ATK Toko', lines=[{'category': self.util, 'amount': 2000}],
        )

    def test_detail_shows_lines(self):
        self.client.force_login(self.manager)
        resp = self.client.get(f'/finance/expenses/{self.exp.pk}/')
        self.assertEqual(resp.status_code, 200)

    def test_manager_can_pay(self):
        self.client.force_login(self.manager)
        resp = self.client.post(f'/finance/expenses/{self.exp.pk}/pay/', {
            'amount': '2000', 'payment_date': '2026-05-06',
            'account': f'cash:{self.cash.pk}',
        })
        self.assertEqual(resp.status_code, 302)
        self.exp.refresh_from_db()
        self.assertEqual(self.exp.status, Expense.STATUS_PAID)

    def test_staff_cannot_void(self):
        self.client.force_login(self.staff)
        resp = self.client.post(f'/finance/expenses/{self.exp.pk}/void/')
        self.assertEqual(resp.status_code, 302)
        self.exp.refresh_from_db()
        self.assertNotEqual(self.exp.status, Expense.STATUS_VOIDED)

    def test_manager_can_void(self):
        self.client.force_login(self.manager)
        resp = self.client.post(f'/finance/expenses/{self.exp.pk}/void/')
        self.assertEqual(resp.status_code, 302)
        self.exp.refresh_from_db()
        self.assertEqual(self.exp.status, Expense.STATUS_VOIDED)
