from hw.tests.factories import make_cl, make_hotel_line, make_invoice, make_remittance
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import posting
from hw.finance_helpers import create_payment_record
from hw.models import ConfirmationLetter
from hw.models.period import FinancialPeriod
from hw.views.remittance_views import _build_reservasi_mengendap


class ReservasiMengendapTest(TestCase):
    """Daftar reservasi yang ditawarkan saat membuat remittance baru.

    Derivasinya membaca jurnal (bukan tabel legacy), jadi setup memosting
    lewat posting layer supaya angka muncul di jurnal.
    """

    def setUp(self):
        self.user = User.objects.create_user("tester", password="pw12345")
        FinancialPeriod.objects.create(
            name="2026",            date_from=date(2026, 1, 1), date_to=date(2026, 12, 31),
        )
        self.invoice = make_invoice(
 invoice_type='hotel',
            invoice_number='INV-NEW-001', customer_name='Budi',
        )
        self.client_obj = self.invoice.client
        self.rem_counter = 0

    def _res(self, number, **kw):
        return make_hotel_line(
            invoice=self.invoice, reservation_number=number, total_sar=kw.pop('total_sar', 10000), **kw
        )

    def _cl(self, number, status):
        existing = ConfirmationLetter.objects.filter(confirmation_number=number).first()
        if existing:   # reservasi yang sudah ditagih: ubah statusnya saja
            existing.reservation_status = status
            existing.save(update_fields=['reservation_status'])
            return existing
        return make_cl(
 confirmation_number=number, reservation_status=status,
            hotel_name='Hotel CL', guest_name='Guest CL',
        )

    def _pay(self, res, amount, received_in='sby'):
        p = create_payment_record(
            invoice=self.invoice, client=self.client_obj,
            payment_date=date(2026, 1, 5), amount=amount, method='transfer',
            created_by=self.user, received_in=received_in, reservation=res,
        )
        posting.post_payment(p, created_by=self.user)

    def _remit(self, res, amount):
        self.rem_counter += 1
        rmt = make_remittance(
 date=date(2026, 1, 10),
            remittance_number=f"RMT-NEW-{self.rem_counter}",
        )
        posting.post_remittance_send(
            rmt, amount_sar=amount,
            created_by=self.user, reservation=res,
        )

    def test_unpaid_reservation_is_listed(self):
        self._res('R1')
        rows = _build_reservasi_mengendap()
        self.assertEqual([r['linked_number'] for r in rows], ['R1'])
        self.assertEqual(rows[0]['terbayar_total'], 0)
        self.assertEqual(rows[0]['mengendap'], 0)

    def test_paid_reservation_still_listed_alongside_unpaid(self):
        self._res('R1', check_in=date(2026, 3, 1))
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
