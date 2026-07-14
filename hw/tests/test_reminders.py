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
        from hw.services.recap import build_recap_message, build_grouped_reminder_message
        cl = _make_cl(confirmation_number='CL-EMJ1')
        recap_msg = build_recap_message([cl], date.today())
        reminder_msg = build_grouped_reminder_message([cl], 'H0_GUEST', recipient_name=cl.guest_name)
        for msg in [recap_msg, reminder_msg]:
            for char in msg:
                self.assertLess(ord(char), 0x1F300,
                    f"Emoji ditemukan di pesan: {repr(char)}")


class ResolveReminderTargetsTest(TestCase):
    def _make_client(self, **kwargs):
        from hw.models import Client
        defaults = dict(company='konoz', name='PT Uji Target', wa='', wa_group='', reminder_target='PIC')
        defaults.update(kwargs)
        return Client.objects.create(**defaults)

    def test_pic_uses_client_wa(self):
        from hw.services.recap import resolve_reminder_targets
        client = self._make_client(wa='628111', reminder_target='PIC')
        cl = _make_cl(guest_phone='628999')
        targets = resolve_reminder_targets(client, [cl])
        self.assertEqual(targets, [('PIC', '628111')])

    def test_pic_falls_back_to_first_pending_guest_phone(self):
        from hw.services.recap import resolve_reminder_targets
        client = self._make_client(wa='', reminder_target='PIC')
        cl = _make_cl(guest_phone='628999')
        targets = resolve_reminder_targets(client, [cl])
        self.assertEqual(targets, [('PIC', '628999')])

    def test_pic_empty_when_no_wa_and_no_guest_phone(self):
        from hw.services.recap import resolve_reminder_targets
        client = self._make_client(wa='', reminder_target='PIC')
        cl = _make_cl(guest_phone='')
        targets = resolve_reminder_targets(client, [cl])
        self.assertEqual(targets, [])

    def test_group_uses_wa_group(self):
        from hw.services.recap import resolve_reminder_targets
        client = self._make_client(wa_group='120363xxx', reminder_target='GROUP')
        cl = _make_cl()
        targets = resolve_reminder_targets(client, [cl])
        self.assertEqual(targets, [('GROUP', '120363xxx')])

    def test_group_empty_when_wa_group_blank_no_fallback(self):
        from hw.services.recap import resolve_reminder_targets
        client = self._make_client(wa_group='', wa='628111', reminder_target='GROUP')
        cl = _make_cl()
        targets = resolve_reminder_targets(client, [cl])
        self.assertEqual(targets, [])

    def test_both_returns_two_targets(self):
        from hw.services.recap import resolve_reminder_targets
        client = self._make_client(wa='628111', wa_group='120363xxx', reminder_target='BOTH')
        cl = _make_cl()
        targets = resolve_reminder_targets(client, [cl])
        self.assertEqual(targets, [('PIC', '628111'), ('GROUP', '120363xxx')])

    def test_both_only_pic_when_group_blank(self):
        from hw.services.recap import resolve_reminder_targets
        client = self._make_client(wa='628111', wa_group='', reminder_target='BOTH')
        cl = _make_cl()
        targets = resolve_reminder_targets(client, [cl])
        self.assertEqual(targets, [('PIC', '628111')])


