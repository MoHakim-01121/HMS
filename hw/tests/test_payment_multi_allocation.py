"""Multi-row allocation save from the Finance "Record Payment" dialog.

An invoice with several reservations gets one PaymentRecord per filled
allocation row. Regression guard for two ways this read as "only the
first row saved": a bad import crashed the whole POST (nothing saved),
and the success redirect landed on created_payments[0]'s detail page
(every row saved, but only row one was visible).
"""
import json
from datetime import date

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import TestCase

from hw.models import Client, Invoice, Reservation, PaymentRecord
from hw.models.period import FinancialPeriod


class MultiAllocationSaveTest(TestCase):
    def setUp(self):
        u = User.objects.create_user('multi_alloc', password='pw12345')
        u.profile.role = 'manager'
        u.profile.save(update_fields=['role'])
        self.client.force_login(u)
        s = self.client.session
        s['active_company'] = 'konoz'
        s.save()

        c = Client.objects.create(company='konoz', name='PT Multi')
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel', client=c,
            invoice_number='INV-MULTI-001', customer_name='PT Multi',
        )
        self.r1 = Reservation.objects.create(invoice=self.invoice, reservation_number='R-1', total_sar=1000)
        self.r2 = Reservation.objects.create(invoice=self.invoice, reservation_number='R-2', total_sar=2000)
        FinancialPeriod.objects.create(
            name='2026-08', date_from=date(2026, 8, 1), date_to=date(2026, 8, 31),
        )

    def _post(self, allocations):
        return self.client.post('/finance/payments/record/', {
            'invoice_id': self.invoice.pk,
            'payment_date': '2026-08-21',
            'amount': str(sum(a['amount'] for a in allocations)),
            'currency': 'SAR',
            'exchange_rate': '1',
            'received_in': 'sby',
            'method': 'Transfer',
            'allocations': json.dumps(allocations),
        }, follow=True)

    def test_both_rows_create_one_payment_each(self):
        resp = self._post([
            {'reservation_id': self.r1.pk, 'amount': 500},
            {'reservation_id': self.r2.pk, 'amount': 1000},
        ])

        payments = list(PaymentRecord.objects.filter(invoice=self.invoice).order_by('pk'))
        self.assertEqual(len(payments), 2)
        self.assertEqual(
            [(p.reservation_id, p.amount) for p in payments],
            [(self.r1.pk, 500.0), (self.r2.pk, 1000.0)],
        )
        self.assertTrue(all(p.status == PaymentRecord.STATUS_ALLOCATED for p in payments))

        msgs = [str(m) for m in get_messages(resp.wsgi_request)]
        self.assertTrue(any('2 payment(s)' in m for m in msgs))

    def test_success_redirects_to_invoice_filtered_list_not_first_detail(self):
        resp = self._post([
            {'reservation_id': self.r1.pk, 'amount': 500},
            {'reservation_id': self.r2.pk, 'amount': 1000},
        ])
        # The redirect must show EVERY created payment (invoice-filtered
        # list), not just the first row's detail page.
        self.assertRedirects(
            resp, f'/finance/payments/?invoice={self.invoice.pk}',
            fetch_redirect_response=False,
        )

    def test_rows_without_amount_are_skipped(self):
        resp = self._post([
            {'reservation_id': self.r1.pk, 'amount': 700},
            {'reservation_id': self.r2.pk, 'amount': 0},
        ])
        payments = list(PaymentRecord.objects.filter(invoice=self.invoice))
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments[0].reservation_id, self.r1.pk)
        msgs = [str(m) for m in get_messages(resp.wsgi_request)]
        self.assertTrue(any('1 payment(s)' in m for m in msgs))
