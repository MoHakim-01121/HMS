"""Client list season KPIs count CLs by when they were sold (created_at),
not by check-in: a CL booked now for next season's travel is this season's
sale (user decision 2026-10-27)."""
from datetime import date, datetime
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from hw.models import ConfirmationLetter
from hw.models.period import Season
from hw.tests.factories import make_cl, make_client

TODAY = date(2026, 10, 27)


def _sold_on(cl, d):
    ConfirmationLetter.objects.filter(pk=cl.pk).update(
        created_at=timezone.make_aware(datetime(d.year, d.month, d.day, 10)))


class ClientSeasonKpiTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        Season.objects.create(name='Musim 1447H', date_from=date(2025, 6, 10), date_to=date(2026, 5, 30))
        Season.objects.create(name='Musim 1448H', date_from=date(2026, 5, 31), date_to=date(2027, 5, 19))
        # Sold this season for next season's travel.
        cls.early = make_client('PT Pesan Awal')
        _sold_on(make_cl(client=cls.early, check_in=date(2027, 8, 1)), date(2026, 7, 1))
        # Sold last season, travelling this season: last season's sale.
        cls.last = make_client('PT Musim Lalu')
        _sold_on(make_cl(client=cls.last, check_in=date(2026, 7, 1)), date(2026, 3, 1))
        cls.user = User.objects.create_superuser('kpi', password='pw12345')

    def _props(self):
        self.client.force_login(self.user)
        with mock.patch('hw.views.client_views.timezone.localdate', return_value=TODAY):
            return self.client.get('/clients/', HTTP_X_INERTIA='true').json()['props']

    def test_season_counts_clients_by_sale_date(self):
        props = self._props()
        self.assertEqual(props['kpis']['season'], 'Musim 1448H')
        self.assertEqual(props['kpis']['active'], 1)
        self.assertEqual(props['kpis']['new'], 1)
        self.assertEqual(props['kpis']['prev_active'], 1)
        status = {c['name']: c['status'] for c in props['clients']}
        self.assertEqual(status['PT Pesan Awal'], 'new')
        self.assertEqual(status['PT Musim Lalu'], 'dormant')

    def test_last_booking_is_the_last_sale(self):
        rows = {c['name']: c for c in self._props()['clients']}
        self.assertEqual(rows['PT Pesan Awal']['last_booking'], '2026-07-01')
        self.assertEqual(rows['PT Pesan Awal']['cl_count'], 1)
        self.assertEqual(rows['PT Musim Lalu']['last_booking'], '2026-03-01')
        self.assertEqual(rows['PT Musim Lalu']['cl_count'], 0)
