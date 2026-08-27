from django.test import TestCase
from hw.models import Client, Invoice, Reservation, Charge, Allocation, CashMovement


class ClientStatsTest(TestCase):
    """Client.total_billed/total_paid/outstanding read the ledger (Charge/
    Allocation/CashMovement), where client resolution is done properly --
    not Invoice.client directly, since an invoice can have that FK set
    before any Charge/CashMovement exists for it yet."""

    def setUp(self):
        self.client_obj = Client.objects.create(company='konoz', name='PT Client Stats')
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-CS-001', customer_name='PT Client Stats',
        )
        self.res = Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=1000)

    def test_total_billed_sums_charges_even_without_invoice_client_fk(self):
        Charge.objects.create(
            company='konoz', client=self.client_obj, invoice=self.invoice, date='2026-01-01',
            amount_sar=1000, reservation=self.res, reason='initial',
        )
        self.assertEqual(self.client_obj.total_billed, 1000)

    def test_total_paid_sums_client_originated_cash(self):
        CashMovement.objects.create(
            company='konoz', client=self.client_obj, invoice=self.invoice, date='2026-01-01',
            from_account='client', to_account='sby', amount=600,
        )
        self.assertEqual(self.client_obj.total_paid, 600)

    def test_outstanding_is_piutang_floored_at_zero(self):
        Charge.objects.create(
            company='konoz', client=self.client_obj, invoice=self.invoice, date='2026-01-01',
            amount_sar=1000, reservation=self.res, reason='initial',
        )
        Allocation.objects.create(
            company='konoz', client=self.client_obj, invoice=self.invoice, date='2026-01-01',
            amount_sar=1500, reservation=self.res, reason='initial',
        )
        # klien bayar lebih dari tagihan -- outstanding tidak boleh negatif
        self.assertEqual(self.client_obj.outstanding, 0)

    def test_outstanding_positive_when_underpaid(self):
        Charge.objects.create(
            company='konoz', client=self.client_obj, invoice=self.invoice, date='2026-01-01',
            amount_sar=1000, reservation=self.res, reason='initial',
        )
        Allocation.objects.create(
            company='konoz', client=self.client_obj, invoice=self.invoice, date='2026-01-01',
            amount_sar=400, reservation=self.res, reason='initial',
        )
        self.assertEqual(self.client_obj.outstanding, 600)
