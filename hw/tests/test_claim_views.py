"""Halaman klaim penggantian: Finance cabang membuat, mengajukan, mencatat
penolakan atau lunasnya (Pusat tidak memakai HMS, jawaban user 2026-10-19)."""
import calendar
import json
from datetime import date

from django.test import TestCase

from hw.models import ExpenseClaim
from hw.models.branch import Branch
from hw.models.period import FinancialPeriod
from hw.models.user import Role
from hw.tests.factories import fund_account, make_account, paid_expense
from hw.tests.test_branch_scope import make_user


def _props(resp):
    return json.loads(resp.context['page'])['props']


class ClaimViewsTest(TestCase):
    def setUp(self):
        for m in range(1, 13):
            FinancialPeriod.objects.create(name=f'2026-{m:02d}', date_from=date(2026, m, 1),
                                           date_to=date(2026, m, calendar.monthrange(2026, m)[1]))
        self.finance = make_user('claim-fin', Role.FINANCE.value, branch='sby')
        self.idr = make_account('sby', 'IDR')
        fund_account(self.idr, 95_000_000, 20_000, date(2026, 1, 1), self.finance)
        sby = Branch.objects.get(code='sby')
        self.e1, _ = paid_expense(sby, self.idr, 1_000_000, date(2026, 1, 15), self.finance, description='Listrik Jan')
        self.e2, _ = paid_expense(sby, self.idr, 2_000_000, date(2026, 2, 15), self.finance, description='Sewa Feb')
        self.client.force_login(self.finance)

    def _new(self, **extra):
        return self.client.post('/finance/claims/new/', {'date_from': '2026-01-01', 'date_to': '2026-02-28', **extra})

    def test_new_preview_lists_claimable(self):
        props = _props(self.client.get('/finance/claims/new/', {'date_from': '2026-01-01', 'date_to': '2026-01-31'}))
        self.assertEqual([e['id'] for e in props['expenses']], [self.e1.pk])
        self.assertEqual(props['total_amount'], 1_000_000)

    def test_branch_finance_creates_and_submits(self):
        resp = self._new(exclude=[str(self.e2.pk)])
        claim = ExpenseClaim.objects.get()
        self.assertRedirects(resp, f'/finance/claims/{claim.pk}/', fetch_redirect_response=False)
        self.assertEqual(claim.total_amount, 1_000_000)
        self.client.post(f'/finance/claims/{claim.pk}/submit/')
        self.assertEqual(ExpenseClaim.objects.get().status, ExpenseClaim.STATUS_SUBMITTED)

    def test_finance_records_paid_and_unpays(self):
        self._new()
        claim = ExpenseClaim.objects.get()
        self.client.post(f'/finance/claims/{claim.pk}/submit/')
        self.client.post(f'/finance/claims/{claim.pk}/pay/', {
            'account': f'bank:{self.idr.pk}', 'paid_date': '2026-03-05', 'reference': 'TRF-9',
        })
        claim.refresh_from_db()
        self.assertEqual((claim.status, claim.paid_date), (ExpenseClaim.STATUS_PAID, date(2026, 3, 5)))
        self.client.post(f'/finance/claims/{claim.pk}/unpay/', {'reason': 'salah tanggal'})
        self.assertEqual(ExpenseClaim.objects.get().status, ExpenseClaim.STATUS_SUBMITTED)

    def test_reject_needs_a_reason(self):
        self._new()
        claim = ExpenseClaim.objects.get()
        self.client.post(f'/finance/claims/{claim.pk}/submit/')
        self.client.post(f'/finance/claims/{claim.pk}/reject/', {'reason': ''})
        self.assertEqual(ExpenseClaim.objects.get().status, ExpenseClaim.STATUS_SUBMITTED)
        self.client.post(f'/finance/claims/{claim.pk}/reject/', {'reason': 'nota kurang'})
        self.assertEqual(ExpenseClaim.objects.get().status, ExpenseClaim.STATUS_REJECTED)

    def test_staff_cannot_pay(self):
        self._new()
        claim = ExpenseClaim.objects.get()
        self.client.post(f'/finance/claims/{claim.pk}/submit/')
        self.client.force_login(make_user('claim-staff', Role.STAFF.value, branch='sby'))
        self.client.post(f'/finance/claims/{claim.pk}/pay/', {'account': f'bank:{self.idr.pk}', 'paid_date': '2026-03-05'})
        self.assertEqual(ExpenseClaim.objects.get().status, ExpenseClaim.STATUS_SUBMITTED)

    def test_manager_cannot_pay(self):
        # Managers approve expenses, but booking money is Finance's (bank).
        self._new()
        claim = ExpenseClaim.objects.get()
        self.client.post(f'/finance/claims/{claim.pk}/submit/')
        self.client.force_login(make_user('claim-mgr', Role.MANAGER.value, branch='sby'))
        self.client.post(f'/finance/claims/{claim.pk}/pay/', {'account': f'bank:{self.idr.pk}', 'paid_date': '2026-03-05'})
        self.assertEqual(ExpenseClaim.objects.get().status, ExpenseClaim.STATUS_SUBMITTED)

    def test_other_branch_cannot_see_claim(self):
        self._new()
        claim = ExpenseClaim.objects.get()
        self.client.force_login(make_user('claim-jkt', Role.FINANCE.value, branch='jkt'))
        self.assertEqual(self.client.get(f'/finance/claims/{claim.pk}/').status_code, 404)
        self.assertEqual(_props(self.client.get('/finance/claims/'))['claims'], [])

    def _json(self, url, data):
        return self.client.post(url, json.dumps(data), content_type='application/json')

    def test_inertia_json_posts(self):
        """Inertia's router.post sends JSON, not form data."""
        self._json('/finance/claims/new/', {'date_from': '2026-01-01', 'date_to': '2026-02-28',
                                            'exclude': [self.e2.pk], 'note': 'Jan saja'})
        claim = ExpenseClaim.objects.get()
        self.assertEqual((claim.date_to, claim.total_amount, claim.note), (date(2026, 2, 28), 1_000_000, 'Jan saja'))
        self._json(f'/finance/claims/{claim.pk}/submit/', {})
        self._json(f'/finance/claims/{claim.pk}/pay/', {'account': f'bank:{self.idr.pk}', 'paid_date': '2026-03-05'})
        self.assertEqual(ExpenseClaim.objects.get().status, ExpenseClaim.STATUS_PAID)
        self._json(f'/finance/claims/{claim.pk}/unpay/', {'reason': 'salah'})
        self.assertEqual(ExpenseClaim.objects.get().status, ExpenseClaim.STATUS_SUBMITTED)
        self._json(f'/finance/claims/{claim.pk}/reject/', {'reason': 'nota kurang'})
        self.assertEqual(ExpenseClaim.objects.get().status, ExpenseClaim.STATUS_REJECTED)

    def test_claim_list_query_count_does_not_grow(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from hw.finance import claim_service as svc
        sby = Branch.objects.get(code='sby')

        def add(n):
            for i in range(n):
                day = date(2026, 3 + len(ExpenseClaim.objects.all()) % 9, 10)
                paid_expense(sby, self.idr, 100_000, day, self.finance)
                svc.create_claim(branch=sby, date_from=day, date_to=day, created_by=self.finance)

        def count():
            self.client.get('/finance/claims/')
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.client.get('/finance/claims/').status_code, 200)
            return len(ctx.captured_queries)

        add(2)
        few = count()
        add(5)
        self.assertEqual(few, count())

    def test_list_detail_csv_and_pdf_render(self):
        self._new()
        claim = ExpenseClaim.objects.get()
        listing = _props(self.client.get('/finance/claims/'))
        self.assertEqual([c['claim_number'] for c in listing['claims']], [claim.claim_number])
        self.assertEqual(listing['kpis']['claimed'], 3_000_000)
        detail = _props(self.client.get(f'/finance/claims/{claim.pk}/'))
        self.assertEqual([i['expense_number'] for i in detail['claim']['items']],
                         [self.e1.expense_number, self.e2.expense_number])
        csv = self.client.get(f'/finance/claims/{claim.pk}/export/csv/')
        self.assertEqual(csv.status_code, 200)
        self.assertIn(self.e1.expense_number, csv.content.decode())
        pdf = self.client.get(f'/finance/claims/{claim.pk}/pdf/')
        self.assertEqual((pdf.status_code, pdf['Content-Type']), (200, 'application/pdf'))
