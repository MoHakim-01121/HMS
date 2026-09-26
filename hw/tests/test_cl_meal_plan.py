"""The CL form's Meals column is a dropdown of what the chosen hotel sells,
and saving it finally fills Room.meal_plan (v2.0 §10) — while still writing
the code into Room.meals, which PDFs and exports keep reading."""
import json
from datetime import date

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from hw.models import Client, ConfirmationLetter, Hotel, MealPlan, Room, RoomType


class CLMealPlanTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'admin@test.com', 'pass')
        self.client.force_login(self.user)
        session = self.client.session
        session['active_company'] = 'konoz'
        session.save()
        self.hotel = Hotel.objects.create(name='Hotel Sawaaed', city='makkah')
        self.hotel.meal_plans.set(MealPlan.objects.filter(code__in=['BB', 'HB']))
        self.room_type = RoomType.objects.create(hotel=self.hotel, name='Double', capacity=2)

    def _post_cl(self, hotel_id=None, **room):
        row = {'room_type': 'Double', 'room_type_id': self.room_type.pk, 'quantity': 1, 'price': 100, **room}
        self.client.post('/cl/new/', {
            'confirmation_number': 'CL-MEAL-001', 'guest_name': 'Ahmad',
            'hotel_name': 'Hotel Sawaaed',
            'hotel_id': str(self.hotel.pk if hotel_id is None else hotel_id),
            'check_in': '2026-10-01', 'check_out': '2026-10-03',
            'reservation_status': 'DEFINITE',
            'rooms': json.dumps([row]),
        })
        return ConfirmationLetter.objects.get(confirmation_number='CL-MEAL-001').rooms.get()

    def _hotel_props(self):
        resp = self.client.get('/cl/new/', HTTP_X_INERTIA='true')
        return next(h for h in resp.json()['props']['hotels'] if h['id'] == self.hotel.pk)

    # ── form context ──

    def test_form_context_carries_only_the_hotels_plans_in_code_order(self):
        self.assertEqual(
            self._hotel_props()['meal_plans'],
            [{'code': 'BB', 'name': 'Bed & Breakfast'}, {'code': 'HB', 'name': 'Half Board'}],
        )

    def test_form_context_hides_inactive_master_codes(self):
        MealPlan.objects.filter(code='HB').update(is_active=False)
        self.assertEqual([mp['code'] for mp in self._hotel_props()['meal_plans']], ['BB'])

    def test_form_context_hides_soft_removed_room_types(self):
        RoomType.objects.create(hotel=self.hotel, name='Gone', capacity=2, is_active=False)
        self.assertEqual([rt['name'] for rt in self._hotel_props()['room_types']], ['Double'])

    def test_form_context_query_count_does_not_grow_with_hotels(self):
        # Filtering a prefetched relation with .filter() re-queries per hotel;
        # the form opens on every CL create/edit, over the whole catalog.
        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get('/cl/new/', HTTP_X_INERTIA='true')
            return len(ctx.captured_queries)
        count()  # the first request pays one-off session/cache warm-up
        baseline = count()
        for i in range(5):
            h = Hotel.objects.create(name=f'Extra {i}', city='makkah')
            h.meal_plans.set(MealPlan.objects.all())
            RoomType.objects.create(hotel=h, name='Suite', capacity=4)
        self.assertEqual(count(), baseline)

    # ── saving ──

    def test_code_the_hotel_sells_links_meal_plan_and_writes_code_to_meals(self):
        room = self._post_cl(meal_plan_code='HB', meals='HB')
        self.assertEqual(room.meal_plan_id, 'HB')
        self.assertEqual(room.meals, 'HB')

    def test_code_the_hotel_does_not_sell_is_not_linked(self):
        room = self._post_cl(meal_plan_code='FB', meals='FB')
        self.assertIsNone(room.meal_plan_id)
        self.assertEqual(room.meals, 'FB')

    def test_legacy_text_that_is_exactly_a_sold_code_gets_linked(self):
        room = self._post_cl(meals='BB')
        self.assertEqual(room.meal_plan_id, 'BB')

    def test_legacy_free_text_is_kept_verbatim_and_unlinked(self):
        room = self._post_cl(meals='BB + late checkout')
        self.assertIsNone(room.meal_plan_id)
        self.assertEqual(room.meals, 'BB + late checkout')

    def test_uncataloged_hotel_never_links(self):
        room = self._post_cl(hotel_id='', meal_plan_code='BB', meals='BB')
        self.assertIsNone(room.meal_plan_id)
        self.assertEqual(room.meals, 'BB')

    def test_edit_form_serializes_meal_plan_code(self):
        room = self._post_cl(meal_plan_code='BB', meals='BB')
        resp = self.client.get(f'/cl/{room.cl_id}/edit/', HTTP_X_INERTIA='true')
        row = resp.json()['props']['cl']['rooms'][0]
        self.assertEqual((row['meal_plan_code'], row['meals']), ('BB', 'BB'))

    def test_edit_form_serializes_empty_code_for_free_text(self):
        room = self._post_cl(meals='BB + late checkout')
        resp = self.client.get(f'/cl/{room.cl_id}/edit/', HTTP_X_INERTIA='true')
        row = resp.json()['props']['cl']['rooms'][0]
        self.assertEqual((row['meal_plan_code'], row['meals']), ('', 'BB + late checkout'))


