from django.contrib.auth.models import User
from django.test import TestCase

from hw.tests.factories import make_cl


class ClListSalespersonFilterTests(TestCase):
    """The CL list's Salesperson filter: a user id, `none` for the CLs made
    before the field existed, and no value for everyone."""

    def setUp(self):
        self.user = User.objects.create_user("tester", password="pw12345")
        self.other = User.objects.create_user("other", password="pw12345", first_name="Siti")
        self.client.force_login(self.user)
        session = self.client.session
        session["active_company"] = "konoz"
        session.save()
        self.mine = make_cl(confirmation_number="HMS/241", salesperson=self.user)
        self.theirs = make_cl(confirmation_number="HMS/142", salesperson=self.other)
        self.legacy = make_cl(confirmation_number="HMS/999")

    def _props(self, **params):
        resp = self.client.get("/cl/", params, HTTP_X_INERTIA="true")
        self.assertEqual(resp.status_code, 200)
        return resp.json()["props"]

    def _numbers(self, **params):
        return {letter["confirmation_number"] for letter in self._props(**params)["letters"]}

    def test_no_salesperson_filter_shows_everyone(self):
        self.assertEqual(self._numbers(), {"HMS/241", "HMS/142", "HMS/999"})

    def test_filters_by_salesperson_id(self):
        self.assertEqual(self._numbers(salesperson=str(self.user.pk)), {"HMS/241"})
        self.assertEqual(self._numbers(salesperson=str(self.other.pk)), {"HMS/142"})

    def test_none_picks_the_legacy_cls_without_a_salesperson(self):
        self.assertEqual(self._numbers(salesperson="none"), {"HMS/999"})

    def test_unknown_value_is_ignored(self):
        self.assertEqual(self._numbers(salesperson="bukan-angka"), {"HMS/241", "HMS/142", "HMS/999"})

    def test_props_name_the_salespeople_and_their_counts(self):
        props = self._props(salesperson=str(self.other.pk))
        self.assertEqual(props["filters"]["salesperson"], str(self.other.pk))
        # The signed-in user is offered as "My CLs", not repeated by name.
        self.assertEqual(
            props["salespeople"],
            [{"id": self.other.pk, "name": "Siti", "count": 1}],
        )
        self.assertEqual(props["counts"]["unassigned"], 1)
        self.assertEqual(props["counts"]["mine"], 1)
        self.assertEqual(props["counts"]["all"], 3)

    def test_me_picks_the_signed_in_users_cls(self):
        self.assertEqual(self._numbers(salesperson="me"), {"HMS/241"})

    def test_own_id_is_normalised_to_me(self):
        self.assertEqual(self._numbers(salesperson=str(self.user.pk)), {"HMS/241"})
        props = self._props(salesperson=str(self.user.pk))
        self.assertEqual(props["filters"]["salesperson"], "me")

    def test_export_csv_honours_me(self):
        resp = self.client.get("/cl/export/csv/", {"salesperson": "me"})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8-sig")
        self.assertIn("HMS/241", content)
        self.assertNotIn("HMS/142", content)
        self.assertNotIn("HMS/999", content)

    def test_picked_salesperson_stays_in_the_menu_outside_their_month(self):
        props = self._props(salesperson=str(self.other.pk), month="2020-01")
        self.assertIn(
            {"id": self.other.pk, "name": "Siti", "count": 0},
            props["salespeople"],
        )
        self.assertEqual(props["letters"], [])

    def test_export_csv_honours_the_salesperson(self):
        resp = self.client.get("/cl/export/csv/", {"salesperson": str(self.user.pk)})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8-sig")
        self.assertIn("HMS/241", content)
        self.assertNotIn("HMS/142", content)
        self.assertNotIn("HMS/999", content)

    def test_export_csv_none_picks_the_legacy_cls(self):
        resp = self.client.get("/cl/export/csv/", {"salesperson": "none"})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8-sig")
        self.assertIn("HMS/999", content)
        self.assertNotIn("HMS/241", content)
