"""FASE D — Expense domain."""
from datetime import date

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase

from hw.models import (
    BankAccount, Branch, CashAccount, Expense, ExpenseCategory, ExpensePayment,
)
from hw.models.journal import JournalEntry, LedgerAccount
from hw.models.period import FinancialPeriod
from hw.finance import expense_service, queries as fq
from hw.finance.errors import FinanceError


class ExpenseBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('exp', password='pw12345')
        FinancialPeriod.objects.create(
            name='2020-2030',            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.sby = Branch.objects.get(code='sby')
        self.cash = CashAccount.objects.get(branch_id='sby')
        self.util = ExpenseCategory.objects.get(code='UTIL')


class ExpenseSeedTest(ExpenseBase):
    def test_default_categories_and_ap_account_seeded(self):
        self.assertEqual(ExpenseCategory.objects.count(), 10)
        self.assertTrue(LedgerAccount.objects.filter(code='2000-AP').exists())


class RecordExpenseTest(ExpenseBase):
    def test_accrual_posts_dr_expense_cr_ap(self):
        exp = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 3, 1), created_by=self.user,
            vendor='PLN', lines=[{'category': self.util, 'amount': 1500}],
        )
        self.assertEqual(exp.status, Expense.STATUS_POSTED)
        self.assertEqual(exp.outstanding_sar, 1500)
        self.assertEqual(fq.ap_balance(), 1500)
        je = JournalEntry.objects.get(reference_type='Expense', reference_id=exp.pk)
        self.assertTrue(je.is_balanced)
        self.assertTrue(all(l.branch_id == 'sby' for l in je.lines.all()))

    def test_pay_now_settles_ap_and_credits_cash(self):
        exp = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 3, 2), created_by=self.user,
            lines=[{'category': self.util, 'amount': 2000}],
            pay_now={'cash_account': self.cash},
        )
        exp.refresh_from_db()
        self.assertEqual(exp.status, Expense.STATUS_PAID)
        self.assertEqual(exp.outstanding_sar, 0)
        self.assertEqual(fq.ap_balance(), 0)
        self.assertEqual(fq.account_balance('1000-KAS-SBY'), -2000)
        self.assertEqual(fq.branch_expense_sar('sby'), 2000)

    def test_partial_payment_sets_partially_paid(self):
        exp = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 3, 3), created_by=self.user,
            lines=[{'category': self.util, 'amount': 5000}],
        )
        expense_service.add_expense_payment(
            exp, amount=2000, payment_date=date(2026, 3, 4),
            cash_account=self.cash, created_by=self.user,
        )
        exp.refresh_from_db()
        self.assertEqual(exp.status, Expense.STATUS_PARTIALLY_PAID)
        self.assertEqual(exp.outstanding_sar, 3000)

    def test_overpayment_rejected(self):
        exp = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 3, 5), created_by=self.user,
            lines=[{'category': self.util, 'amount': 1000}],
        )
        with self.assertRaises(FinanceError):
            expense_service.add_expense_payment(
                exp, amount=2000, payment_date=date(2026, 3, 6),
                cash_account=self.cash, created_by=self.user,
            )


class VoidExpenseTest(ExpenseBase):
    def test_void_reverses_all_entries(self):
        exp = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 3, 7), created_by=self.user,
            lines=[{'category': self.util, 'amount': 3000}],
            pay_now={'cash_account': self.cash},
        )
        expense_service.void_expense(exp, created_by=self.user)
        exp.refresh_from_db()
        self.assertEqual(exp.status, Expense.STATUS_VOIDED)
        self.assertEqual(fq.ap_balance(), 0)
        self.assertEqual(fq.account_balance('1000-KAS-SBY'), 0)
        self.assertEqual(fq.branch_expense_sar('sby'), 0)


class ExpensePaymentConstraintTest(ExpenseBase):
    def test_exactly_one_account_enforced(self):
        exp = Expense.objects.create(
            expense_number='EXP-C1', branch=self.sby, expense_date=date(2026, 3, 1),
            total_amount=100, total_amount_sar=100, status=Expense.STATUS_POSTED,
            period=FinancialPeriod.objects.first(), created_by=self.user,
        )
        bank = BankAccount.objects.create(
            branch=self.sby, name='Ops', currency='SAR',
            ledger_account=LedgerAccount.objects.get(code='1000-KAS-SBY'),
            bank_name='BCA', account_identifier='1',
        )
        with self.assertRaises(IntegrityError):
            ExpensePayment.objects.create(
                expense=exp, payment_date=date(2026, 3, 1), amount=100, amount_sar=100,
                bank_account=bank, cash_account=self.cash, created_by=self.user,
            )