class BuildGroupedReminderMessageTest(TestCase):
    def _make_client(self, **kwargs):
        from hw.models import Client
        defaults = dict(company='konoz', name='PT Grup Uji')
        defaults.update(kwargs)
        return Client.objects.create(**defaults)

    def test_merges_two_bookings_same_hotel_into_one_block(self):
        from hw.services.recap import build_grouped_reminder_message
        client = self._make_client(name='PT Merge')
        cl1 = _make_cl(client=client, hotel_name='Hilton Makkah', confirmation_number='CL-M1')
        cl2 = _make_cl(client=client, hotel_name='Hilton Makkah', confirmation_number='CL-M2')
        msg = build_grouped_reminder_message([cl1, cl2], 'H0_GUEST', recipient_name=client.name)
        self.assertEqual(msg.count('HILTON MAKKAH'), 1)
        self.assertIn('CL-M1', msg)
        self.assertIn('CL-M2', msg)

    def test_booking_line_uses_rsv_and_kamar_two_line_format(self):
        from hw.models import Room
        from hw.services.recap import build_grouped_reminder_message
        client = self._make_client(name='PT Format')
        cl = _make_cl(client=client, hotel_name='Hilton Makkah', confirmation_number='555')
        Room.objects.create(cl=cl, room_type='Double', quantity=3, price=500000)
        Room.objects.create(cl=cl, room_type='Quad', quantity=5, price=700000)
        msg = build_grouped_reminder_message([cl], 'H0_GUEST', recipient_name=client.name)
        self.assertIn('1. #RSV : 555\n   Kamar : 3 Double, 5 Quad', msg)
        self.assertNotIn('Tamu:', msg)
        self.assertNotIn('No. CL', msg)

    def test_blank_line_between_bookings(self):
        from hw.services.recap import build_grouped_reminder_message
        client = self._make_client(name='PT Spasi')
        cl1 = _make_cl(client=client, hotel_name='Hilton Makkah', confirmation_number='CL-B1')
        cl2 = _make_cl(client=client, hotel_name='Hilton Makkah', confirmation_number='CL-B2')
        msg = build_grouped_reminder_message([cl1, cl2], 'H0_GUEST', recipient_name=client.name)
        self.assertIn('1. #RSV : CL-B1\n   Kamar : -\n\n2. #RSV : CL-B2', msg)

    def test_keeps_two_different_hotels_separate_in_one_message(self):
        from hw.services.recap import build_grouped_reminder_message
        client = self._make_client(name='PT Split')
        cl1 = _make_cl(client=client, hotel_name='Hilton Makkah', confirmation_number='CL-S1')
        cl2 = _make_cl(client=client, hotel_name='Swissotel Madinah', confirmation_number='CL-S2')
        msg = build_grouped_reminder_message([cl1, cl2], 'H0_GUEST', recipient_name=client.name)
        self.assertIn('HILTON MAKKAH', msg)
        self.assertIn('SWISSOTEL MADINAH', msg)
        self.assertLess(msg.index('HILTON MAKKAH'), msg.index('SWISSOTEL MADINAH'))

    def test_greets_recipient_name_not_pic(self):
        from hw.services.recap import build_grouped_reminder_message
        client = self._make_client(name='PT Salam Benar', pic='Budi Santoso')
        cl = _make_cl(client=client)
        msg = build_grouped_reminder_message([cl], 'H0_GUEST', recipient_name=client.name)
        self.assertIn('PT Salam Benar', msg)
        self.assertNotIn('Budi Santoso', msg)

    def test_h1_includes_besok_and_date(self):
        from hw.services.recap import build_grouped_reminder_message
        client = self._make_client(name='PT H1')
        cl = _make_cl(client=client, check_in=date.today() + timedelta(days=1))
        msg = build_grouped_reminder_message([cl], 'H1_GUEST', recipient_name=client.name)
        self.assertIn('besok', msg.lower())

    def test_h0_has_no_besok(self):
        from hw.services.recap import build_grouped_reminder_message
        client = self._make_client(name='PT H0')
        cl = _make_cl(client=client, check_in=date.today())
        msg = build_grouped_reminder_message([cl], 'H0_GUEST', recipient_name=client.name)
        self.assertNotIn('besok', msg.lower())

    def test_accepts_guest_name_as_recipient_without_client(self):
        from hw.services.recap import build_grouped_reminder_message
        cl1 = _make_cl(client=None, guest_name='Nur Sultan', hotel_name='Sawaed Al Kheir', confirmation_number='CL-G1')
        cl2 = _make_cl(client=None, guest_name='Nur Sultan', hotel_name='Sawaed Al Kheir', confirmation_number='CL-G2')
        msg = build_grouped_reminder_message([cl1, cl2], 'H0_GUEST', recipient_name='Nur Sultan')
        self.assertIn('Nur Sultan', msg)
        self.assertIn('CL-G1', msg)
        self.assertIn('CL-G2', msg)

    def test_h0_uses_saved_template_from_settings(self):
        from hw.models import MessageTemplate
        from hw.services.recap import build_grouped_reminder_message
        MessageTemplate.objects.create(
            template_type='H0_GUEST',
            body='Salam {client_name}, check-in hari ini:\n{booking_blocks}\nTTD Konoz',
        )
        client = self._make_client(name='PT Template H0')
        cl = _make_cl(client=client, confirmation_number='CL-T0')
        msg = build_grouped_reminder_message([cl], 'H0_GUEST', recipient_name=client.name)
        self.assertIn('Salam PT Template H0', msg)
        self.assertIn('CL-T0', msg)
        self.assertIn('TTD Konoz', msg)

    def test_h1_uses_saved_template_from_settings(self):
        from hw.models import MessageTemplate
        from hw.services.recap import build_grouped_reminder_message
        MessageTemplate.objects.create(
            template_type='H1_GUEST',
            body='Halo {client_name}, besok {check_in_date}:\n{booking_blocks}\nTTD Konoz',
        )
        client = self._make_client(name='PT Template H1')
        check_in = date.today() + timedelta(days=1)
        cl = _make_cl(client=client, check_in=check_in, confirmation_number='CL-T1')
        msg = build_grouped_reminder_message([cl], 'H1_GUEST', recipient_name=client.name)
        self.assertIn('Halo PT Template H1', msg)
        self.assertIn(check_in.strftime('%d %b %Y'), msg)
        self.assertIn('CL-T1', msg)
        self.assertIn('TTD Konoz', msg)

    def test_falls_back_to_default_when_no_template_saved(self):
        from hw.services.recap import build_grouped_reminder_message
        client = self._make_client(name='PT Tanpa Template')
        cl = _make_cl(client=client, confirmation_number='CL-DF')
        msg = build_grouped_reminder_message([cl], 'H0_GUEST', recipient_name=client.name)
        self.assertIn('Berikut detail check-in hari ini', msg)
        self.assertIn('CL-DF', msg)


