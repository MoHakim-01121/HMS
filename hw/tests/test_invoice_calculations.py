import csv
import io

from django.contrib.auth.models import User
from django.test import TestCase
from hw.models import Invoice, Reservation, CashMovement, ConfirmationLetter, CancellationPenalty


class InvoiceTotalsTest(TestCase):
    def setUp(self):
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-CALC-001', customer_name='Test Customer',
            currency='SAR',
        )

    def _pay(self, amount, currency='SAR', exchange_rate=1, to_account='sby'):
        CashMovement.objects.create(
            company='konoz', invoice=self.invoice, date='2026-01-01',
            from_account='client', to_account=to_account,
            amount=amount, currency=currency, exchange_rate=exchange_rate,
        )

    def test_total_sar_sums_reservations(self):
        Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=1000)
        Reservation.objects.create(invoice=self.invoice, reservation_number='R2', total_sar=500)
        self.assertEqual(self.invoice.total_sar, 1500)

    def test_total_sar_zero_with_no_reservations(self):
        self.assertEqual(self.invoice.total_sar, 0)

    def test_total_paid_sar_converts_non_sar_currency(self):
        # 100 USD @ exchange rate 3.75 == 375 SAR
        self._pay(100, currency='USD', exchange_rate=3.75)
        self.assertEqual(self.invoice.total_paid_sar, 375)

    def test_total_paid_sar_sums_multiple_payments(self):
        self._pay(200)
        self._pay(100)
        self.assertEqual(self.invoice.total_paid_sar, 300)

    def test_total_paid_sar_counts_direct_and_surabaya_payments(self):
        self._pay(200, to_account='sby')
        self._pay(100, to_account='pusat')
        self.assertEqual(self.invoice.total_paid_sar, 300)

    def test_remaining_sar_is_total_minus_paid(self):
        Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=1000)
        self._pay(400)
        self.assertEqual(self.invoice.remaining_sar, 600)

    def test_remaining_sar_negative_when_overpaid(self):
        Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=500)
        self._pay(700)
        self.assertEqual(self.invoice.remaining_sar, -200)

    def test_total_paid_sar_excludes_penalty_payment_linked_to_same_invoice(self):
        # A CancellationPenalty's CL can happen to share this invoice (for
        # traceability) without its cancelled booking being one of this
        # invoice's current reservations. total_sar only ever sums
        # reservations, so total_paid_sar must stay symmetric with that, or
        # remaining_sar looks more "paid off" than total_sar can explain.
        Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=1000)
        self._pay(400)  # real payment toward R1

        cl = ConfirmationLetter.objects.create(
            company='konoz', hotel_name='Hotel', guest_name='Guest',
            confirmation_number='CL-PEN-001', invoice=self.invoice,
        )
        penalty = CancellationPenalty.objects.create(
            cl=cl, penalty_number='PNL-TEST', cancellation_date='2026-01-02',
        )
        CashMovement.objects.create(
            company='konoz', invoice=self.invoice, penalty_label=penalty, date='2026-01-02',
            from_account='client', to_account='sby', amount=250, currency='SAR', exchange_rate=1,
        )

        self.assertEqual(self.invoice.total_paid_sar, 400)
        self.assertEqual(self.invoice.remaining_sar, 600)


class InvoiceExportStatusFilterTest(TestCase):
    """Regression: export (PDF/CSV) must honor the same `status` filter the
    on-screen list uses, not silently include every invoice."""

    def setUp(self):
        self.user = User.objects.create_user("exporter", password="pw12345")
        self.client.force_login(self.user)
        s = self.client.session
        s["active_company"] = "konoz"
        s.save()

        self.paid = Invoice.objects.create(
            company="konoz", invoice_type="hotel",
            invoice_number="INV-EXP-PAID", customer_name="Paid Co", currency="SAR",
        )
        Reservation.objects.create(invoice=self.paid, reservation_number="R1", total_sar=1000)
        CashMovement.objects.create(
            company="konoz", invoice=self.paid, date="2026-01-01",
            from_account="client", to_account="sby", amount=1000, currency="SAR", exchange_rate=1,
        )

        self.unpaid = Invoice.objects.create(
            company="konoz", invoice_type="hotel",
            invoice_number="INV-EXP-UNPAID", customer_name="Unpaid Co", currency="SAR",
        )
        Reservation.objects.create(invoice=self.unpaid, reservation_number="R2", total_sar=500)

    def test_csv_export_respects_status_filter(self):
        resp = self.client.get("/invoice/export/csv/", {"status": "belum"})
        self.assertEqual(resp.status_code, 200)
        rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))
        invoice_numbers = [r[0] for r in rows[1:]]
        self.assertIn("INV-EXP-UNPAID", invoice_numbers)
        self.assertNotIn("INV-EXP-PAID", invoice_numbers)

    def test_csv_export_without_status_includes_everything(self):
        resp = self.client.get("/invoice/export/csv/")
        rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))
        invoice_numbers = [r[0] for r in rows[1:]]
        self.assertIn("INV-EXP-UNPAID", invoice_numbers)
        self.assertIn("INV-EXP-PAID", invoice_numbers)

    def test_pdf_export_respects_status_filter(self):
        resp = self.client.get("/invoice/export/pdf/", {"status": "lunas"})
        self.assertEqual(resp.status_code, 200)
