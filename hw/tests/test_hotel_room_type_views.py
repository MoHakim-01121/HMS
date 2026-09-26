"""Room types are managed from the hotel detail page, one row at a time,
through their own routes — no longer as a JSON blob inside the hotel form."""
import json

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Hotel, MealPlan, RoomType
from hw.models.user import Role
from hw.tests.test_access_control import make_user


class _LoggedInAdmin(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'admin@test.com', 'pass')
        self.client.force_login(self.user)
        session = self.client.session
        session['active_company'] = 'konoz'
        session.save()
        self.hotel = Hotel.objects.create(name='Hotel Sawaaed', city='makkah')

    def _new(self, **fields):
        data = {'name': 'Suite', 'capacity': '4', 'view': '', **fields}
        return self.client.post(f'/hotels/{self.hotel.pk}/room-types/new/', data)

    def _edit(self, rt, **fields):
        data = {'name': rt.name, 'capacity': str(rt.capacity), 'view': rt.view, **fields}
        return self.client.post(f'/hotels/{self.hotel.pk}/room-types/{rt.pk}/edit/', data)


class RoomTypeCreateTest(_LoggedInAdmin):
    def test_creates_room_type_and_returns_to_hotel_detail(self):
        resp = self._new(name='Quad Kaaba View', capacity='4', view='kaaba')
        self.assertRedirects(resp, f'/hotels/{self.hotel.pk}/', fetch_redirect_response=False)
        rt = RoomType.objects.get(hotel=self.hotel, name='Quad Kaaba View')
        self.assertEqual((rt.capacity, rt.occupancy, rt.view, rt.is_active), (4, 'quad', 'kaaba', True))

    def test_blank_name_is_rejected(self):
        resp = self._new(name='   ')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(RoomType.objects.filter(hotel=self.hotel).exists())

    def test_duplicate_active_name_is_rejected_not_an_integrity_error(self):
        RoomType.objects.create(hotel=self.hotel, name='Suite', capacity=2)
        resp = self._new(name='Suite', capacity='6')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(RoomType.objects.filter(hotel=self.hotel, name='Suite').count(), 1)
        self.assertEqual(RoomType.objects.get(hotel=self.hotel, name='Suite').capacity, 2)

    def test_same_name_in_another_hotel_is_allowed(self):
        other = Hotel.objects.create(name='Other', city='makkah')
        RoomType.objects.create(hotel=other, name='Suite', capacity=2)
        self._new(name='Suite')
        self.assertTrue(RoomType.objects.filter(hotel=self.hotel, name='Suite').exists())

    def test_soft_removed_name_is_reactivated_not_duplicated(self):
        rt = RoomType.objects.create(hotel=self.hotel, name='Suite', capacity=2, is_active=False)
        self._new(name='Suite', capacity='5')
        rt.refresh_from_db()
        self.assertTrue(rt.is_active)
        self.assertEqual((rt.capacity, rt.occupancy), (5, 'quint'))
        self.assertEqual(RoomType.objects.filter(hotel=self.hotel, name='Suite').count(), 1)

    def test_capacity_is_clamped_to_at_least_one(self):
        self._new(capacity='0')
        self.assertEqual(RoomType.objects.get(hotel=self.hotel, name='Suite').capacity, 1)

    def test_new_form_get_renders_with_choices(self):
        resp = self.client.get(f'/hotels/{self.hotel.pk}/room-types/new/', HTTP_X_INERTIA='true')
        page = resp.json()
        self.assertEqual(page['component'], 'Hotel/RoomTypeForm')
        self.assertFalse(page['props']['edit'])
        self.assertEqual(page['props']['occupancy_labels'],
                         {'2': 'Double', '3': 'Triple', '4': 'Quad', '5': 'Quint'})
        self.assertNotIn('occupancy_choices', page['props'])


