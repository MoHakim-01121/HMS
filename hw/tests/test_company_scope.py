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

    def test_returns_session_value_when_set(self):
        from django.test import RequestFactory
        from hw.views.helpers import get_active_company
        request = RequestFactory().get("/")
        request.session = self.client.session
        request.session["active_company"] = "ijabah"
        self.assertEqual(get_active_company(request), "ijabah")


class SessionMissingCompanyTests(TestCase):
    """If the active_company session key is ever absent, views must fall back
    to a concrete default company (not skip the company filter and leak
    cross-company data)."""

    def setUp(self):
        self.user = User.objects.create_user("noscope", password="pw12345")
        self.client.force_login(self.user)
        # Deliberately do NOT set session["active_company"]

        self.ijabah_visa = Invoice.objects.create(
            company="ijabah", invoice_type="visa",
            invoice_number="IJH-VISA-002", customer_name="Ijabah Cust 2",
        )

    def test_services_detail_without_session_key_is_scoped_not_leaked(self):
        resp = self.client.get(f"/services/{self.ijabah_visa.pk}/", HTTP_X_INERTIA="true")
        # Default company is 'konoz', so an ijabah invoice must 404 — not be
        # returned just because the session key was never set.
        self.assertEqual(resp.status_code, 404)
