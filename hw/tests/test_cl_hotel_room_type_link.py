import json
from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import ConfirmationLetter, Hotel, Room, RoomType


class CLHotelRoomTypeLinkTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'admin@test.com', 'pass')
        self.client.force_login(self.user)
        session = self.client.session
        session['active_company'] = 'konoz'
        session.save()
        self.hotel = Hotel.objects.create(company='konoz', name='Hotel Sawaaed', city='makkah')
        self.room_type = RoomType.objects.create(hotel=self.hotel, name='Double View Kaaba', capacity=2)

    def _cl_payload(self, **rooms_extra):
        room = {'room_type': 'Double View Kaaba', 'quantity': 2, 'price': 500, **rooms_extra}
        return {
            'confirmation_number': 'CL-LINK-001', 'guest_name': 'Ahmad',
            'hotel_name': 'Hotel Sawaaed', 'hotel_id': str(self.hotel.pk),
            'check_in': '2026-09-01', 'check_out': '2026-09-03',
            'reservation_status': 'DEFINITE',
            'rooms': json.dumps([room]),
        }

    def test_create_cl_links_hotel_and_room_type(self):
        self.client.post('/cl/new/', self._cl_payload(room_type_id=self.room_type.pk))
        cl = ConfirmationLetter.objects.get(confirmation_number='CL-LINK-001')
        self.assertEqual(cl.hotel_id, self.hotel.pk)
        room = cl.rooms.get()
        self.assertEqual(room.room_type_ref_id, self.room_type.pk)
        self.assertEqual(room.room_type, 'Double View Kaaba')

    def test_create_cl_without_hotel_id_leaves_hotel_and_ref_null(self):
        payload = self._cl_payload()
        payload['hotel_id'] = ''
        payload['hotel_name'] = 'Some Untracked Hotel'
        self.client.post('/cl/new/', payload)
        cl = ConfirmationLetter.objects.get(confirmation_number='CL-LINK-001')
        self.assertIsNone(cl.hotel_id)
        room = cl.rooms.get()
        self.assertIsNone(room.room_type_ref_id)
        self.assertEqual(room.room_type, 'Double View Kaaba')

    def test_room_type_id_from_a_different_hotel_is_ignored(self):
        other_hotel = Hotel.objects.create(company='konoz', name='Other Hotel', city='makkah')
        other_room_type = RoomType.objects.create(hotel=other_hotel, name='Double View Kaaba', capacity=2)
        self.client.post('/cl/new/', self._cl_payload(room_type_id=other_room_type.pk))
        cl = ConfirmationLetter.objects.get(confirmation_number='CL-LINK-001')
        room = cl.rooms.get()
        self.assertIsNone(room.room_type_ref_id)

    def test_form_context_hotels_include_id_and_room_types(self):
        resp = self.client.get('/cl/new/', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        page = resp.json()
        hotel_props = next(h for h in page['props']['hotels'] if h['id'] == self.hotel.pk)
        self.assertEqual(
            hotel_props['room_types'],
            [{'id': self.room_type.pk, 'name': 'Double View Kaaba', 'capacity': 2}],
        )

    def test_cl_edit_get_includes_room_type_ref_id(self):
        self.client.post('/cl/new/', self._cl_payload(room_type_id=self.room_type.pk))
        cl = ConfirmationLetter.objects.get(confirmation_number='CL-LINK-001')
        room = cl.rooms.get()
        self.assertEqual(room.room_type_ref_id, self.room_type.pk)
        resp = self.client.get(f'/cl/{cl.pk}/edit/', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        room_data = resp.json()['props']['cl']['rooms'][0]
        self.assertEqual(room_data['room_type_id'], self.room_type.pk)

    def test_cl_edit_get_returns_empty_string_for_null_room_type_ref(self):
        payload = self._cl_payload()
        payload['hotel_id'] = ''
        self.client.post('/cl/new/', payload)
        cl = ConfirmationLetter.objects.get(confirmation_number='CL-LINK-001')
        resp = self.client.get(f'/cl/{cl.pk}/edit/', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        room_data = resp.json()['props']['cl']['rooms'][0]
        self.assertEqual(room_data['room_type_id'], "")