class ResolveGuestTargetTest(TestCase):
    def test_returns_guest_channel_with_phone(self):
        from hw.services.recap import resolve_guest_target
        cl = _make_cl(client=None, guest_phone='628999')
        self.assertEqual(resolve_guest_target([cl]), [('GUEST', '628999')])

    def test_empty_when_no_phone(self):
        from hw.services.recap import resolve_guest_target
        cl = _make_cl(client=None, guest_phone='')
        self.assertEqual(resolve_guest_target([cl]), [])

    def test_uses_first_pending_cl_with_phone(self):
        from hw.services.recap import resolve_guest_target
        cl1 = _make_cl(client=None, guest_phone='', confirmation_number='CL-NP1')
        cl2 = _make_cl(client=None, guest_phone='628999', confirmation_number='CL-NP2')
        self.assertEqual(resolve_guest_target([cl1, cl2]), [('GUEST', '628999')])


class GroupGuestsTest(TestCase):
    def test_same_name_blank_and_filled_phone_grouped(self):
        from hw.services.recap import group_guests
        cl1 = _make_cl(guest_name='Nur Sultan', guest_phone='', confirmation_number='CL-BP1')
        cl2 = _make_cl(guest_name='Nur Sultan', guest_phone='085385557053', confirmation_number='CL-BP2')
        groups = group_guests([cl1, cl2])
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(list(groups.values())[0]), 2)

    def test_same_name_two_distinct_phones_kept_separate(self):
        from hw.services.recap import group_guests
        cl1 = _make_cl(guest_name='Ahmad', guest_phone='628111', confirmation_number='CL-DP1')
        cl2 = _make_cl(guest_name='Ahmad', guest_phone='628222', confirmation_number='CL-DP2')
        groups = group_guests([cl1, cl2])
        self.assertEqual(len(groups), 2)

    def test_blank_phone_stays_standalone_when_name_ambiguous(self):
        from hw.services.recap import group_guests
        cl1 = _make_cl(guest_name='Ahmad', guest_phone='628111', confirmation_number='CL-AM1')
        cl2 = _make_cl(guest_name='Ahmad', guest_phone='628222', confirmation_number='CL-AM2')
        cl3 = _make_cl(guest_name='Ahmad', guest_phone='', confirmation_number='CL-AM3')
        groups = group_guests([cl1, cl2, cl3])
        self.assertEqual(len(groups), 3)

    def test_different_names_never_grouped(self):
        from hw.services.recap import group_guests
        cl1 = _make_cl(guest_name='Nur Sultan', confirmation_number='CL-DN1')
        cl2 = _make_cl(guest_name='Budi', confirmation_number='CL-DN2')
        groups = group_guests([cl1, cl2])
        self.assertEqual(len(groups), 2)

    def test_name_matching_ignores_case_and_whitespace(self):
        from hw.services.recap import group_guests
        cl1 = _make_cl(guest_name='Nur Sultan', guest_phone='628999', confirmation_number='CL-CS1')
        cl2 = _make_cl(guest_name='  NUR SULTAN ', guest_phone='', confirmation_number='CL-CS2')
        groups = group_guests([cl1, cl2])
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(list(groups.values())[0]), 2)


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

    def test_includes_client_id_and_name_when_set(self):
        from hw.models import Client
        client = Client.objects.create(company='konoz', name='PT Upcoming')
        cl2 = _make_cl(client=client, check_in=date.today(), confirmation_number='CL-UPC1')
        resp = self.client.get('/calendar/', HTTP_X_INERTIA='true')
        entries = resp.json()['props']['upcoming_checkins']
        entry = next(e for e in entries if e['pk'] == cl2.pk)
        self.assertEqual(entry['client_id'], client.pk)
        self.assertEqual(entry['client_name'], 'PT Upcoming')

    def test_client_fields_none_when_no_client(self):
        resp = self.client.get('/calendar/', HTTP_X_INERTIA='true')
        entry = resp.json()['props']['upcoming_checkins'][0]
        self.assertIsNone(entry['client_id'])
        self.assertIsNone(entry['client_name'])


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

    @patch('hw.tasks.send_wa')
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


class SendReminderGroupViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('tester7', password='pw12345')
        self.client.force_login(self.user)
        s = self.client.session; s['active_company'] = 'konoz'; s.save()

    def _make_client(self, **kwargs):
        from hw.models import Client
        defaults = dict(company='konoz', name='PT Grup View', wa='628111', reminder_target='PIC')
        defaults.update(kwargs)
        return Client.objects.create(**defaults)

    @override_settings(REMINDER_H1_H0_ENABLED=False)
    def test_returns_error_when_disabled(self):
        client = self._make_client()
        cl = _make_cl(client=client, check_in=date.today())
        resp = self.client.post('/calendar/send-reminder-group/', {'cl_ids': [cl.pk]})
        self.assertFalse(resp.json()['ok'])

    @patch('hw.tasks.send_wa')
    def test_sends_grouped_message_and_creates_logs(self, mock_send):
        mock_send.return_value = {'status': True}
        client = self._make_client()
        cl1 = _make_cl(client=client, check_in=date.today(), confirmation_number='CL-V1')
        cl2 = _make_cl(client=client, check_in=date.today(), confirmation_number='CL-V2')
        resp = self.client.post('/calendar/send-reminder-group/', {'cl_ids': [cl1.pk, cl2.pk]})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['ok'])
        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(ReminderLog.objects.filter(cl__in=[cl1, cl2]).count(), 2)

    def test_error_when_different_check_in_dates(self):
        client = self._make_client()
        cl1 = _make_cl(client=client, check_in=date.today(), confirmation_number='CL-DD1')
        cl2 = _make_cl(client=client, check_in=date.today() + timedelta(days=1), confirmation_number='CL-DD2')
        resp = self.client.post('/calendar/send-reminder-group/', {'cl_ids': [cl1.pk, cl2.pk]})
        self.assertFalse(resp.json()['ok'])

    def test_error_when_different_clients(self):
        client1 = self._make_client(name='PT A')
        client2 = self._make_client(name='PT B')
        cl1 = _make_cl(client=client1, check_in=date.today(), confirmation_number='CL-DC1')
        cl2 = _make_cl(client=client2, check_in=date.today(), confirmation_number='CL-DC2')
        resp = self.client.post('/calendar/send-reminder-group/', {'cl_ids': [cl1.pk, cl2.pk]})
        self.assertFalse(resp.json()['ok'])

    def test_error_when_no_wa_configured(self):
        client = self._make_client(wa='', wa_group='', reminder_target='GROUP')
        cl = _make_cl(client=client, check_in=date.today())
        resp = self.client.post('/calendar/send-reminder-group/', {'cl_ids': [cl.pk]})
        self.assertFalse(resp.json()['ok'])

    @patch('hw.tasks.send_wa')
    def test_sends_guest_grouped_message_when_no_client(self, mock_send):
        mock_send.return_value = {'status': True}
        cl1 = _make_cl(client=None, guest_name='Nur Sultan', guest_phone='628999',
                        check_in=date.today(), confirmation_number='CL-GV1')
        cl2 = _make_cl(client=None, guest_name='Nur Sultan', guest_phone='628999',
                        check_in=date.today(), confirmation_number='CL-GV2')
        resp = self.client.post('/calendar/send-reminder-group/', {'cl_ids': [cl1.pk, cl2.pk]})
        self.assertTrue(resp.json()['ok'])
        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(ReminderLog.objects.filter(cl__in=[cl1, cl2]).count(), 2)

    def test_error_when_guest_names_differ_and_no_client(self):
        cl1 = _make_cl(client=None, guest_name='Nur Sultan', guest_phone='628999', check_in=date.today(), confirmation_number='CL-GD1')
        cl2 = _make_cl(client=None, guest_name='Budi', guest_phone='628111', check_in=date.today(), confirmation_number='CL-GD2')
        resp = self.client.post('/calendar/send-reminder-group/', {'cl_ids': [cl1.pk, cl2.pk]})
        self.assertFalse(resp.json()['ok'])

    def test_error_when_mixing_client_and_no_client(self):
        client = self._make_client()
        cl1 = _make_cl(client=client, check_in=date.today(), confirmation_number='CL-MIX1')
        cl2 = _make_cl(client=None, check_in=date.today(), confirmation_number='CL-MIX2')
        resp = self.client.post('/calendar/send-reminder-group/', {'cl_ids': [cl1.pk, cl2.pk]})
        self.assertFalse(resp.json()['ok'])

    def test_error_when_guest_has_no_phone(self):
        cl = _make_cl(client=None, guest_phone='', check_in=date.today())
        resp = self.client.post('/calendar/send-reminder-group/', {'cl_ids': [cl.pk]})
        self.assertFalse(resp.json()['ok'])

    @patch('hw.tasks.send_wa')
    def test_sends_guest_group_when_one_booking_has_blank_phone(self, mock_send):
        mock_send.return_value = {'status': True}
        cl1 = _make_cl(client=None, guest_name='Nur Sultan', guest_phone='',
                        check_in=date.today(), confirmation_number='CL-BPV1')
        cl2 = _make_cl(client=None, guest_name='Nur Sultan', guest_phone='085385557053',
                        check_in=date.today(), confirmation_number='CL-BPV2')
        resp = self.client.post('/calendar/send-reminder-group/', {'cl_ids': [cl1.pk, cl2.pk]})
        self.assertTrue(resp.json()['ok'])
        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(ReminderLog.objects.filter(cl__in=[cl1, cl2]).count(), 2)

    @patch('hw.tasks.send_wa')
    def test_resend_allowed_when_already_sent_today(self, mock_send):
        mock_send.return_value = {'status': True}
        client = self._make_client()
        cl = _make_cl(client=client, check_in=date.today(), confirmation_number='CL-AS1')
        ReminderLog.objects.create(cl=cl, reminder_type='H0_GUEST', phone='628111', status='SENT')
        resp = self.client.post('/calendar/send-reminder-group/', {'cl_ids': [cl.pk]})
        self.assertTrue(resp.json()['ok'])
        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(ReminderLog.objects.filter(cl=cl, status='SENT').count(), 2)

    @patch('hw.tasks.send_wa')
    def test_resend_includes_already_sent_bookings(self, mock_send):
        mock_send.return_value = {'status': True}
        client = self._make_client()
        cl_sent = _make_cl(client=client, check_in=date.today(), confirmation_number='CL-PS1')
        cl_new  = _make_cl(client=client, check_in=date.today(), confirmation_number='CL-PS2')
        ReminderLog.objects.create(cl=cl_sent, reminder_type='H0_GUEST', phone='628111', status='SENT')
        resp = self.client.post('/calendar/send-reminder-group/', {'cl_ids': [cl_sent.pk, cl_new.pk]})
        self.assertTrue(resp.json()['ok'])
        self.assertEqual(mock_send.call_count, 1)
        message = mock_send.call_args[0][1]
        self.assertIn('CL-PS2', message)
        self.assertIn('CL-PS1', message)
        self.assertEqual(ReminderLog.objects.filter(cl=cl_sent).count(), 2)
        self.assertTrue(ReminderLog.objects.filter(cl=cl_new, status='SENT').exists())

    @patch('hw.tasks.send_wa')
    def test_guest_phone_resolved_from_already_sent_sibling(self, mock_send):
        mock_send.return_value = {'status': True}
        cl_sent  = _make_cl(client=None, guest_name='Nur Sultan', guest_phone='628999',
                            check_in=date.today(), confirmation_number='CL-SB1')
        cl_blank = _make_cl(client=None, guest_name='Nur Sultan', guest_phone='',
                            check_in=date.today(), confirmation_number='CL-SB2')
        ReminderLog.objects.create(cl=cl_sent, reminder_type='H0_GUEST', phone='628999', status='SENT')
        resp = self.client.post('/calendar/send-reminder-group/', {'cl_ids': [cl_sent.pk, cl_blank.pk]})
        self.assertTrue(resp.json()['ok'])
        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(mock_send.call_args[0][0], '628999')
        self.assertTrue(ReminderLog.objects.filter(cl=cl_blank, status='SENT').exists())


