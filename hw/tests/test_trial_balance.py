"""Trial balance: opening, movement and closing per account. Balance-sheet
accounts carry their balance forward; income and expense start each
financial year (January–December) at zero, the years before rolled into
Retained Earnings by a virtual year-end close (no closing journal)."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import accounts as coa
from hw.finance import queries as q
from hw.models.journal import JournalEntry, JournalLine
from hw.models.period import FinancialPeriod


class TrialBalanceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('tb', password='x', is_superuser=True)
        cls.periods = {y: FinancialPeriod.objects.create(name=f'TB-{y}', date_from=date(y, 1, 1), date_to=date(y, 12, 31))
                       for y in (2025, 2026, 2027)}
        cls.n = 0
        # 2025: 1000 hotel income sold on credit, 100 bank fee paid in cash.
        cls._je(date(2025, 3, 1), (coa.AR, 1000), (coa.INC_HOTEL, -1000))
        cls._je(date(2025, 4, 1), (coa.EXP_BANKFEE, 100), (coa.CASH_SBY, -100))
        # 2026: the 1000 collected, 500 more income.
        cls._je(date(2026, 2, 1), (coa.CASH_SBY, 1000), (coa.AR, -1000))
        cls._je(date(2026, 7, 1), (coa.AR, 500), (coa.INC_HOTEL, -500))
        # 2027: 200 more income.
        cls._je(date(2027, 1, 15), (coa.AR, 200), (coa.INC_HOTEL, -200))

    @classmethod
    def _je(cls, d, *legs):
        cls.n += 1
        je = JournalEntry.objects.create(
            entry_number=f'JE-TB{cls.n:04d}', entry_type=JournalEntry.TYPE_ADJUSTMENT,
            description='tb', entry_date=d, period=cls.periods[d.year], created_by=cls.user)
        for i, (account, amount) in enumerate(legs, start=1):
            JournalLine.objects.create(journal_entry=je, line_no=i, account_id=account,
                                       debit=max(amount, 0), credit=max(-amount, 0))

    def _rows(self, **kw):
        tb = q.trial_balance(**kw)
        self.assertTrue(tb['balanced'])
        return tb, {r['account']: r for r in tb['rows']}

    def test_every_row_adds_up(self):
        tb, rows = self._rows(date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        for r in tb['rows']:
            self.assertEqual(r['opening'] + r['debit'] - r['credit'], r['closing'], r['account'])

    def test_balance_sheet_accounts_carry_their_balance_forward(self):
        _, rows = self._rows(date_from=date(2026, 6, 1), date_to=date(2026, 12, 31))
        cash = rows[coa.CASH_SBY]
        self.assertEqual((cash['opening'], cash['debit'], cash['credit'], cash['closing']), (900, 0, 0, 900))
        self.assertEqual(rows[coa.AR]['closing'], 500)

    def test_income_starts_the_financial_year_at_zero(self):
        _, rows = self._rows(date_from=date(2026, 6, 1), date_to=date(2026, 12, 31))
        self.assertEqual(rows[coa.INC_HOTEL]['opening'], 0)
        self.assertEqual(rows[coa.INC_HOTEL]['closing'], -500)
        self.assertNotIn(coa.EXP_BANKFEE, rows)
        # 2025: income 1000 less the 100 fee.
        self.assertEqual(rows[coa.RETAINED_EARNINGS]['opening'], -900)
        self.assertEqual(rows[coa.RETAINED_EARNINGS]['closing'], -900)

    def test_a_range_across_new_year_closes_the_year_inside_it(self):
        # A season: June 2026 to May 2027.
        tb, rows = self._rows(date_from=date(2026, 6, 1), date_to=date(2027, 5, 31))
        inc = rows[coa.INC_HOTEL]
        # 500 earned in 2026 is closed out on 31 Dec; only 2027's 200 is left.
        self.assertEqual((inc['opening'], inc['debit'], inc['credit'], inc['closing']), (0, 500, 700, -200))
        re = rows[coa.RETAINED_EARNINGS]
        self.assertEqual((re['opening'], re['debit'], re['credit'], re['closing']), (-900, 0, 500, -1400))
        self.assertEqual(tb['year_ends'], ['2026-12-31'])

    def test_no_range_reads_everything_up_to_today_as_of_the_last_year(self):
        tb, rows = self._rows()
        self.assertEqual(rows[coa.INC_HOTEL]['closing'], -200)
        self.assertEqual(rows[coa.RETAINED_EARNINGS]['closing'], -1400)
        self.assertEqual(sum(r['closing'] for r in tb['rows']), 0)
