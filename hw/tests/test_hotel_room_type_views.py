import json
from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Hotel, RoomType


class HotelRoomTypeSaveTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'admin@test.com', 'pass')
        self.client.force_login(self.user)
        session = self.client.session
        session['active_company'] = 'konoz'
        session.save()

    def _post(self, url, room_types, **extra):
        data = {
            'name': 'Hotel Sawaaed', 'city': 'makkah', 'stars': '4', 'area': '',
            'room_types': json.dumps(room_types),
            **extra,
        }
        return self.client.post(url, data)

    def test_create_hotel_creates_room_types(self):
        self._post('/hotels/new/', [{'name': 'Double View Kaaba', 'capacity': 2}, {'name': 'Suite', 'capacity': 4}])
        hotel = Hotel.objects.get(name='Hotel Sawaaed')
        self.assertEqual(hotel.room_types.count(), 2)
        self.assertEqual(set(hotel.room_types.values_list('name', flat=True)), {'Double View Kaaba', 'Suite'})

    def test_edit_hotel_updates_existing_room_type(self):
        hotel = Hotel.objects.create( name='Hotel Sawaaed', city='makkah')
        rt = RoomType.objects.create(hotel=hotel, name='Suite', capacity=4)
        self._post(f'/hotels/{hotel.pk}/edit/', [{'id': rt.pk, 'name': 'Suite', 'capacity': 6}])
        rt.refresh_from_db()
        self.assertEqual(rt.capacity, 6)

    def test_edit_hotel_soft_removes_dropped_room_type(self):
        hotel = Hotel.objects.create( name='Hotel Sawaaed', city='makkah')
        rt = RoomType.objects.create(hotel=hotel, name='Suite', capacity=4)
        self._post(f'/hotels/{hotel.pk}/edit/', [])
        rt.refresh_from_db()
        self.assertFalse(rt.is_active)
        # Soft-removed, not deleted — the row must still exist.
        self.assertTrue(RoomType.objects.filter(pk=rt.pk).exists())

    def test_edit_hotel_reactivates_room_type_resubmitted_by_id(self):
        hotel = Hotel.objects.create( name='Hotel Sawaaed', city='makkah')
        rt = RoomType.objects.create(hotel=hotel, name='Suite', capacity=4, is_active=False)
        self._post(f'/hotels/{hotel.pk}/edit/', [{'id': rt.pk, 'name': 'Suite', 'capacity': 4}])
        rt.refresh_from_db()
        self.assertTrue(rt.is_active)

    def test_hotel_edit_get_includes_room_types(self):
        hotel = Hotel.objects.create( name='Hotel Sawaaed', city='makkah')
        rt = RoomType.objects.create(hotel=hotel, name='Suite', capacity=4)
        resp = self.client.get(f'/hotels/{hotel.pk}/edit/', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        page = resp.json()
        self.assertEqual(
            page['props']['hotel']['room_types'],
            [{'id': rt.id, 'name': 'Suite', 'capacity': 4, 'occupancy': '', 'view': ''}],
        )

    def test_edit_hotel_omits_room_types_key_leaves_types_untouched(self):
        """Finding 1 fix: POST without room_types key should not touch existing room types."""
        hotel = Hotel.objects.create( name='Hotel Sawaaed', city='makkah')
        rt = RoomType.objects.create(hotel=hotel, name='Suite', capacity=4)
        # POST with all required fields but NO room_types key at all
        data = {
            'name': 'Hotel Sawaaed', 'city': 'makkah', 'stars': '4', 'area': '',
            # Intentionally omit room_types key
        }
        self.client.post(f'/hotels/{hotel.pk}/edit/', data)
        rt.refresh_from_db()
        # Room type should remain unchanged
        self.assertTrue(rt.is_active)
        self.assertEqual(rt.capacity, 4)
