"""Halaman Laporan Cabang (Fase 3)."""
import json

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from hw.models import Client
from hw.models.user import Role
from hw.tests import test_fund_flow
from hw.tests.factories import make_account
from hw.tests.test_branch_scope import make_user


def _props(resp):
    return json.loads(resp.context['page'])['props']


class BranchReportViewTest(TestCase):
    setUp = test_fund_flow.FundFlowScenario.setUp
    _send = test_fund_flow.FundFlowScenario._send

    def test_report_renders_month_and_quarter(self):
        self._send(95_000_000)
        month = _props(self.client.get('/finance/branch-report/', {'kind': 'month', 'value': '2026-09'}))
        self.assertEqual((month['branch'], month['period']['value']), ('sby', '2026-09'))
        self.assertEqual(month['report']['profit']['fx_idr'], 2_125_000)
        self.assertEqual(month['previous']['fx_idr'], 0)
        quarter = _props(self.client.get('/finance/branch-report/', {'kind': 'quarter', 'value': '2026-Q3'}))
        self.assertEqual((quarter['period']['date_from'], quarter['period']['prev']['label']), ('2026-07-01', 'Q2 2026'))
        self.assertNotIn('pusat', [b['value'] for b in month['branch_choices']])

    def test_admin_looking_at_head_office_sees_the_branches(self):
        """Pusat is picked in the sidebar: the report still lists the branches."""
        from hw.active_branch import SESSION_KEY
        session = self.client.session
        session[SESSION_KEY] = 'pusat'
        session.save()
        resp = self.client.get('/finance/branch-report/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(_props(resp)['branch'], 'sby')

    def test_other_branch_refused(self):
        self.client.force_login(make_user('br-jkt', Role.FINANCE.value, branch='jkt'))
        self.assertEqual(self.client.get('/finance/branch-report/', {'branch': 'sby'}).status_code, 404)
        # Jakarta does not run on HMS yet (inactive): nothing to report for this
        # user, so the page sends them to Fund Flow with a note, and the menu hides it.
        self.assertRedirects(self.client.get('/finance/branch-report/'), '/finance/fund-flow/',
                             fetch_redirect_response=False)
        self.assertFalse(self._shared_user()['report_branches'])
        self.client.force_login(make_user('br-sby', Role.FINANCE.value, branch='sby'))
        props = _props(self.client.get('/finance/branch-report/'))
        self.assertEqual([b['value'] for b in props['branch_choices']], ['sby'])
        self.assertTrue(props['auth']['user']['report_branches'])

    def _shared_user(self):
        return _props(self.client.get('/finance/fund-flow/'))['auth']['user']

    def test_csv_names_unpriced_profit(self):
        from datetime import date

        from hw.finance import posting
        from hw.tests.factories import make_remittance
        rem = make_remittance(from_account=self.idr, amount_sent=4_750_000, exchange_rate=4750,
                              date=date(2026, 9, 20), remittance_number='RMT-OLD', is_legacy=True)
        posting.resync_remittance(rem, created_by=self.user)
        text = self.client.get('/finance/branch-report/export/csv/', {'kind': 'month', 'value': '2026-09'}).content.decode()
        self.assertIn('Not priced', text)

    def test_csv(self):
        self._send(95_000_000)
        resp = self.client.get('/finance/branch-report/export/csv/', {'kind': 'month', 'value': '2026-09'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('2125000', resp.content.decode().replace(',', ''))

    def test_query_count_does_not_grow(self):
        self._send(95_000_000)

        def count():
            self.client.get('/finance/branch-report/', {'kind': 'month', 'value': '2026-09'})
            with CaptureQueriesContext(connection) as ctx:
                self.client.get('/finance/branch-report/', {'kind': 'month', 'value': '2026-09'})
            return len(ctx.captured_queries)

        few = count()
        for i in range(4):
            make_account('sby', ['USD', 'SAR', 'IDR', 'USD'][i])
            Client.objects.create(name=f'PT Count {i}')
        self.assertEqual(few, count())