class RoomTypeEditTest(_LoggedInAdmin):
    def test_updates_fields(self):
        rt = RoomType.objects.create(hotel=self.hotel, name='Suite', capacity=4)
        self._edit(rt, name='Royal Suite', capacity='6', view='haram')
        rt.refresh_from_db()
        self.assertEqual((rt.name, rt.capacity, rt.view), ('Royal Suite', 6, 'haram'))

    def test_get_prefills_fields(self):
        rt = RoomType.objects.create(hotel=self.hotel, name='Suite', capacity=4, view='city')
        resp = self.client.get(f'/hotels/{self.hotel.pk}/room-types/{rt.pk}/edit/', HTTP_X_INERTIA='true')
        props = resp.json()['props']
        self.assertTrue(props['edit'])
        self.assertEqual(props['room_type'], {'name': 'Suite', 'capacity': 4, 'view': 'city'})

    def test_rename_onto_another_active_name_is_rejected(self):
        RoomType.objects.create(hotel=self.hotel, name='Double', capacity=2)
        rt = RoomType.objects.create(hotel=self.hotel, name='Suite', capacity=4)
        resp = self._edit(rt, name='Double')
        self.assertEqual(resp.status_code, 200)
        rt.refresh_from_db()
        self.assertEqual(rt.name, 'Suite')

    def test_rename_onto_soft_removed_name_is_rejected_and_keeps_that_row(self):
        # Deleting the soft-removed row to make room would blank
        # Room.room_type_ref on every CL that used it.
        ghost = RoomType.objects.create(hotel=self.hotel, name='Double', capacity=2, is_active=False)
        rt = RoomType.objects.create(hotel=self.hotel, name='Suite', capacity=4)
        resp = self._edit(rt, name='Double')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(RoomType.objects.filter(pk=ghost.pk).exists())
        rt.refresh_from_db()
        self.assertEqual(rt.name, 'Suite')

    def test_keeping_own_name_is_not_a_clash(self):
        rt = RoomType.objects.create(hotel=self.hotel, name='Suite', capacity=4)
        self._edit(rt, capacity='3')
        rt.refresh_from_db()
        self.assertEqual(rt.capacity, 3)

    def test_room_type_of_another_hotel_is_404(self):
        other = Hotel.objects.create(name='Other', city='makkah')
        foreign = RoomType.objects.create(hotel=other, name='Suite', capacity=4)
        resp = self.client.get(f'/hotels/{self.hotel.pk}/room-types/{foreign.pk}/edit/')
        self.assertEqual(resp.status_code, 404)


class RoomTypeDeleteTest(_LoggedInAdmin):
    def test_delete_is_a_soft_remove(self):
        rt = RoomType.objects.create(hotel=self.hotel, name='Suite', capacity=4)
        resp = self.client.post(f'/hotels/{self.hotel.pk}/room-types/{rt.pk}/delete/')
        self.assertRedirects(resp, f'/hotels/{self.hotel.pk}/', fetch_redirect_response=False)
        rt.refresh_from_db()
        self.assertFalse(rt.is_active)

    def test_delete_requires_post(self):
        rt = RoomType.objects.create(hotel=self.hotel, name='Suite', capacity=4)
        resp = self.client.get(f'/hotels/{self.hotel.pk}/room-types/{rt.pk}/delete/')
        self.assertEqual(resp.status_code, 405)
        rt.refresh_from_db()
        self.assertTrue(rt.is_active)


