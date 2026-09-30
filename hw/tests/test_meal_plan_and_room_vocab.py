"""FASE F remainder — MealPlan master + RoomType occupancy/view vocabulary,
and the per-hotel narrowing of that master."""
import json

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Hotel, MealPlan, RoomType, room_type_name
from hw.models.user import Role
from hw.tests.test_access_control import make_user


class MealPlanSeedTest(TestCase):
    def test_default_meal_plans_seeded(self):
        codes = set(MealPlan.objects.values_list('code', flat=True))
        self.assertEqual(codes, {'RO', 'BB', 'HB', 'FB'})


class _AdminCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('vocabadmin', 'a@a.com', 'pass')
        self.client.force_login(self.user)
        session = self.client.session
        session['active_company'] = 'konoz'
        session.save()
        self.hotel = Hotel.objects.create(name='Hotel Vocab', city='makkah')


class RoomTypeOccupancyViewTest(_AdminCase):
    def test_saves_view_and_derives_occupancy(self):
        self.client.post(f'/hotels/{self.hotel.pk}/room-types/new/', {
            'name': 'Quad Kaaba View', 'capacity': '4', 'view': 'kaaba',
        })
        rt = RoomType.objects.get(hotel=self.hotel, name='Quad Kaaba View')
        self.assertEqual(rt.occupancy, 'quad')
        self.assertEqual(rt.view, 'kaaba')

    def test_posted_occupancy_is_ignored_in_favour_of_capacity(self):
        # A stale client still sending the old field cannot make them disagree.
        self.client.post(f'/hotels/{self.hotel.pk}/room-types/new/', {
            'name': 'Mixed', 'capacity': '4', 'occupancy': 'double', 'view': '',
        })
        self.assertEqual(RoomType.objects.get(hotel=self.hotel, name='Mixed').occupancy, 'quad')

    def test_invalid_view_is_blanked(self):
        self.client.post(f'/hotels/{self.hotel.pk}/room-types/new/', {
            'name': 'Weird Room', 'capacity': '2', 'view': 'bogus',
        })
        self.assertEqual(RoomType.objects.get(hotel=self.hotel, name='Weird Room').view, '')

    def test_edit_form_serializes_raw_view(self):
        # Raw code, not label: the form's <select> values are the codes.
        rt = RoomType.objects.create(hotel=self.hotel, name='Double Non View', capacity=2, view='non_view')
        resp = self.client.get(f'/hotels/{self.hotel.pk}/room-types/{rt.pk}/edit/', HTTP_X_INERTIA='true')
        props = resp.json()['props']['room_type']
        self.assertEqual(props['view'], 'non_view')
        self.assertNotIn('occupancy', props)


