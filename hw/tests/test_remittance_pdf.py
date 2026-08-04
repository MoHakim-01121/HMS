from datetime import date

from django.test import TestCase

from hw.models import (
    ConfirmationLetter, Invoice, Payment, Remittance, RemittanceLine, Reservation,
)
from hw.views.remittance_views import _build_ledger_rows, _prev_sent_map


class PrevSentMapTest(TestCase):
    """Prev Sent hanya boleh menghitung remittance yang dibuat SEBELUM remittance ini."""

    def setUp(self):
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-PREV-001', customer_name='Test Customer',
        )
        Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=10000)
        self.rem1 = Remittance.objects.create(company='konoz', date=date(2026, 1, 1), remittance_number='RMT-001')
        RemittanceLine.objects.create(remittance=self.rem1, invoice=self.invoice, linked_number='R1', amount_sar=2000)
        self.rem2 = Remittance.objects.create(company='konoz', date=date(2026, 2, 1), remittance_number='RMT-002')
        RemittanceLine.objects.create(remittance=self.rem2, invoice=self.invoice, linked_number='R1', amount_sar=2000)

    def test_first_remittance_has_no_prev_sent(self):
        self.assertEqual(_prev_sent_map(self.rem1, ['R1']).get('R1', 0), 0)

    def test_second_remittance_counts_only_the_earlier_one(self):
        self.assertEqual(_prev_sent_map(self.rem2, ['R1']).get('R1', 0), 2000)

    def test_same_date_falls_back_to_creation_order(self):
        rem3 = Remittance.objects.create(company='konoz', date=date(2026, 2, 1), remittance_number='RMT-003')
        RemittanceLine.objects.create(remittance=rem3, invoice=self.invoice, linked_number='R1', amount_sar=1000)
        # rem2 tanggalnya sama tapi dibuat lebih dulu -> ikut terhitung
        self.assertEqual(_prev_sent_map(rem3, ['R1']).get('R1', 0), 4000)
        # rem2 tidak boleh kena imbas rem3 yang dibuat belakangan
        self.assertEqual(_prev_sent_map(self.rem2, ['R1']).get('R1', 0), 2000)

    def test_empty_linked_numbers(self):
        self.assertEqual(_prev_sent_map(self.rem1, []), {})


class RemittancePdfOrderingTest(TestCase):
    """Baris PDF diurutkan check-in terdekat dulu, baris tanpa check-in paling bawah."""

    def setUp(self):
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-ORD-001', customer_name='Test Customer',
        )
        Reservation.objects.create(invoice=self.invoice, reservation_number='900', total_sar=1000, check_in=date(2026, 6, 30))
        Reservation.objects.create(invoice=self.invoice, reservation_number='100', total_sar=1000, check_in=date(2026, 6, 11))
        Reservation.objects.create(invoice=self.invoice, reservation_number='500', total_sar=1000, check_in=date(2026, 6, 20))
        self.rem = Remittance.objects.create(company='konoz', date=date(2026, 6, 10), remittance_number='RMT-010')
        for num in ('100', '500', '900', 'NOCI'):
            RemittanceLine.objects.create(remittance=self.rem, invoice=self.invoice, linked_number=num, amount_sar=100)

    def test_lines_sorted_by_check_in_ascending(self):
        from hw.views import remittance_views

        captured = {}

        def fake_render(request, qs, template, filename, extra_ctx):
            captured.update(extra_ctx)
            from django.http import HttpResponse
            return HttpResponse(b'ok')

        from hw.views import helpers
        original = helpers._render_list_pdf
        helpers._render_list_pdf = fake_render
        try:
            request = type('R', (), {'GET': {}, 'user': None})()
            remittance_views.remittance_pdf.__wrapped__(request, self.rem.pk)
        finally:
            helpers._render_list_pdf = original

        order = [row['line'].linked_number for row in captured['lines']]
        self.assertEqual(order, ['100', '500', '900', 'NOCI'])