class HotelFormNoLongerOwnsRoomTypesTest(_LoggedInAdmin):
    def test_posting_room_types_to_hotel_edit_is_ignored(self):
        rt = RoomType.objects.create(hotel=self.hotel, name='Suite', capacity=4)
        self.client.post(f'/hotels/{self.hotel.pk}/edit/', {
            'name': 'Hotel Sawaaed', 'city': 'makkah', 'stars': '4', 'area': '',
            # The old form's payload shape: a list missing an existing type
            # used to soft-remove it, a new entry used to create one.
            'room_types': json.dumps([{'name': 'Injected', 'capacity': 2}]),
        })
        rt.refresh_from_db()
        self.assertTrue(rt.is_active)
        self.assertFalse(RoomType.objects.filter(name='Injected').exists())

    def test_hotel_edit_form_props_no_longer_carry_room_types(self):
        resp = self.client.get(f'/hotels/{self.hotel.pk}/edit/', HTTP_X_INERTIA='true')
        self.assertNotIn('room_types', resp.json()['props']['hotel'])


class RoomTypePermissionTest(TestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create(name='Hotel Sawaaed', city='makkah')
        self.rt = RoomType.objects.create(hotel=self.hotel, name='Suite', capacity=4)

    def _login(self, role):
        user = make_user(f'u_{role}', role)
        self.client.force_login(user)
        session = self.client.session
        session['active_company'] = 'konoz'
        session.save()

    def test_viewer_cannot_add_edit_or_remove(self):
        self._login(Role.VIEWER.value)
        base = f'/hotels/{self.hotel.pk}/room-types'
        self.client.post(f'{base}/new/', {'name': 'Sneaky', 'capacity': '2'})
        self.client.post(f'{base}/{self.rt.pk}/edit/', {'name': 'Renamed', 'capacity': '2'})
        self.client.post(f'{base}/{self.rt.pk}/delete/')
        self.rt.refresh_from_db()
        self.assertEqual((self.rt.name, self.rt.is_active), ('Suite', True))
        self.assertFalse(RoomType.objects.filter(name='Sneaky').exists())

    def test_viewer_can_still_read_the_catalog_on_detail(self):
        self._login(Role.VIEWER.value)
        resp = self.client.get(f'/hotels/{self.hotel.pk}/', HTTP_X_INERTIA='true')
        self.assertEqual([rt['name'] for rt in resp.json()['props']['hotel']['room_types']], ['Suite'])


class HotelDetailRoomTypeTest(_LoggedInAdmin):
    """The detail page exposes the catalog read-only to anyone with view access."""

    def _detail(self):
        resp = self.client.get(f'/hotels/{self.hotel.pk}/', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        return resp.json()['props']['hotel']

    def test_detail_includes_room_types(self):
        rt = RoomType.objects.create(hotel=self.hotel, name='Suite', capacity=4)
        self.assertEqual(
            self._detail()['room_types'],
            [{'id': rt.id, 'name': 'Suite', 'capacity': 4, 'view': ''}],
        )

    def test_detail_excludes_soft_removed_room_types(self):
        RoomType.objects.create(hotel=self.hotel, name='Suite', capacity=4, is_active=False)
        RoomType.objects.create(hotel=self.hotel, name='Double', capacity=2)
        self.assertEqual([rt['name'] for rt in self._detail()['room_types']], ['Double'])

    def test_detail_serializes_view_as_label(self):
        RoomType.objects.create(hotel=self.hotel, name='Quad Kaaba View', capacity=4, view='kaaba')
        rt = self._detail()['room_types'][0]
        self.assertEqual(rt['view'], 'Kaaba View')
        # Occupancy only restates capacity, so the page no longer gets it.
        self.assertNotIn('occupancy', rt)

    def test_detail_without_room_types_sends_empty_list(self):
        self.assertEqual(self._detail()['room_types'], [])

    def test_detail_includes_hotel_meal_plans_in_code_order(self):
        self.hotel.meal_plans.set(MealPlan.objects.filter(code__in=['HB', 'BB']))
        self.assertEqual(
            self._detail()['meal_plans'],
            [{'code': 'BB', 'name': 'Bed & Breakfast'}, {'code': 'HB', 'name': 'Half Board'}],
        )


class RoomTypeBulkTest(_LoggedInAdmin):
    def _bulk(self, capacities, views=()):
        return self.client.post(f'/hotels/{self.hotel.pk}/room-types/bulk/', {
            'capacities': json.dumps(list(capacities)), 'views': json.dumps(list(views)),
        })

    def _names(self, **filters):
        return set(RoomType.objects.filter(hotel=self.hotel, **filters).values_list('name', flat=True))

    def test_creates_every_capacity_view_combination(self):
        resp = self._bulk([2, 3], ['kaaba', 'city'])
        self.assertRedirects(resp, f'/hotels/{self.hotel.pk}/', fetch_redirect_response=False)
        self.assertEqual(self._names(), {
            'Double Kaaba View', 'Triple Kaaba View', 'Double City View', 'Triple City View',
        })
        rt = RoomType.objects.get(hotel=self.hotel, name='Triple City View')
        self.assertEqual((rt.capacity, rt.occupancy, rt.view, rt.is_active), (3, 'triple', 'city', True))

    def test_no_view_ticked_creates_names_without_a_view(self):
        self._bulk([4, 5])
        self.assertEqual(self._names(), {'Quad', 'Quint'})
        self.assertEqual(set(RoomType.objects.filter(hotel=self.hotel).values_list('view', flat=True)), {''})

    def test_existing_active_name_is_skipped_not_overwritten(self):
        # The operator tuned this one (capacity 5 under a "Quad" name), so leave it.
        rt = RoomType.objects.create(hotel=self.hotel, name='Quad Kaaba View', capacity=5, view='kaaba')
        self._bulk([4], ['kaaba', 'city'])
        rt.refresh_from_db()
        self.assertEqual(rt.capacity, 5)
        self.assertEqual(RoomType.objects.filter(hotel=self.hotel, name='Quad Kaaba View').count(), 1)
        self.assertIn('Quad City View', self._names())

    def test_soft_removed_name_is_reactivated_not_duplicated(self):
        rt = RoomType.objects.create(hotel=self.hotel, name='Double', capacity=2, is_active=False)
        self._bulk([2])
        rt.refresh_from_db()
        self.assertTrue(rt.is_active)
        self.assertEqual(RoomType.objects.filter(hotel=self.hotel, name='Double').count(), 1)

    def test_no_capacity_is_rejected_and_creates_nothing(self):
        resp = self._bulk([], ['kaaba'])
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(RoomType.objects.filter(hotel=self.hotel).exists())

    def test_values_outside_the_vocabulary_are_dropped(self):
        # 6 has no occupancy word; "other" would give a meaningless name.
        self._bulk([2, 6, 'x'], ['kaaba', 'other', 'bogus'])
        self.assertEqual(self._names(), {'Double Kaaba View'})

    def test_garbled_payload_is_treated_as_empty(self):
        resp = self.client.post(f'/hotels/{self.hotel.pk}/room-types/bulk/',
                                {'capacities': '{not json', 'views': '[]'})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(RoomType.objects.filter(hotel=self.hotel).exists())

    def test_get_renders_choices_and_existing_names(self):
        RoomType.objects.create(hotel=self.hotel, name='Double', capacity=2)
        RoomType.objects.create(hotel=self.hotel, name='Gone', capacity=2, is_active=False)
        page = self.client.get(f'/hotels/{self.hotel.pk}/room-types/bulk/', HTTP_X_INERTIA='true').json()
        self.assertEqual(page['component'], 'Hotel/RoomTypeBulkForm')
        props = page['props']
        self.assertEqual([c['value'] for c in props['capacity_choices']], [2, 3, 4, 5])
        self.assertNotIn('other', [v['value'] for v in props['view_choices']])
        self.assertEqual(props['existing_names'], ['Double'])

    def test_viewer_cannot_bulk_create(self):
        self.client.force_login(make_user('u_bulk_viewer', Role.VIEWER.value))
        self._bulk([2, 3], ['kaaba'])
        self.assertFalse(RoomType.objects.filter(hotel=self.hotel).exists())
