"""FASE D — Expense domain."""
from datetime import date

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

from hw.models import (
    Branch, CashAccount, Expense, ExpenseCategory, ExpenseLine, ExpensePayment, InvoiceLine, Vendor,
)
from hw.models.journal import JournalEntry, LedgerAccount
from hw.models.period import FinancialPeriod
from hw.finance import expense_service, queries as fq
from hw.finance.errors import FinanceError
from hw.tests.factories import make_hotel_line, make_invoice, make_service_line


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
        self.assertEqual(ExpenseCategory.objects.count(), 11)
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
        je = JournalEntry.objects.get(source_expense=exp.pk)
        self.assertTrue(je.is_balanced)
        self.assertTrue(all(l.branch_id == 'sby' for l in je.lines.all()))

    def test_pay_now_settles_ap_and_credits_cash(self):
        exp = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 3, 2), created_by=self.user,
            lines=[{'category': self.util, 'amount': 2000}],
            pay_now={'account': self.cash},
        )
        exp.refresh_from_db()
        self.assertEqual(exp.status, Expense.STATUS_POSTED)
        self.assertEqual(exp.display_status, Expense.STATUS_PAID)
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
            account=self.cash, created_by=self.user,
        )
        exp.refresh_from_db()
        self.assertEqual(exp.display_status, Expense.STATUS_PARTIALLY_PAID)
        self.assertEqual(exp.outstanding_sar, 3000)

    def test_overpayment_rejected(self):
        exp = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 3, 5), created_by=self.user,
            lines=[{'category': self.util, 'amount': 1000}],
        )
        with self.assertRaises(FinanceError):
            expense_service.add_expense_payment(
                exp, amount=2000, payment_date=date(2026, 3, 6),
                account=self.cash, created_by=self.user,
            )


class VoidExpenseTest(ExpenseBase):
    def test_void_reverses_all_entries(self):
        exp = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 3, 7), created_by=self.user,
            lines=[{'category': self.util, 'amount': 3000}],
            pay_now={'account': self.cash},
        )
        expense_service.void_expense(exp, created_by=self.user)
        exp.refresh_from_db()
        self.assertEqual(exp.status, Expense.STATUS_VOIDED)
        self.assertEqual(fq.ap_balance(), 0)
        self.assertEqual(fq.account_balance('1000-KAS-SBY'), 0)
        self.assertEqual(fq.branch_expense_sar('sby'), 0)


class ExpensePaymentConstraintTest(ExpenseBase):
    def test_exactly_one_account_enforced(self):
        # Schema v2: satu kolom akun wajib — pembayaran tanpa akun ditolak
        # database, dan "dua akun sekaligus" tidak bisa lagi ditulis.
        exp = Expense.objects.create(
            expense_number='EXP-C1', branch=self.sby, expense_date=date(2026, 3, 1),
            status=Expense.STATUS_POSTED, created_by=self.user,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExpensePayment.objects.create(
                expense=exp, payment_date=date(2026, 3, 1), amount=100, amount_sar=100,
                created_by=self.user,
            )

    def test_service_refuses_payment_without_account(self):
        exp = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 3, 1), created_by=self.user,
            lines=[{'category': self.util, 'amount': 100}],
        )
        with self.assertRaises(FinanceError):
            expense_service.add_expense_payment(
                exp, amount=100, payment_date=date(2026, 3, 1), account=None, created_by=self.user,
            )


class VendorMasterTest(ExpenseBase):
    def test_vendor_name_resolves_to_one_master_row(self):
        a = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 3, 1), created_by=self.user,
            vendor='PLN', lines=[{'category': self.util, 'amount': 100}],
        )
        b = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 3, 2), created_by=self.user,
            vendor=' pln ', lines=[{'category': self.util, 'amount': 200}],
        )
        self.assertEqual(a.vendor_id, b.vendor_id)
        self.assertEqual(Vendor.objects.count(), 1)
        self.assertEqual(a.total_amount_sar, 100)

    def test_no_vendor_is_allowed(self):
        exp = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 3, 1), created_by=self.user,
            lines=[{'category': self.util, 'amount': 100}],
        )
        self.assertIsNone(exp.vendor)

    def test_line_amount_must_be_positive(self):
        exp = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 3, 1), created_by=self.user,
            lines=[{'category': self.util, 'amount': 100}],
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExpenseLine.objects.create(expense=exp, category=self.util, amount=0, amount_sar=0)


class ServiceVendorCostTest(ExpenseBase):
    def setUp(self):
        super().setUp()
        self.svc_cat = ExpenseCategory.objects.get(code='SVC-VENDOR')
        self.invoice = make_invoice(branch=self.sby, invoice_type='visa')
        self.line = InvoiceLine.objects.get(pk=make_service_line(self.invoice, 'Visa', qty=10, price=500).pk)

    def test_vendor_cost_links_to_service_line(self):
        exp = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 3, 1), created_by=self.user, vendor='Muassasah',
            lines=[{'category': self.svc_cat, 'amount': 3000, 'service_line': self.line}],
        )
        el = exp.lines.get()
        self.assertEqual(el.service_line_id, self.line.pk)
        self.assertEqual(el.unit_cost, 300)
        self.assertEqual(el.account_code, '5500-EXP-SVC-VENDOR')
        self.assertEqual(fq.branch_expense_sar('sby'), 3000)

    def test_other_branch_cannot_book_the_cost(self):
        jed = Branch.objects.exclude(pk='sby').first()
        with self.assertRaises(FinanceError):
            expense_service.record_expense(
                branch=jed, expense_date=date(2026, 3, 1), created_by=self.user,
                lines=[{'category': self.svc_cat, 'amount': 3000, 'service_line': self.line}],
            )

    def test_hotel_line_is_not_a_service_line(self):
        hotel = InvoiceLine.objects.get(pk=make_hotel_line(make_invoice(branch=self.sby)).pk)
        with self.assertRaises(FinanceError):
            expense_service.record_expense(
                branch=self.sby, expense_date=date(2026, 3, 1), created_by=self.user,
                lines=[{'category': self.svc_cat, 'amount': 3000, 'service_line': hotel}],
            )

    def test_invoice_context_shows_vendor_cost(self):
        from hw.views.context import _build_visa_services_context
        expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 3, 1), created_by=self.user,
            lines=[{'category': self.svc_cat, 'amount': 3000, 'service_line': self.line}],
        )
        rows = _build_visa_services_context(self.invoice)
        self.assertEqual(rows[0]['vendor_cost_sar'], 3000)
