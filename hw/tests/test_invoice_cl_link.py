import json
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Client, ConfirmationLetter, Invoice
from hw.models.period import FinancialPeriod
from hw.finance import queries as fq


class InvoiceEditClLinkTests(TestCase):
    """Regression coverage: editing a hotel invoice must not silently unlink
    a Confirmation Letter that was already attached to it."""

    def setUp(self):
        self.user = User.objects.create_user("tester", password="pw12345")
        self.client.force_login(self.user)
        s = self.client.session
        s["active_company"] = "konoz"
        s.save()

        self.invoice = Invoice.objects.create(
            company="konoz", invoice_type="hotel",
            invoice_number="INV-CL-001", customer_name="Test Customer",
            currency="SAR",
        )
        self.cl = ConfirmationLetter.objects.create(
            company="konoz", hotel_name="Hotel A", guest_name="Guest A",
            confirmation_number="CL-LINK-001", invoice=self.invoice,
        )

    def test_edit_form_returns_currently_linked_cl_ids(self):
        resp = self.client.get(f"/invoice/{self.invoice.pk}/edit/", HTTP_X_INERTIA="true")
        props = resp.json()["props"]
        self.assertIn("linked_cl_ids", props["invoice"])
        self.assertEqual(props["invoice"]["linked_cl_ids"], [self.cl.pk])

    def test_saving_edit_form_with_seeded_ids_preserves_cl_link(self):
        # Simulate the React form re-submitting exactly what the GET response seeded it with,
        # i.e. the user edits some other field and saves without touching CL linking.
        get_resp = self.client.get(f"/invoice/{self.invoice.pk}/edit/", HTTP_X_INERTIA="true")
        linked_ids = get_resp.json()["props"]["invoice"]["linked_cl_ids"]

        resp = self.client.post(f"/invoice/{self.invoice.pk}/edit/", {
            "company": "konoz",
            "invoice_number": "INV-CL-001",
            "customer_name": "Test Customer Updated",
            "issued_date": "",
            "due_date": "",
            "linked_cl_ids": json.dumps(linked_ids),
        })
        self.assertEqual(resp.status_code, 302)
        self.cl.refresh_from_db()
        self.assertEqual(self.cl.invoice_id, self.invoice.pk)


class InvoiceChargeClientResolutionTests(TestCase):
    """Regression: linking a CL to a hotel invoice must resolve Charge.client
    immediately, not one save behind. _billing_client() reads
    invoice.confirmation_letters, so the CL link has to land before
    _save_reservations/_save_hotel_payments run (see invoice_views.py)."""

    def setUp(self):
        self.user = User.objects.create_user("tester2", password="pw12345")
        self.client.force_login(self.user)
        s = self.client.session
        s["active_company"] = "konoz"
        s.save()
        FinancialPeriod.objects.create(
            name="2020-2030", company="konoz",
            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.customer = Client.objects.create(company="konoz", name="PT Regression Client")
        self.cl = ConfirmationLetter.objects.create(
            company="konoz", hotel_name="Hotel Regress", guest_name="Guest Regress",
            confirmation_number="CL-REGRESS-001", client=self.customer,
        )

    def test_invoice_new_with_linked_cl_resolves_charge_client(self):
        resp = self.client.post("/invoice/new/", {
            "invoice_number": "INV-REGRESS-001",
            "customer_name": "PT Regression Client",
            "issued_date": "",
            "due_date": "",
            "linked_cl_ids": json.dumps([self.cl.pk]),
            "reservations": json.dumps([{
                "reservation_number": "CL-REGRESS-001",
                "hotel": "Hotel Regress",
                "check_in": "",
                "check_out": "",
                "reservation_total": "1000",
            }]),
            "payments": "[]",
        })
        self.assertEqual(resp.status_code, 302)
        invoice = Invoice.objects.get(invoice_number="INV-REGRESS-001")
        invoice.refresh_from_db()
        self.assertEqual(invoice.client_id, self.customer.pk)
        self.assertEqual(fq.invoice_charged_sar(invoice.id), 1000)
        self.assertEqual(fq.client_receivable(self.customer.id), 1000)

    def test_invoice_edit_relinking_cl_resolves_charge_client(self):
        invoice = Invoice.objects.create(
            company="konoz", invoice_type="hotel",
            invoice_number="INV-REGRESS-002", customer_name="Test Customer",
            currency="SAR",
        )
        resp = self.client.post(f"/invoice/{invoice.pk}/edit/", {
            "invoice_number": "INV-REGRESS-002",
            "customer_name": "Test Customer",
            "issued_date": "",
            "due_date": "",
            "linked_cl_ids": json.dumps([self.cl.pk]),
            "reservations": json.dumps([{
                "reservation_number": "CL-REGRESS-001",
                "hotel": "Hotel Regress",
                "check_in": "",
                "check_out": "",
                "reservation_total": "500",
            }]),
            "payments": "[]",
        })
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.client_id, self.customer.pk)
        self.assertEqual(fq.invoice_charged_sar(invoice.id), 500)
