from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import posting
from hw.finance_helpers import create_payment_record
from hw.models import Client, Invoice, Reservation
from hw.models.period import FinancialPeriod


class ClientDetailViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="pw12345")
        self.client.force_login(self.user)
        s = self.client.session
        s["active_company"] = "konoz"
        s.save()

        FinancialPeriod.objects.create(
            name="2026",            date_from=date(2026, 1, 1), date_to=date(2026, 12, 31),
        )
        self.client_obj = Client.objects.create( name="PT Detail View")
        # invoice.client dipasang supaya charge (yang di-posting ke jurnal)
        # ter-atribusi ke client -- jurnal membaca client dari dimensi baris.
        invoice = Invoice.objects.create(
 invoice_type="hotel",
            invoice_number="INV-CDV-001", customer_name="PT Detail View",
            client=self.client_obj, issued_date=date(2026, 1, 2),
        )
        self.invoice = invoice
        self.res = Reservation.objects.create(
            invoice=invoice, reservation_number="R1", total_sar=5000,
        )
        posting.post_invoice_charge(invoice, created_by=self.user)
        p = create_payment_record(
            invoice=invoice, client=self.client_obj,
            payment_date=date(2026, 1, 5), amount=6000, method="transfer",
            created_by=self.user, received_in="sby", reservation=self.res,
        )
        posting.post_payment(p, created_by=self.user)

    def test_detail_page_reports_balance_and_activity(self):
        # Bayar 6000 utk tagihan 5000 → piutang client negatif (lebihan
        # dana), aktivitas 2 baris (charge debit + payment credit).
        resp = self.client.get(f"/clients/{self.client_obj.pk}/", HTTP_X_INERTIA="true")
        self.assertEqual(resp.status_code, 200)
        props = resp.json()["props"]

        self.assertEqual(props["client"]["saldo_dana"], 0)  # tidak ada titipan CUST_CREDIT
        self.assertEqual(props["client"]["outstanding"], 0)  # lebihan bayar → piutang ≠ positif
        self.assertEqual(len(props["activity"]), 2)
        self.assertEqual(props["activity"][0]["type"], "debit")
        self.assertEqual(props["activity"][1]["type"], "credit")
        self.assertEqual(props["activity"][-1]["balance"], -1000)  # client punya kelebihan 1000

    def test_detail_page_lists_invoice_linked_via_journal(self):
        resp = self.client.get(f"/clients/{self.client_obj.pk}/", HTTP_X_INERTIA="true")
        props = resp.json()["props"]
        invoice_numbers = [inv["invoice_number"] for inv in props["invoices"]]
        self.assertIn("INV-CDV-001", invoice_numbers)

    def test_resolved_invoices_includes_invoice_with_client_fk_but_no_journal_yet(self):
        # Invoice.client (populated by the invoice/services forms) can be
        # set before any journal entry exists for it -- e.g. a brand-new
        # invoice with no reservations/payments saved yet. resolved_invoices
        # must not depend on journal lines alone, or this invoice silently
        # vanishes from the client's totals/statement until its first entry
        # (charge/payment) lands.
        fk_only_invoice = Invoice.objects.create(
 invoice_type="hotel",
            invoice_number="INV-CDV-002", customer_name="PT Detail View",
            client=self.client_obj,
        )
        self.assertIn(fk_only_invoice, self.client_obj.resolved_invoices)
