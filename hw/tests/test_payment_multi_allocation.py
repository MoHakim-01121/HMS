"""Multi-row allocation save from the Finance "Record Payment" dialog.

A single transfer covering several reservations is recorded as ONE
PaymentRecord (carrying the original amount + exchange rate for analysis)
plus one analytic PaymentAllocation per reservation, expressed in SAR.
This guards the regression where each filled allocation row became its own
PaymentRecord whose SAR amount was re-divided by the (non-SAR) exchange
rate — producing "Allocation (10.000) != Amount (48.000.000)".
"""
import json
from datetime import date

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import TestCase

from hw.models import Client, Invoice, Reservation, PaymentRecord, PaymentAllocation
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

    def _post(self, amount, allocations, currency='SAR', exchange_rate='1'):
        return self.client.post('/finance/payments/record/', {
            'invoice_id': self.invoice.pk,
            'payment_date': '2026-08-21',
            'amount': str(amount),
            'currency': currency,
            'exchange_rate': exchange_rate,
            'received_in': 'sby',
            'method': 'Transfer',
            'allocations': json.dumps(allocations),
        }, follow=True)

    def test_all_rows_become_one_record_plus_allocations(self):
        resp = self._post(1500, [
            {'reservation_id': self.r1.pk, 'amount': 500},
            {'reservation_id': self.r2.pk, 'amount': 1000},
        ])

        payments = list(PaymentRecord.objects.filter(invoice=self.invoice))
        self.assertEqual(len(payments), 1)
        p = payments[0]
        self.assertEqual(p.amount, 1500)
        self.assertEqual(p.amount_sar, 1500)
        self.assertEqual(p.status, PaymentRecord.STATUS_ALLOCATED)

        allocs = list(PaymentAllocation.objects.filter(payment=p).order_by('reservation_id'))
        self.assertEqual(
            [(a.reservation_id, a.amount_sar) for a in allocs],
            [(self.r1.pk, 500), (self.r2.pk, 1000)],
        )

        msgs = [str(m) for m in get_messages(resp.wsgi_request)]
        self.assertTrue(any('Payment berhasil' in m for m in msgs))

    def test_non_sar_amount_keeps_original_currency_and_rate_for_analysis(self):
        # 48,000,000 IDR @ 4800 == 10,000 SAR (riyal patokan), split in SAR.
        # This is the regression case: allocation is in SAR (patokan riyal),
        # while the payment record keeps the IDR amount + rate for analysis.
        resp = self._post(48_000_000, [
            {'reservation_id': self.r1.pk, 'amount': 6000},
            {'reservation_id': self.r2.pk, 'amount': 4000},
        ], currency='IDR', exchange_rate='4800')

        payments = list(PaymentRecord.objects.filter(invoice=self.invoice))
        self.assertEqual(len(payments), 1)
        p = payments[0]
        # Kurs & nominal asli dipertahankan untuk analisis...
        self.assertEqual(p.amount, 48_000_000)
        self.assertEqual(p.currency, 'IDR')
        self.assertEqual(float(p.exchange_rate), 4800.0)
        # ...sementara nilai SAR (riyal patokan) dihitung via convert_to_sar.
        self.assertEqual(p.amount_sar, 10000)

        allocs = list(PaymentAllocation.objects.filter(payment=p).order_by('reservation_id'))
        self.assertEqual(
            [(a.reservation_id, a.amount_sar) for a in allocs],
            [(self.r1.pk, 6000), (self.r2.pk, 4000)],
        )
        self.assertTrue(all(a.amount_sar <= p.amount_sar for a in allocs))
        self.assertEqual(sum(a.amount_sar for a in allocs), p.amount_sar)

        msgs = [str(m) for m in get_messages(resp.wsgi_request)]
        self.assertTrue(any('Payment berhasil' in m for m in msgs))

    def test_allocation_over_payment_amount_is_rejected(self):
        resp = self._post(5000, [
            {'reservation_id': self.r1.pk, 'amount': 6000},
            {'reservation_id': self.r2.pk, 'amount': 4000},
        ])
        msgs = [str(m) for m in get_messages(resp.wsgi_request)]
        self.assertFalse(PaymentRecord.objects.filter(invoice=self.invoice).exists())
        self.assertTrue(any('melebihi nilai SAR pembayaran' in m for m in msgs))

    def test_success_redirects_to_invoice_filtered_list(self):
        resp = self._post(1500, [
            {'reservation_id': self.r1.pk, 'amount': 500},
            {'reservation_id': self.r2.pk, 'amount': 1000},
        ])
        self.assertRedirects(
            resp, f'/finance/payments/?invoice={self.invoice.pk}',
            fetch_redirect_response=False,
        )

    def test_rows_without_amount_are_skipped(self):
        resp = self._post(700, [
            {'reservation_id': self.r1.pk, 'amount': 700},
            {'reservation_id': self.r2.pk, 'amount': 0},
        ])
        payments = list(PaymentRecord.objects.filter(invoice=self.invoice))
        self.assertEqual(len(payments), 1)
        allocs = list(PaymentAllocation.objects.filter(payment=payments[0]))
        self.assertEqual(len(allocs), 1)
        self.assertEqual(allocs[0].reservation_id, self.r1.pk)
        msgs = [str(m) for m in get_messages(resp.wsgi_request)]
        self.assertTrue(any('Payment berhasil' in m for m in msgs))
