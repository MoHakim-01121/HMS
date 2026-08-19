import io
import json
from datetime import date, time as dtime

from django.contrib.auth.models import User
from django.test import TestCase
from django.template.loader import render_to_string

from hw.models import Client, Visit, VisitPhoto
from hw.models.user import Role
from hw.permissions import can
from hw.tests.test_access_control import make_user
from hw.utils import haversine_meters


class VisitModelTest(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(
            company='konoz', name='Agen Barokah', lat=21.4225, lng=39.8262,
        )
        self.user = User.objects.create_user('staff1', password='pw12345')

    def test_create_visit_defaults_to_planned(self):
        v = Visit.objects.create(
            company='konoz', client=self.client_obj, staff=self.user,
            scheduled_date=date(2026, 8, 10), purpose='Follow up renewal kontrak',
        )
        self.assertEqual(v.status, Visit.PLANNED)
        self.assertIsNone(v.visited_at)
        self.assertIsNone(v.distance_meters)

    def test_visit_photo_upload_path_uses_visit_id(self):
        v = Visit.objects.create(
            company='konoz', client=self.client_obj, staff=self.user,
            scheduled_date=date(2026, 8, 10), purpose='x',
        )
        photo = VisitPhoto.objects.create(visit=v)
        from hw.models.visit import _visit_photo_path
        self.assertEqual(_visit_photo_path(photo, 'a.jpg'), f"visits/photos/{v.id}/a.jpg")


class VisitPermissionMatrixTest(TestCase):
    def test_staff_can_view_create_edit_but_not_delete_visits(self):
        user = make_user('vperm_staff', role=Role.STAFF.value)
        self.assertTrue(can(user, 'visits', 'view'))
        self.assertTrue(can(user, 'visits', 'create'))
        self.assertTrue(can(user, 'visits', 'edit'))
        self.assertFalse(can(user, 'visits', 'delete'))

    def test_viewer_can_only_view_visits(self):
        user = make_user('vperm_viewer', role=Role.VIEWER.value)
        self.assertTrue(can(user, 'visits', 'view'))
        self.assertFalse(can(user, 'visits', 'create'))

    def test_manager_has_full_visits_access(self):
        user = make_user('vperm_manager', role=Role.MANAGER.value)
        self.assertTrue(can(user, 'visits', 'delete'))


class HaversineMetersTest(TestCase):
    def test_same_point_is_zero(self):
        self.assertEqual(round(haversine_meters(21.4225, 39.8262, 21.4225, 39.8262)), 0)

    def test_known_distance_masjid_haram_to_nabawi(self):
        # ~339km straight-line between Masjid al-Haram and Masjid Nabawi.
        d = haversine_meters(21.4225, 39.8262, 24.4672, 39.6112)
        self.assertTrue(330_000 < d < 350_000, d)


class VisitViewsTest(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(company='konoz', name='Agen Barokah', lat=21.4225, lng=39.8262)
        self.staff = make_user('vviews_staff', role=Role.STAFF.value)
        self.other_staff = make_user('vviews_other', role=Role.STAFF.value)
        self.manager = make_user('vviews_manager', role=Role.MANAGER.value)

    def test_staff_can_create_visit(self):
        self.client.force_login(self.staff)
        resp = self.client.post('/visits/new/', {
            'client_id': self.client_obj.pk, 'scheduled_date': '2026-08-10',
            'purpose': 'Follow up renewal kontrak',
        })
        self.assertEqual(resp.status_code, 302)
        v = Visit.objects.get()
        self.assertEqual(v.staff_id, self.staff.id)
        self.assertEqual(v.status, Visit.PLANNED)

    def test_create_visit_requires_client_and_purpose(self):
        self.client.force_login(self.staff)
        resp = self.client.post('/visits/new/', {'scheduled_date': '2026-08-10'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Visit.objects.count(), 0)

    def test_staff_list_only_shows_own_visits(self):
        Visit.objects.create(company='konoz', client=self.client_obj, staff=self.staff,
                              scheduled_date=date(2026, 8, 10), purpose='mine')
        Visit.objects.create(company='konoz', client=self.client_obj, staff=self.other_staff,
                              scheduled_date=date(2026, 8, 11), purpose='not mine')
        self.client.force_login(self.staff)
        resp = self.client.get('/visits/?date=2026-08-10', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        props = resp.json()['props']
        self.assertEqual([v['day'] for v in props['month_visits']], [10])

    def test_manager_list_shows_all_visits(self):
        Visit.objects.create(company='konoz', client=self.client_obj, staff=self.staff,
                              scheduled_date=date(2026, 8, 10), purpose='a')
        Visit.objects.create(company='konoz', client=self.client_obj, staff=self.other_staff,
                              scheduled_date=date(2026, 8, 11), purpose='b')
        self.client.force_login(self.manager)
        resp = self.client.get('/visits/?date=2026-08-10', HTTP_X_INERTIA='true')
        self.assertEqual(len(resp.json()['props']['month_visits']), 2)

    def test_staff_cannot_open_another_staffs_visit(self):
        v = Visit.objects.create(company='konoz', client=self.client_obj, staff=self.other_staff,
                                  scheduled_date=date(2026, 8, 10), purpose='not mine')
        self.client.force_login(self.staff)
        resp = self.client.get(f'/visits/{v.pk}/')
        self.assertEqual(resp.status_code, 404)

    def test_viewer_cannot_create(self):
        viewer = make_user('vviews_viewer', role=Role.VIEWER.value)
        self.client.force_login(viewer)
        resp = self.client.get('/visits/new/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/dashboard/')

    def test_create_visit_stores_time_slot(self):
        self.client.force_login(self.staff)
        resp = self.client.post('/visits/new/', {
            'client_id': self.client_obj.pk, 'scheduled_date': '2026-08-10',
            'start_time': '09:00', 'end_time': '10:00',
            'purpose': 'Follow up',
        })
        self.assertEqual(resp.status_code, 302)
        v = Visit.objects.get()
        self.assertEqual(v.start_time, dtime(9, 0))
        self.assertEqual(v.end_time, dtime(10, 0))

    def test_create_rejects_end_before_start(self):
        self.client.force_login(self.staff)
        resp = self.client.post('/visits/new/', {
            'client_id': self.client_obj.pk, 'scheduled_date': '2026-08-10',
            'start_time': '10:00', 'end_time': '09:00', 'purpose': 'x',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Visit.objects.count(), 0)

    def test_create_rejects_overlapping_slot(self):
        self.client.force_login(self.staff)
        self.client.post('/visits/new/', {
            'client_id': self.client_obj.pk, 'scheduled_date': '2026-08-10',
            'start_time': '09:00', 'end_time': '10:00', 'purpose': 'pertama',
        })
        resp = self.client.post('/visits/new/', {
            'client_id': self.client_obj.pk, 'scheduled_date': '2026-08-10',
            'start_time': '09:30', 'end_time': '11:00', 'purpose': 'kedua',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Visit.objects.count(), 1)

    def test_create_allows_adjacent_slots(self):
        self.client.force_login(self.staff)
        self.client.post('/visits/new/', {
            'client_id': self.client_obj.pk, 'scheduled_date': '2026-08-10',
            'start_time': '09:00', 'end_time': '10:00', 'purpose': 'a',
        })
        resp = self.client.post('/visits/new/', {
            'client_id': self.client_obj.pk, 'scheduled_date': '2026-08-10',
            'start_time': '10:00', 'end_time': '11:00', 'purpose': 'b',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Visit.objects.count(), 2)

    def test_create_does_not_block_other_staff(self):
        self.client.force_login(self.staff)
        self.client.post('/visits/new/', {
            'client_id': self.client_obj.pk, 'scheduled_date': '2026-08-10',
            'start_time': '09:00', 'end_time': '10:00', 'purpose': 'a',
        })
        self.client.force_login(self.other_staff)
        resp = self.client.post('/visits/new/', {
            'client_id': self.client_obj.pk, 'scheduled_date': '2026-08-10',
            'start_time': '09:30', 'end_time': '10:30', 'purpose': 'b',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Visit.objects.count(), 2)

    def test_edit_excludes_own_slot_from_overlap_check(self):
        v = Visit.objects.create(
            company='konoz', client=self.client_obj, staff=self.staff,
            scheduled_date=date(2026, 8, 10), purpose='x',
            start_time=dtime(9, 0), end_time=dtime(10, 0),
        )
        self.client.force_login(self.staff)
        resp = self.client.post(f'/visits/{v.pk}/edit/', {
            'client_id': self.client_obj.pk, 'scheduled_date': '2026-08-10',
            'start_time': '09:30', 'end_time': '10:30', 'purpose': 'updated',
        })
        self.assertEqual(resp.status_code, 302)
        v.refresh_from_db()
        self.assertEqual(v.start_time, dtime(9, 30))
        self.assertEqual(v.end_time, dtime(10, 30))

    def test_edit_rejects_overlap_with_other_visit(self):
        v = Visit.objects.create(
            company='konoz', client=self.client_obj, staff=self.staff,
            scheduled_date=date(2026, 8, 10), purpose='x',
            start_time=dtime(9, 0), end_time=dtime(10, 0),
        )
        Visit.objects.create(
            company='konoz', client=self.client_obj, staff=self.staff,
            scheduled_date=date(2026, 8, 10), purpose='y',
            start_time=dtime(11, 0), end_time=dtime(12, 0),
        )
        self.client.force_login(self.staff)
        resp = self.client.post(f'/visits/{v.pk}/edit/', {
            'client_id': self.client_obj.pk, 'scheduled_date': '2026-08-10',
            'start_time': '11:30', 'end_time': '12:30', 'purpose': 'updated',
        })
        self.assertEqual(resp.status_code, 200)
        v.refresh_from_db()
        self.assertEqual(v.start_time, dtime(9, 0))

    def test_cancelled_visit_does_not_block(self):
        Visit.objects.create(
            company='konoz', client=self.client_obj, staff=self.staff,
            scheduled_date=date(2026, 8, 10), purpose='cancelled',
            status=Visit.CANCELLED, start_time=dtime(9, 0), end_time=dtime(10, 0),
        )
        self.client.force_login(self.staff)
        resp = self.client.post('/visits/new/', {
            'client_id': self.client_obj.pk, 'scheduled_date': '2026-08-10',
            'start_time': '09:00', 'end_time': '10:00', 'purpose': 'baru',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Visit.objects.count(), 2)

    def test_list_serves_month_visits_for_schedule_board(self):
        Visit.objects.create(company='konoz', client=self.client_obj, staff=self.staff,
                             scheduled_date=date(2026, 8, 5), purpose='a',
                             start_time=dtime(9, 0), end_time=dtime(10, 0))
        Visit.objects.create(company='konoz', client=self.client_obj, staff=self.other_staff,
                             scheduled_date=date(2026, 8, 20), purpose='b')
        Visit.objects.create(company='konoz', client=self.client_obj, staff=self.staff,
                             scheduled_date=date(2026, 7, 3), purpose='other month')
        self.client.force_login(self.manager)
        resp = self.client.get('/visits/?date=2026-08-10', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        props = resp.json()['props']
        self.assertEqual(props['tab'], 'schedule')
        self.assertEqual(props['year'], 2026)
        self.assertEqual(props['month'], 8)
        self.assertEqual(props['selected_date'], '2026-08-10')
        days = [v['day'] for v in props['month_visits']]
        self.assertEqual(days, [5, 20])
        v5 = next(v for v in props['month_visits'] if v['day'] == 5)
        self.assertEqual(v5['start_time'], '09:00')
        self.assertEqual(v5['end_time'], '10:00')

    def test_list_scopes_staff_to_own_visits(self):
        Visit.objects.create(company='konoz', client=self.client_obj, staff=self.staff,
                             scheduled_date=date(2026, 8, 5), purpose='mine')
        Visit.objects.create(company='konoz', client=self.client_obj, staff=self.other_staff,
                             scheduled_date=date(2026, 8, 6), purpose='not mine')
        self.client.force_login(self.staff)
        resp = self.client.get('/visits/?date=2026-08-10', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        props = resp.json()['props']
        self.assertEqual([v['day'] for v in props['month_visits']], [5])
        self.assertTrue(props['is_staff'])

    def test_list_staff_filter_for_manager(self):
        Visit.objects.create(company='konoz', client=self.client_obj, staff=self.other_staff,
                             scheduled_date=date(2026, 8, 5), purpose='a')
        self.client.force_login(self.manager)
        resp = self.client.get(
            f'/visits/?date=2026-08-10&staff={self.staff.pk}',
            HTTP_X_INERTIA='true',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['props']['month_visits'], [])

    def test_list_history_tab_returns_table(self):
        Visit.objects.create(company='konoz', client=self.client_obj, staff=self.staff,
                             scheduled_date=date(2026, 8, 5), purpose='done',
                             status=Visit.COMPLETED)
        self.client.force_login(self.manager)
        resp = self.client.get('/visits/?tab=history', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        props = resp.json()['props']
        self.assertEqual(props['tab'], 'history')
        self.assertEqual(len(props['visits']), 1)
        self.assertIsNotNone(props['pagination'])


class VisitCompleteTest(TestCase):
    def setUp(self):
        self.client_with_geo = Client.objects.create(company='konoz', name='Agen Geo', lat=21.4225, lng=39.8262)
        self.client_no_geo = Client.objects.create(company='konoz', name='Agen NoGeo')
        self.staff = make_user('vcc_staff', role=Role.STAFF.value)
        self.other_staff = make_user('vcc_other', role=Role.STAFF.value)

    def _visit(self, client_obj, staff=None):
        return Visit.objects.create(
            company='konoz', client=client_obj, staff=staff or self.staff,
            scheduled_date=date(2026, 8, 10), purpose='x',
        )

    def _complete(self, visit, **overrides):
        payload = {
            'checkin_lat': 21.4225, 'checkin_lng': 39.8262, 'result_notes': 'Ketemu PIC.',
            'outcome': Visit.OUTCOME_ORDER, 'estimated_value': '',
        }
        payload.update(overrides)
        return self.client.post(
            f'/visits/{visit.pk}/complete/',
            data=json.dumps(payload), content_type='application/json',
        )

    def test_complete_computes_distance_from_client_coords(self):
        v = self._visit(self.client_with_geo)
        self.client.force_login(self.staff)
        resp = self._complete(v)
        self.assertEqual(resp.status_code, 200)
        v.refresh_from_db()
        self.assertEqual(v.status, Visit.COMPLETED)
        self.assertIsNotNone(v.visited_at)
        self.assertEqual(v.distance_meters, 0)

    def test_complete_without_client_coords_leaves_distance_null(self):
        v = self._visit(self.client_no_geo)
        self.client.force_login(self.staff)
        resp = self._complete(v, checkin_lat=21.0, checkin_lng=39.0)
        self.assertEqual(resp.status_code, 200)
        v.refresh_from_db()
        self.assertIsNone(v.distance_meters)

    def test_complete_requires_result_notes(self):
        v = self._visit(self.client_with_geo)
        self.client.force_login(self.staff)
        resp = self._complete(v, result_notes='')
        self.assertEqual(resp.status_code, 400)
        v.refresh_from_db()
        self.assertEqual(v.status, Visit.PLANNED)

    def test_complete_requires_outcome(self):
        v = self._visit(self.client_with_geo)
        self.client.force_login(self.staff)
        resp = self._complete(v, outcome='')
        self.assertEqual(resp.status_code, 400)
        v.refresh_from_db()
        self.assertEqual(v.status, Visit.PLANNED)

    def test_complete_rejects_unknown_outcome(self):
        v = self._visit(self.client_with_geo)
        self.client.force_login(self.staff)
        resp = self._complete(v, outcome='MADE_UP')
        self.assertEqual(resp.status_code, 400)

    def test_complete_stores_outcome_and_estimated_value(self):
        v = self._visit(self.client_with_geo)
        self.client.force_login(self.staff)
        resp = self._complete(v, outcome=Visit.OUTCOME_ORDER, estimated_value='1250.50')
        self.assertEqual(resp.status_code, 200)
        v.refresh_from_db()
        self.assertEqual(v.outcome, Visit.OUTCOME_ORDER)
        self.assertEqual(float(v.estimated_value), 1250.50)

    def test_complete_without_value_stores_null(self):
        v = self._visit(self.client_with_geo)
        self.client.force_login(self.staff)
        resp = self._complete(v, outcome=Visit.OUTCOME_NOT_MET, estimated_value='')
        self.assertEqual(resp.status_code, 200)
        v.refresh_from_db()
        self.assertIsNone(v.estimated_value)

    def test_complete_rejects_negative_estimated_value(self):
        v = self._visit(self.client_with_geo)
        self.client.force_login(self.staff)
        resp = self._complete(v, outcome=Visit.OUTCOME_ORDER, estimated_value='-5')
        self.assertEqual(resp.status_code, 400)

    def test_complete_stores_pic_and_contact(self):
        v = self._visit(self.client_with_geo)
        self.client.force_login(self.staff)
        resp = self._complete(v, pic_name='Ustadz Ahmad', pic_phone='+966 55 123 4567')
        self.assertEqual(resp.status_code, 200)
        v.refresh_from_db()
        self.assertEqual(v.pic_name, 'Ustadz Ahmad')
        self.assertEqual(v.pic_phone, '+966 55 123 4567')

    def test_complete_without_pic_stores_blank(self):
        v = self._visit(self.client_with_geo)
        self.client.force_login(self.staff)
        resp = self._complete(v)
        self.assertEqual(resp.status_code, 200)
        v.refresh_from_db()
        self.assertEqual(v.pic_name, '')
        self.assertEqual(v.pic_phone, '')

    def test_staff_cannot_complete_another_staffs_visit(self):
        v = self._visit(self.client_with_geo, staff=self.other_staff)
        self.client.force_login(self.staff)
        resp = self._complete(v)
        self.assertEqual(resp.status_code, 404)

    def test_cannot_complete_an_already_completed_visit(self):
        v = self._visit(self.client_with_geo)
        v.status = Visit.COMPLETED
        v.save()
        self.client.force_login(self.staff)
        resp = self._complete(v)
        self.assertEqual(resp.status_code, 400)

    def test_cancel_sets_status(self):
        v = self._visit(self.client_with_geo)
        self.client.force_login(self.staff)
        resp = self.client.post(f'/visits/{v.pk}/cancel/')
        self.assertEqual(resp.status_code, 302)
        v.refresh_from_db()
        self.assertEqual(v.status, Visit.CANCELLED)


class VisitPhotoTest(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(company='konoz', name='Agen Foto', lat=21.4, lng=39.8)
        self.staff = make_user('vphoto_staff', role=Role.STAFF.value)
        self.visit = Visit.objects.create(company='konoz', client=self.client_obj, staff=self.staff,
                                           scheduled_date=date(2026, 8, 10), purpose='x')

    def _jpeg_bytes(self):
        # Minimal valid JPEG header bytes so python-magic detects image/jpeg.
        return io.BytesIO(bytes.fromhex('ffd8ffe000104a46494600010100000100010000ffd9'))

    def test_upload_photo(self):
        self.client.force_login(self.staff)
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile('proof.jpg', self._jpeg_bytes().read(), content_type='image/jpeg')
        resp = self.client.post(f'/visits/{self.visit.pk}/photos/upload/', {'file': f})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.visit.photos.count(), 1)

    def test_reject_non_image_file(self):
        self.client.force_login(self.staff)
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile('proof.txt', b'not an image', content_type='text/plain')
        resp = self.client.post(f'/visits/{self.visit.pk}/photos/upload/', {'file': f})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.visit.photos.count(), 0)

    def test_delete_photo(self):
        photo = VisitPhoto.objects.create(visit=self.visit)
        self.client.force_login(self.staff)
        resp = self.client.post(f'/visits/{self.visit.pk}/photos/{photo.pk}/delete/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.visit.photos.count(), 0)


class VisitPdfTest(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(company='konoz', name='Agen Geo', lat=21.4225, lng=39.8262)
        self.staff = make_user('vpdf_staff', role=Role.STAFF.value)
        self.other_staff = make_user('vpdf_other', role=Role.STAFF.value)

    def _visit(self, staff=None):
        return Visit.objects.create(
            company='konoz', client=self.client_obj, staff=staff or self.staff,
            scheduled_date=date(2026, 8, 10), purpose='Follow up renewal kontrak',
            status=Visit.COMPLETED, outcome=Visit.OUTCOME_ORDER, estimated_value='1500',
            pic_name='Ustadz Ahmad', pic_phone='+966 55 123 4567',
            result_notes='Ketemu PIC, bahas paket.',
        )

    def test_pdf_returns_pdf(self):
        v = self._visit()
        self.client.force_login(self.staff)
        resp = self.client.get(f'/visits/{v.pk}/pdf/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertTrue(resp.content.startswith(b'%PDF'))

    def test_pdf_contains_pic_and_contact(self):
        v = self._visit()
        html = render_to_string('hw/visit/visit_pdf.html', {'visit': v})
        self.assertIn('Ustadz Ahmad', html)
        self.assertIn('+966 55 123 4567', html)

    def test_pdf_scopes_another_staffs_visit(self):
        v = self._visit(staff=self.other_staff)
        self.client.force_login(self.staff)
        resp = self.client.get(f'/visits/{v.pk}/pdf/')
        self.assertEqual(resp.status_code, 404)


class VisitRecapTest(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(company='konoz', name='Agen Geo', lat=21.4, lng=39.8)
        self.staff = make_user('vrec_staff', role=Role.STAFF.value)
        self.other_staff = make_user('vrec_other', role=Role.STAFF.value)
        self.manager = make_user('vrec_manager', role=Role.MANAGER.value)

    def _visit(self, d, staff, status=Visit.COMPLETED, outcome=Visit.OUTCOME_ORDER, value=None, distance=100):
        return Visit.objects.create(
            company='konoz', client=self.client_obj, staff=staff,
            scheduled_date=d, purpose='x', status=status,
            outcome=outcome, estimated_value=value, distance_meters=distance,
        )

    def test_recap_groups_by_month_and_aggregates(self):
        self._visit(date(2026, 8, 5), self.staff, outcome=Visit.OUTCOME_ORDER, value='1000', distance=500)
        self._visit(date(2026, 8, 20), self.other_staff, status=Visit.CANCELLED)
        self._visit(date(2026, 7, 3), self.other_staff, outcome=Visit.OUTCOME_PROSPECT, value='200', distance=50)
        self.client.force_login(self.manager)
        resp = self.client.get('/visits/recap/', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        monthly = resp.json()['props']['monthly']
        self.assertEqual(len(monthly), 2)
        aug = next(m for m in monthly if m['period'] == '2026-08')
        self.assertEqual(aug['total'], 2)
        self.assertEqual(aug['completed'], 1)
        self.assertEqual(aug['cancelled'], 1)
        self.assertEqual(aug['total_value_sar'], 1000)
        self.assertEqual(aug['total_distance_meters'], 500)
        order = next(o for o in aug['outcomes'] if o['key'] == Visit.OUTCOME_ORDER)
        self.assertEqual(order['count'], 1)

    def test_recap_scopes_staff_to_own_visits(self):
        self._visit(date(2026, 8, 5), self.staff)
        self._visit(date(2026, 8, 6), self.other_staff)
        self.client.force_login(self.staff)
        resp = self.client.get('/visits/recap/', HTTP_X_INERTIA='true')
        monthly = resp.json()['props']['monthly']
        self.assertEqual(monthly[0]['total'], 1)
        self.assertEqual(monthly[0]['staffs'][0]['name'], self.staff.username)
