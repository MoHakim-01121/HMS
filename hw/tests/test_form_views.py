from django.contrib.auth.models import User
from django.test import TestCase


class FlashShareTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="pw12345")
        self.client.force_login(self.user)
        session = self.client.session
        session["active_company"] = "konoz"
        session.save()

    def test_success_message_shared_as_flash(self):
        # client_delete already redirects to the (Inertia) client_list with a
        # messages.success — this exercises flash sharing WITHOUT depending on
        # any view migrated in a later task.
        from hw.models import Client
        c = Client.objects.create(company="konoz", name="PT Uji Flash")
        # POST the delete — expect redirect, do NOT follow it
        resp = self.client.post(f"/clients/{c.pk}/delete/")
        self.assertEqual(resp.status_code, 302)
        redirect_url = resp["Location"]
        # Now GET the redirect target with the Inertia header (no version header
        # so the middleware does not treat it as stale and return 409).
        resp2 = self.client.get(
            redirect_url,
            HTTP_X_INERTIA="true",
        )
        self.assertEqual(resp2.status_code, 200)
        # After following the redirect, the Inertia page JSON carries flash.success.
        page = resp2.json()
        self.assertIn("flash", page["props"])
        self.assertIsNotNone(page["props"]["flash"]["success"])
