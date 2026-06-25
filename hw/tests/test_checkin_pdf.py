from datetime import date, time, timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth.models import User
from hw.models import ConfirmationLetter


def _make_cl(**kwargs):
    defaults = dict(
        company='konoz', hotel_name='Hilton Makkah',
        guest_name='Ahmad', guest_phone='628123456789',
        check_in=date.today(), check_out=date.today() + timedelta(days=3),
        confirmation_number='KNZ-001', reservation_status='DEFINITE',
    )
    defaults.update(kwargs)
    return ConfirmationLetter.objects.create(**defaults)


class CheckinPdfGroupingTest(TestCase):
    def test_groups_by_date_then_hotel(self):
        today = date.today()
        tomorrow = today + timedelta(days=1)
        cl1 = _make_cl(guest_name='Ahmad', hotel_name='Hotel A', check_in=today, confirmation_number='K-001')
        cl2 = _make_cl(guest_name='Budi', hotel_name='Hotel B', check_in=today, confirmation_number='K-002')
        cl3 = _make_cl(guest_name='Candra', hotel_name='Hotel A', check_in=tomorrow, confirmation_number='K-003')

        from hw.views.pdf import _build_checkin_groups
        groups = _build_checkin_groups(
            ConfirmationLetter.objects.prefetch_related('rooms').order_by('check_in', 'hotel_name', 'guest_name')
        )

        self.assertEqual(len(groups), 2)  # 2 tanggal
        self.assertEqual(groups[0]['date'], today)
        self.assertEqual(len(groups[0]['hotels']), 2)  # Hotel A + Hotel B
        self.assertEqual(groups[0]['hotels'][0]['name'], 'Hotel A')
        self.assertEqual(groups[0]['hotels'][0]['guests'][0]['guest_name'], 'Ahmad')
        self.assertEqual(groups[0]['total'], 2)
        self.assertEqual(groups[1]['date'], tomorrow)
        self.assertEqual(len(groups[1]['hotels']), 1)

    def test_guest_fields_in_group(self):
        today = date.today()
        cl = _make_cl(
            guest_name='Zaid', hotel_name='Hilton', check_in=today,
            check_out=today + timedelta(days=5),
            confirmation_number='K-010',
            estimasi_tiba=time(14, 30),
            pic_name='Pak Budi', pic_phone='0812345',
        )
        from hw.views.pdf import _build_checkin_groups
        groups = _build_checkin_groups(
            ConfirmationLetter.objects.prefetch_related('rooms').order_by('check_in', 'hotel_name', 'guest_name')
        )
        guest = groups[0]['hotels'][0]['guests'][0]
        self.assertEqual(guest['guest_name'], 'Zaid')
        self.assertEqual(guest['confirmation_number'], 'K-010')
        self.assertEqual(guest['eta'], '14:30')
        self.assertEqual(guest['pic_name'], 'Pak Budi')
        self.assertEqual(guest['pic_phone'], '0812345')
        self.assertEqual(guest['num_nights'], 5)
        self.assertEqual(guest['no'], 1)

    def test_eta_dash_when_none(self):
        today = date.today()
        _make_cl(estimasi_tiba=None)
        from hw.views.pdf import _build_checkin_groups
        groups = _build_checkin_groups(
            ConfirmationLetter.objects.prefetch_related('rooms').order_by('check_in', 'hotel_name', 'guest_name')
        )
        guest = groups[0]['hotels'][0]['guests'][0]
        self.assertEqual(guest['eta'], '—')

    def test_pic_dash_when_empty(self):
        _make_cl(pic_name='', pic_phone='')
        from hw.views.pdf import _build_checkin_groups
        groups = _build_checkin_groups(
            ConfirmationLetter.objects.prefetch_related('rooms').order_by('check_in', 'hotel_name', 'guest_name')
        )
        guest = groups[0]['hotels'][0]['guests'][0]
        self.assertEqual(guest['pic_name'], '—')
        self.assertEqual(guest['pic_phone'], '—')


class CheckinPdfViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('tester', password='pw12345')
        self.client.force_login(self.user)
        session = self.client.session
        session['active_company'] = 'konoz'
        session.save()

    @patch('hw.views.pdf.HTML')
    def test_all_returns_pdf(self, mock_html):
        mock_html.return_value.write_pdf.return_value = b'%PDF-dummy'
        resp = self.client.get('/calendar/checkin-pdf/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn('checkin-rekap-', resp['Content-Disposition'])

    @patch('hw.views.pdf.HTML')
    def test_date_param_returns_pdf(self, mock_html):
        mock_html.return_value.write_pdf.return_value = b'%PDF-dummy'
        today_str = date.today().isoformat()
        resp = self.client.get(f'/calendar/checkin-pdf/?date={today_str}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn(f'checkin-{today_str}.pdf', resp['Content-Disposition'])

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get('/calendar/checkin-pdf/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp['Location'])
