import json

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import ConfirmationLetter, Invoice


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
