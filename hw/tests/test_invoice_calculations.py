import csv
import io
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import posting
from hw.finance_helpers import allocate_payment, confirm_payment, create_payment_record
from hw.models import CancellationPenalty, Client, Invoice
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_hotel_line, make_invoice


class InvoiceTotalsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('calc', password='pw12345')
        FinancialPeriod.objects.create(
            name='2026-01',            date_from=date(2026, 1, 1), date_to=date(2026, 12, 31),
        )
        self.client_obj = Client.objects.create( name='Test Customer')
        self.invoice = make_invoice(
 invoice_type='hotel',
            invoice_number='INV-CALC-001', customer_name='Test Customer',
            client=self.client_obj, currency='SAR', issued_date=date(2026, 1, 1),
        )

    def _charge(self):
        posting.post_invoice_charge(self.invoice, created_by=self.user)

    def _pay(self, amount, currency='SAR', exchange_rate=1, received_in='sby'):
        p = create_payment_record(
            invoice=self.invoice, client=self.client_obj, payment_date=date(2026, 1, 1),
            amount=amount, currency=currency, exchange_rate=exchange_rate,
            method='transfer', created_by=self.user, received_in=received_in,
        )
        confirm_payment(p, confirmed_by=self.user)
        return p

    def test_total_sar_sums_reservations(self):
        make_hotel_line(invoice=self.invoice, reservation_number='R1', total_sar=1000)
        make_hotel_line(invoice=self.invoice, reservation_number='R2', total_sar=500)
        self.assertEqual(self.invoice.total_sar, 1500)

    def test_total_sar_zero_with_no_reservations(self):
        self.assertEqual(self.invoice.total_sar, 0)

    def test_total_paid_sar_converts_non_sar_currency(self):
        # 100 USD @ exchange rate 3.75 == 375 SAR
        from hw.tests.factories import make_account
        make_account('sby', 'USD')
        self._pay(100, currency='USD', exchange_rate=3.75)
        self.assertEqual(self.invoice.total_paid_sar, 375)

    def test_total_paid_sar_sums_multiple_payments(self):
        self._pay(200)
        self._pay(100)
        self.assertEqual(self.invoice.total_paid_sar, 300)

    def test_total_paid_sar_counts_direct_and_surabaya_payments(self):
        self._pay(200, received_in='sby')
        self._pay(100, received_in='pusat')
        self.assertEqual(self.invoice.total_paid_sar, 300)

    def test_remaining_sar_is_total_minus_paid(self):
        make_hotel_line(invoice=self.invoice, reservation_number='R1', total_sar=1000)
        self._charge()
        self._pay(400)
        self.assertEqual(self.invoice.remaining_sar, 600)

    def test_remaining_sar_negative_when_overpaid(self):
        make_hotel_line(invoice=self.invoice, reservation_number='R1', total_sar=500)
        self._charge()
        self._pay(700)
        self.assertEqual(self.invoice.remaining_sar, -200)

    def test_penalty_is_part_of_the_invoice_total(self):
        """Denda ditagih sebagai baris invoice: reservasi yang batal bernilai 0,
        dendanya masuk total, dan uang yang sudah diterima tetap terhitung."""
        from hw.finance.penalty_billing import bill_penalty
        line = make_hotel_line(invoice=self.invoice, reservation_number='R1', total_sar=1000)
        self._charge()
        self._pay(400)

        cl = line.confirmation_letter
        cl.reservation_status = 'CANCELLED'
        cl.save(update_fields=['reservation_status'])
        penalty = CancellationPenalty.objects.create(
            cl=cl, penalty_number='PNL-TEST',
            cancellation_date=date(2026, 1, 2), penalty_amount=250,
        )
        bill_penalty(penalty, user=self.user)

        self.assertEqual(self.invoice.total_sar, 250)
        self.assertEqual(self.invoice.total_paid_sar, 400)
        self.assertEqual(self.invoice.remaining_sar, -150)

    def test_total_paid_sar_sees_finance_page_payment(self):
        make_hotel_line(invoice=self.invoice, reservation_number='R1', total_sar=1000)
        self._charge()
        payment = create_payment_record(
            invoice=self.invoice, client=self.client_obj, payment_date=date(2026, 1, 1),
            amount=400, method='transfer', created_by=self.user,
        )
        confirm_payment(payment, confirmed_by=self.user)
        allocate_payment(payment, allocation_date=payment.payment_date, created_by=self.user)

        self.assertEqual(self.invoice.total_paid_sar, 400)
        self.assertEqual(self.invoice.remaining_sar, 600)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.financial_state, Invoice.FINANCIAL_STATE_PARTIAL)


class InvoiceExportStatusFilterTest(TestCase):
    """Regression: export (PDF/CSV) must honor the same `status` filter the
    on-screen list uses, not silently include every invoice."""

    def setUp(self):
        self.user = User.objects.create_user("exporter", password="pw12345")
        self.client.force_login(self.user)
        s = self.client.session
        s["active_company"] = "konoz"
        s.save()
        FinancialPeriod.objects.create(
            name="2026",            date_from=date(2026, 1, 1), date_to=date(2026, 12, 31),
        )
        client_obj = Client.objects.create( name="Paid Co")

        self.paid = make_invoice(
 invoice_type="hotel",
            invoice_number="INV-EXP-PAID", customer_name="Paid Co",
            client=client_obj, currency="SAR", issued_date=date(2026, 1, 1),
        )
        make_hotel_line(invoice=self.paid, reservation_number="R1", total_sar=1000)
        posting.post_invoice_charge(self.paid, created_by=self.user)
        p = create_payment_record(
            invoice=self.paid, client=client_obj, payment_date=date(2026, 1, 1),
            amount=1000, method="transfer", created_by=self.user,
        )
        confirm_payment(p, confirmed_by=self.user)

        self.unpaid = make_invoice(
 invoice_type="hotel",
            invoice_number="INV-EXP-UNPAID", customer_name="Unpaid Co", currency="SAR",
        )
        make_hotel_line(invoice=self.unpaid, reservation_number="R2", total_sar=500)

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
