from datetime import date, timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from hw.models import ConfirmationLetter, ReminderLog, RecapLog


def _make_cl(**kwargs):
    defaults = dict(
        company='konoz', hotel_name='Hilton Makkah',
        guest_name='Ahmad', guest_phone='628123456789',
        check_in=date.today(), check_out=date.today() + timedelta(days=3),
        confirmation_number='CL-001', reservation_status='DEFINITE',
    )
    defaults.update(kwargs)
    return ConfirmationLetter.objects.create(**defaults)


class ReminderLogModelTest(TestCase):
    def test_create_reminder_log(self):
        cl = _make_cl()
        log = ReminderLog.objects.create(
            cl=cl, reminder_type='H0_GUEST', phone='628123456789', status='SENT',
        )
        self.assertEqual(ReminderLog.objects.count(), 1)
        self.assertEqual(log.cl, cl)
        self.assertEqual(log.error, '')

    def test_create_recap_log(self):
        log = RecapLog.objects.create(
            target_type='PHONE', target='628xxx', cl_count=3,
            message='test', status='SENT', triggered_by='AUTO',
        )
        self.assertEqual(RecapLog.objects.count(), 1)
        self.assertEqual(log.error, '')

    def test_cl_estimasi_fields(self):
        from datetime import time
        cl = _make_cl(estimasi_tiba=time(14, 0), pic_name='Budi', pic_phone='0812xxx')
        cl.refresh_from_db()
        self.assertEqual(cl.estimasi_tiba.hour, 14)
        self.assertEqual(cl.pic_name, 'Budi')


class FonnteServiceTest(TestCase):
    @patch('hw.services.fonnte.requests.post')
    def test_send_wa_success(self, mock_post):
        from hw.services.fonnte import send_wa
        mock_post.return_value.json.return_value = {'status': True}
        result = send_wa('628123', 'Hello')
        self.assertEqual(result, {'status': True})
        call_kwargs = mock_post.call_args
        self.assertEqual(call_kwargs.args[0], 'https://api.fonnte.com/send')
        self.assertEqual(call_kwargs.kwargs['data']['target'], '628123')

    @patch('hw.services.fonnte.requests.post')
    def test_send_wa_failure_returns_dict(self, mock_post):
        from hw.services.fonnte import send_wa
        mock_post.return_value.json.return_value = {'status': False, 'reason': 'invalid token'}
        result = send_wa('628123', 'Hello')
        self.assertFalse(result['status'])

    @patch('hw.services.fonnte.requests.post')
    def test_send_wa_connection_error_returns_clean_dict(self, mock_post):
        import requests as _req
        from hw.services.fonnte import send_wa
        mock_post.side_effect = _req.exceptions.ConnectionError('getaddrinfo failed')
        result = send_wa('628123', 'Hello')
        self.assertFalse(result['status'])
        self.assertIn('Fonnte', result['reason'])
        self.assertNotIn('getaddrinfo', result['reason'])

    @patch('hw.services.fonnte.requests.post')
    def test_send_wa_timeout_returns_clean_dict(self, mock_post):
        import requests as _req
        from hw.services.fonnte import send_wa
        mock_post.side_effect = _req.exceptions.Timeout()
        result = send_wa('628123', 'Hello')
        self.assertFalse(result['status'])
        self.assertIn('timed out', result['reason'])


