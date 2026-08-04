from datetime import date

from django.test import TestCase

from hw.models import ConfirmationLetter, Invoice, Payment, Reservation
from hw.views.remittance_views import _build_reservasi_mengendap


class ReservasiMengendapTest(TestCase):
    """Daftar reservasi yang ditawarkan saat membuat remittance baru."""

    def setUp(self):
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-NEW-001', customer_name='Budi',
        )

    def _res(self, number, **kw):
        return Reservation.objects.create(
            invoice=self.invoice, reservation_number=number, total_sar=kw.pop('total_sar', 10000), **kw
        )

    def _cl(self, number, status):
        return ConfirmationLetter.objects.create(
            company='konoz', confirmation_number=number, reservation_status=status,
            hotel_name='Hotel CL', guest_name='Guest CL',
        )

    def _pay(self, res, amount, method='cash'):
        Payment.objects.create(
            invoice=self.invoice, linked_number=res, amount=amount, currency='SAR',
            exchange_rate=1, method=method, payment_date=date(2026, 1, 5),
        )

    def test_unpaid_reservation_is_listed(self):
        self._res('R1')
        rows = _build_reservasi_mengendap()
        self.assertEqual([r['linked_number'] for r in rows], ['R1'])
        self.assertEqual(rows[0]['terbayar_total'], 0)
        self.assertEqual(rows[0]['mengendap'], 0)

    def test_paid_reservation_still_listed_alongside_unpaid(self):
        self._res('R1', check_in=date(2026, 3, 1))
        self._res('R2', check_in=date(2026, 2, 1))
        self._pay('R2', 5000)
        rows = _build_reservasi_mengendap()
        self.assertEqual({r['linked_number'] for r in rows}, {'R1', 'R2'})

    def test_cancelled_without_money_is_hidden(self):
        self._res('R1')
        self._cl('R1', 'CANCELLED')
        self.assertEqual(_build_reservasi_mengendap(), [])

    def test_cancelled_with_money_still_shown(self):
        self._res('R1')
        self._cl('R1', 'CANCELLED')
        self._pay('R1', 3000)
        rows = _build_reservasi_mengendap()
        self.assertEqual([r['linked_number'] for r in rows], ['R1'])
        self.assertEqual(rows[0]['terbayar_sby'], 3000)

    def test_non_cancelled_status_is_listed_even_without_money(self):
        self._res('R1')
        self._cl('R1', 'TENTATIVE')
        rows = _build_reservasi_mengendap()
        self.assertEqual([r['linked_number'] for r in rows], ['R1'])
