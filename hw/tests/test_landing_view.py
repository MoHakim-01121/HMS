from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase


class LandingViewTest(TestCase):
    def test_anonymous_user_sees_landing_page(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)

    def test_authenticated_user_is_redirected_to_dashboard(self):
        user = User.objects.create_user('staff_landing', password='pw12345')
        self.client.force_login(user)
        resp = self.client.get('/')
        self.assertRedirects(resp, '/dashboard/')

    def test_authenticated_user_with_permission_can_preview(self):
        # Default 'staff' role (see hw/permissions.py role_matrix) includes
        # landing:view, matching the same gate already used by landing_manage.
        user = User.objects.create_user('staff_preview', password='pw12345')
        self.client.force_login(user)
        resp = self.client.get('/?preview=1')
        self.assertEqual(resp.status_code, 200)

    def test_preview_flag_alone_does_not_bypass_without_permission(self):
        user = User.objects.create_user('staff_nogrant', password='pw12345')
        self.client.force_login(user)
        with patch('hw.views.can', return_value=False):
            resp = self.client.get('/?preview=1')
        self.assertRedirects(resp, '/dashboard/')