from django.core.management import call_command


class SendCheckInRemindersCommandTest(TestCase):
    def setUp(self):
        self.cl_today     = _make_cl(check_in=date.today(), confirmation_number='CL-T01')
        self.cl_tomorrow  = _make_cl(check_in=date.today() + timedelta(days=1), confirmation_number='CL-T02')
        self.cl_cancelled = _make_cl(check_in=date.today(), reservation_status='CANCELLED', confirmation_number='CL-T03')

    @override_settings(REMINDER_H1_H0_ENABLED=False)
    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_skips_when_disabled(self, mock_send):
        call_command('send_checkin_reminders')
        mock_send.assert_not_called()
        self.assertEqual(ReminderLog.objects.count(), 0)

    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_sends_h0_for_today(self, mock_send):
        mock_send.return_value = {'status': True}
        call_command('send_checkin_reminders')
        self.assertEqual(ReminderLog.objects.filter(cl=self.cl_today, reminder_type='H0_GUEST', status='SENT').count(), 1)

    @override_settings(REMINDER_H1_H0_ENABLED=True)
    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_sends_h1_for_tomorrow(self, mock_send):
        mock_send.return_value = {'status': True}
        call_command('send_checkin_reminders')
        self.assertEqual(ReminderLog.objects.filter(cl=self.cl_tomorrow, reminder_type='H1_GUEST', status='SENT').count(), 1)

    @override_settings(REMINDER_H1_H0_ENABLED=True)
    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_skips_cancelled(self, mock_send):
        mock_send.return_value = {'status': True}
        call_command('send_checkin_reminders')
        self.assertFalse(ReminderLog.objects.filter(cl=self.cl_cancelled).exists())

    @override_settings(REMINDER_H1_H0_ENABLED=True)
    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_idempotent_skips_already_sent(self, mock_send):
        mock_send.return_value = {'status': True}
        ReminderLog.objects.create(
            cl=self.cl_today, reminder_type='H0_GUEST', phone='628123456789', status='SENT',
        )
        call_command('send_checkin_reminders')
        self.assertEqual(mock_send.call_count, 1)  # hanya H1 tomorrow, H0 today di-skip

    @override_settings(REMINDER_H1_H0_ENABLED=True)
    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_records_failed_log_on_error(self, mock_send):
        mock_send.return_value = {'status': False, 'reason': 'invalid token'}
        call_command('send_checkin_reminders')
        log = ReminderLog.objects.get(cl=self.cl_today, reminder_type='H0_GUEST')
        self.assertEqual(log.status, 'FAILED')
        self.assertEqual(log.error, 'invalid token')

    @override_settings(REMINDER_H1_H0_ENABLED=True)
    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_skips_cl_without_phone(self, mock_send):
        cl_no_phone = _make_cl(guest_name='Tanpa Telepon', guest_phone='', confirmation_number='CL-NP')
        call_command('send_checkin_reminders')
        self.assertFalse(ReminderLog.objects.filter(cl=cl_no_phone).exists())


