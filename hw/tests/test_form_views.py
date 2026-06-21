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


class ClientFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester2", password="pw12345")
        self.client.force_login(self.user)
        s = self.client.session; s["active_company"] = "konoz"; s.save()

    def _inertia(self, url, data, follow=False):
        return self.client.post(url, data, follow=follow, HTTP_X_INERTIA="true")

    def test_get_renders_inertia_form(self):
        resp = self.client.get("/clients/new/", HTTP_X_INERTIA="true")
        self.assertEqual(resp.json()["component"], "Client/Form")

    def test_missing_name_returns_errors(self):
        resp = self._inertia("/clients/new/", {"name": ""})
        page = resp.json()
        self.assertEqual(page["component"], "Client/Form")
        self.assertIn("name", page["props"]["errors"])

    def test_valid_create_redirects_to_detail(self):
        from hw.models import Client
        resp = self._inertia("/clients/new/", {"name": "PT Sahabat"})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Client.objects.filter(name="PT Sahabat").exists())


class PenaltyViewTests(TestCase):
    def setUp(self):
        from hw.models import ConfirmationLetter
        self.user = User.objects.create_user("tester3", password="pw12345")
        self.client.force_login(self.user)
        s = self.client.session; s["active_company"] = "konoz"; s.save()
        self.cl = ConfirmationLetter.objects.create(
            company="konoz", guest_name="Budi", confirmation_number="CL-1",
        )

    def _inertia_get(self, url):
        return self.client.get(url, HTTP_X_INERTIA="true")

    def _make_penalty(self, number="PNL-001"):
        from datetime import date
        from hw.models import CancellationPenalty
        return CancellationPenalty.objects.create(
            cl=self.cl, penalty_number=number,
            cancellation_date=date.today(), penalty_amount=500,
        )

    def test_detail_renders_inertia(self):
        p = self._make_penalty()
        resp = self._inertia_get(f"/penalty/{p.pk}/")
        self.assertEqual(resp.json()["component"], "Penalty/Detail")

    def test_new_get_renders_form(self):
        resp = self._inertia_get(f"/cl/{self.cl.pk}/penalty/new/")
        self.assertEqual(resp.json()["component"], "Penalty/Form")

    def test_new_post_creates_and_redirects(self):
        from datetime import date
        from hw.models import CancellationPenalty
        resp = self.client.post(
            f"/cl/{self.cl.pk}/penalty/new/",
            {
                "penalty_number": "PNL-X", "cancellation_date": date.today().isoformat(),
                "penalty_amount": "500", "penalty_currency": "SAR", "exchange_rate": "1",
            },
            HTTP_X_INERTIA="true",
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(CancellationPenalty.objects.filter(penalty_number="PNL-X").exists())


class UserAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "a@a.com", "pw12345")
        self.client.force_login(self.admin)

    def _inertia_get(self, url):
        return self.client.get(url, HTTP_X_INERTIA="true")

    def _inertia_post(self, url, data):
        return self.client.post(url, data, HTTP_X_INERTIA="true")

    def test_user_list_renders_inertia(self):
        page = self._inertia_get("/users/").json()
        self.assertEqual(page["component"], "User/List")
        self.assertTrue(any(u["username"] == "admin" for u in page["props"]["users"]))

    def test_new_get_renders_form(self):
        self.assertEqual(self._inertia_get("/users/new/").json()["component"], "User/Form")

    def test_password_mismatch_returns_error(self):
        page = self._inertia_post("/users/new/", {"username": "bob", "password": "a", "password_confirm": "b"}).json()
        self.assertEqual(page["component"], "User/Form")
        self.assertIn("password_confirm", page["props"]["errors"])

    def test_duplicate_username_returns_error(self):
        resp = self._inertia_post("/users/new/", {"username": "admin", "password": "x", "password_confirm": "x"})
        self.assertIn("username", resp.json()["props"]["errors"])

    def test_valid_create_redirects(self):
        resp = self._inertia_post("/users/new/", {"username": "carol", "password": "pw", "password_confirm": "pw"})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(username="carol").exists())


class ClFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester4", password="pw12345")
        self.client.force_login(self.user)
        s = self.client.session; s["active_company"] = "konoz"; s.save()

    def _post(self, url, data):
        return self.client.post(url, data, HTTP_X_INERTIA="true")

    def test_get_renders_inertia_form(self):
        resp = self.client.get("/cl/new/", HTTP_X_INERTIA="true")
        self.assertEqual(resp.json()["component"], "Cl/Form")

    def test_checkout_before_checkin_returns_error(self):
        page = self._post("/cl/new/", {
            "confirmation_number": "CLX-1", "company": "konoz",
            "check_in": "2026-06-10", "check_out": "2026-06-05", "rooms": "[]",
        }).json()
        self.assertEqual(page["component"], "Cl/Form")
        self.assertIn("check_out", page["props"]["errors"])

    def test_duplicate_number_returns_error(self):
        from hw.models import ConfirmationLetter
        ConfirmationLetter.objects.create(company="konoz", confirmation_number="CLX-DUP")
        page = self._post("/cl/new/", {"confirmation_number": "CLX-DUP", "company": "konoz", "rooms": "[]"}).json()
        self.assertIn("confirmation_number", page["props"]["errors"])

    def test_valid_create_with_rooms(self):
        from hw.models import ConfirmationLetter, Room
        resp = self._post("/cl/new/", {
            "confirmation_number": "CLX-OK", "company": "konoz",
            "guest_name": "Budi", "hotel_name": "Hilton",
            "reservation_status": "DEFINITE",
            "rooms": '[{"room_type":"Double","meals":"BB","quantity":2,"price":300}]',
        })
        self.assertEqual(resp.status_code, 302)
        cl = ConfirmationLetter.objects.get(confirmation_number="CLX-OK")
        rooms = Room.objects.filter(cl=cl)
        self.assertEqual(rooms.count(), 1)
        self.assertEqual(rooms.first().quantity, 2)


class ProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("profiler", password="pw12345")
        self.client.force_login(self.user)

    def test_profile_renders_inertia(self):
        resp = self.client.get("/account/profile/", HTTP_X_INERTIA="true")
        self.assertEqual(resp.status_code, 200)
        page = resp.json()
        self.assertEqual(page["component"], "Account/Profile")
        self.assertEqual(page["props"]["account"]["username"], "profiler")
        self.assertIn("activities", page["props"])

    def test_profile_serializes_activity_with_changes(self):
        from hw.models import ActivityLog, log_activity
        log_activity(self.user, ActivityLog.ACTION_EDIT, "Hotel", "Hilton", "konoz",
                     [{"label": "Nama", "before": "A", "after": "B"}])
        page = self.client.get("/account/profile/", HTTP_X_INERTIA="true").json()
        acts = page["props"]["activities"]
        edits = [a for a in acts if a["action"] == "edit"]
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["object_ref"], "Hilton")
        self.assertEqual(edits[0]["changes"][0]["after"], "B")


class SessionExpiryInertiaTests(TestCase):
    """An expired session must redirect Inertia (XHR) requests cleanly via a
    409 + X-Inertia-Location, instead of feeding the HTML login page back to the
    Inertia client (which errors out)."""

    def test_inertia_request_when_logged_out_returns_409_location(self):
        # No login → @login_required would redirect to /login/.
        resp = self.client.get("/remittance/", HTTP_X_INERTIA="true")
        self.assertEqual(resp.status_code, 409)
        self.assertIn("/login/", resp["X-Inertia-Location"])

    def test_inertia_post_when_logged_out_returns_409_location(self):
        resp = self.client.post("/remittance/1/delete/", HTTP_X_INERTIA="true")
        self.assertEqual(resp.status_code, 409)
        self.assertIn("/login/", resp["X-Inertia-Location"])

    def test_non_inertia_request_still_redirects_302(self):
        # Plain browser navigation keeps the normal redirect behaviour.
        resp = self.client.get("/remittance/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])

    def test_inertia_redirect_to_non_login_is_untouched(self):
        # An authenticated Inertia action that redirects to another Inertia page
        # must NOT be converted to a 409.
        user = User.objects.create_user("sess_ok", password="pw12345")
        self.client.force_login(user)
        s = self.client.session; s["active_company"] = "konoz"; s.save()
        from hw.models import Client
        c = Client.objects.create(company="konoz", name="PT Sesi")
        resp = self.client.post(f"/clients/{c.pk}/delete/", HTTP_X_INERTIA="true")
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("/login/", resp["Location"])
