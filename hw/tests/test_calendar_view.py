from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.http import HttpResponse
from django.test import TestCase

from hw.models import RoomType
from hw.models.confirmation import ReservationStatus
from hw.tests.factories import make_cl, make_client, make_hotel, make_room


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


class CheckinRecapPdfTest(TestCase):
    """The check-in recap: one day or a range, by date, then hotel."""

    def setUp(self):
        self.client.force_login(User.objects.create_superuser("cal", password="pw12345"))

    def _ctx(self, **params):
        with patch('hw.views.helpers._render_list_pdf', return_value=HttpResponse()) as render:
            res = self.client.get('/calendar/checkin-pdf/', params)
        self.assertEqual(res.status_code, 200)
        return render.call_args.kwargs['extra_ctx']

    def test_renders_a_pdf(self):
        cl = make_cl(check_in=date(2026, 10, 15), check_out=date(2026, 10, 18), guest_name='Barokah Umrah')
        make_room(cl=cl, room_type='Quad', quantity=4)
        res = self.client.get('/calendar/checkin-pdf/', {'start': '2026-10-15', 'end': '2026-10-15'})
        self.assertEqual(res['Content-Type'], 'application/pdf')
        self.assertTrue(res.content.startswith(b'%PDF'))
        self.assertIn('checkin-recap-2026-10-15.pdf', res['Content-Disposition'])

    def test_groups_by_date_then_hotel_makkah_first(self):
        madinah = make_hotel('Pullman Madinah', city='madinah')
        makkah = make_hotel('Swissotel Makkah', city='makkah')
        make_cl(hotel=madinah, guest_name='Ahmad', check_in=date(2026, 10, 15), check_out=date(2026, 10, 17))
        make_cl(hotel=makkah, guest_name='Budi', check_in=date(2026, 10, 15), check_out=date(2026, 10, 17))
        make_cl(hotel=makkah, guest_name='Candra', check_in=date(2026, 10, 16), check_out=date(2026, 10, 17))

        ctx = self._ctx(start='2026-10-15', end='2026-10-16')
        self.assertEqual([g['date'] for g in ctx['groups']], [date(2026, 10, 15), date(2026, 10, 16)])
        self.assertEqual([h['name'] for h in ctx['groups'][0]['hotels']], ['Swissotel Makkah', 'Pullman Madinah'])
        self.assertEqual(ctx['groups'][0]['hotels'][1]['rows'][0]['client_name'], 'Ahmad')
        self.assertEqual((ctx['total_checkins'], ctx['total_hotels']), (3, 2))

    def test_one_line_per_room_type_and_meal_smallest_room_first(self):
        cl = make_cl(check_in=date(2026, 10, 15), check_out=date(2026, 10, 20))
        make_room(cl=cl, room_type='Quad', quantity=4, meals='FB')
        make_room(cl=cl, room_type='Double', quantity=2, meals='BB')
        make_room(cl=cl, room_type='Quad', quantity=1, meals='FB')
        row = self._ctx(start='2026-10-15')['groups'][0]['hotels'][0]['rows'][0]
        self.assertEqual([(l['room_type'], l['rooms'], l['pax']) for l in row['lines']],
                         [('Double - BB', 2, 4), ('Quad - FB', 5, 20)])
        self.assertEqual((row['rooms'], row['pax'], row['span']), (7, 24, 3))

    def test_views_of_one_size_run_kaaba_haram_city_then_none(self):
        cl = make_cl(check_in=date(2026, 10, 15), check_out=date(2026, 10, 20))
        for name, view in (('Quad', ''), ('Quad City View', 'city'), ('Quad Kaaba View', 'kaaba'), ('Quad Haram View', 'haram')):
            make_room(cl=cl, room_type_ref=RoomType.objects.create(hotel=cl.hotel, name=name, capacity=4, view=view), quantity=1)
        row = self._ctx(start='2026-10-15')['groups'][0]['hotels'][0]['rows'][0]
        self.assertEqual([l['room_type'] for l in row['lines']],
                         ['Quad Kaaba View', 'Quad Haram View', 'Quad City View', 'Quad'])

    def test_a_single_room_type_has_no_total_row(self):
        cl = make_cl(check_in=date(2026, 10, 15), check_out=date(2026, 10, 20))
        make_room(cl=cl, room_type='Quad', quantity=8, meals='FB')
        row = self._ctx(start='2026-10-15')['groups'][0]['hotels'][0]['rows'][0]
        self.assertEqual((row['lines'][0]['room_type'], row['span']), ('Quad - FB', 1))

    def test_row_carries_the_booking_and_the_hotel_its_totals(self):
        client = make_client('Barokah Umrah')
        cl = make_cl(client=client, check_in=date(2026, 10, 15), check_out=date(2026, 10, 20), confirmation_number='K-010',
                     reservation_status=ReservationStatus.TENTATIVE, note='Perlu konfirmasi FB')
        make_room(cl=cl, room_type='Quad', quantity=4, meals='FB')
        make_room(cl=cl, room_type='Double', quantity=2, meals='FB')

        ctx = self._ctx(start='2026-10-15')
        hotel = ctx['groups'][0]['hotels'][0]
        row = hotel['rows'][0]
        self.assertEqual((row['confirmation_number'], row['rooms'], row['pax'], row['tentative'], row['note']),
                         ('K-010', 6, 20, True, 'Perlu konfirmasi FB'))
        self.assertEqual((row['check_in'], row['check_out']), (date(2026, 10, 15), date(2026, 10, 20)))
        self.assertEqual((hotel['rooms'], hotel['pax']), (6, 20))
        self.assertEqual((ctx['total_rooms'], ctx['total_pax']), (6, 20))

    def test_every_booking_names_its_travel_client(self):
        hotel = make_hotel('Swissotel Makkah')
        travel = make_client('Barokah Travel')
        make_cl(hotel=hotel, client=travel, guest_name='Zain', confirmation_number='K-1',
                check_in=date(2026, 10, 15), check_out=date(2026, 10, 17))
        make_cl(hotel=hotel, guest_name='Budi', confirmation_number='K-2',
                check_in=date(2026, 10, 15), check_out=date(2026, 10, 17))
        make_cl(hotel=hotel, client=travel, guest_name='Ahmad', confirmation_number='K-3',
                check_in=date(2026, 10, 15), check_out=date(2026, 10, 17))
        rows = self._ctx(start='2026-10-15')['groups'][0]['hotels'][0]['rows']
        self.assertEqual([r['client_name'] for r in rows], ['Barokah Travel', 'Barokah Travel', 'Budi'])

    def test_counts_check_ins_as_the_calendar_does(self):
        hotel = make_hotel('Swissotel Makkah')
        for _ in range(2):  # two CLs of one client at one hotel are one check-in
            make_cl(hotel=hotel, guest_name='Ahmad', check_in=date(2026, 10, 15), check_out=date(2026, 10, 17))
        ctx = self._ctx(start='2026-10-15')
        self.assertEqual(ctx['groups'][0]['total'], 1)
        self.assertEqual(ctx['total_checkins'], 1)

    def test_leaves_out_cancelled_and_other_dates(self):
        make_cl(check_in=date(2026, 10, 15), check_out=date(2026, 10, 17), reservation_status=ReservationStatus.CANCELLED)
        make_cl(check_in=date(2026, 10, 14), check_out=date(2026, 10, 17))
        make_cl(check_in=date(2026, 10, 16), check_out=date(2026, 10, 17))
        self.assertEqual(self._ctx(start='2026-10-15')['groups'], [])

    def test_bad_dates_fall_back_to_today(self):
        make_cl(check_in=date.today(), check_out=date.today() + timedelta(days=1))
        self.assertEqual(len(self._ctx(start='nope', end='nope')['groups']), 1)

    def test_end_before_start_is_the_start_day(self):
        make_cl(check_in=date(2026, 10, 15), check_out=date(2026, 10, 17))
        self.assertEqual(len(self._ctx(start='2026-10-15', end='2026-10-01')['groups']), 1)

    def test_needs_the_export_permission(self):
        with patch('hw.permissions.can', side_effect=lambda user, module, action: action != 'export'):
            res = self.client.get('/calendar/checkin-pdf/', {'start': '2026-10-15'})
        self.assertEqual(res.status_code, 302)