class GroupedReminderCommandTest(TestCase):
    def _make_client(self, **kwargs):
        from hw.models import Client
        defaults = dict(company='konoz', name='PT Grup Command', wa='628111', reminder_target='PIC')
        defaults.update(kwargs)
        return Client.objects.create(**defaults)

    @override_settings(REMINDER_H1_H0_ENABLED=True)
    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_two_bookings_same_hotel_send_once_log_twice(self, mock_send):
        mock_send.return_value = {'status': True}
        client = self._make_client()
        _make_cl(client=client, hotel_name='Hilton Makkah', check_in=date.today(), confirmation_number='CL-G1')
        _make_cl(client=client, hotel_name='Hilton Makkah', check_in=date.today(), confirmation_number='CL-G2')
        call_command('send_checkin_reminders')
        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(ReminderLog.objects.filter(reminder_type='H0_GUEST', status='SENT').count(), 2)

    @override_settings(REMINDER_H1_H0_ENABLED=True)
    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_two_bookings_different_hotels_still_one_send(self, mock_send):
        mock_send.return_value = {'status': True}
        client = self._make_client()
        _make_cl(client=client, hotel_name='Hilton Makkah', check_in=date.today(), confirmation_number='CL-D1')
        _make_cl(client=client, hotel_name='Swissotel Madinah', check_in=date.today(), confirmation_number='CL-D2')
        call_command('send_checkin_reminders')
        self.assertEqual(mock_send.call_count, 1)
        sent_message = mock_send.call_args[0][1]
        self.assertIn('HILTON MAKKAH', sent_message)
        self.assertIn('SWISSOTEL MADINAH', sent_message)

    @override_settings(REMINDER_H1_H0_ENABLED=True)
    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_cl_without_client_sent_individually(self, mock_send):
        mock_send.return_value = {'status': True}
        _make_cl(client=None, check_in=date.today(), confirmation_number='CL-NOCLIENT')
        call_command('send_checkin_reminders')
        self.assertEqual(mock_send.call_count, 1)
        log = ReminderLog.objects.get(reminder_type='H0_GUEST')
        self.assertEqual(log.cl.confirmation_number, 'CL-NOCLIENT')

    @override_settings(REMINDER_H1_H0_ENABLED=True)
    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_partial_already_sent_only_sends_pending(self, mock_send):
        mock_send.return_value = {'status': True}
        client = self._make_client()
        cl_sent    = _make_cl(client=client, hotel_name='Hilton Makkah', check_in=date.today(), confirmation_number='CL-P1')
        cl_pending = _make_cl(client=client, hotel_name='Hilton Makkah', check_in=date.today(), confirmation_number='CL-P2')
        ReminderLog.objects.create(cl=cl_sent, reminder_type='H0_GUEST', phone='628111', status='SENT')
        call_command('send_checkin_reminders')
        self.assertEqual(mock_send.call_count, 1)
        sent_message = mock_send.call_args[0][1]
        self.assertNotIn('CL-P1', sent_message)
        self.assertIn('CL-P2', sent_message)

    @override_settings(REMINDER_H1_H0_ENABLED=True)
    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_both_target_sends_to_two_channels(self, mock_send):
        mock_send.return_value = {'status': True}
        client = self._make_client(wa='628111', wa_group='120363xxx', reminder_target='BOTH')
        _make_cl(client=client, hotel_name='Hilton Makkah', check_in=date.today(), confirmation_number='CL-B1')
        call_command('send_checkin_reminders')
        self.assertEqual(mock_send.call_count, 2)
        self.assertEqual(ReminderLog.objects.filter(reminder_type='H0_GUEST', status='SENT').count(), 2)

    @override_settings(REMINDER_H1_H0_ENABLED=True)
    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_skips_when_group_target_has_no_wa_group(self, mock_send):
        client = self._make_client(wa='', wa_group='', reminder_target='GROUP')
        _make_cl(client=client, check_in=date.today(), confirmation_number='CL-SKIP1')
        call_command('send_checkin_reminders')
        mock_send.assert_not_called()
        self.assertEqual(ReminderLog.objects.count(), 0)

    @override_settings(REMINDER_H1_H0_ENABLED=True)
    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_guest_without_client_same_name_and_phone_grouped(self, mock_send):
        mock_send.return_value = {'status': True}
        _make_cl(client=None, guest_name='Nur Sultan', guest_phone='628999', hotel_name='Sawaed Al Kheir',
                  check_in=date.today(), confirmation_number='CL-GU1')
        _make_cl(client=None, guest_name='Nur Sultan', guest_phone='628999', hotel_name='Sawaed Al Kheir',
                  check_in=date.today(), confirmation_number='CL-GU2')
        call_command('send_checkin_reminders')
        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(mock_send.call_args[0][0], '628999')
        self.assertEqual(ReminderLog.objects.filter(reminder_type='H0_GUEST', status='SENT').count(), 2)

    @override_settings(REMINDER_H1_H0_ENABLED=True)
    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_guest_without_client_different_phone_not_grouped(self, mock_send):
        mock_send.return_value = {'status': True}
        _make_cl(client=None, guest_name='Nur Sultan', guest_phone='628999', check_in=date.today(), confirmation_number='CL-DP1')
        _make_cl(client=None, guest_name='Nur Sultan', guest_phone='628111', check_in=date.today(), confirmation_number='CL-DP2')
        call_command('send_checkin_reminders')
        self.assertEqual(mock_send.call_count, 2)

    @override_settings(REMINDER_H1_H0_ENABLED=True)
    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_guest_without_client_blank_phone_merges_with_filled(self, mock_send):
        mock_send.return_value = {'status': True}
        _make_cl(client=None, guest_name='Nur Sultan', guest_phone='', hotel_name='Sawaed Al Kheir',
                  check_in=date.today(), confirmation_number='CL-BP1')
        _make_cl(client=None, guest_name='Nur Sultan', guest_phone='085385557053', hotel_name='Sawaed Al Kheir',
                  check_in=date.today(), confirmation_number='CL-BP2')
        call_command('send_checkin_reminders')
        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(mock_send.call_args[0][0], '085385557053')
        self.assertEqual(ReminderLog.objects.filter(reminder_type='H0_GUEST', status='SENT').count(), 2)

    @override_settings(REMINDER_H1_H0_ENABLED=True)
    @patch('hw.management.commands.send_checkin_reminders.send_wa')
    def test_blank_phone_booking_retried_with_sibling_phone(self, mock_send):
        mock_send.return_value = {'status': True}
        cl_sent = _make_cl(client=None, guest_name='Nur Sultan', guest_phone='628999',
                           check_in=date.today(), confirmation_number='CL-RT1')
        cl_blank = _make_cl(client=None, guest_name='Nur Sultan', guest_phone='',
                            check_in=date.today(), confirmation_number='CL-RT2')
        ReminderLog.objects.create(cl=cl_sent, reminder_type='H0_GUEST', phone='628999', status='SENT')
        call_command('send_checkin_reminders')
        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(mock_send.call_args[0][0], '628999')
        self.assertTrue(ReminderLog.objects.filter(cl=cl_blank, status='SENT').exists())


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
