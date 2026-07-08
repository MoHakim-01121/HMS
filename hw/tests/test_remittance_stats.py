from django.test import TestCase
from hw.models import Invoice, Payment, Remittance, RemittanceLine
from hw.views.invoice_views import _invoice_stats


class InvoiceStatsTest(TestCase):
    def setUp(self):
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-STAT-001', customer_name='Test Customer',
        )
        from hw.models import Reservation
        Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=1000)

    def _stats(self):
        qs = Invoice.objects.filter(pk=self.invoice.pk)
        return _invoice_stats(qs, 'konoz')

    def test_total_tagihan_sums_reservation_totals(self):
        self.assertEqual(self._stats()['total_tagihan'], 1000)

    def test_cash_payment_counts_as_terbayar_surabaya(self):
        Payment.objects.create(invoice=self.invoice, amount=400, currency='SAR', exchange_rate=1, method='cash')
        stats = self._stats()
        self.assertEqual(stats['terbayar_surabaya'], 400)
        self.assertEqual(stats['terbayar_pusat'], 0)

    def test_direct_payment_counts_as_terbayar_pusat(self):
        Payment.objects.create(invoice=self.invoice, amount=400, currency='SAR', exchange_rate=1, method='direct')
        stats = self._stats()
        self.assertEqual(stats['terbayar_pusat'], 400)
        self.assertEqual(stats['terbayar_surabaya'], 0)

    def test_belum_terbayar_is_total_minus_all_payments(self):
        Payment.objects.create(invoice=self.invoice, amount=300, currency='SAR', exchange_rate=1, method='cash')
        Payment.objects.create(invoice=self.invoice, amount=200, currency='SAR', exchange_rate=1, method='direct')
        self.assertEqual(self._stats()['belum_terbayar'], 500)  # 1000 - 300 - 200

    def test_mengendap_excludes_amount_already_remitted(self):
        Payment.objects.create(invoice=self.invoice, amount=600, currency='SAR', exchange_rate=1, method='cash')
        remittance = Remittance.objects.create(company='konoz', date='2026-01-01')
        RemittanceLine.objects.create(remittance=remittance, invoice=self.invoice, linked_number='R1', amount_sar=200)
        # 600 collected in Surabaya, 200 already sent up -> 400 still held
        self.assertEqual(self._stats()['mengendap'], 400)
