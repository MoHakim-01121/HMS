"""Laporan cabang (Fase 3): laba cabang = laba kurs saja, biaya operasional
ditampilkan terpisah (diganti Pusat), posisi per akhir periode."""
from datetime import date

from django.test import TestCase

from hw.finance import branch_report as br
from hw.finance import fund_flow
from hw.models.period import Season
from hw.tests import test_fund_flow

TODAY = date(2026, 10, 19)


class PeriodBoundsTest(TestCase):
    def test_month_quarter_year_range_bounds(self):
        m = br.period_bounds('month', '2026-03', today=TODAY)
        self.assertEqual((m['date_from'], m['date_to']), (date(2026, 3, 1), date(2026, 3, 31)))
        self.assertEqual((m['prev']['date_from'], m['prev']['date_to']), (date(2026, 2, 1), date(2026, 2, 28)))
        y = br.period_bounds('year', '2026', today=TODAY)
        self.assertEqual((y['date_from'], y['date_to'], y['prev']['date_from']),
                         (date(2026, 1, 1), date(2026, 12, 31), date(2025, 1, 1)))
        r = br.period_bounds('range', '2026-01-11..2026-01-20', today=TODAY)
        self.assertEqual((r['prev']['date_from'], r['prev']['date_to']), (date(2026, 1, 1), date(2026, 1, 10)))
        bad = br.period_bounds('month', 'nonsense', today=TODAY)
        self.assertEqual((bad['date_from'], bad['date_to']), (date(2026, 10, 1), date(2026, 10, 31)))

    def test_quarter_bounds(self):
        q = br.period_bounds('quarter', '2026-Q1', today=TODAY)
        self.assertEqual((q['date_from'], q['date_to']), (date(2026, 1, 1), date(2026, 3, 31)))
        self.assertEqual((q['prev']['date_from'], q['prev']['date_to']), (date(2025, 10, 1), date(2025, 12, 31)))
        self.assertEqual(br.period_bounds('quarter', '', today=TODAY)['value'], '2026-Q4')

    def test_season_and_first_season_has_no_previous(self):
        first = Season.objects.create(name='1447H', date_from=date(2025, 6, 1), date_to=date(2026, 5, 31))
        second = Season.objects.create(name='1448H', date_from=date(2026, 6, 1), date_to=date(2027, 5, 31))
        s = br.period_bounds('season', str(second.pk), today=TODAY)
        self.assertEqual((s['date_from'], s['label'], s['prev']['label']), (date(2026, 6, 1), '1448H', '1447H'))
        self.assertIsNone(br.period_bounds('season', str(first.pk), today=TODAY)['prev'])

    def test_range_and_season_kinds_stick_without_a_value(self):
        r = br.period_bounds('range', '', today=TODAY)
        self.assertEqual((r['kind'], r['date_from'], r['date_to']), ('range', date(2026, 10, 1), date(2026, 10, 31)))
        s = br.period_bounds('season', '', today=TODAY)      # no season exists
        self.assertEqual((s['kind'], s['value'], s['prev']), ('season', '', None))

    def test_crafted_values_fall_back_instead_of_failing(self):
        for kind, value in (('year', '0000'), ('year', '0001'), ('quarter', '0001-Q1'),
                            ('range', '0001-01-01..0001-01-05'), ('month', '0000-01')):
            p = br.period_bounds(kind, value, today=TODAY)
            self.assertGreaterEqual(p['date_from'].year, 1900, (kind, value))

    def test_profit_delta_only_against_a_positive_base(self):
        self.assertEqual(br.profit_delta(1_500_000, 1_000_000), '+50%')
        self.assertIsNone(br.profit_delta(-500_000, -1_000_000))
        self.assertIsNone(br.profit_delta(500_000, 0))
        self.assertIsNone(br.profit_delta(None, 1_000_000))


class BranchReportTest(TestCase):
    setUp = test_fund_flow.FundFlowScenario.setUp
    _send = test_fund_flow.FundFlowScenario._send
    _spend = test_fund_flow.FundFlowScenario._spend

    def test_profit_is_fx_only_and_expenses_shown_apart(self):
        self._send(95_000_000)
        self._spend(500_000)
        rep = br.branch_report('sby', date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(rep['profit']['fx_idr'], 2_125_000)
        self.assertEqual(rep['expenses']['total'], 500_000)
        self.assertEqual((rep['expenses']['paid_back'], rep['expenses']['claimed'], rep['expenses']['unclaimed']),
                         (0, 0, 500_000))
        fx = fund_flow.fx_profit(branch='sby', date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))
        self.assertEqual(fund_flow.net_profit(fx), 2_125_000)

    def test_period_without_transfers_earns_zero(self):
        rep = br.branch_report('sby', date(2026, 8, 1), date(2026, 8, 31))   # no transfer in August
        self.assertEqual((rep['profit']['fx_idr'], rep['profit']['transfers']), (0, []))

    def test_position_as_of_period_end(self):
        self._send(95_000_000)
        self._spend(500_000)                                    # 12 September
        idr = lambda rep: next(a['native'] for a in rep['position']['accounts'] if a['currency'] == 'IDR')
        before = br.branch_report('sby', date(2026, 9, 1), date(2026, 9, 11))
        after = br.branch_report('sby', date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(idr(before) - idr(after), 500_000)
        self.assertEqual((before['position']['owed_by_hq_idr'], after['position']['owed_by_hq_idr']), (0, 500_000))
        self.assertEqual(after['position']['as_of'], '2026-09-30')

    def test_expense_status_is_read_at_period_end(self):
        """A claim paid after the period still shows as waiting in that period."""
        from hw.finance import claim_service
        from hw.models.branch import Branch
        self._send(95_000_000)
        self._spend(500_000)                                    # 12 September
        claim = claim_service.create_claim(branch=Branch.objects.get(code='sby'), date_from=date(2026, 9, 1),
                                           date_to=date(2026, 9, 30), created_by=self.user)
        claim_service.submit_claim(claim, by=self.user)
        claim_service.mark_paid(claim, account=self.idr, paid_date=date(2026, 10, 5), by=self.user)
        sep = br.branch_report('sby', date(2026, 9, 1), date(2026, 9, 30))['expenses']
        self.assertEqual((sep['paid_back'], sep['claimed']), (0, 500_000))

    def test_position_has_no_unused_ledger_figures(self):
        self.assertNotIn('ledger_sar', br.branch_report('sby', date(2026, 9, 1), date(2026, 9, 30))['position'])
