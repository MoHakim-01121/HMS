"""A search on the CL and invoice lists looks past the month nav: the CL or
invoice wanted is often in another month (user decision 2026-10-29). A range
picked in the filter still holds, and the KPIs stay on the month."""
from datetime import date, datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from hw.models import ConfirmationLetter
from hw.tests.factories import make_cl, make_client, make_invoice


def _sold_on(cl, d):
    ConfirmationLetter.objects.filter(pk=cl.pk).update(
        created_at=timezone.make_aware(datetime(d.year, d.month, d.day, 10)))


class ListSearchAllDatesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        client = make_client('PT Cari Lintas Bulan')
        _sold_on(make_cl(client=client, check_in=date(2026, 3, 10)), date(2026, 2, 1))
        make_invoice(client=client, due_date=date(2026, 2, 15))
        cls.user = User.objects.create_superuser('search', password='pw12345')

    def _props(self, url):
        self.client.force_login(self.user)
        return self.client.get(url, HTTP_X_INERTIA='true').json()['props']

    def test_cl_search_finds_other_month(self):
        props = self._props('/cl/?month=2026-10&q=Lintas')
        self.assertTrue(props['search_all'])
        self.assertEqual(len(props['letters']), 1)
        self.assertEqual(props['kpis']['cur']['count'], 0)
        self.assertNotIn('date_from', props['export_qs'])

    def test_cl_month_without_search_stays_on_month(self):
        props = self._props('/cl/?month=2026-10')
        self.assertFalse(props['search_all'])
        self.assertEqual(props['letters'], [])

    def test_cl_check_in_range_still_holds(self):
        props = self._props('/cl/?from=2026-10-01&to=2026-10-31&q=Lintas')
        self.assertFalse(props['search_all'])
        self.assertEqual(props['letters'], [])

    def test_invoice_search_finds_other_month(self):
        props = self._props('/invoice/?month=2026-10&q=Lintas')
        self.assertTrue(props['search_all'])
        self.assertEqual(len(props['invoices']), 1)

    def test_invoice_due_range_still_holds(self):
        props = self._props('/invoice/?from=2026-10-01&to=2026-10-31&q=Lintas')
        self.assertFalse(props['search_all'])
        self.assertEqual(props['invoices'], [])
