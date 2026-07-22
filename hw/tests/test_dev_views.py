from django.contrib.auth.models import User
from django.test import TestCase


class StyleGuideAccessTests(TestCase):
    def test_anonymous_user_redirects_to_login(self):
        # Mirrors health_check (hw/views/__init__.py:134-139): anonymous
        # users are redirected to login, NOT shown a 404 — only an
        # authenticated-but-not-superuser request gets the 404.
        resp = self.client.get("/dev/style-guide/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])

    def test_regular_user_gets_404(self):
        user = User.objects.create_user("regular", password="pw12345")
        self.client.force_login(user)
        resp = self.client.get("/dev/style-guide/")
        self.assertEqual(resp.status_code, 404)

    def test_superuser_gets_200(self):
        admin = User.objects.create_superuser("admin", "admin@example.com", "pw12345")
        self.client.force_login(admin)
        resp = self.client.get("/dev/style-guide/")
        self.assertEqual(resp.status_code, 200)
