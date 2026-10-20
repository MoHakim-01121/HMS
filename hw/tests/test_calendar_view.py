from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models.confirmation import ReservationStatus
from hw.tests.factories import make_cl, make_hotel, make_room


class CalendarViewTest(TestCase):
    """The calendar timeline: two weeks from a Sunday, or a month, with every
    booking that touches the range sent as real dates."""

    def setUp(self):
        self.client.force_login(User.objects.create_superuser("cal", password="pw12345"))

    def _props(self, **params):
        res = self.client.get('/calendar/', params, HTTP_X_INERTIA='true')
        self.assertEqual(res.status_code, 200)
        return res.json()['props']

    def test_two_weeks_open_on_the_sunday_of_the_anchor_week(self):
        props = self._props(start='2026-10-15')  # a Thursday
        self.assertEqual((props['view'], props['start'], props['end']), ('weeks', '2026-10-11', '2026-10-24'))

    def test_month_view_covers_the_month_holding_the_anchor(self):
        props = self._props(view='month', start='2026-02-10')
        self.assertEqual((props['view'], props['start'], props['end']), ('month', '2026-02-01', '2026-02-28'))

    def test_bad_start_falls_back_to_this_week(self):
        props = self._props(start='nope')
        self.assertLessEqual(date.fromisoformat(props['start']), date.today())
        self.assertGreater(date.fromisoformat(props['end']), date.today())

    def test_bookings_in_range_with_rooms_and_city_order(self):
        madinah = make_hotel('Pullman Madinah', city='madinah')
        makkah = make_hotel('Swissotel Makkah', city='makkah')
        cl = make_cl(hotel=makkah, guest_name='Barokah Umrah', check_in=date(2026, 10, 15),
                     check_out=date(2026, 10, 20), reservation_status=ReservationStatus.TENTATIVE)
        make_room(cl=cl, room_type='Quad', quantity=4)
        make_room(cl=cl, room_type='Double', quantity=2)
        make_cl(hotel=madinah, check_in=date(2026, 10, 9), check_out=date(2026, 10, 11))  # leaves on day one
        make_cl(hotel=makkah, check_in=date(2026, 10, 12), check_out=date(2026, 10, 14),
                reservation_status=ReservationStatus.CANCELLED)
        make_cl(hotel=makkah, check_in=date(2026, 11, 2), check_out=date(2026, 11, 4))  # outside

        props = self._props(start='2026-10-11')
        self.assertEqual([h['name'] for h in props['hotels']], ['Swissotel Makkah', 'Pullman Madinah'])
        self.assertEqual(len(props['bookings']), 2)
        b = next(x for x in props['bookings'] if x['client'] == 'Barokah Umrah')
        self.assertEqual((b['check_in'], b['check_out'], b['tentative'], b['rooms'], b['room_types']),
                         ('2026-10-15', '2026-10-20', True, 6, '4 Quad, 2 Double'))
        self.assertEqual((b['inv_number'], b['inv_open']), ('', None))

    def test_month_view_reaches_past_the_two_weeks(self):
        make_cl(check_in=date(2026, 10, 28), check_out=date(2026, 10, 30))
        self.assertEqual(len(self._props(start='2026-10-01')['bookings']), 0)
        self.assertEqual(len(self._props(view='month', start='2026-10-01')['bookings']), 1)
        self.assertEqual(len(self._props(start=(date(2026, 10, 28) - timedelta(days=3)).isoformat())['bookings']), 1)