class CLDuplicateLinkTest(TestCase):
    """Duplicating used to copy only text, so the copy opened with its
    room-type dropdowns locked and no billing client. Links now carry over
    while still valid for a new booking."""

    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'admin@test.com', 'pass')
        self.client.force_login(self.user)
        session = self.client.session
        session['active_company'] = 'konoz'
        session.save()
        self.customer = Client.objects.create(name='PT Dup Client')
        self.hotel = Hotel.objects.create(name='Hotel Sawaaed', city='makkah')
        self.hotel.meal_plans.set(MealPlan.objects.filter(code__in=['BB', 'HB']))
        self.rt = RoomType.objects.create(hotel=self.hotel, name='Quad Kaaba View', capacity=4)
        self.original = ConfirmationLetter.objects.create(
            confirmation_number='CL-DUP-001', guest_name='Ahmad', client=self.customer,
            hotel=self.hotel, hotel_name='Hotel Sawaaed',
            check_in=date(2026, 10, 1), check_out=date(2026, 10, 3), reservation_status='DEFINITE',
        )
        Room.objects.create(cl=self.original, room_type='Quad Kaaba View', room_type_ref=self.rt,
                            meals='BB', meal_plan_id='BB', quantity=2, price=300)

    def _duplicate(self):
        resp = self.client.get(f'/cl/{self.original.pk}/duplicate/')
        self.assertEqual(resp.status_code, 302)
        copy = ConfirmationLetter.objects.exclude(pk=self.original.pk).get()
        return copy, copy.rooms.get()

    def test_carries_client_hotel_and_room_links(self):
        copy, room = self._duplicate()
        self.assertEqual((copy.client_id, copy.hotel_id), (self.customer.pk, self.hotel.pk))
        self.assertEqual((room.room_type_ref_id, room.meal_plan_id), (self.rt.pk, 'BB'))
        self.assertEqual((room.room_type, room.meals, room.quantity), ('Quad Kaaba View', 'BB', 2))

    def test_copy_opens_ready_to_edit(self):
        # The UX point: the edit form gets the ids, so the dropdowns are live.
        copy, _ = self._duplicate()
        props = self.client.get(f'/cl/{copy.pk}/edit/', HTTP_X_INERTIA='true').json()['props']['cl']
        self.assertEqual(props['hotel_id'], self.hotel.pk)
        self.assertEqual((props['rooms'][0]['room_type_id'], props['rooms'][0]['meal_plan_code']), (self.rt.pk, 'BB'))

    def test_inactive_client_is_not_carried(self):
        Client.objects.filter(pk=self.customer.pk).update(is_active=False)
        copy, _ = self._duplicate()
        self.assertIsNone(copy.client_id)

    def test_inactive_hotel_drops_hotel_and_its_room_links_but_keeps_text(self):
        Hotel.objects.filter(pk=self.hotel.pk).update(is_active=False)
        copy, room = self._duplicate()
        self.assertIsNone(copy.hotel_id)
        self.assertEqual(copy.hotel_name, 'Hotel Sawaaed')
        self.assertEqual((room.room_type_ref_id, room.meal_plan_id), (None, None))
        self.assertEqual((room.room_type, room.meals), ('Quad Kaaba View', 'BB'))

    def test_soft_removed_room_type_is_not_linked_but_text_is_kept(self):
        RoomType.objects.filter(pk=self.rt.pk).update(is_active=False)
        _, room = self._duplicate()
        self.assertIsNone(room.room_type_ref_id)
        self.assertEqual(room.room_type, 'Quad Kaaba View')

    def test_meal_the_hotel_stopped_selling_is_not_linked_but_text_is_kept(self):
        self.hotel.meal_plans.set(MealPlan.objects.filter(code='HB'))
        _, room = self._duplicate()
        self.assertIsNone(room.meal_plan_id)
        self.assertEqual(room.meals, 'BB')

    def test_original_is_untouched(self):
        self._duplicate()
        self.original.refresh_from_db()
        room = self.original.rooms.get()
        self.assertEqual((self.original.client_id, room.room_type_ref_id, room.meal_plan_id),
                         (self.customer.pk, self.rt.pk, 'BB'))
