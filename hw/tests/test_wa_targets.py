from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth.models import User
from unittest.mock import patch

from hw.models import WATarget, ConfirmationLetter, RecapLog


def _make_cl(**kwargs):
    defaults = dict(
        company='konoz', hotel_name='Hilton', guest_name='Ahmad',
        guest_phone='628123456789',
        check_in=date.today(), check_out=date.today() + timedelta(days=3),
        confirmation_number='CL-W01', reservation_status='DEFINITE',
    )
    defaults.update(kwargs)
    return ConfirmationLetter.objects.create(**defaults)


class WATargetModelTest(TestCase):
    def test_create_phone_target(self):
        t = WATarget.objects.create(label='Tim A', target='628123456789')
        self.assertEqual(t.target_type, 'PHONE')
        self.assertTrue(t.is_active)

    def test_long_number_is_phone(self):
        t = WATarget.objects.create(label='Tim B', target='6281234567890')
        self.assertEqual(t.target_type, 'PHONE')

    def test_short_target_is_group(self):
        t = WATarget.objects.create(label='Grup', target='123456789')
        self.assertEqual(t.target_type, 'GROUP')

    def test_target_with_dash_is_group(self):
        t = WATarget.objects.create(label='Grup Ops', target='628-GROUP-001')
        self.assertEqual(t.target_type, 'GROUP')

    def test_target_unique(self):
        WATarget.objects.create(label='A', target='628111222333')
        with self.assertRaises(Exception):
            WATarget.objects.create(label='B', target='628111222333')

    def test_default_is_active_true(self):
        t = WATarget.objects.create(label='C', target='628999888777')
        self.assertTrue(t.is_active)


class WATargetViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('staff1', password='pw12345')
        self.client.force_login(self.user)

    def test_add_target_success(self):
        resp = self.client.post('/calendar/wa-targets/', {
            'label': 'Grup Ops', 'target': '628123456789012',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(WATarget.objects.count(), 1)
        self.assertEqual(data['target_type'], 'PHONE')

    def test_add_target_missing_field(self):
        resp = self.client.post('/calendar/wa-targets/', {'label': 'Grup'})
        self.assertFalse(resp.json()['ok'])
        self.assertIn('error', resp.json())

    def test_add_target_duplicate(self):
        WATarget.objects.create(label='A', target='628111222333444')
        resp = self.client.post('/calendar/wa-targets/', {
            'label': 'B', 'target': '628111222333444',
        })
        self.assertFalse(resp.json()['ok'])
        self.assertIn('Nomor sudah terdaftar', resp.json()['error'])

    def test_toggle_target(self):
        t = WATarget.objects.create(label='X', target='628999000111222')
        resp = self.client.post(f'/calendar/wa-targets/{t.pk}/toggle/')
        self.assertTrue(resp.json()['ok'])
        self.assertFalse(resp.json()['is_active'])
        resp2 = self.client.post(f'/calendar/wa-targets/{t.pk}/toggle/')
        self.assertTrue(resp2.json()['is_active'])

    def test_delete_target(self):
        t = WATarget.objects.create(label='Y', target='628777666555444')
        resp = self.client.post(f'/calendar/wa-targets/{t.pk}/delete/')
        self.assertTrue(resp.json()['ok'])
        self.assertFalse(WATarget.objects.filter(pk=t.pk).exists())

    def test_delete_nonexistent_returns_404(self):
        resp = self.client.post('/calendar/wa-targets/99999/delete/')
        self.assertEqual(resp.status_code, 404)

    def test_add_returns_405_on_get(self):
        resp = self.client.get('/calendar/wa-targets/')
        self.assertEqual(resp.status_code, 405)


class CalendarViewWATargetsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('staff2', password='pw12345')
        self.client.force_login(self.user)
        s = self.client.session; s['active_company'] = 'konoz'; s.save()

    def test_recap_settings_view_includes_wa_targets(self):
        WATarget.objects.create(label='Tim', target='628123000111222')
        resp = self.client.get('/calendar/recap-settings/', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        props = resp.json()['props']
        self.assertIn('wa_targets', props)
        self.assertEqual(len(props['wa_targets']), 1)
        self.assertEqual(props['wa_targets'][0]['label'], 'Tim')


class CalendarSendRecapWATargetTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('staff3', password='pw12345')
        self.client.force_login(self.user)
        s = self.client.session; s['active_company'] = 'konoz'; s.save()
        from datetime import time
        self.cl = _make_cl(estimasi_tiba=time(14, 0), pic_name='Budi', pic_phone='0812')

    def test_send_recap_no_active_targets_returns_error(self):
        resp = self.client.post('/calendar/send-recap/')
        self.assertFalse(resp.json()['ok'])
        self.assertIn('Belum ada nomor penerima', resp.json()['message'])

    @patch('hw.views.calendar_views.send_wa')
    def test_send_recap_uses_only_active_wa_targets(self, mock_send):
        mock_send.return_value = {'status': True}
        WATarget.objects.create(label='Tim A', target='628111000222333')
        WATarget.objects.create(label='Tim B', target='628444000555666', is_active=False)
        resp = self.client.post('/calendar/send-recap/')
        self.assertTrue(resp.json()['ok'])
        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(RecapLog.objects.count(), 1)

    @patch('hw.views.calendar_views.send_wa')
    def test_send_recap_creates_log_per_target(self, mock_send):
        mock_send.return_value = {'status': True}
        WATarget.objects.create(label='A', target='628111000222333')
        WATarget.objects.create(label='B', target='628444000555666')
        resp = self.client.post('/calendar/send-recap/')
        self.assertEqual(RecapLog.objects.count(), 2)
