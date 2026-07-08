from django.test import TestCase
from hw.models import Invoice, Reservation, Payment


class InvoiceTotalsTest(TestCase):
    def setUp(self):
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-CALC-001', customer_name='Test Customer',
            currency='SAR',
        )

    def test_total_sar_sums_reservations(self):
        Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=1000)
        Reservation.objects.create(invoice=self.invoice, reservation_number='R2', total_sar=500)
        self.assertEqual(self.invoice.total_sar, 1500)

    def test_total_sar_zero_with_no_reservations(self):
        self.assertEqual(self.invoice.total_sar, 0)

    def test_total_paid_sar_converts_non_sar_currency(self):
        # 100 USD @ exchange rate 3.75 == 375 SAR
        Payment.objects.create(invoice=self.invoice, amount=100, currency='USD', exchange_rate=3.75)
        self.assertEqual(self.invoice.total_paid_sar, 375)

    def test_total_paid_sar_sums_multiple_payments(self):
        Payment.objects.create(invoice=self.invoice, amount=200, currency='SAR', exchange_rate=1)
        Payment.objects.create(invoice=self.invoice, amount=100, currency='SAR', exchange_rate=1)
        self.assertEqual(self.invoice.total_paid_sar, 300)

    def test_remaining_sar_is_total_minus_paid(self):
        Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=1000)
        Payment.objects.create(invoice=self.invoice, amount=400, currency='SAR', exchange_rate=1)
        self.assertEqual(self.invoice.remaining_sar, 600)

    def test_remaining_sar_negative_when_overpaid(self):
        Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=500)
        Payment.objects.create(invoice=self.invoice, amount=700, currency='SAR', exchange_rate=1)
        self.assertEqual(self.invoice.remaining_sar, -200)
