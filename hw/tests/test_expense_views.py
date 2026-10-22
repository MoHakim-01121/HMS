"""Expense screens (decided 2026-10-11): Finance records; Finance (the
recorder too), a Manager or an Admin approves; Finance pays and voids; head
office's Finance and the Admin manage categories."""
import json
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import expense_service
from hw.finance.accounts import cash_ledger_for
from hw.models import BankAccount, Branch, Expense, ExpenseCategory, UserBranchAccess, UserProfile
from hw.models.period import FinancialPeriod
from hw.tests.factories import fund_account

DAY = date(2026, 9, 10)


def make_user(username, role, branch=None):
    user = User.objects.create_user(username, password='pw12345')
    UserProfile.objects.filter(user=user).update(role=role, all_branches=branch is None)
    if branch:
        UserBranchAccess.objects.create(profile=user.profile, branch_id=branch)
    return User.objects.get(pk=user.pk)


class ExpenseViewsBase(TestCase):
    def setUp(self):
        FinancialPeriod.objects.create(name='2020-2030', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31))
        self.finance = make_user('exp_fin', 'finance')
        self.manager = make_user('exp_mgr', 'manager')
        self.staff = make_user('exp_staff', 'staff')
        self.sby = Branch.objects.get(code='sby')
        self.idr = BankAccount.objects.create(branch_id='sby', name='IDR', currency='IDR', bank_name='Mandiri',
                                              account_identifier='111', ledger_account_id=cash_ledger_for('sby', 'IDR'))
        fund_account(self.idr, 100_000_000, 20_000, date(2026, 9, 1), self.finance)

    def _record(self, user, day='2026-09-10', line=None, **extra):
        self.client.force_login(user)
        line = line or {'category': 'TELECOM', 'amount': 1_000_000, 'no_receipt_reason': 'Tagihan online'}
        return self.client.post('/finance/expenses/record/', {
            'expense_date': day, 'vendor': 'Telkom', 'lines': json.dumps([line]), **extra,
        })

    def _submitted(self):
        return expense_service.submit_expense(
            branch=self.sby, expense_date=DAY, created_by=self.finance, vendor='PLN',
            lines=[{'category': ExpenseCategory.objects.get(code='UTIL'), 'amount': 10_000_000}],
        )


class RecordTest(ExpenseViewsBase):
    def test_finance_records_an_expense_awaiting_approval(self):
        resp = self._record(self.finance)
        exp = Expense.objects.get()
        self.assertRedirects(resp, f'/finance/expenses/{exp.pk}/', fetch_redirect_response=False)
        self.assertEqual((exp.status, exp.currency, exp.total_amount), (Expense.STATUS_SUBMITTED, 'IDR', 1_000_000))

    def test_a_line_needs_a_receipt_or_a_reason(self):
        self._record(self.finance, line={'category': 'TELECOM', 'amount': 1_000_000})
        self.assertFalse(Expense.objects.exists())

    def test_receipts_are_kept_per_line(self):
        import base64

        from django.core.files.uploadedfile import SimpleUploadedFile
        png = SimpleUploadedFile('telkom.png', base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='),
            content_type='image/png')
        self._record(self.finance, line={'category': 'TELECOM', 'amount': 1_000_000}, receipts_0=png)
        line = Expense.objects.get().lines.get()
        self.assertEqual([r.name for r in line.receipts.all()], ['telkom.png'])
        self.assertEqual(line.no_receipt_reason, '')
        self.assertEqual(Expense.objects.get().spent_by, self.finance)

    def test_manager_and_staff_do_not_record(self):
        for user in (self.manager, self.staff):
            self._record(user)
        self.assertFalse(Expense.objects.exists())

    def test_list_counts_what_waits(self):
        self._submitted()
        self.client.force_login(self.manager)
        props = self.client.get('/finance/expenses/', HTTP_X_INERTIA='true').json()['props']
        # Waiting is counted whatever month the expense is dated.
        self.assertEqual(props['kpis']['waiting_count'], 1)


class DecisionTest(ExpenseViewsBase):
    def _post(self, user, exp, action, data=None):
        self.client.force_login(user)
        self.client.post(f'/finance/expenses/{exp.pk}/{action}/', data or {})
        exp.refresh_from_db()
        return exp

    def test_the_recorder_may_approve_their_own(self):
        self.assertEqual(self._post(self.finance, self._submitted(), 'approve').status, Expense.STATUS_APPROVED)

    def test_a_manager_approves_but_does_not_pay(self):
        exp = self._post(self.manager, self._submitted(), 'approve')
        self.assertEqual(exp.status, Expense.STATUS_APPROVED)
        exp = self._post(self.manager, exp, 'pay', {'account': self.idr.token, 'payment_date': '2026-09-12'})
        self.assertEqual(exp.status, Expense.STATUS_APPROVED)

    def test_staff_cannot_approve(self):
        self.assertEqual(self._post(self.staff, self._submitted(), 'approve').status, Expense.STATUS_SUBMITTED)

    def test_finance_pays_on_the_transfer_date(self):
        exp = self._post(self.manager, self._submitted(), 'approve')
        exp = self._post(self.finance, exp, 'pay', {'account': self.idr.token, 'payment_date': '2026-09-14',
                                                    'reference': 'TRF-14'})
        self.assertEqual(exp.status, Expense.STATUS_PAID)
        self.assertEqual((exp.payment.payment_date, exp.payment.amount_sar, exp.expense_date),
                         (date(2026, 9, 14), 2_000, DAY))

    def test_reject_and_void(self):
        exp = self._post(self.manager, self._submitted(), 'reject', {'reason': 'nota tidak jelas'})
        self.assertEqual((exp.status, exp.decision_note), (Expense.STATUS_REJECTED, 'nota tidak jelas'))
        paid = self._post(self.finance, self._submitted(), 'approve')
        paid = self._post(self.finance, paid, 'pay', {'account': self.idr.token, 'payment_date': '2026-09-14'})
        self.assertEqual(self._post(self.manager, paid, 'void').status, Expense.STATUS_PAID)
        self.assertEqual(self._post(self.finance, paid, 'void', {'reason': 'salah'}).status, Expense.STATUS_VOIDED)

    def test_detail_offers_only_the_branchs_rupiah_accounts(self):
        self.client.force_login(self.finance)
        props = self.client.get(f'/finance/expenses/{self._submitted().pk}/', HTTP_X_INERTIA='true').json()['props']
        self.assertEqual([a['value'] for a in props['account_choices']], [self.idr.token])


class CategoryScreenTest(ExpenseViewsBase):
    def test_head_office_finance_adds_a_category(self):
        self.client.force_login(self.finance)
        self.assertEqual(self.client.get('/finance/expenses/categories/').status_code, 200)
        self.client.post('/finance/expenses/categories/new/', {'name': 'Komisi Sales'})
        self.assertTrue(ExpenseCategory.objects.filter(name='Komisi Sales').exists())

    def test_branch_finance_and_managers_do_not(self):
        self.client.force_login(make_user('sby_fin', 'finance', branch='sby'))
        self.assertEqual(self.client.get('/finance/expenses/categories/').status_code, 404)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get('/finance/expenses/categories/').status_code, 302)
        self.client.post('/finance/expenses/categories/new/', {'name': 'Titipan'})
        self.assertFalse(ExpenseCategory.objects.filter(name='Titipan').exists())
