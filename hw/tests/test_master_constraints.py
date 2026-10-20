"""Schema v2 F2b — aturan master data yang dijaga database: hotel, tipe kamar, vendor."""
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from hw.models import Hotel, RoomType, Vendor


class HotelConstraintTest(TestCase):
    def test_name_unique_per_city_only(self):
        Hotel.objects.create(name='Al Safwah', city='makkah')
        Hotel.objects.create(name='Al Safwah', city='madinah')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Hotel.objects.create(name='Al Safwah', city='makkah')

    def test_stars_must_be_one_to_five(self):
        for bad in (0, 6):
            with self.assertRaises(IntegrityError), transaction.atomic():
                Hotel.objects.create(name=f'H{bad}', city='makkah', stars=bad)

    def test_city_must_be_known(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Hotel.objects.create(name='H', city='jeddah')


class HotelFormTest(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser('admin', password='x'))

    def test_duplicate_is_refused_with_a_message_not_a_crash(self):
        Hotel.objects.create(name='Al Safwah', city='makkah')
        resp = self.client.post(reverse('hotel_new'), {'name': 'al safwah', 'city': 'makkah', 'stars': '4', 'is_active': 'on'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Hotel.objects.count(), 1)

    def test_out_of_range_stars_refused(self):
        self.client.post(reverse('hotel_new'), {'name': 'New', 'city': 'makkah', 'stars': '9', 'is_active': 'on'})
        self.assertFalse(Hotel.objects.filter(name='New').exists())

    def test_list_filters_by_allotment_status_and_location(self):
        Hotel.objects.create(name='A', city='makkah', stars=5, has_allotment=True, lat=21.4, lng=39.8)
        Hotel.objects.create(name='B', city='makkah', stars=2, is_active=False)
        Hotel.objects.create(name='C', city='madinah', stars=3, has_allotment=True)

        def names(qs):
            resp = self.client.get(reverse('hotel_list') + qs, HTTP_X_INERTIA='true')
            return sorted(h['name'] for h in resp.json()['props']['hotels'])

        self.assertEqual(names('?allotment=yes'), ['A', 'C'])
        self.assertEqual(names('?status=inactive'), ['B'])
        self.assertEqual(names('?location=missing'), ['B', 'C'])
        self.assertEqual(names('?location=set,missing'), ['A', 'B', 'C'])
        self.assertEqual(names('?stars=2'), ['B'])
        self.assertEqual(names('?allotment=yes&location=set'), ['A'])

    def test_city_and_stars_are_required(self):
        self.client.post(reverse('hotel_new'), {'name': 'No City', 'stars': '4'})
        self.client.post(reverse('hotel_new'), {'name': 'No Stars', 'city': 'makkah'})
        self.assertFalse(Hotel.objects.filter(name__in=['No City', 'No Stars']).exists())

    def test_edit_saves_coordinates_and_keeps_the_stored_route(self):
        route = [[21.4203, 39.8265], [21.4182, 39.8288]]
        h = Hotel.objects.create(name='Elaf Ajyad', city='makkah', route=route)
        self.client.post(reverse('hotel_edit', args=[h.pk]), {
            'name': 'Elaf Ajyad', 'city': 'makkah', 'stars': '4', 'is_active': 'on',
            'lat': '21.41816', 'lng': '39.82877', 'avg_occupancy': '3.4',
        })
        h.refresh_from_db()
        self.assertEqual((h.lat, h.lng), (21.41816, 39.82877))
        self.assertEqual(h.route, route)
        self.assertEqual(h.distance_label, '337 m')

    def test_clearing_coordinates_removes_the_distance(self):
        h = Hotel.objects.create(name='Elaf Ajyad', city='makkah', lat=21.41816, lng=39.82877)
        self.client.post(reverse('hotel_edit', args=[h.pk]), {'name': 'Elaf Ajyad', 'city': 'makkah', 'stars': '4', 'lat': '', 'lng': ''})
        h.refresh_from_db()
        self.assertIsNone(h.lat)
        self.assertEqual(h.distance_label, '—')


class RoomTypeConstraintTest(TestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create(name='H', city='makkah')

    def test_capacity_range(self):
        for bad in (0, 11):
            with self.assertRaises(IntegrityError), transaction.atomic():
                RoomType.objects.create(hotel=self.hotel, name=f'R{bad}', capacity=bad)

    def test_view_must_be_known_or_blank(self):
        RoomType.objects.create(hotel=self.hotel, name='Plain', capacity=2, view='')
        with self.assertRaises(IntegrityError), transaction.atomic():
            RoomType.objects.create(hotel=self.hotel, name='Sea', capacity=2, view='sea')

    def test_occupancy_is_derived_from_capacity(self):
        rt = RoomType.objects.create(hotel=self.hotel, name='Q', capacity=4)
        self.assertEqual(rt.occupancy, 'quad')
        rt.capacity = 3
        self.assertEqual(rt.occupancy, 'triple')
        self.assertEqual(RoomType(capacity=7).occupancy, '')


class VendorTest(TestCase):
    def test_one_row_per_vendor_name(self):
        Vendor.objects.create(name='PT. Visa Cepat')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Vendor.objects.create(name='VISA CEPAT')
