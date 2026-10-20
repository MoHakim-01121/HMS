"""Branch expenses (decided 2026-10-11): rupiah only, recorded by Finance,
approved, then paid from one of the branch's rupiah accounts at that
account's own carrying rate. Nothing reaches the books before payment."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import expense_service, queries as fq
from hw.finance.accounts import cash_ledger_for
from hw.finance.errors import FinanceError
from hw.models import (
    BankAccount, BankTransaction, Branch, CashAccount, Expense, ExpenseCategory, ExpensePayment,
    Vendor,
)
from hw.models.journal import JournalEntry, JournalLine, LedgerAccount
from hw.models.period import FinancialPeriod
from hw.tests.factories import fund_account, paid_expense

DAY = date(2026, 9, 10)


class ExpenseBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('exp', password='pw12345')
        FinancialPeriod.objects.create(name='2020-2030', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31))
        self.sby = Branch.objects.get(code='sby')
        self.util = ExpenseCategory.objects.get(code='UTIL')
        self.idr = BankAccount.objects.create(branch_id='sby', name='IDR', currency='IDR', bank_name='Mandiri',
                                              account_identifier='111', ledger_account_id=cash_ledger_for('sby', 'IDR'))
        # 100 jt rupiah worth 20.000 SAR on the books: an average of 5.000 per riyal.
        fund_account(self.idr, 100_000_000, 20_000, date(2026, 9, 1), self.user)

    def _submit(self, amount=10_000_000, **kw):
        return expense_service.submit_expense(
            branch=self.sby, expense_date=DAY, created_by=self.user, vendor=kw.pop('vendor', 'PLN'),
            lines=kw.pop('lines', [{'category': self.util, 'amount': amount}]), **kw,
        )

    def _ledger(self, account):
        lines = JournalLine.objects.filter(account_id=account.ledger_account_id)
        native = sum((l.amount_txn or 0) * (1 if l.debit else -1) for l in lines)
        return native, sum(l.debit - l.credit for l in lines)

    def _cash_book(self, account):
        rows = BankTransaction.objects.filter(account=account).exclude(status=BankTransaction.STATUS_VOIDED)
        return sum(r.amount if r.direction == 'in' else -r.amount for r in rows)


class SeedTest(ExpenseBase):
    def test_salary_has_its_own_category_and_account(self):
        salary = ExpenseCategory.objects.get(code='SALARY')
        self.assertEqual((salary.name, salary.ledger_account_id), ('Gaji & Honor', '5400-EXP-SALARY'))
        self.assertEqual(ExpenseCategory.objects.count(), 11)


class FlowTest(ExpenseBase):
    def test_submitted_expense_waits_and_touches_nothing(self):
        exp = self._submit()
        self.assertEqual((exp.status, exp.currency, exp.total_amount, exp.total_amount_sar),
                         (Expense.STATUS_SUBMITTED, 'IDR', 10_000_000, 0))
        self.assertFalse(JournalEntry.objects.filter(entry_type=JournalEntry.TYPE_EXPENSE).exists())
        self.assertEqual(self._cash_book(self.idr), 100_000_000)

    def test_the_recorder_may_approve_it(self):
        exp = expense_service.approve_expense(self._submit(), approved_by=self.user)
        self.assertEqual((exp.status, exp.decided_by), (Expense.STATUS_APPROVED, self.user))
        with self.assertRaises(FinanceError):
            expense_service.approve_expense(exp, approved_by=self.user)

    def test_payment_is_valued_at_the_accounts_carrying_rate(self):
        exp = expense_service.approve_expense(self._submit(), approved_by=self.user)
        ep = expense_service.pay_expense(exp, account=self.idr, payment_date=DAY, paid_by=self.user, reference='TRF1')
        exp.refresh_from_db()
        # 10 jt at the account's 5.000 per riyal: 2.000 SAR, whatever anyone types.
        self.assertEqual((exp.status, ep.amount, ep.amount_sar, exp.total_amount_sar),
                         (Expense.STATUS_PAID, 10_000_000, 2_000, 2_000))
        # The rest keeps its rate: 90 jt worth 18.000 SAR, still 5.000 per riyal.
        self.assertEqual(self._ledger(self.idr), (90_000_000, 18_000))
        self.assertEqual(self._cash_book(self.idr), 90_000_000)
        entry = JournalEntry.objects.for_source('ExpensePayment', ep.pk).get()
        self.assertTrue(entry.is_balanced)
        self.assertEqual(entry.entry_date, DAY)
        self.assertEqual(fq.branch_expense_sar('sby'), 2_000)

    def test_several_lines_share_the_value(self):
        meals = ExpenseCategory.objects.get(code='MEALS')
        exp = self._submit(lines=[{'category': self.util, 'amount': 3_000_000},
                                  {'category': meals, 'amount': 1_000_001}])
        expense_service.approve_expense(exp, approved_by=self.user)
        ep = expense_service.pay_expense(exp, account=self.idr, payment_date=DAY, paid_by=self.user)
        shares = list(exp.lines.order_by('pk').values_list('amount_sar', flat=True))
        self.assertEqual(sum(shares), ep.amount_sar)
        self.assertEqual(shares[0], 600)

    def test_rejected_expense_leaves_nothing(self):
        exp = expense_service.reject_expense(self._submit(), rejected_by=self.user, reason='dobel')
        self.assertEqual((exp.status, exp.decision_note), (Expense.STATUS_REJECTED, 'dobel'))
        with self.assertRaises(FinanceError):
            expense_service.approve_expense(exp, approved_by=self.user)
        self.assertFalse(JournalEntry.objects.filter(entry_type=JournalEntry.TYPE_EXPENSE).exists())

    def test_void_reverses_the_payment(self):
        exp, ep = paid_expense(self.sby, self.idr, 10_000_000, DAY, self.user)
        expense_service.void_expense(exp, voided_by=self.user, reason='salah input')
        exp.refresh_from_db()
        ep.refresh_from_db()
        self.assertEqual((exp.status, ep.status), (Expense.STATUS_VOIDED, ExpensePayment.STATUS_VOID))
        self.assertEqual(self._ledger(self.idr), (100_000_000, 20_000))
        self.assertEqual(self._cash_book(self.idr), 100_000_000)
        with self.assertRaises(FinanceError):
            expense_service.void_expense(exp, voided_by=self.user)


class PaymentGuardTest(ExpenseBase):
    def _approved(self, amount=10_000_000):
        return expense_service.approve_expense(self._submit(amount), approved_by=self.user)

    def test_unapproved_expense_is_not_paid(self):
        with self.assertRaises(FinanceError):
            expense_service.pay_expense(self._submit(), account=self.idr, payment_date=DAY, paid_by=self.user)

    def test_paid_from_a_rupiah_account_of_its_branch(self):
        sar_cash = CashAccount.objects.get(branch_id='sby')
        with self.assertRaisesMessage(FinanceError, 'rupiah'):
            expense_service.pay_expense(self._approved(), account=sar_cash, payment_date=DAY, paid_by=self.user)
        Branch.objects.filter(code='jkt').update(is_active=True)
        jkt_idr = BankAccount.objects.create(branch_id='jkt', name='IDR JKT', currency='IDR', bank_name='BCA',
                                             account_identifier='222', ledger_account_id=cash_ledger_for('jkt', 'IDR'))
        with self.assertRaisesMessage(FinanceError, 'cabang lain'):
            expense_service.pay_expense(self._approved(), account=jkt_idr, payment_date=DAY, paid_by=self.user)

    def test_rupiah_the_account_does_not_hold_is_refused(self):
        with self.assertRaises(FinanceError):
            expense_service.pay_expense(self._approved(150_000_000), account=self.idr, payment_date=DAY,
                                        paid_by=self.user)
        self.assertEqual(self._cash_book(self.idr), 100_000_000)

    def test_head_office_records_no_expenses(self):
        with self.assertRaisesMessage(FinanceError, 'Pusat'):
            expense_service.submit_expense(branch=Branch.objects.get(code='pusat'), expense_date=DAY,
                                           created_by=self.user, lines=[{'category': self.util, 'amount': 1}])

    def test_line_amount_must_be_positive(self):
        with self.assertRaises(FinanceError):
            self._submit(lines=[{'category': self.util, 'amount': 0}])


class VendorTest(ExpenseBase):
    def test_vendor_name_resolves_to_one_master_row(self):
        self._submit(vendor='PT. Safaar')
        self._submit(vendor='SAFAAR')
        self.assertEqual(Vendor.objects.count(), 1)

    def test_no_vendor_is_allowed(self):
        self.assertIsNone(self._submit(vendor='').vendor)

class CategoryTest(ExpenseBase):
    def test_a_new_category_gets_its_own_account(self):
        cat = expense_service.create_category('Komisi Sales')
        self.assertEqual((cat.code, cat.ledger_account_id), ('KOMISI-SALE', '5510-EXP-KOMISI-SALE'))
        self.assertEqual(LedgerAccount.objects.get(code=cat.ledger_account_id).type, 'expense')
        second = expense_service.create_category('Asuransi')
        self.assertEqual(second.ledger_account_id, '5520-EXP-ASURANSI')
        with self.assertRaises(FinanceError):
            expense_service.create_category('komisi sales')

    def test_rename_and_deactivate(self):
        cat = expense_service.create_category('Parkir')
        expense_service.update_category(cat, name='Parkir & Tol', is_active=False)
        cat.refresh_from_db()
        self.assertEqual((cat.name, cat.is_active, cat.ledger_account.name), ('Parkir & Tol', False, 'Beban Parkir & Tol'))
