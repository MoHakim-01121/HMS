from django.test import TestCase
from hw.models import Invoice, Reservation, CashMovement
from hw.views.invoice_views import _invoice_stats


class InvoiceStatsTest(TestCase):
    def setUp(self):
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-STAT-001', customer_name='Test Customer',
        )
        Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=1000)

    def _mov(self, from_account, to_account, amount):
        return CashMovement.objects.create(
            company='konoz', invoice=self.invoice, date='2026-01-01',
            from_account=from_account, to_account=to_account, amount=amount,
        )

    def _stats(self):
        qs = Invoice.objects.filter(pk=self.invoice.pk)
        return _invoice_stats(qs, 'konoz')

    def test_total_tagihan_sums_reservation_totals(self):
        from hw.models import Charge
        Charge.objects.create(
            company='konoz', client=None, invoice=self.invoice, date='2026-01-01',
            amount_sar=1000, reservation=Reservation.objects.get(invoice=self.invoice), reason='initial',
        )
        self.assertEqual(self._stats()['total_tagihan'], 1000)

    def test_cash_payment_counts_as_terbayar_surabaya(self):
        self._mov('client', 'sby', 400)
        stats = self._stats()
        self.assertEqual(stats['terbayar_surabaya'], 400)
        self.assertEqual(stats['terbayar_pusat'], 0)

    def test_direct_payment_counts_as_terbayar_pusat(self):
        self._mov('client', 'pusat', 400)
        stats = self._stats()
        self.assertEqual(stats['terbayar_pusat'], 400)
        self.assertEqual(stats['terbayar_surabaya'], 0)

    def test_belum_terbayar_is_total_minus_all_payments(self):
        from hw.models import Charge
        Charge.objects.create(
            company='konoz', client=None, invoice=self.invoice, date='2026-01-01',
            amount_sar=1000, reservation=Reservation.objects.get(invoice=self.invoice), reason='initial',
        )
        self._mov('client', 'sby', 300)
        self._mov('client', 'pusat', 200)
        self.assertEqual(self._stats()['belum_terbayar'], 500)  # 1000 - 300 - 200

    def test_mengendap_excludes_amount_already_remitted(self):
        self._mov('client', 'sby', 600)
        self._mov('sby', 'pusat', 200)
        # 600 collected in Surabaya, 200 already sent up -> 400 still held
        self.assertEqual(self._stats()['mengendap'], 400)

    def test_mengendap_can_go_negative_when_more_sent_than_received(self):
        self._mov('client', 'sby', 200)
        self._mov('sby', 'pusat', 600)
        # Surabaya kirim lebih dari yang diterima -- kredit di pusat, bukan 0
        self.assertEqual(self._stats()['mengendap'], -400)
