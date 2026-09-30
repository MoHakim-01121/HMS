"""Services list shows each invoice's total — the same figure as its detail page."""
from django.contrib.auth.models import User
from django.test import TestCase

from hw.tests.factories import make_invoice, make_service_line


class ServicesListTotalTest(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser('admin', 'admin@test.com', 'pass'))

    def _rows(self):
        resp = self.client.get('/services/', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        return {r['invoice_number']: r for r in resp.json()['props']['invoices']}

    def test_total_is_sum_of_items_in_invoice_currency(self):
        inv = make_invoice(invoice_type='visa', invoice_number='SVC-T-1',
                                     customer_name='Global Tour', currency='USD')
        make_service_line(invoice=inv, name='Visa', qty=3, price=150)
        make_service_line(invoice=inv, name='Handling', qty=1, price=40)

        row = self._rows()['SVC-T-1']
        self.assertEqual((row['total'], row['currency']), (490, 'USD'))

    def test_invoice_without_items_totals_zero(self):
        make_invoice(invoice_type='visa', invoice_number='SVC-T-2',
                               customer_name='Global Tour')
        self.assertEqual(self._rows()['SVC-T-2']['total'], 0)
