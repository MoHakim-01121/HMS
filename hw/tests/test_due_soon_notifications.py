from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from hw.tests.factories import make_cl, make_hotel_line, make_invoice


def _make_cl(**kwargs):
    defaults = dict(
        hotel_name='Hilton Makkah',
        guest_name='Ahmad', guest_phone='628123456789',
        check_in=date.today(), check_out=date.today() + timedelta(days=3),
        confirmation_number='CL-001', reservation_status='DEFINITE',
    )
    defaults.update(kwargs)
    return make_cl(**defaults)


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
        inv = make_invoice( invoice_type='hotel',
                                     invoice_number='INV-001', customer_name='PT Uji',
                                     due_date=date.today())
        make_hotel_line(invoice=inv, reservation_number='RSV-1', total_sar=1000)
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
