from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Client, Invoice, Reservation
from hw.models.period import FinancialPeriod
from hw.finance import posting
from hw.finance_helpers import create_payment_record, confirm_payment
from hw.views.invoice_views import _invoice_stats


class InvoiceStatsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('stats', password='x')
        FinancialPeriod.objects.create(
            name='2020-2030', company='konoz',
            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.client_obj = Client.objects.create(company='konoz', name='Test Customer')
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel', invoice_number='INV-STAT-001',
            customer_name='Test Customer', client=self.client_obj, issued_date=date(2026, 1, 1),
        )
        self.res = Reservation.objects.create(
            invoice=self.invoice, reservation_number='R1', total_sar=1000,
        )
        posting.post_invoice_charge(self.invoice, created_by=self.user)

    def _pay(self, amount, received_in='sby'):
        p = create_payment_record(
            invoice=self.invoice, client=self.client_obj, payment_date=date(2026, 1, 1),
            amount=amount, method='transfer', created_by=self.user, received_in=received_in,
            reservation=self.res,
        )
        confirm_payment(p, confirmed_by=self.user)

    def _stats(self):
        return _invoice_stats(Invoice.objects.filter(pk=self.invoice.pk), 'konoz')

    def test_total_tagihan_from_journal_charge(self):
        self.assertEqual(self._stats()['total_tagihan'], 1000)

    def test_surabaya_payment_counts_as_terbayar_surabaya(self):
        self._pay(400, received_in='sby')
        stats = self._stats()
        self.assertEqual(stats['terbayar_surabaya'], 400)
        self.assertEqual(stats['terbayar_pusat'], 0)

    def test_direct_payment_counts_as_terbayar_pusat(self):
        self._pay(400, received_in='pusat')
        stats = self._stats()
        self.assertEqual(stats['terbayar_pusat'], 400)
        self.assertEqual(stats['terbayar_surabaya'], 0)

    def test_belum_terbayar_is_total_minus_all_payments(self):
        self._pay(300, received_in='sby')
        self._pay(200, received_in='pusat')
        self.assertEqual(self._stats()['belum_terbayar'], 500)

    def test_mengendap_is_surabaya_cash_for_these_invoices(self):
        self._pay(600, received_in='sby')
        self._pay(100, received_in='pusat')
        self.assertEqual(self._stats()['mengendap'], 600)