class RecapServiceTest(TestCase):
    def test_build_recap_groups_by_hotel(self):
        from hw.services.recap import build_recap_message
        cl1 = _make_cl(hotel_name='Hilton Makkah', guest_name='Ahmad', confirmation_number='CL-001')
        cl2 = _make_cl(hotel_name='Hilton Makkah', guest_name='Budi', confirmation_number='CL-002')
        cl3 = _make_cl(hotel_name='Marriott', guest_name='Cici', confirmation_number='CL-003')
        msg = build_recap_message([cl1, cl2, cl3], date.today())
        self.assertIn('HILTON MAKKAH', msg)
        self.assertIn('MARRIOTT', msg)
        self.assertLess(msg.index('HILTON MAKKAH'), msg.index('MARRIOTT'))
        self.assertIn('CL-001', msg)
        self.assertIn('3 tamu | 2 hotel', msg)

    def test_build_reminder_h0_contains_hari_ini(self):
        from hw.services.recap import build_reminder_message
        cl = _make_cl()
        msg = build_reminder_message(cl, 'H0_GUEST')
        self.assertIn(cl.guest_name, msg)
        self.assertIn(cl.hotel_name, msg)
        self.assertIn('hari ini', msg.lower())

    def test_build_reminder_h1_contains_besok(self):
        from hw.services.recap import build_reminder_message
        cl = _make_cl(check_in=date.today() + timedelta(days=1))
        msg = build_reminder_message(cl, 'H1_GUEST')
        self.assertIn('besok', msg.lower())

    def test_build_reminder_h1_includes_confirmation_number(self):
        from hw.services.recap import build_reminder_message
        cl = _make_cl(confirmation_number='CL-XTEST')
        msg = build_reminder_message(cl, 'H1_GUEST')
        self.assertIn('CL-XTEST', msg)

    def test_build_reminder_h1_includes_rooms(self):
        from hw.services.recap import build_reminder_message
        from hw.models import Room
        cl = _make_cl(confirmation_number='CL-RTEST')
        Room.objects.create(cl=cl, room_type='Deluxe', quantity=2, price=500000)
        msg = build_reminder_message(cl, 'H1_GUEST')
        self.assertIn('2 Deluxe', msg)

    def test_build_reminder_h0_includes_confirmation_number(self):
        from hw.services.recap import build_reminder_message
        cl = _make_cl(confirmation_number='CL-H0TEST')
        msg = build_reminder_message(cl, 'H0_GUEST')
        self.assertIn('CL-H0TEST', msg)

    def test_build_recap_no_flag_for_missing_phone(self):
        from hw.services.recap import build_recap_message
        cl = _make_cl(guest_phone='', confirmation_number='CL-INC1')
        cl.estimasi_tiba = __import__('datetime').time(14, 0)
        cl.save()
        msg = build_recap_message([cl], date.today())
        self.assertNotIn('[!]', msg)

    def test_build_recap_flags_incomplete_no_estimasi(self):
        from hw.services.recap import build_recap_message
        cl = _make_cl(confirmation_number='CL-INC2')  # estimasi_tiba=None by default
        msg = build_recap_message([cl], date.today())
        self.assertIn('[!]', msg)

    def test_build_recap_no_flag_when_complete(self):
        from datetime import time
        from hw.services.recap import build_recap_message
        cl = _make_cl(guest_phone='628123456789', confirmation_number='CL-COMP1')
        cl.estimasi_tiba = time(14, 0)
        cl.save()
        msg = build_recap_message([cl], date.today())
        self.assertNotIn('[!]', msg)

    def test_build_recap_footer_shows_incomplete_count(self):
        from datetime import time
        from hw.services.recap import build_recap_message
        cl_complete = _make_cl(confirmation_number='CL-FC1')
        cl_complete.estimasi_tiba = time(14, 0)
        cl_complete.save()
        cl_incomplete = _make_cl(confirmation_number='CL-FI1')  # estimasi_tiba=None
        msg = build_recap_message([cl_complete, cl_incomplete], date.today())
        self.assertIn('1 belum ETA', msg)

    def test_build_recap_no_emoji(self):
        from hw.services.recap import build_recap_message, build_reminder_message
        cl = _make_cl(confirmation_number='CL-EMJ1')
        recap_msg = build_recap_message([cl], date.today())
        reminder_msg = build_reminder_message(cl, 'H0_GUEST')
        for msg in [recap_msg, reminder_msg]:
            for char in msg:
                self.assertLess(ord(char), 0x1F300,
                    f"Emoji ditemukan di pesan: {repr(char)}")


import json
from datetime import time
from django.contrib.auth.models import User


class CalendarUpcomingCheckinsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('tester3', password='pw12345')
        self.client.force_login(self.user)
        s = self.client.session; s['active_company'] = 'konoz'; s.save()
        self.cl = _make_cl(check_in=date.today())

    def test_calendar_view_includes_upcoming(self):
        resp = self.client.get('/calendar/', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        props = resp.json()['props']
        self.assertIn('upcoming_checkins', props)
        self.assertEqual(len(props['upcoming_checkins']), 1)
        entry = props['upcoming_checkins'][0]
        self.assertEqual(entry['pk'], self.cl.pk)
        self.assertIn('h0_sent', entry)
        self.assertIn('h1_sent', entry)
        self.assertIn('h0_failed', entry)
        self.assertIn('h1_failed', entry)
        self.assertIn('rooms', entry)

    def test_h0_failed_flag_when_reminder_failed(self):
        ReminderLog.objects.create(
            cl=self.cl, reminder_type='H0_GUEST', phone='628123456789', status='FAILED',
        )
        resp = self.client.get('/calendar/', HTTP_X_INERTIA='true')
        entry = resp.json()['props']['upcoming_checkins'][0]
        self.assertTrue(entry['h0_failed'])
        self.assertFalse(entry['h0_sent'])


class EstimasiSaveTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('tester4', password='pw12345')
        self.client.force_login(self.user)
        self.cl = _make_cl()

    def test_saves_estimasi_and_pic(self):
        resp = self.client.post(
            f'/calendar/cl/{self.cl.pk}/estimasi/',
            {'estimasi_tiba': '14:00', 'pic_name': 'Budi', 'pic_phone': '0812xxx'},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['ok'])
        self.cl.refresh_from_db()
        self.assertEqual(self.cl.estimasi_tiba.strftime('%H:%M'), '14:00')
        self.assertEqual(self.cl.pic_name, 'Budi')
        self.assertEqual(self.cl.pic_phone, '0812xxx')

    def test_returns_405_on_get(self):
        resp = self.client.get(f'/calendar/cl/{self.cl.pk}/estimasi/')
        self.assertEqual(resp.status_code, 405)

    def test_clears_estimasi_if_empty(self):
        self.cl.estimasi_tiba = time(14, 0)
        self.cl.save()
        self.client.post(f'/calendar/cl/{self.cl.pk}/estimasi/', {'estimasi_tiba': '', 'pic_name': '', 'pic_phone': ''})
        self.cl.refresh_from_db()
        self.assertIsNone(self.cl.estimasi_tiba)


class SendRecapViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('tester5', password='pw12345')
        self.client.force_login(self.user)
        s = self.client.session; s['active_company'] = 'konoz'; s.save()
        self.cl = _make_cl(estimasi_tiba=time(14, 0), pic_name='Budi', pic_phone='0812')

    @patch('hw.views.calendar_views.send_wa')
    def test_sends_recap_and_creates_log(self, mock_send):
        from hw.models import WATarget
        WATarget.objects.create(label='Tim', target='628111222333')
        mock_send.return_value = {'status': True}
        resp = self.client.post('/calendar/send-recap/')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['ok'])
        self.assertEqual(RecapLog.objects.filter(triggered_by='MANUAL').count(), 1)

    def test_returns_error_if_no_estimasi(self):
        _make_cl(confirmation_number='CL-X99')  # tanpa estimasi
        cl_no_est = _make_cl(confirmation_number='CL-X100', check_in=date.today())
        resp = self.client.post('/calendar/send-recap/')
        # self.cl punya estimasi tapi yang baru tidak, self.cl harus ikut rekap
        # Test utama: jika TIDAK ADA yang punya estimasi, harus gagal
        self.cl.estimasi_tiba = None
        self.cl.save()
        resp2 = self.client.post('/calendar/send-recap/')
        data = resp2.json()
        self.assertFalse(data['ok'])


class SendReminderViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('tester6', password='pw12345')
        self.client.force_login(self.user)
        self.cl = _make_cl()

    @patch('hw.views.calendar_views.send_wa')
    def test_sends_reminder_and_creates_log(self, mock_send):
        mock_send.return_value = {'status': True}
        resp = self.client.post(f'/calendar/send-reminder/{self.cl.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['ok'])
        self.assertEqual(ReminderLog.objects.filter(cl=self.cl).count(), 1)

    def test_returns_error_if_no_phone(self):
        cl_no_phone = _make_cl(guest_phone='', confirmation_number='CL-NP2')
        resp = self.client.post(f'/calendar/send-reminder/{cl_no_phone.pk}/')
        self.assertFalse(resp.json()['ok'])


from django.core.management import call_command


class SendCheckInRemindersCommandTest(TestCase):
    def setUp(self):
        self.cl_today     = _make_cl(check_in=date.today(), confirmation_number='CL-T01')
        self.cl_tomorrow  = _make_cl(check_in=date.today() + timedelta(days=1), confirmation_number='CL-T02')
        self.cl_cancelled = _make_cl(check_in=date.today(), reservation_status='CANCELLED', confirmation_number='CL-T03')

    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_sends_h0_for_today(self, mock_send):
        mock_send.return_value = {'status': True}
        call_command('send_checkin_reminders')
        self.assertEqual(ReminderLog.objects.filter(cl=self.cl_today, reminder_type='H0_GUEST', status='SENT').count(), 1)

    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_sends_h1_for_tomorrow(self, mock_send):
        mock_send.return_value = {'status': True}
        call_command('send_checkin_reminders')
        self.assertEqual(ReminderLog.objects.filter(cl=self.cl_tomorrow, reminder_type='H1_GUEST', status='SENT').count(), 1)

    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_skips_cancelled(self, mock_send):
        mock_send.return_value = {'status': True}
        call_command('send_checkin_reminders')
        self.assertFalse(ReminderLog.objects.filter(cl=self.cl_cancelled).exists())

    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_idempotent_skips_already_sent(self, mock_send):
        mock_send.return_value = {'status': True}
        ReminderLog.objects.create(
            cl=self.cl_today, reminder_type='H0_GUEST', phone='628123456789', status='SENT',
        )
        call_command('send_checkin_reminders')
        self.assertEqual(mock_send.call_count, 1)  # hanya H1 tomorrow, H0 today di-skip

    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_records_failed_log_on_error(self, mock_send):
        mock_send.return_value = {'status': False, 'reason': 'invalid token'}
        call_command('send_checkin_reminders')
        log = ReminderLog.objects.get(cl=self.cl_today, reminder_type='H0_GUEST')
        self.assertEqual(log.status, 'FAILED')
        self.assertEqual(log.error, 'invalid token')

    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_skips_cl_without_phone(self, mock_send):
        cl_no_phone = _make_cl(guest_phone='', confirmation_number='CL-NP')
        call_command('send_checkin_reminders')
        self.assertFalse(ReminderLog.objects.filter(cl=cl_no_phone).exists())


class SendCheckInRecapCommandTest(TestCase):
    def setUp(self):
        self.cl1 = _make_cl(hotel_name='Hilton', confirmation_number='CL-R01')
        self.cl2 = _make_cl(hotel_name='Marriott', confirmation_number='CL-R02')

    @override_settings(FONNTE_TEAM_TARGETS=['628team'])
    @patch('hw.management.commands.send_checkin_recap.send_wa')
    def test_sends_recap_to_all_targets(self, mock_send):
        mock_send.return_value = {'status': True}
        call_command('send_checkin_recap')
        self.assertEqual(mock_send.call_count, 1)
        log = RecapLog.objects.first()
        self.assertEqual(log.cl_count, 2)
        self.assertEqual(log.triggered_by, 'AUTO')

    @override_settings(FONNTE_TEAM_TARGETS=['628a', '628b'])
    @patch('hw.management.commands.send_checkin_recap.send_wa')
    def test_sends_to_multiple_targets(self, mock_send):
        mock_send.return_value = {'status': True}
        call_command('send_checkin_recap')
        self.assertEqual(mock_send.call_count, 2)

    @override_settings(FONNTE_TEAM_TARGETS=['628team'])
    @patch('hw.management.commands.send_checkin_recap.send_wa')
    def test_message_contains_hotel_groups(self, mock_send):
        mock_send.return_value = {'status': True}
        call_command('send_checkin_recap')
        msg = mock_send.call_args.args[1]
        self.assertIn('HILTON', msg)
        self.assertIn('MARRIOTT', msg)
