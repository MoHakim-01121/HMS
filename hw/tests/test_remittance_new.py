from datetime import date

from django.test import TestCase

from hw.models import ConfirmationLetter, Invoice, CashMovement, Reservation
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

    def _pay(self, res, amount, to_account='sby'):
        CashMovement.objects.create(
            company='konoz', invoice=self.invoice, reservation_label=res,
            from_account='client', to_account=to_account,
            amount=amount, currency='SAR', exchange_rate=1,
            date=date(2026, 1, 5),
        )

    def test_unpaid_reservation_is_listed(self):
        self._res('R1')
        rows = _build_reservasi_mengendap()
        self.assertEqual([r['linked_number'] for r in rows], ['R1'])
        self.assertEqual(rows[0]['terbayar_total'], 0)
        self.assertEqual(rows[0]['mengendap'], 0)

    def test_paid_reservation_still_listed_alongside_unpaid(self):
        r1 = self._res('R1', check_in=date(2026, 3, 1))
        r2 = self._res('R2', check_in=date(2026, 2, 1))
        self._pay(r2, 5000)
        rows = _build_reservasi_mengendap()
        self.assertEqual({r['linked_number'] for r in rows}, {'R1', 'R2'})

    def test_cancelled_without_money_is_hidden(self):
        self._res('R1')
        self._cl('R1', 'CANCELLED')
        self.assertEqual(_build_reservasi_mengendap(), [])

    def test_cancelled_with_money_still_shown(self):
        r1 = self._res('R1')
        self._cl('R1', 'CANCELLED')
        self._pay(r1, 3000)
        rows = _build_reservasi_mengendap()
        self.assertEqual([r['linked_number'] for r in rows], ['R1'])
        self.assertEqual(rows[0]['terbayar_sby'], 3000)

    def test_non_cancelled_status_is_listed_even_without_money(self):
        self._res('R1')
        self._cl('R1', 'TENTATIVE')
        rows = _build_reservasi_mengendap()
        self.assertEqual([r['linked_number'] for r in rows], ['R1'])

    def test_mengendap_can_go_negative(self):
        r1 = self._res('R1')
        self._pay(r1, 2000, to_account='sby')
        CashMovement.objects.create(
            company='konoz', invoice=self.invoice, reservation_label=r1,
            from_account='sby', to_account='pusat',
            amount=6000, currency='SAR', exchange_rate=1, date=date(2026, 1, 10),
        )
        rows = _build_reservasi_mengendap()
        self.assertEqual(rows[0]['mengendap'], -4000)
