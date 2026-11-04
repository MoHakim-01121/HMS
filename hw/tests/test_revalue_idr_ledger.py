"""revalue_idr_ledger: a legacy remittance credited at its full SAR is revalued
at the account's average, the gap becomes branch FX gain, and an expense paid
later at the broken average follows.

Scenario: 120,000,000 IDR held at 25,000 SAR (4,800). Legacy RMT 95,000,000 IDR
→ 20,000 SAR booked at 20,000; its carrying value is 19,792, so 208 SAR gain is
missing. Expense 1,000,000 IDR paid afterwards was valued 200 (5,000 SAR /
25,000,000 IDR); at the corrected average (5,208 / 25,000,000) it is 208."""
from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.test import TestCase

from hw.finance import accounts as coa
from hw.finance import posting
from hw.models import BankTransaction
from hw.models.journal import JournalLine
from hw.models.period import FinancialPeriod
from hw.tests.factories import fund_account, make_account, make_remittance, paid_expense

LEDGER = '1000-KAS-SBY-IDR'


def _sum(account, **filters):
    rows = JournalLine.objects.filter(account_id=account, **filters)
    return sum(r.debit - r.credit for r in rows)


class RevalueIdrLedgerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('rv', password='pw12345')
        FinancialPeriod.objects.create(name='2026', date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        self.idr = make_account('sby', 'IDR')
        fund_account(self.idr, 120_000_000, 25_000, date(2026, 6, 1), self.user)
        self.rem = make_remittance(from_account=self.idr, amount_sent=95_000_000, exchange_rate=Decimal(4750),
                                   date=date(2026, 6, 6), is_legacy=True)
        posting.post_remittance_send(self.rem, amount_sar=20_000, created_by=self.user)
        self.exp, self.ep = paid_expense(self.idr.branch, self.idr, 1_000_000, date(2026, 6, 10), self.user)

    def test_dry_run_writes_nothing(self):
        out = StringIO()
        call_command('revalue_idr_ledger', stdout=out)
        self.assertIn(f'{LEDGER}: 4,800 SAR → 5,000 SAR', out.getvalue())
        self.assertEqual(_sum(coa.INC_FX_GAIN), 0)
        self.assertEqual(_sum(LEDGER), 4_800)

    def test_commit_books_gain_and_revalues_expense(self):
        self.assertEqual(self.ep.amount_sar, 200)
        call_command('revalue_idr_ledger', '--commit', stdout=StringIO())
        self.assertEqual(-_sum(coa.INC_FX_GAIN, branch_id='sby'), 208)
        self.assertEqual(_sum(LEDGER), 25_000 - 19_792 - 208)
        self.ep.refresh_from_db()
        self.assertEqual(self.ep.amount_sar, 208)
        self.assertEqual(sum(line.amount_sar for line in self.exp.lines.all()), 208)
        bt = BankTransaction.objects.get(source_type='ExpensePayment', source_id=self.ep.pk)
        self.assertEqual(bt.amount_sar, 208)
        self.assertEqual(posting.carrying_sar(self.idr, 24_000_000, date(2026, 6, 30)), 5_000)

    def test_second_commit_is_refused(self):
        call_command('revalue_idr_ledger', '--commit', stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command('revalue_idr_ledger', '--commit', stdout=StringIO())
