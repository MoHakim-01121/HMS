"""FASE F remainder — MealPlan master + RoomType occupancy/view vocabulary."""
import json

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Hotel, MealPlan, RoomType


class MealPlanSeedTest(TestCase):
    def test_default_meal_plans_seeded(self):
        codes = set(MealPlan.objects.values_list('code', flat=True))
        self.assertEqual(codes, {'RO', 'BB', 'HB', 'FB'})


class RoomTypeOccupancyViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('vocabadmin', 'a@a.com', 'pass')
        self.client.force_login(self.user)
        session = self.client.session
        session['active_company'] = 'konoz'
        session.save()
        self.hotel = Hotel.objects.create( name='Hotel Vocab', city='makkah')

    def test_hotel_edit_saves_occupancy_and_view(self):
        self.client.post(f'/hotels/{self.hotel.pk}/edit/', {
            'name': self.hotel.name, 'city': 'makkah', 'stars': '4',
            'room_types': json.dumps([
                {'name': 'Quad Kaaba View', 'capacity': 4, 'occupancy': 'quad', 'view': 'kaaba'},
            ]),
        })
        rt = RoomType.objects.get(hotel=self.hotel, name='Quad Kaaba View')
        self.assertEqual(rt.occupancy, 'quad')
        self.assertEqual(rt.view, 'kaaba')

    def test_invalid_vocabulary_values_are_blanked(self):
        self.client.post(f'/hotels/{self.hotel.pk}/edit/', {
            'name': self.hotel.name, 'city': 'makkah', 'stars': '4',
            'room_types': json.dumps([
                {'name': 'Weird Room', 'capacity': 2, 'occupancy': 'bogus', 'view': 'bogus'},
            ]),
        })
        rt = RoomType.objects.get(hotel=self.hotel, name='Weird Room')
        self.assertEqual(rt.occupancy, '')
        self.assertEqual(rt.view, '')

    def test_edit_form_serializes_occupancy_and_view(self):
        RoomType.objects.create(hotel=self.hotel, name='Double Non View', capacity=2, occupancy='double', view='non_view')
        resp = self.client.get(f'/hotels/{self.hotel.pk}/edit/', HTTP_X_INERTIA='true')
        rt_props = resp.json()['props']['hotel']['room_types'][0]
        self.assertEqual(rt_props['occupancy'], 'double')
        self.assertEqual(rt_props['view'], 'non_view')
