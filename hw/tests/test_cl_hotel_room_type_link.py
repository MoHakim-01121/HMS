import json
from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Client, ConfirmationLetter, Hotel, RoomType


class CLHotelRoomTypeLinkTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'admin@test.com', 'pass')
        self.client.force_login(self.user)
        session = self.client.session
        session['active_company'] = 'konoz'
        session.save()
        self.customer = Client.objects.create(name='PT Ahmad Wisata')
        self.hotel = Hotel.objects.create( name='Hotel Sawaaed', city='makkah')
        self.room_type = RoomType.objects.create(hotel=self.hotel, name='Double View Kaaba', capacity=2)

    def _cl_payload(self, **rooms_extra):
        room = {'room_type': 'Double View Kaaba', 'room_type_id': self.room_type.pk,
                'quantity': 2, 'price': 500, **rooms_extra}
        return {
            'confirmation_number': 'CL-LINK-001', 'guest_name': 'PT Ahmad Wisata',
            'client_id': str(self.customer.pk),
            'hotel_name': 'Hotel Sawaaed', 'hotel_id': str(self.hotel.pk),
            'check_in': '2026-09-01', 'check_out': '2026-09-03',
            'reservation_status': 'DEFINITE', 'salesperson_id': str(self.user.pk),
            'rooms': json.dumps([room]),
        }

    def _errors(self, payload):
        resp = self.client.post('/cl/new/', payload, HTTP_X_INERTIA='true')
        return resp.json()['props'].get('errors', {})

    def test_create_cl_links_hotel_and_room_type(self):
        self.client.post('/cl/new/', self._cl_payload())
        cl = ConfirmationLetter.objects.get(confirmation_number='CL-LINK-001')
        self.assertEqual((cl.client_id, cl.hotel_id), (self.customer.pk, self.hotel.pk))
        # Nama dibaca dari master, tidak disimpan sebagai teks di CL.
        self.assertEqual((cl.guest_name, cl.hotel_name), ('PT Ahmad Wisata', 'Hotel Sawaaed'))
        room = cl.rooms.get()
        self.assertEqual(room.room_type_ref_id, self.room_type.pk)
        self.assertEqual(room.room_type, 'Double View Kaaba')

    def test_hotel_typed_but_not_picked_is_refused(self):
        payload = self._cl_payload()
        payload['hotel_id'] = ''
        payload['hotel_name'] = 'Some Untracked Hotel'
        self.assertIn('hotel_name', self._errors(payload))
        self.assertFalse(ConfirmationLetter.objects.exists())

    def test_client_typed_but_not_picked_is_refused(self):
        payload = self._cl_payload()
        payload['client_id'] = ''
        payload['guest_name'] = 'Free Text Guest'
        self.assertIn('guest_name', self._errors(payload))
        self.assertFalse(ConfirmationLetter.objects.exists())

    def test_room_type_from_a_different_hotel_is_refused(self):
        other_hotel = Hotel.objects.create( name='Other Hotel', city='makkah')
        other_room_type = RoomType.objects.create(hotel=other_hotel, name='Double View Kaaba', capacity=2)
        self.assertIn('rooms', self._errors(self._cl_payload(room_type_id=other_room_type.pk)))
        self.assertFalse(ConfirmationLetter.objects.exists())

    def test_room_without_a_catalog_type_is_refused(self):
        self.assertIn('rooms', self._errors(self._cl_payload(room_type_id='')))
        self.assertFalse(ConfirmationLetter.objects.exists())

    def test_reservation_needs_at_least_one_room(self):
        payload = self._cl_payload()
        payload['rooms'] = '[]'
        self.assertIn('rooms', self._errors(payload))

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
        self.client.post('/cl/new/', self._cl_payload())
        cl = ConfirmationLetter.objects.get(confirmation_number='CL-LINK-001')
        resp = self.client.get(f'/cl/{cl.pk}/edit/', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        room_data = resp.json()['props']['cl']['rooms'][0]
        self.assertEqual(room_data['room_type_id'], self.room_type.pk)
