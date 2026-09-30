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
