from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import posting
from hw.finance_helpers import create_payment_record
from hw.models import Client
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_hotel_line, make_invoice, set_line_total


class ClientStatsTest(TestCase):
    """Client.total_billed/total_paid/outstanding read the general ledger
    (queries.py), which attributes both sides by the client dimension on the
    journal line -- set from invoice.client at charge time and from the
    payment's client at payment time."""

    def setUp(self):
        self.user = User.objects.create_user("cstats", password="pw12345")
        FinancialPeriod.objects.create(
            name="2026",            date_from=date(2026, 1, 1), date_to=date(2026, 12, 31),
        )
        self.client_obj = Client.objects.create( name='PT Client Stats')
        self.invoice = make_invoice(
 invoice_type='hotel',
            invoice_number='INV-CS-001', customer_name='PT Client Stats',
            client=self.client_obj, issued_date=date(2026, 1, 2),
        )
        self.res = make_hotel_line(
            invoice=self.invoice, reservation_number='R1', total_sar=1000,
        )

    def _charge(self, amount):
        self.res = set_line_total(self.res, amount)
        posting.post_invoice_charge(self.invoice, created_by=self.user)

    def _pay(self, amount):
        p = create_payment_record(
            invoice=self.invoice, client=self.client_obj,
            payment_date=date(2026, 2, 1), amount=amount, method='transfer',
            created_by=self.user, received_in='sby', reservation=self.res,
        )
        posting.post_payment(p, created_by=self.user)

    def test_total_billed_sums_charges(self):
        self._charge(1000)
        self.assertEqual(self.client_obj.total_billed, 1000)
        # PaymentRecord lain di cakupan periode sama tidak menambah tagihan.
        self.assertEqual(self.client_obj.total_billed, 1000)

    def test_total_paid_sums_client_originated_cash(self):
        self._pay(600)
        # Charge nol → outstanding = 0, tapi paid tetap terhitung dari kas masuk.
        self.assertEqual(self.client_obj.total_paid, 600)

    def test_outstanding_is_piutang_floored_at_zero(self):
        self._charge(1000)
        self._pay(1500)  # bayar lebih banyak dari tagihan
        self.assertEqual(self.client_obj.total_billed, 1000)
        self.assertEqual(self.client_obj.total_paid, 1500)
        self.assertEqual(self.client_obj.outstanding, 0)

    def test_outstanding_positive_when_underpaid(self):
        self._charge(1000)
        self._pay(400)
        self.assertEqual(self.client_obj.outstanding, 600)
