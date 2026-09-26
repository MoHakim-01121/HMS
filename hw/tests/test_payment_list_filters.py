"""Payment list search / filter / sort (CL-style filter bar).

The list and the CSV export share _apply_payment_filters, so both are pinned
here: an export taken from a searched list must return the same rows.
"""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Client, Invoice
from hw.models.payment import PaymentRecord
from hw.models.period import FinancialPeriod


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
        self.invoice = Invoice.objects.create(
            invoice_number='INV-FLT-777', customer_name='PT Alpha Travel', client=self.alpha,
        )
        self.p1 = self._pay('PAY-FLT-001', self.alpha, date(2026, 1, 10), 1000, 'pending', invoice=self.invoice)
        self.p2 = self._pay('PAY-FLT-002', self.beta, date(2026, 2, 10), 5000, 'applied', reference='TRX-BCA-555')
        self.p3 = self._pay('PAY-FLT-003', self.beta, date(2026, 3, 10), 3000, 'voided', method='Cash')

    def _pay(self, number, client, pay_date, amount, status, invoice=None, reference='', method='Transfer'):
        return PaymentRecord.objects.create(
            payment_number=number, client=client, invoice=invoice,
            payment_date=pay_date, amount=amount, amount_sar=amount,
            method=method, reference=reference, status=status,
            period=self.period, created_by=self.user,
        )

    def _numbers(self, query=''):
        resp = self.client.get(self.URL + query, HTTP_X_INERTIA='true')
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
        rows, _ = self._numbers('?q=FLT-001,FLT-003')
        self.assertEqual(sorted(rows), ['PAY-FLT-001', 'PAY-FLT-003'])

    def test_multi_status_group_filter(self):
        rows, props = self._numbers('?status=pending&status=cancelled')
        self.assertEqual(sorted(rows), ['PAY-FLT-001', 'PAY-FLT-003'])
        self.assertEqual(props['status_list'], ['pending', 'cancelled'])
        self.assertEqual(props['active_filters'], 1)

    def test_allocated_group_includes_legacy_allocated_status(self):
        self._pay('PAY-FLT-004', self.alpha, date(2026, 4, 1), 700, 'allocated')
        rows, _ = self._numbers('?status=allocated')
        self.assertEqual(sorted(rows), ['PAY-FLT-002', 'PAY-FLT-004'])

    def test_raw_status_from_old_link_maps_to_its_group(self):
        rows, props = self._numbers('?status=voided')
        self.assertEqual(rows, ['PAY-FLT-003'])
        self.assertEqual(props['status_list'], ['cancelled'])

    def test_row_carries_group_label(self):
        _, props = self._numbers()
        row = next(p for p in props['payments'] if p['payment_number'] == 'PAY-FLT-003')
        self.assertEqual((row['status_group'], row['status_group_label'], row['status_group_tone']),
                         ('cancelled', 'Cancelled', 'gray'))

    def test_unknown_status_is_ignored(self):
        rows, props = self._numbers('?status=bogus')
        self.assertEqual(len(rows), 3)
        self.assertEqual(props['status_list'], [])

    def test_payment_date_range(self):
        rows, props = self._numbers('?date_from=2026-02-01&date_to=2026-02-28')
        self.assertEqual(rows, ['PAY-FLT-002'])
        self.assertEqual((props['date_from'], props['date_to']), ('2026-02-01', '2026-02-28'))
        self.assertEqual(props['active_filters'], 1)

    def test_sort_options(self):
        self.assertEqual(self._numbers('?sort=payment_date')[0], ['PAY-FLT-001', 'PAY-FLT-002', 'PAY-FLT-003'])
        self.assertEqual(self._numbers('?sort=-payment_date')[0], ['PAY-FLT-003', 'PAY-FLT-002', 'PAY-FLT-001'])
        self.assertEqual(self._numbers('?sort=-amount_sar')[0], ['PAY-FLT-002', 'PAY-FLT-003', 'PAY-FLT-001'])
        _, props = self._numbers('?sort=nonsense')
        self.assertEqual(props['sort'], '-created_at')

    def test_status_counts_ignore_active_filters(self):
        _, props = self._numbers('?q=FLT-001')
        counts = {g['key']: g['count'] for g in props['status_groups']}
        self.assertEqual(counts, {'pending': 1, 'unallocated': 0, 'partial': 0, 'allocated': 1, 'cancelled': 1})
        self.assertEqual(props['total_count'], 1)

    def test_csv_export_honours_search(self):
        resp = self.client.get('/finance/payments/export/csv/?q=beta&status=allocated')
        self.assertEqual(resp.status_code, 200)
        body = b''.join(resp.streaming_content).decode('utf-8') if resp.streaming else resp.content.decode('utf-8')
        self.assertIn('PAY-FLT-002', body)
        self.assertNotIn('PAY-FLT-001', body)
        self.assertNotIn('PAY-FLT-003', body)

    def test_void_payment_shows_no_unallocated_amount(self):
        # p3 is voided with no allocation: the row must not read "3000 unalloc",
        # and the unapplied stat must only count effective payments (p2 here).
        _, props = self._numbers()
        row = next(p for p in props['payments'] if p['payment_number'] == 'PAY-FLT-003')
        self.assertEqual(row['unallocated_sar'], 0)
        self.assertEqual(props['stats']['unapplied_total'], 5000)
        self.assertEqual(props['stats']['unapplied_count'], 1)

    def test_void_payment_is_not_reported_as_allocated(self):
        resp = self.client.get(f'/finance/payments/{self.p3.pk}/', HTTP_X_INERTIA='true')
        payment = resp.json()['props']['payment']
        self.assertEqual((payment['allocated_sar'], payment['unallocated_sar']), (0, 0))

    def test_every_status_has_a_group(self):
        # _payment_props looks the group up by key: a status added to the model
        # without a group would turn the whole list into a 500.
        from hw.views.payment_views import PAYMENT_STATUS_GROUPS
        grouped = {st for _, _, _, statuses in PAYMENT_STATUS_GROUPS for st in statuses}
        self.assertEqual(grouped, {value for value, _ in PaymentRecord.STATUS_CHOICES})

    def test_partial_reload_skips_dialog_and_stats_props(self):
        resp = self.client.get(
            self.URL + '?q=beta', HTTP_X_INERTIA='true',
            HTTP_X_INERTIA_PARTIAL_COMPONENT='Payment/List',
            HTTP_X_INERTIA_PARTIAL_DATA='payments,pagination,q',
        )
        props = resp.json()['props']
        self.assertEqual(sorted(p['payment_number'] for p in props['payments']), ['PAY-FLT-002', 'PAY-FLT-003'])
        for lazy in ('invoice_choices', 'client_choices', 'account_choices', 'stats'):
            self.assertNotIn(lazy, props)