class LedgerTest(TestCase):
    """Buku besar Surabaya <-> Pusat: satu baris per reservasi."""

    def setUp(self):
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-LED-001', customer_name='Budi',
        )
        Reservation.objects.create(
            invoice=self.invoice, reservation_number='R1', total_sar=10000,
            hotel='Hilton Makkah', check_in=date(2026, 3, 10), check_out=date(2026, 3, 14),
        )
        Reservation.objects.create(
            invoice=self.invoice, reservation_number='R2', total_sar=5000,
            hotel='Anwar Al Madinah', check_in=date(2026, 2, 5), check_out=date(2026, 2, 8),
        )

    def _cl(self, number, status, **kw):
        return ConfirmationLetter.objects.create(
            company='konoz', confirmation_number=number, reservation_status=status,
            hotel_name=kw.get('hotel', 'Hotel CL'), guest_name=kw.get('guest', 'Guest CL'),
        )

    def _pay(self, res, amount, method):
        return Payment.objects.create(
            invoice=self.invoice, linked_number=res, amount=amount, currency='SAR',
            exchange_rate=1, method=method, payment_date=date(2026, 1, 5),
        )

    def _remit(self, res, amount, day, number):
        rem = Remittance.objects.create(company='konoz', date=date(2026, 1, day), remittance_number=number)
        RemittanceLine.objects.create(remittance=rem, invoice=self.invoice, linked_number=res, amount_sar=amount)
        return rem

    def _row(self, led, number):
        return next(r for r in led['rows'] if r['linked_number'] == number)

    def test_row_carries_reservation_detail(self):
        self._pay('R1', 600, 'cash')
        row = self._row(_build_ledger_rows(), 'R1')
        self.assertEqual(row['linked_number'], 'R1')
        self.assertEqual(row['hotel'], 'Hilton Makkah')
        self.assertEqual(row['guest'], 'Budi')
        self.assertEqual(row['check_in'], date(2026, 3, 10))
        self.assertEqual(row['check_out'], date(2026, 3, 14))
        self.assertEqual(row['total_sar'], 10000)  # total tagihan reservasi

    def test_debit_credit_and_balance_per_reservation(self):
        self._pay('R1', 600, 'cash')
        self._remit('R1', 200, 10, 'RMT-L01')
        row = self._row(_build_ledger_rows(), 'R1')
        # balance = total tagihan (10000) - credit (200), bukan debit - credit
        self.assertEqual((row['debit'], row['credit'], row['balance']), (600, 200, 9800))

    def test_payments_for_one_reservation_are_merged_into_one_row(self):
        self._pay('R1', 600, 'cash')
        self._pay('R1', 400, 'bank transfer')
        self._remit('R1', 200, 10, 'RMT-L01')
        self._remit('R1', 300, 11, 'RMT-L02')
        led = _build_ledger_rows()
        self.assertEqual(len([r for r in led['rows'] if r['linked_number'] == 'R1']), 1)
        row = self._row(led, 'R1')
        self.assertEqual((row['debit'], row['credit']), (1000, 500))

    def test_direct_payment_counts_as_debit_and_credit(self):
        self._pay('R1', 600, 'cash')
        self._pay('R2', 400, 'direct')
        led = _build_ledger_rows()
        self.assertEqual(led['direct_total'], 400)
        self.assertEqual(led['total_debit'], 1000)   # 600 sby + 400 direct
        self.assertEqual(led['total_credit'], 400)   # direct sudah di Pusat
        row = self._row(led, 'R2')
        # balance = total tagihan R2 (5000) - credit (400): direct baru menutup sebagian kewajiban
        self.assertEqual((row['debit'], row['credit'], row['balance']), (400, 400, 4600))
        self.assertEqual(led['balance'], 15000 - 400)  # total tagihan - total credit

    def test_direct_plus_surabaya_on_same_reservation(self):
        self._pay('R1', 600, 'cash')
        self._pay('R1', 400, 'direct')
        self._remit('R1', 200, 10, 'RMT-L01')
        row = self._row(_build_ledger_rows(), 'R1')
        self.assertEqual((row['debit'], row['credit'], row['balance']), (1000, 600, 10000 - 600))

    def test_rows_sorted_by_check_in_and_numbered(self):
        rows = _build_ledger_rows()['rows']
        self.assertEqual([r['linked_number'] for r in rows], ['R2', 'R1'])
        self.assertEqual([r['no'] for r in rows], [1, 2])

    def test_totals_and_overall_balance(self):
        self._pay('R1', 600, 'cash')
        self._pay('R2', 300, 'cash')
        self._remit('R1', 200, 10, 'RMT-L01')
        led = _build_ledger_rows()
        self.assertEqual(led['total_tagihan'], 15000)  # 10000 + 5000
        self.assertEqual(led['total_debit'], 900)
        self.assertEqual(led['total_credit'], 200)
        self.assertEqual(led['balance'], 15000 - 200)  # kewajiban ke hotel, bukan cuma kas mengendap

    def test_balance_zero_when_full_amount_remitted(self):
        # balance nol hanya kalau credit menutup seluruh total tagihan reservasi,
        # bukan sekadar menyamai jumlah yang sudah dibayar client
        self._remit('R1', 10000, 10, 'RMT-L01')
        self.assertEqual(self._row(_build_ledger_rows(), 'R1')['balance'], 0)

    def test_check_in_range_filter(self):
        led = _build_ledger_rows(date_from=date(2026, 3, 1))
        self.assertEqual([r['linked_number'] for r in led['rows']], ['R1'])
        led = _build_ledger_rows(date_to=date(2026, 2, 28))
        self.assertEqual([r['linked_number'] for r in led['rows']], ['R2'])

    def test_reservation_without_master_data_still_listed(self):
        self._remit('R-HILANG', 500, 10, 'RMT-L01')
        row = self._row(_build_ledger_rows(), 'R-HILANG')
        self.assertEqual((row['hotel'], row['guest']), ('—', '—'))
        self.assertEqual((row['debit'], row['credit'], row['balance']), (0, 500, -500))

    # --- pelacakan: reservasi tanpa pergerakan uang tetap tampil ---

    def test_definite_and_tentative_listed_without_any_money(self):
        self._cl('R1', 'DEFINITE')
        self._cl('R2', 'TENTATIVE')
        led = _build_ledger_rows()
        self.assertEqual([r['linked_number'] for r in led['rows']], ['R2', 'R1'])
        self.assertEqual(self._row(led, 'R1')['status'], 'DEFINITE')
        self.assertEqual(self._row(led, 'R2')['status'], 'TENTATIVE')
        # belum ada uang bergerak sama sekali, tapi kewajiban ke hotel tetap penuh
        self.assertEqual(led['balance'], 15000)
        self.assertEqual(led['total_tagihan'], 15000)

    def test_cancelled_without_money_is_hidden(self):
        self._cl('R1', 'CANCELLED')
        self._cl('R2', 'DEFINITE')
        led = _build_ledger_rows()
        self.assertEqual([r['linked_number'] for r in led['rows']], ['R2'])

    def test_cancelled_with_money_still_shown(self):
        self._cl('R1', 'CANCELLED')
        self._pay('R1', 600, 'cash')
        led = _build_ledger_rows()
        row = self._row(led, 'R1')
        self.assertEqual(row['status'], 'CANCELLED')
        self.assertEqual(row['debit'], 600)

    def test_reservation_without_cl_has_blank_status_but_is_listed(self):
        led = _build_ledger_rows()
        self.assertEqual(self._row(led, 'R1')['status'], '')

    def test_cl_without_invoice_is_still_tracked(self):
        self._cl('CL-NOINV', 'DEFINITE', hotel='Swissotel', guest='Rina')
        row = self._row(_build_ledger_rows(), 'CL-NOINV')
        self.assertEqual((row['hotel'], row['guest']), ('Swissotel', 'Rina'))
        self.assertEqual((row['debit'], row['credit'], row['balance']), (0, 0, 0))

    def test_cl_without_invoice_uses_cl_dates_and_room_total(self):
        from hw.models import Room
        cl = self._cl('CL-ROOM', 'TENTATIVE')
        cl.check_in = date(2026, 4, 1)
        cl.check_out = date(2026, 4, 3)
        cl.save()
        Room.objects.create(cl=cl, room_type='Double', quantity=2, price=500)
        row = self._row(_build_ledger_rows(), 'CL-ROOM')
        self.assertEqual(row['check_in'], date(2026, 4, 1))
        self.assertEqual(row['check_out'], date(2026, 4, 3))
        self.assertEqual(row['total_sar'], cl.total_price)
