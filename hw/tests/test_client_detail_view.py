from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Client, Invoice, Reservation, Charge, Allocation, CashMovement


class ClientDetailViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="pw12345")
        self.client.force_login(self.user)
        s = self.client.session
        s["active_company"] = "konoz"
        s.save()

        self.client_obj = Client.objects.create(company="konoz", name="PT Detail View")
        # invoice.client is deliberately left unset -- the only reliable link is
        # via Charge.client below, matching how invoices are linked in practice.
        invoice = Invoice.objects.create(
            company="konoz", invoice_type="hotel",
            invoice_number="INV-CDV-001", customer_name="PT Detail View",
        )
        self.invoice = invoice
        res = Reservation.objects.create(invoice=invoice, reservation_number="R1", total_sar=5000)
        Charge.objects.create(
            company="konoz", client=self.client_obj, invoice=invoice, date="2026-01-01",
            amount_sar=5000, reservation=res, reason="initial",
        )
        CashMovement.objects.create(
            company="konoz", client=self.client_obj, invoice=invoice, date="2026-01-05",
            from_account="client", to_account="sby", amount=6000, currency="SAR", exchange_rate=1,
            reservation_label=res,
        )
        Allocation.objects.create(
            company="konoz", client=self.client_obj, invoice=invoice, date="2026-01-05",
            amount_sar=5000, reservation=res, reason="initial",
        )

    def test_detail_page_reports_fund_balance_and_activity(self):
        resp = self.client.get(f"/clients/{self.client_obj.pk}/", HTTP_X_INERTIA="true")
        self.assertEqual(resp.status_code, 200)
        props = resp.json()["props"]

        self.assertEqual(props["client"]["saldo_dana"], 1000)  # paid 6000, only 5000 allocated
        self.assertEqual(len(props["activity"]), 2)
        self.assertEqual(props["activity"][0]["type"], "debit")
        self.assertEqual(props["activity"][1]["type"], "credit")
        self.assertEqual(props["activity"][-1]["balance"], -1000)  # client has 1000 unused credit

    def test_detail_page_lists_invoices_linked_only_via_charge(self):
        # Regression: client_detail used to read c.invoices (Invoice.client
        # FK) instead of c.resolved_invoices, so this list was always empty
        # even when Charge.client correctly linked the invoice to the client.
        resp = self.client.get(f"/clients/{self.client_obj.pk}/", HTTP_X_INERTIA="true")
        props = resp.json()["props"]
        invoice_numbers = [inv["invoice_number"] for inv in props["invoices"]]
        self.assertIn("INV-CDV-001", invoice_numbers)

    def test_resolved_invoices_includes_invoice_with_client_fk_but_no_charge_yet(self):
        # Invoice.client (populated by the invoice/services forms) can be
        # set before any Charge exists for it -- e.g. a brand-new invoice
        # with no reservations/payments saved yet. resolved_invoices must
        # not depend on Charge alone, or this invoice silently vanishes
        # from the client's totals/statement until its first Charge lands.
        fk_only_invoice = Invoice.objects.create(
            company="konoz", invoice_type="hotel",
            invoice_number="INV-CDV-002", customer_name="PT Detail View",
            client=self.client_obj,
        )
        self.assertIn(fk_only_invoice, self.client_obj.resolved_invoices)
