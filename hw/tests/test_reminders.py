from hw.tests.factories import make_cl, make_room
from datetime import date, timedelta
from django.core.cache import cache
from django.test import TestCase
from hw.models import ConfirmationLetter


def _make_cl(**kwargs):
    defaults = dict(
        hotel_name='Hilton Makkah',
        guest_name='Ahmad', guest_phone='628123456789',
        check_in=date.today(), check_out=date.today() + timedelta(days=3),
        confirmation_number='CL-001', reservation_status='DEFINITE',
    )
    defaults.update(kwargs)
    return make_cl(**defaults)


class ClEstimasiFieldTest(TestCase):
    def test_cl_estimasi_fields(self):
        from datetime import time
        cl = _make_cl(estimasi_tiba=time(14, 0), pic_name='Budi', pic_phone='0812xxx')
        cl.refresh_from_db()
        self.assertEqual(cl.estimasi_tiba.hour, 14)
        self.assertEqual(cl.pic_name, 'Budi')


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
        defaults = dict(name='PT Uji Target', wa='', wa_group='', reminder_target='PIC')
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
        defaults = dict(name='PT Grup Uji')
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
        make_room(cl=cl, room_type='Double', quantity=3, price=500000)
        make_room(cl=cl, room_type='Quad', quantity=5, price=700000)
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

    def test_h1_says_lusa_for_check_in_two_days_away(self):
        from hw.services.recap import build_grouped_reminder_message
        client = self._make_client(name='PT H2')
        cl = _make_cl(client=client, check_in=date.today() + timedelta(days=2))
        msg = build_grouped_reminder_message([cl], 'H1_GUEST', recipient_name=client.name)
        self.assertIn('lusa', msg.lower())
        self.assertNotIn('besok', msg.lower())

    def test_h1_says_n_hari_lagi_for_check_in_far_away(self):
        from hw.services.recap import build_grouped_reminder_message
        client = self._make_client(name='PT H3')
        cl = _make_cl(client=client, check_in=date.today() + timedelta(days=5),
                     check_out=date.today() + timedelta(days=7))
        msg = build_grouped_reminder_message([cl], 'H1_GUEST', recipient_name=client.name)
        self.assertIn('5 hari lagi', msg.lower())
        self.assertNotIn('besok', msg.lower())

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
        self.assertIn('rooms', entry)

    def test_includes_client_id_and_name_when_set(self):
        from hw.models import Client
        client = Client.objects.create( name='PT Upcoming')
        cl2 = _make_cl(client=client, check_in=date.today(), confirmation_number='CL-UPC1')
        resp = self.client.get('/calendar/', HTTP_X_INERTIA='true')
        entries = resp.json()['props']['upcoming_checkins']
        entry = next(e for e in entries if e['pk'] == cl2.pk)
        self.assertEqual(entry['client_id'], client.pk)
        self.assertEqual(entry['client_name'], 'PT Upcoming')

    def test_client_fields_are_always_present(self):
        # Schema v2: tidak ada reservasi tanpa client.
        resp = self.client.get('/calendar/', HTTP_X_INERTIA='true')
        entry = resp.json()['props']['upcoming_checkins'][0]
        self.assertIsNotNone(entry['client_id'])
        self.assertTrue(entry['client_name'])


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

    def test_returns_recap_message(self):
        resp = self.client.post('/calendar/send-recap/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertIn('HILTON', data['message'])
        self.assertEqual(data['cl_count'], 1)

    def test_builds_message_even_without_estimasi(self):
        self.cl.estimasi_tiba = None
        self.cl.save()
        resp = self.client.post('/calendar/send-recap/')
        self.assertTrue(resp.json()['ok'])
        self.assertIn('message', resp.json())

    def test_returns_error_if_no_bookings_at_all(self):
        self.cl.delete()
        resp = self.client.post('/calendar/send-recap/')
        self.assertFalse(resp.json()['ok'])


class SendReminderGroupViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('tester7', password='pw12345')
        self.client.force_login(self.user)
        s = self.client.session; s['active_company'] = 'konoz'; s.save()

    def _make_client(self, **kwargs):
        from hw.models import Client
        defaults = dict(name='PT Grup View', wa='628111', reminder_target='PIC')
        defaults.update(kwargs)
        return Client.objects.create(**defaults)

    def test_returns_grouped_message_and_phone(self):
        client = self._make_client()
        cl1 = _make_cl(client=client, check_in=date.today(), confirmation_number='CL-V1')
        cl2 = _make_cl(client=client, check_in=date.today(), confirmation_number='CL-V2')
        resp = self.client.post('/calendar/send-reminder-group/', {'cl_ids': [cl1.pk, cl2.pk]})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertIn('CL-V1', data['message'])
        self.assertIn('CL-V2', data['message'])
        self.assertEqual(data['phone'], '628111')
        self.assertEqual(data['reminder_type'], 'H0_GUEST')

    def test_builds_message_for_check_in_beyond_h1(self):
        client = self._make_client()
        cl = _make_cl(client=client, check_in=date.today() + timedelta(days=3),
                     check_out=date.today() + timedelta(days=5), confirmation_number='CL-H3')
        resp = self.client.post('/calendar/send-reminder-group/', {'cl_ids': [cl.pk]})
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['reminder_type'], 'H1_GUEST')

    def test_error_when_check_in_already_passed(self):
        client = self._make_client()
        cl = _make_cl(client=client, check_in=date.today() - timedelta(days=1), confirmation_number='CL-PAST')
        resp = self.client.post('/calendar/send-reminder-group/', {'cl_ids': [cl.pk]})
        self.assertFalse(resp.json()['ok'])

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

    def test_message_built_even_without_wa_number(self):
        client = self._make_client(wa='', wa_group='', reminder_target='GROUP')
        cl = _make_cl(client=client, check_in=date.today())
        resp = self.client.post('/calendar/send-reminder-group/', {'cl_ids': [cl.pk]})
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['phone'], '')

    def _pic_client(self, name='Nur Sultan'):
        """Client tanpa nomor WA sendiri, pengingat ke PIC: nomornya diambil
        dari booking."""
        from hw.models import Client
        return Client.objects.create(name=name, reminder_target='PIC')

    def test_falls_back_to_the_booking_phone_when_client_has_no_wa(self):
        client = self._pic_client()
        cl1 = _make_cl(client=client, guest_phone='628999',
                       check_in=date.today(), confirmation_number='CL-GV1')
        cl2 = _make_cl(client=client, guest_phone='628999',
                       check_in=date.today(), confirmation_number='CL-GV2')
        resp = self.client.post('/calendar/send-reminder-group/', {'cl_ids': [cl1.pk, cl2.pk]})
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['phone'], '628999')

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

    def test_booking_phone_is_found_on_any_booking_of_the_group(self):
        client = self._pic_client()
        cl1 = _make_cl(client=client, guest_phone='',
                       check_in=date.today(), confirmation_number='CL-BPV1')
        cl2 = _make_cl(client=client, guest_phone='085385557053',
                       check_in=date.today(), confirmation_number='CL-BPV2')
        resp = self.client.post('/calendar/send-reminder-group/', {'cl_ids': [cl1.pk, cl2.pk]})
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['phone'], '085385557053')



class DueSoonNotificationsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('notif_user', password='pw12345')
        self.client.force_login(self.user)
        s = self.client.session; s['active_company'] = 'konoz'; s.save()
        cache.clear()

    def _notifs(self):
        resp = self.client.get('/dashboard/', HTTP_X_INERTIA='true')
        self.assertEqual(resp.status_code, 200)
        return resp.json()['props'].get('due_soon_notifs', [])

    def test_empty_when_nothing_due(self):
        self.assertEqual(self._notifs(), [])

    def test_includes_check_in_today(self):
        _make_cl(check_in=date.today(), check_out=date.today() + timedelta(days=3),
                 confirmation_number='CL-CIN1', hotel_name='Hilton Makkah', guest_name='Ahmad')
        ci = [n for n in self._notifs() if n['type'] == 'check_in']
        self.assertEqual(len(ci), 1)
        entry = ci[0]
        self.assertEqual(entry['ref'], 'CL-CIN1')
        self.assertEqual(entry['title'], 'Ahmad')
        self.assertEqual(entry['meta'], 'Hilton Makkah')
        self.assertEqual(entry['days'], 0)
        self.assertIn('cl/', entry['url'])

    def test_excludes_check_out_today(self):
        _make_cl(check_in=date.today() - timedelta(days=3), check_out=date.today(),
                 confirmation_number='CL-COUT1', hotel_name='Marriott', guest_name='Budi')
        co = [n for n in self._notifs() if n['type'] == 'check_out']
        self.assertEqual(len(co), 0)

    def test_excludes_cancelled(self):
        _make_cl(check_in=date.today(), confirmation_number='CL-CAN1', reservation_status='CANCELLED')
        notifs = self._notifs()
        self.assertFalse(any(n['ref'] == 'CL-CAN1' for n in notifs))

    def test_excludes_past_check_in(self):
        _make_cl(check_in=date.today() - timedelta(days=1),
                 check_out=date.today(), confirmation_number='CL-PAST1')
        notifs = self._notifs()
        self.assertFalse(any(n['ref'] == 'CL-PAST1' for n in notifs))

    def test_excludes_check_in_beyond_threshold(self):
        _make_cl(check_in=date.today() + timedelta(days=8),
                 check_out=date.today() + timedelta(days=9), confirmation_number='CL-FAR1')
        notifs = self._notifs()
        self.assertFalse(any(n['ref'] == 'CL-FAR1' for n in notifs))

    def test_sorted_by_days(self):
        _make_cl(check_in=date.today() + timedelta(days=3),
                 check_out=date.today() + timedelta(days=5), confirmation_number='CL-3DAY')
        _make_cl(check_in=date.today(), confirmation_number='CL-TODAY')
        days = [n['days'] for n in self._notifs()]
        self.assertEqual(days, sorted(days))

    def test_invoice_notifs_keep_remaining(self):
        from hw.models import Invoice, Reservation
        inv = Invoice.objects.create( invoice_type='HOTEL',
                                     invoice_number='INV-001', customer_name='PT Uji',
                                     due_date=date.today())
        Reservation.objects.create(invoice=inv, reservation_number='RSV-1', total_sar=1000)
        inv_notif = [n for n in self._notifs() if n['type'] == 'invoice_due']
        self.assertEqual(len(inv_notif), 1)
        self.assertEqual(inv_notif[0]['ref'], 'INV-001')
        self.assertEqual(inv_notif[0]['remaining'], 1000)
        self.assertIn('invoice/', inv_notif[0]['url'])

    def test_due_soon_count_matches_notifs(self):
        _make_cl(check_in=date.today(), confirmation_number='CL-CNT1')
        resp = self.client.get('/dashboard/', HTTP_X_INERTIA='true')
        props = resp.json()['props']
        self.assertEqual(props['due_soon_count'], len(props['due_soon_notifs']))
