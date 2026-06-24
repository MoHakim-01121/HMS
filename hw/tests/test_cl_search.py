from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import ConfirmationLetter
from hw.views.cl_views import _parse_search_tokens


class ParseSearchTokensTests(TestCase):
    def test_single_token_no_comma(self):
        self.assertEqual(_parse_search_tokens("241"), ["241"])

    def test_multi_token_splits_by_comma(self):
        self.assertEqual(_parse_search_tokens("241,142,555"), ["241", "142", "555"])

    def test_strips_whitespace_around_commas(self):
        self.assertEqual(_parse_search_tokens("241 , 142"), ["241", "142"])

    def test_empty_tokens_are_dropped(self):
        self.assertEqual(_parse_search_tokens("241,,555"), ["241", "555"])

    def test_all_empty_tokens_returns_empty_list(self):
        self.assertEqual(_parse_search_tokens(" , , "), [])

    def test_token_truncated_at_100_chars(self):
        long = "x" * 150
        result = _parse_search_tokens(long)
        self.assertEqual(len(result[0]), 100)

    def test_token_over_100_in_multi(self):
        long = "x" * 150
        result = _parse_search_tokens(f"abc,{long}")
        self.assertEqual(result[0], "abc")
        self.assertEqual(len(result[1]), 100)


class ClListMultiSearchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="pw12345")
        self.client.force_login(self.user)
        s = self.client.session
        s["active_company"] = "konoz"
        s.save()
        ConfirmationLetter.objects.create(
            company="konoz", confirmation_number="HMS/241", guest_name="Ahmad", hotel_name="Hotel A"
        )
        ConfirmationLetter.objects.create(
            company="konoz", confirmation_number="HMS/142", guest_name="Budi", hotel_name="Hotel B"
        )
        ConfirmationLetter.objects.create(
            company="konoz", confirmation_number="HMS/999", guest_name="Citra", hotel_name="Hotel C"
        )

    def _get_letters(self, q):
        resp = self.client.get("/cl/", {"q": q}, HTTP_X_INERTIA="true")
        self.assertEqual(resp.status_code, 200)
        return resp.json()["props"]["letters"]

    def test_single_query_matches_confirmation_number(self):
        letters = self._get_letters("HMS/241")
        self.assertEqual(len(letters), 1)
        self.assertEqual(letters[0]["confirmation_number"], "HMS/241")

    def test_single_query_matches_guest_name(self):
        letters = self._get_letters("Ahmad")
        self.assertEqual(len(letters), 1)
        self.assertEqual(letters[0]["confirmation_number"], "HMS/241")

    def test_multi_query_returns_matching_cls(self):
        letters = self._get_letters("HMS/241,HMS/142")
        numbers = {l["confirmation_number"] for l in letters}
        self.assertEqual(numbers, {"HMS/241", "HMS/142"})

    def test_multi_query_does_not_return_unmatched_cl(self):
        letters = self._get_letters("HMS/241,HMS/142")
        numbers = {l["confirmation_number"] for l in letters}
        self.assertNotIn("HMS/999", numbers)

    def test_multi_query_matches_guest_name(self):
        letters = self._get_letters("Ahmad,Budi")
        numbers = {l["confirmation_number"] for l in letters}
        self.assertEqual(numbers, {"HMS/241", "HMS/142"})

    def test_multi_query_matches_hotel_name(self):
        letters = self._get_letters("Hotel A,Hotel B")
        numbers = {l["confirmation_number"] for l in letters}
        self.assertEqual(numbers, {"HMS/241", "HMS/142"})

    def test_empty_comma_query_returns_all(self):
        letters = self._get_letters(" , , ")
        self.assertEqual(len(letters), 3)

    def test_multi_query_export_csv_filters_correctly(self):
        resp = self.client.get("/cl/export/csv/", {"q": "HMS/241,HMS/142"})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8-sig")
        self.assertIn("HMS/241", content)
        self.assertIn("HMS/142", content)
        self.assertNotIn("HMS/999", content)

    def test_multi_query_export_pdf_returns_200(self):
        resp = self.client.get("/cl/export/pdf/", {"q": "HMS/241,HMS/142"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/pdf", resp.get("Content-Type", ""))
