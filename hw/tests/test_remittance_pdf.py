from datetime import date

from django.test import TestCase

from hw.models import Invoice, Remittance, RemittanceLine, Reservation
from hw.views.remittance_views import _prev_sent_map


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
