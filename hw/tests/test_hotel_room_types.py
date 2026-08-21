from django.db import IntegrityError
from django.test import TestCase

from hw.models import Hotel, RoomType


class RoomTypeModelTest(TestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create(company='konoz', name='Hotel Sawaaed', city='makkah')

    def test_str_includes_hotel_name(self):
        rt = RoomType.objects.create(hotel=self.hotel, name='Double View Kaaba', capacity=2)
        self.assertEqual(str(rt), 'Double View Kaaba (Hotel Sawaaed)')

    def test_default_capacity_is_two(self):
        rt = RoomType.objects.create(hotel=self.hotel, name='Double Non View')
        self.assertEqual(rt.capacity, 2)

    def test_default_is_active_true(self):
        rt = RoomType.objects.create(hotel=self.hotel, name='Double Non View')
        self.assertTrue(rt.is_active)

    def test_duplicate_name_same_hotel_raises(self):
        RoomType.objects.create(hotel=self.hotel, name='Suite', capacity=2)
        with self.assertRaises(IntegrityError):
            RoomType.objects.create(hotel=self.hotel, name='Suite', capacity=4)

    def test_same_name_different_hotel_is_allowed(self):
        other_hotel = Hotel.objects.create(company='konoz', name='Hotel Zam Zam', city='makkah')
        RoomType.objects.create(hotel=self.hotel, name='Suite', capacity=2)
        # Must not raise — uniqueness is scoped per hotel, not global.
        RoomType.objects.create(hotel=other_hotel, name='Suite', capacity=2)
        self.assertEqual(RoomType.objects.filter(name='Suite').count(), 2)
