from django.test import TestCase
from django.contrib.auth.models import User

from hw.models import Invoice


class ActiveCompanyHelperTests(TestCase):
    def test_defaults_to_konoz_when_session_key_missing(self):
        from django.test import RequestFactory
        from hw.views.helpers import get_active_company
        request = RequestFactory().get("/")
        request.session = self.client.session  # fresh session, no active_company key
        self.assertEqual(get_active_company(request), "konoz")

    def test_stale_or_unknown_session_value_is_clamped_to_konoz(self):
        """Single-company deployment: a session left over from before Ijabah
        was retired (or any other value that isn't a valid company) must not
        be trusted as-is — it has to fall back to the one real company."""
        from django.test import RequestFactory
        from hw.views.helpers import get_active_company
        request = RequestFactory().get("/")
        request.session = self.client.session
        request.session["active_company"] = "ijabah"
        self.assertEqual(get_active_company(request), "konoz")


class SessionMissingCompanyTests(TestCase):
    """If the active_company session key is ever absent, views must fall back
    to a concrete default company (not skip the company filter and leak
    cross-company data)."""

    def setUp(self):
        self.user = User.objects.create_user("noscope", password="pw12345")
        self.client.force_login(self.user)
        # Deliberately do NOT set session["active_company"]

        # A row with a company value that isn't the one real company anymore
        # (e.g. left over from before Ijabah was retired, or otherwise
        # corrupted) — must still not leak just because scoping is lenient.
        self.other_company_invoice = Invoice.objects.create(
            company="other", invoice_type="visa",
            invoice_number="OTH-VISA-002", customer_name="Other Co Cust",
        )

    def test_services_detail_without_session_key_is_scoped_not_leaked(self):
        resp = self.client.get(f"/services/{self.other_company_invoice.pk}/", HTTP_X_INERTIA="true")
        # Default company is 'konoz', so a mismatched-company invoice must
        # 404 — not be returned just because the session key was never set.
        self.assertEqual(resp.status_code, 404)


class HotelInvoiceCompanyIsServerAssignedTests(TestCase):
    """The hotel invoice form used to submit its own `company` field, which the
    create/edit views wrote straight to the model with no can_use_company check.
    Company must come from the session, and a POSTed one must be ignored —
    even a value naming a company that no longer exists (e.g. the retired
    Ijabah, or anything else outside Company.values)."""

    def setUp(self):
        self.user = User.objects.create_user("scoped", password="pw12345")
        self.client.force_login(self.user)
        session = self.client.session
        session["active_company"] = "konoz"
        session.save()

    def _payload(self, **over):
        data = {
            "invoice_number": "INV-SCOPE-001",
            "customer_name": "Cust",
            "issued_date": "2026-07-01",
            "due_date": "2026-07-31",
            "reservations": "[]",
            "payments": "[]",
            "linked_cl_ids": "[]",
        }
        data.update(over)
        return data

    def test_create_ignores_posted_company_and_uses_active(self):
        self.client.post("/invoice/new/", self._payload(company="ijabah"))
        invoice = Invoice.objects.get(invoice_number="INV-SCOPE-001")
        self.assertEqual(invoice.company, "konoz")

    def test_edit_cannot_move_invoice_out_of_active_company(self):
        invoice = Invoice.objects.create(
            company="konoz", invoice_type="hotel",
            invoice_number="INV-SCOPE-002", customer_name="Cust",
        )
        self.client.post(
            f"/invoice/{invoice.pk}/edit/",
            self._payload(invoice_number="INV-SCOPE-002", company="ijabah"),
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.company, "konoz")
