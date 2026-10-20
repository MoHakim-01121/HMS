"""Payment list search / filter / sort (CL-style filter bar).

The list and the CSV export share _apply_payment_filters, so both are pinned
here: an export taken from a searched list must return the same rows.
"""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Client, PaymentAllocation
from hw.models.payment import PaymentRecord
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_hotel_line, make_invoice, make_payment


class PaymentListFilterTests(TestCase):
    URL = '/finance/payments/'

    def setUp(self):
        self.user = User.objects.create_user('payfilter', password='pw12345')
        self.user.profile.role = 'manager'
        self.user.profile.save(update_fields=['role'])
        self.client.force_login(self.user)
        self.period = FinancialPeriod.objects.create(
            name='2020-2030', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.alpha = Client.objects.create(name='PT Alpha Travel')
        self.beta = Client.objects.create(name='PT Beta Umrah')
        self.invoice = make_invoice(
            invoice_number='INV-FLT-777', customer_name='PT Alpha Travel', client=self.alpha,
        )
        self.p1 = self._pay('PAY-FLT-001', self.alpha, date(2026, 1, 10), 1000, 'pending', invoice=self.invoice)
        self.p2 = self._pay('PAY-FLT-002', self.beta, date(2026, 2, 10), 5000, 'applied', reference='TRX-BCA-555')
        self.p3 = self._pay('PAY-FLT-003', self.beta, date(2026, 3, 10), 3000, 'voided', method='Cash')

    def _pay(self, number, client, pay_date, amount, status, invoice=None, reference='', method='Transfer'):
        # "applied" is not a stored status: it is a confirmed payment whose
        # money is fully allocated to invoice lines.
        applied = status == 'applied'
        payment = make_payment(
            payment_number=number, client=client, invoice=invoice,
            payment_date=pay_date, amount=amount, amount_sar=amount,
            method=method, reference=reference, status='confirmed' if applied else status,
            created_by=self.user,
        )
        if applied:
            line = make_hotel_line(invoice=make_invoice(client=client))
            PaymentAllocation.objects.create(payment=payment, invoice_line=line, amount_sar=amount)
        return payment

    def _numbers(self, query=''):
        # The list opens on the current month; year=all shows every date.
        sep = '&' if query else '?'
        resp = self.client.get(self.URL + query + sep + 'year=all', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        props = resp.json()['props']
        return [p['payment_number'] for p in props['payments']], props

    def test_search_matches_payment_number_client_invoice_reference_method(self):
        self.assertEqual(self._numbers('?q=FLT-001')[0], ['PAY-FLT-001'])
        self.assertEqual(sorted(self._numbers('?q=beta')[0]), ['PAY-FLT-002', 'PAY-FLT-003'])
        self.assertEqual(self._numbers('?q=INV-FLT-777')[0], ['PAY-FLT-001'])
        self.assertEqual(self._numbers('?q=BCA-555')[0], ['PAY-FLT-002'])
        self.assertEqual(self._numbers('?q=cash')[0], ['PAY-FLT-003'])

    def test_search_comma_separated_tokens_are_ored(self):
        rows, _ = self._numbers('?q=FLT-001%2CFLT-003')
        self.assertEqual(sorted(rows), ['PAY-FLT-001', 'PAY-FLT-003'])

    def test_multi_status_group_filter(self):
        rows, props = self._numbers('?status=pending,cancelled')
        self.assertEqual(sorted(rows), ['PAY-FLT-001', 'PAY-FLT-003'])
        self.assertEqual(props['filters']['status'], ['pending', 'cancelled'])

    def test_allocation_groups_follow_the_allocation_rows(self):
        self._pay('PAY-FLT-004', self.alpha, date(2026, 4, 1), 700, 'applied')
        unallocated = self._pay('PAY-FLT-005', self.alpha, date(2026, 4, 2), 900, 'confirmed')
        partial = self._pay('PAY-FLT-006', self.alpha, date(2026, 4, 3), 800, 'confirmed')
        line = make_hotel_line(invoice=make_invoice(client=self.alpha))
        PaymentAllocation.objects.create(payment=partial, invoice_line=line, amount_sar=300)
        self.assertEqual(sorted(self._numbers('?status=allocated')[0]), ['PAY-FLT-002', 'PAY-FLT-004'])
        # "Not fully applied": nothing applied yet, or part of it.
        self.assertEqual(sorted(self._numbers('?status=open')[0]), [unallocated.payment_number, partial.payment_number])
        row = next(p for p in self._numbers()[1]['payments'] if p['payment_number'] == 'PAY-FLT-006')
        self.assertEqual((row['group'], row['unallocated_sar']), ('partial', 500))

    def test_row_carries_group(self):
        _, props = self._numbers()
        row = next(p for p in props['payments'] if p['payment_number'] == 'PAY-FLT-003')
        self.assertEqual((row['group'], row['status']), ('cancelled', 'voided'))

    def test_unknown_status_is_ignored(self):
        rows, props = self._numbers('?status=bogus')
        self.assertEqual(len(rows), 3)
        self.assertEqual(props['filters']['status'], [])

    def test_payment_date_range(self):
        rows, props = self._numbers('?from=2026-02-01&to=2026-02-28')
        self.assertEqual(rows, ['PAY-FLT-002'])

    def test_month(self):
        resp = self.client.get(self.URL + '?month=2026-02', HTTP_X_INERTIA='true').json()['props']
        self.assertEqual([p['payment_number'] for p in resp['payments']], ['PAY-FLT-002'])
        self.assertEqual(resp['kpis']['received'], 5000)

    def test_sort_by_date(self):
        self.assertEqual(self._numbers('?sort=date')[0], ['PAY-FLT-001', 'PAY-FLT-002', 'PAY-FLT-003'])
        self.assertEqual(self._numbers('?sort=-date')[0], ['PAY-FLT-003', 'PAY-FLT-002', 'PAY-FLT-001'])

    def test_status_counts_ignore_the_status_filter(self):
        _, props = self._numbers('?status=pending')
        self.assertEqual(props['counts'], {'pending': 1, 'open': 0, 'allocated': 1, 'cancelled': 1})

    def test_csv_export_honours_search(self):
        resp = self.client.get('/finance/payments/export/csv/?q=beta&status=allocated')
        self.assertEqual(resp.status_code, 200)
        body = b''.join(resp.streaming_content).decode('utf-8') if resp.streaming else resp.content.decode('utf-8')
        self.assertIn('PAY-FLT-002', body)
        self.assertNotIn('PAY-FLT-001', body)
        self.assertNotIn('PAY-FLT-003', body)

    def test_void_payment_shows_no_unallocated_amount(self):
        # p3 is voided with no allocation: the row must not read "3000 unalloc",
        # and unapplied cash only counts effective payments.
        _, props = self._numbers()
        row = next(p for p in props['payments'] if p['payment_number'] == 'PAY-FLT-003')
        self.assertEqual(row['unallocated_sar'], 0)
        kpis = lambda: self.client.get(self.URL + '?month=2026-04', HTTP_X_INERTIA='true').json()['props']['kpis']
        self.assertEqual((kpis()['unapplied_sar'], kpis()['unapplied_count']), (0, 0))
        self._pay('PAY-FLT-007', self.alpha, date(2026, 4, 5), 700, 'confirmed')
        self.assertEqual((kpis()['unapplied_sar'], kpis()['unapplied_count']), (700, 1))

    def test_void_payment_is_not_reported_as_allocated(self):
        resp = self.client.get(f'/finance/payments/{self.p3.pk}/', HTTP_X_INERTIA='true')
        payment = resp.json()['props']['payment']
        self.assertEqual((payment['allocated_sar'], payment['unallocated_sar']), (0, 0))

    def test_every_status_has_a_group(self):
        # _payment_props looks the group up by key: a status added to the model
        # without a group would turn the whole list into a 500.
        from hw.views.payment_views import PAYMENT_STATUS_GROUPS
        from hw.views.payment_views import _group_of
        keys = {key for key, _, _ in PAYMENT_STATUS_GROUPS}
        for value, _label in PaymentRecord.STATUS_CHOICES:
            self.assertIn(_group_of(PaymentRecord(status=value, amount_sar=1)), keys, value)

    def test_partial_reload_skips_dialog_props(self):
        resp = self.client.get(
            self.URL + '?q=beta&year=all', HTTP_X_INERTIA='true',
            HTTP_X_INERTIA_PARTIAL_COMPONENT='Payment/List',
            HTTP_X_INERTIA_PARTIAL_DATA='payments,pagination',
        )
        props = resp.json()['props']
        self.assertEqual(sorted(p['payment_number'] for p in props['payments']), ['PAY-FLT-002', 'PAY-FLT-003'])
        for lazy in ('invoice_choices', 'client_choices', 'account_choices'):
            self.assertNotIn(lazy, props)