class RoomTypeOccupancyDerivationTest(TestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create(name='Hotel Derive', city='makkah')

    def test_occupancy_follows_capacity(self):
        for capacity, occupancy in [(1, ''), (2, 'double'), (3, 'triple'), (4, 'quad'), (5, 'quint'), (6, '')]:
            rt = RoomType.objects.create(hotel=self.hotel, name=f'R{capacity}', capacity=capacity)
            rt.refresh_from_db()
            self.assertEqual(rt.occupancy, occupancy, capacity)

    def test_capacity_change_with_update_fields_changes_occupancy(self):
        rt = RoomType.objects.create(hotel=self.hotel, name='R', capacity=2)
        rt.capacity = 3
        rt.save(update_fields=['capacity'])
        rt.refresh_from_db()
        self.assertEqual(rt.occupancy, 'triple')

    def test_occupancy_is_not_a_stored_column(self):
        # Schema v2: tidak ada kolom yang bisa berbeda dari capacity (dulu
        # .update(occupancy=…) bisa menghasilkan "Quad, capacity 2").
        self.assertNotIn('occupancy', [f.name for f in RoomType._meta.get_fields()])


class RoomTypeNameTest(TestCase):
    def test_conventional_names(self):
        self.assertEqual(room_type_name(4, 'kaaba'), 'Quad Kaaba View')
        self.assertEqual(room_type_name(2, 'non_view'), 'Double Non View')
        self.assertEqual(room_type_name(3, ''), 'Triple')

    def test_other_view_is_left_out(self):
        self.assertEqual(room_type_name(5, 'other'), 'Quint')

    def test_capacity_without_an_occupancy_word(self):
        self.assertEqual(room_type_name(6, 'city'), '6 Pax City View')


class HotelMealPlanSelectionTest(_AdminCase):
    def _save(self, codes):
        return self.client.post(f'/hotels/{self.hotel.pk}/meal-plans/', {'meal_plans': json.dumps(codes)})

    def _codes(self):
        return sorted(self.hotel.meal_plans.values_list('code', flat=True))

    def test_get_offers_active_master_and_current_selection(self):
        self.hotel.meal_plans.set(MealPlan.objects.filter(code='BB'))
        resp = self.client.get(f'/hotels/{self.hotel.pk}/meal-plans/', HTTP_X_INERTIA='true')
        page = resp.json()
        self.assertEqual(page['component'], 'Hotel/MealPlanForm')
        self.assertEqual([mp['code'] for mp in page['props']['available']], ['BB', 'FB', 'HB', 'RO'])
        self.assertEqual(page['props']['selected'], ['BB'])

    def test_post_sets_selection_and_returns_to_detail(self):
        resp = self._save(['BB', 'HB'])
        self.assertRedirects(resp, f'/hotels/{self.hotel.pk}/', fetch_redirect_response=False)
        self.assertEqual(self._codes(), ['BB', 'HB'])

    def test_post_replaces_rather_than_appends(self):
        self.hotel.meal_plans.set(MealPlan.objects.all())
        self._save(['RO'])
        self.assertEqual(self._codes(), ['RO'])

    def test_empty_list_clears_selection(self):
        self.hotel.meal_plans.set(MealPlan.objects.all())
        self._save([])
        self.assertEqual(self._codes(), [])

    def test_unknown_codes_are_dropped(self):
        self._save(['BB', 'XX'])
        self.assertEqual(self._codes(), ['BB'])

    def test_inactive_master_codes_are_dropped(self):
        MealPlan.objects.filter(code='FB').update(is_active=False)
        self._save(['BB', 'FB'])
        self.assertEqual(self._codes(), ['BB'])

    def test_malformed_payload_leaves_selection_untouched(self):
        self.hotel.meal_plans.set(MealPlan.objects.filter(code__in=['BB', 'HB']))
        for garbage in ('not json', json.dumps('BB'), json.dumps({'BB': True})):
            resp = self.client.post(f'/hotels/{self.hotel.pk}/meal-plans/', {'meal_plans': garbage})
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(self._codes(), ['BB', 'HB'], garbage)

    def test_new_hotel_starts_with_every_active_plan(self):
        # Same starting point migration 0104 gave the existing hotels.
        MealPlan.objects.filter(code='FB').update(is_active=False)
        self.client.post('/hotels/new/', {'name': 'Fresh Hotel', 'city': 'makkah', 'stars': '3'})
        fresh = Hotel.objects.get(name='Fresh Hotel')
        self.assertEqual(sorted(fresh.meal_plans.values_list('code', flat=True)), ['BB', 'HB', 'RO'])

    def test_hotel_edit_does_not_touch_meal_plans(self):
        self.hotel.meal_plans.set(MealPlan.objects.filter(code='BB'))
        self.client.post(f'/hotels/{self.hotel.pk}/edit/', {'name': 'Hotel Vocab', 'city': 'makkah', 'stars': '4'})
        self.assertEqual(self._codes(), ['BB'])


class HotelMealPlanPermissionTest(TestCase):
    def test_viewer_cannot_change_selection(self):
        hotel = Hotel.objects.create(name='Hotel Vocab', city='makkah')
        hotel.meal_plans.set(MealPlan.objects.filter(code='BB'))
        user = make_user('viewer1', Role.VIEWER.value)
        self.client.force_login(user)
        session = self.client.session
        session['active_company'] = 'konoz'
        session.save()
        self.client.post(f'/hotels/{hotel.pk}/meal-plans/', {'meal_plans': json.dumps(['RO', 'FB'])})
        self.assertEqual(list(hotel.meal_plans.values_list('code', flat=True)), ['BB'])
