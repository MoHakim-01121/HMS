from django.contrib.auth.models import User
from django.test import TestCase


class LandingViewTest(TestCase):
    """The public landing page is not used: "/" opens the login."""

    def test_anonymous_user_goes_to_login(self):
        resp = self.client.get('/')
        self.assertRedirects(resp, '/login/')

    def test_authenticated_user_is_redirected_to_dashboard(self):
        user = User.objects.create_user('staff_landing', password='pw12345')
        self.client.force_login(user)
        resp = self.client.get('/')
        self.assertRedirects(resp, '/dashboard/')

    def test_public_hotel_page_is_gone(self):
        self.assertEqual(self.client.get('/properties/').status_code, 404)
