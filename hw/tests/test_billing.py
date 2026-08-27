from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from unittest.mock import patch

from hw.ai import generate_draft_message
from hw.models import BillingLog, Client, ConfirmationLetter, Invoice, Reservation, ServiceItem


def _make_invoice(**kwargs):
    defaults = dict(
        company='konoz', invoice_type='hotel',
        invoice_number='INV-BL-001', customer_name='Test Customer',
        currency='SAR',
    )
    defaults.update(kwargs)
    return Invoice.objects.create(**defaults)


class BillingLogModelTest(TestCase):
    def test_create_billing_log(self):
        invoice = _make_invoice()
        log = BillingLog.objects.create(
            invoice=invoice, target='628123456789',
            message='Halo, tagihan Anda', status='SENT',
        )
        self.assertEqual(BillingLog.objects.count(), 1)
        self.assertEqual(log.invoice, invoice)
        self.assertEqual(log.error, '')
        self.assertIsNotNone(log.sent_at)
        self.assertEqual(list(invoice.billing_logs.all()), [log])


class SendBillingTaskTest(TestCase):
    @patch('hw.tasks.send_wa')
    def test_creates_sent_log_on_success(self, mock_send):
        from hw.tasks import send_billing_task
        invoice = _make_invoice(invoice_number='INV-BT-001')
        mock_send.return_value = {'status': True}
        send_billing_task(invoice.pk, '628123456789', 'pesan tagihan')
        log = BillingLog.objects.get(invoice=invoice)
        self.assertEqual(log.status, 'SENT')
        self.assertEqual(log.target, '628123456789')
        self.assertEqual(log.message, 'pesan tagihan')
        self.assertEqual(log.error, '')
        mock_send.assert_called_once_with('628123456789', 'pesan tagihan')

    @patch('hw.tasks.send_wa')
    def test_creates_failed_log_on_failure(self, mock_send):
        from hw.tasks import send_billing_task
        invoice = _make_invoice(invoice_number='INV-BT-002')
        mock_send.return_value = {'status': False, 'reason': 'invalid token'}
        send_billing_task(invoice.pk, '628123456789', 'pesan tagihan')
        log = BillingLog.objects.get(invoice=invoice)
        self.assertEqual(log.status, 'FAILED')
        self.assertEqual(log.error, 'invalid token')

    @patch('hw.tasks.send_wa')
    def test_creates_failed_log_on_exception(self, mock_send):
        from hw.tasks import send_billing_task
        invoice = _make_invoice(invoice_number='INV-BT-003')
        mock_send.side_effect = RuntimeError('boom')
        send_billing_task(invoice.pk, '628123456789', 'pesan tagihan')
        log = BillingLog.objects.get(invoice=invoice)
        self.assertEqual(log.status, 'FAILED')
        self.assertEqual(log.error, 'boom')

    @patch('hw.views.pdf._render_invoice_pdf')
    @patch('hw.tasks.send_wa_file')
    def test_with_pdf_renders_and_sends_file(self, mock_send_file, mock_render):
        from unittest.mock import MagicMock
        from hw.tasks import send_billing_task
        invoice = _make_invoice(invoice_number='INV-BT-PDF1')
        mock_render.return_value = MagicMock(content=b'%PDF-fake')
        mock_send_file.return_value = {'status': True}
        send_billing_task(invoice.pk, '628123', 'caption', with_pdf=True)
        mock_render.assert_called_once()
        mock_send_file.assert_called_once_with('628123', 'caption', b'%PDF-fake', 'INV-BT-PDF1.pdf')
        log = BillingLog.objects.get(invoice=invoice)
        self.assertEqual(log.status, 'SENT')

    @patch('hw.views.pdf._render_services_pdf')
    @patch('hw.tasks.send_wa_file')
    def test_with_pdf_uses_services_renderer_for_visa(self, mock_send_file, mock_render):
        from unittest.mock import MagicMock
        from hw.tasks import send_billing_task
        invoice = _make_invoice(invoice_number='INV-BT-PDF2', invoice_type='visa')
        mock_render.return_value = MagicMock(content=b'%PDF-visa')
        mock_send_file.return_value = {'status': True}
        send_billing_task(invoice.pk, '628123', 'caption', with_pdf=True)
        mock_render.assert_called_once()
        self.assertEqual(BillingLog.objects.get(invoice=invoice).status, 'SENT')

    @patch('hw.views.pdf._render_invoice_pdf')
    @patch('hw.tasks.send_wa_file')
    def test_with_pdf_render_failure_logs_failed(self, mock_send_file, mock_render):
        from hw.tasks import send_billing_task
        invoice = _make_invoice(invoice_number='INV-BT-PDF3')
        mock_render.side_effect = RuntimeError('render boom')
        send_billing_task(invoice.pk, '628123', 'caption', with_pdf=True)
        mock_send_file.assert_not_called()
        log = BillingLog.objects.get(invoice=invoice)
        self.assertEqual(log.status, 'FAILED')
        self.assertEqual(log.error, 'render boom')

    @patch('hw.tasks.send_wa_file')
    @patch('hw.tasks.send_wa')
    def test_without_pdf_still_uses_send_wa(self, mock_send, mock_send_file):
        from hw.tasks import send_billing_task
        invoice = _make_invoice(invoice_number='INV-BT-PDF4')
        mock_send.return_value = {'status': True}
        send_billing_task(invoice.pk, '628123', 'teks saja', with_pdf=False)
        mock_send.assert_called_once_with('628123', 'teks saja')
        mock_send_file.assert_not_called()


class BillingSendEndpointTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('staff1', password='pw12345')
        self.client.force_login(self.user)
        s = self.client.session; s['active_company'] = 'konoz'; s.save()
        self.wa_client = Client.objects.create(
            company='konoz', name='Travel Amanah',
            wa='628111222333', wa_group='120363abc@g.us',
        )
        self.invoice = _make_invoice(invoice_number='INV-EP-001')
        # Invoice has no client FK of its own -- client resolves via a linked CL.
        ConfirmationLetter.objects.create(
            company='konoz', hotel_name='Hilton', guest_name='Ahmad',
            confirmation_number='CL-EP-SETUP', invoice=self.invoice, client=self.wa_client,
        )

    def _post(self, payload):
        return self.client.post(
            '/billing/send/', payload, content_type='application/json',
        )

    def test_non_post_rejected(self):
        resp = self.client.get('/billing/send/')
        self.assertEqual(resp.status_code, 405)

    @patch('hw.views.billing_views.async_task')
    def test_send_to_client_wa_resolves_number_on_server(self, mock_task):
        resp = self._post({'pk': self.invoice.pk, 'message': 'halo', 'target_kind': 'client_wa'})
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertTrue(data['queued'])
        mock_task.assert_called_once_with(
            'hw.tasks.send_billing_task', self.invoice.pk, '628111222333', 'halo', False,
        )

    @patch('hw.views.billing_views.async_task')
    def test_with_pdf_flag_is_forwarded(self, mock_task):
        resp = self._post({
            'pk': self.invoice.pk, 'message': 'halo',
            'target_kind': 'client_wa', 'with_pdf': True,
        })
        self.assertTrue(resp.json()['ok'])
        mock_task.assert_called_once_with(
            'hw.tasks.send_billing_task', self.invoice.pk, '628111222333', 'halo', True,
        )

    @patch('hw.views.billing_views.async_task')
    def test_send_to_client_group(self, mock_task):
        resp = self._post({'pk': self.invoice.pk, 'message': 'halo', 'target_kind': 'client_group'})
        self.assertTrue(resp.json()['ok'])
        mock_task.assert_called_once_with(
            'hw.tasks.send_billing_task', self.invoice.pk, '120363abc@g.us', 'halo', False,
        )

    @patch('hw.views.billing_views.async_task')
    def test_send_to_manual_target(self, mock_task):
        resp = self._post({
            'pk': self.invoice.pk, 'message': 'halo',
            'target_kind': 'manual', 'manual_target': '628999888777',
        })
        self.assertTrue(resp.json()['ok'])
        mock_task.assert_called_once_with(
            'hw.tasks.send_billing_task', self.invoice.pk, '628999888777', 'halo', False,
        )

    @patch('hw.views.billing_views.async_task')
    def test_send_resolves_client_from_linked_cls(self, mock_task):
        # Endpoint juga harus memakai client hasil resolve via CL, bukan hanya FK langsung.
        invoice = _make_invoice(invoice_number='INV-EP-CL1')
        ConfirmationLetter.objects.create(
            company='konoz', hotel_name='Hilton', guest_name='Ahmad',
            confirmation_number='CL-EP-1', invoice=invoice, client=self.wa_client,
        )
        resp = self._post({'pk': invoice.pk, 'message': 'halo', 'target_kind': 'client_wa'})
        self.assertTrue(resp.json()['ok'])
        mock_task.assert_called_once_with(
            'hw.tasks.send_billing_task', invoice.pk, '628111222333', 'halo', False,
        )

    @patch('hw.views.billing_views.async_task')
    def test_client_without_wa_errors(self, mock_task):
        self.wa_client.wa = ''
        self.wa_client.save()
        resp = self._post({'pk': self.invoice.pk, 'message': 'halo', 'target_kind': 'client_wa'})
        data = resp.json()
        self.assertFalse(data['ok'])
        self.assertIn('message', data)
        mock_task.assert_not_called()

    @patch('hw.views.billing_views.async_task')
    def test_invoice_without_client_errors_on_client_kind(self, mock_task):
        orphan = _make_invoice(invoice_number='INV-EP-002')
        resp = self._post({'pk': orphan.pk, 'message': 'halo', 'target_kind': 'client_wa'})
        self.assertFalse(resp.json()['ok'])
        mock_task.assert_not_called()

    @patch('hw.views.billing_views.async_task')
    def test_manual_without_target_errors(self, mock_task):
        resp = self._post({'pk': self.invoice.pk, 'message': 'halo', 'target_kind': 'manual', 'manual_target': '  '})
        self.assertFalse(resp.json()['ok'])
        mock_task.assert_not_called()

    @patch('hw.views.billing_views.async_task')
    def test_empty_message_errors(self, mock_task):
        resp = self._post({'pk': self.invoice.pk, 'message': '   ', 'target_kind': 'client_wa'})
        self.assertFalse(resp.json()['ok'])
        mock_task.assert_not_called()

    @patch('hw.views.billing_views.async_task')
    def test_other_company_invoice_is_404(self, mock_task):
        other = _make_invoice(invoice_number='INV-EP-003', company='ijabah')
        resp = self._post({'pk': other.pk, 'message': 'halo', 'target_kind': 'manual', 'manual_target': '628'})
        self.assertEqual(resp.status_code, 404)
        mock_task.assert_not_called()

    @patch('hw.views.billing_views.async_task')
    def test_invalid_body_is_400(self, mock_task):
        resp = self.client.post('/billing/send/', 'bukan json', content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        mock_task.assert_not_called()


class DetailBillingPropsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('staff2', password='pw12345')
        self.client.force_login(self.user)
        s = self.client.session; s['active_company'] = 'konoz'; s.save()
        self.wa_client = Client.objects.create(
            company='konoz', name='Travel Amanah', wa='628111222333', wa_group='',
        )

    def test_invoice_detail_has_wa_send_and_last_billing(self):
        invoice = _make_invoice(invoice_number='INV-PR-001')
        ConfirmationLetter.objects.create(
            company='konoz', hotel_name='Hilton', guest_name='Ahmad',
            confirmation_number='CL-PR-001', invoice=invoice, client=self.wa_client,
        )
        BillingLog.objects.create(
            invoice=invoice, target='628111222333', message='m', status='SENT',
        )
        resp = self.client.get(f'/invoice/{invoice.pk}/', HTTP_X_INERTIA='true')
        props = resp.json()['props']
        self.assertEqual(props['wa_send'], {
            'client_name': 'Travel Amanah', 'client_wa': '628111222333',
            'has_wa': True, 'has_group': False,
        })
        self.assertEqual(props['last_billing']['target'], '628111222333')
        self.assertEqual(props['last_billing']['status'], 'SENT')
        self.assertIn('sent_at', props['last_billing'])

    def test_invoice_detail_without_client_or_logs(self):
        invoice = _make_invoice(invoice_number='INV-PR-002')
        resp = self.client.get(f'/invoice/{invoice.pk}/', HTTP_X_INERTIA='true')
        props = resp.json()['props']
        self.assertEqual(props['wa_send'], {
            'client_name': None, 'client_wa': '',
            'has_wa': False, 'has_group': False,
        })
        self.assertIsNone(props['last_billing'])

    def test_invoice_detail_resolves_client_from_linked_cls(self):
        # Invoice tanpa client FK langsung, tapi CL yang terhubung punya client.
        invoice = _make_invoice(invoice_number='INV-PR-CL1')
        ConfirmationLetter.objects.create(
            company='konoz', hotel_name='Hilton', guest_name='Ahmad',
            confirmation_number='CL-BP-1', invoice=invoice, client=self.wa_client,
        )
        ConfirmationLetter.objects.create(
            company='konoz', hotel_name='Hilton', guest_name='Budi',
            confirmation_number='CL-BP-2', invoice=invoice, client=self.wa_client,
        )
        resp = self.client.get(f'/invoice/{invoice.pk}/', HTTP_X_INERTIA='true')
        props = resp.json()['props']
        self.assertEqual(props['wa_send']['client_name'], 'Travel Amanah')
        self.assertTrue(props['wa_send']['has_wa'])

    def test_invoice_detail_ambiguous_cl_clients_stays_manual(self):
        # Dua CL menunjuk client berbeda → tidak ada client default.
        other = Client.objects.create(company='konoz', name='Travel Lain', wa='628444555666')
        invoice = _make_invoice(invoice_number='INV-PR-CL2')
        ConfirmationLetter.objects.create(
            company='konoz', hotel_name='Hilton', guest_name='Ahmad',
            confirmation_number='CL-BP-3', invoice=invoice, client=self.wa_client,
        )
        ConfirmationLetter.objects.create(
            company='konoz', hotel_name='Hilton', guest_name='Budi',
            confirmation_number='CL-BP-4', invoice=invoice, client=other,
        )
        resp = self.client.get(f'/invoice/{invoice.pk}/', HTTP_X_INERTIA='true')
        props = resp.json()['props']
        self.assertIsNone(props['wa_send']['client_name'])
        self.assertFalse(props['wa_send']['has_wa'])

    def test_services_detail_has_wa_send_and_last_billing(self):
        invoice = _make_invoice(invoice_number='INV-PR-003', invoice_type='visa')
        ConfirmationLetter.objects.create(
            company='konoz', hotel_name='Hilton', guest_name='Ahmad',
            confirmation_number='CL-PR-003', invoice=invoice, client=self.wa_client,
        )
        resp = self.client.get(f'/services/{invoice.pk}/', HTTP_X_INERTIA='true')
        props = resp.json()['props']
        self.assertTrue(props['wa_send']['has_wa'])
        self.assertIsNone(props['last_billing'])


class BillingMessageTemplateTest(TestCase):
    def _hotel_invoice(self, **kwargs):
        inv = _make_invoice(**kwargs)
        Reservation.objects.create(
            invoice=inv, reservation_number='R-100', hotel='Hilton Makkah', total_sar=10000,
        )
        Reservation.objects.create(
            invoice=inv, reservation_number='R-101', hotel='Movenpick Madinah', total_sar=5000,
        )
        return inv

    def test_hotel_unpaid_multi_rsv(self):
        inv = self._hotel_invoice(
            invoice_number='INV-TM-001',
            due_date=date.today() + timedelta(days=10),
        )
        msg = generate_draft_message('invoice', inv)
        self.assertIn('Assalamualaikum Wr Wb team Test Customer,', msg)
        self.assertIn('Invoice INV-TM-001 Anda telah diterbitkan.', msg)
        self.assertIn('- RSV : R-100\n  Hotel: Hilton Makkah', msg)
        self.assertIn('- RSV : R-101\n  Hotel: Movenpick Madinah', msg)
        self.assertIn('Total: 15.000 SAR', msg)
        self.assertIn('Terbayar: 0 SAR', msg)
        self.assertIn('Sisa: 15.000 SAR', msg)
        self.assertIn('Mohon lakukan pembayaran sebelum jatuh tempo.', msg)
        self.assertIn('Informasi Pembayaran:', msg)
        self.assertIn('Nama Bank : Mandiri', msg)
        self.assertIn('No. Rekening : 1400550111117', msg)
        self.assertIn('Atas Nama : Konoz Almotaheda Indonesia', msg)
        self.assertIn('Terima kasih,\n*Konoz United Surabaya*', msg)

    def test_hotel_due_date_bold_and_indonesian_month(self):
        # Far-future date: a hardcoded near date rots once the real clock
        # passes it and the message flips to the "lewat jatuh tempo" branch.
        inv = self._hotel_invoice(invoice_number='INV-TM-002', due_date=date(2099, 8, 15))
        msg = generate_draft_message('invoice', inv)
        self.assertIn('*Jatuh Tempo: 15 Agu 2099*\nMohon lakukan pembayaran', msg)

    def test_hotel_overdue(self):
        inv = self._hotel_invoice(
            invoice_number='INV-TM-003',
            due_date=date.today() - timedelta(days=14),
        )
        msg = generate_draft_message('invoice', inv)
        self.assertIn('Sudah lewat jatuh tempo (14 hari). Mohon segera lakukan pembayaran.', msg)

    def test_hotel_without_due_date(self):
        inv = self._hotel_invoice(invoice_number='INV-TM-004')
        msg = generate_draft_message('invoice', inv)
        self.assertNotIn('Jatuh Tempo', msg)
        self.assertNotIn('Mohon', msg)

    def test_hotel_lunas(self):
        inv = self._hotel_invoice(
            invoice_number='INV-TM-005',
            due_date=date.today() - timedelta(days=3),
        )
        msg = generate_draft_message('invoice_lunas', inv)
        self.assertIn('Pembayaran Invoice INV-TM-005 telah kami terima. Invoice Anda telah *LUNAS*.', msg)
        self.assertIn('Terbayar: 15.000 SAR', msg)
        self.assertIn('Sisa: 0 SAR', msg)
        self.assertNotIn('Jatuh Tempo', msg)
        self.assertNotIn('Informasi Pembayaran', msg)

    def test_services_lines_and_currency(self):
        inv = _make_invoice(
            invoice_number='INV-TM-006', invoice_type='visa', currency='USD',
        )
        ServiceItem.objects.create(invoice=inv, service_number=1, name='Visa Umroh', qty=10, price=100)
        ServiceItem.objects.create(invoice=inv, service_number=2, name='Handling', qty=10, price=50)
        msg = generate_draft_message('services', inv)
        self.assertIn('- Layanan: Visa Umroh x10', msg)
        self.assertIn('- Layanan: Handling x10', msg)
        self.assertIn('Total: 1.500 USD', msg)
        self.assertIn('Sisa: 1.500 USD', msg)

    def test_client_name_resolved_via_cl(self):
        wa_client = Client.objects.create(company='konoz', name='Travel Amanah', wa='628111')
        inv = self._hotel_invoice(invoice_number='INV-TM-007')
        ConfirmationLetter.objects.create(
            company='konoz', hotel_name='Hilton', guest_name='Ahmad',
            confirmation_number='CL-TM-1', invoice=inv, client=wa_client,
        )
        msg = generate_draft_message('invoice', inv)
        self.assertIn('team Travel Amanah,', msg)

    def test_signature_follows_company(self):
        inv = self._hotel_invoice(invoice_number='INV-TM-008', company='ijabah')
        msg = generate_draft_message('invoice', inv)
        self.assertIn('Terima kasih,\n*Ijabah*', msg)
        self.assertNotIn('Informasi Pembayaran', msg)


class SendWaFileTest(TestCase):
    @patch('hw.services.fonnte.requests.post')
    def test_sends_multipart_with_caption(self, mock_post):
        from hw.services.fonnte import send_wa_file
        mock_post.return_value.json.return_value = {'status': True}
        result = send_wa_file('628123', 'caption tagihan', b'%PDF-fake', 'INV-001.pdf')
        self.assertTrue(result['status'])
        call = mock_post.call_args
        self.assertEqual(call.args[0], 'https://api.fonnte.com/send')
        self.assertEqual(call.kwargs['data']['target'], '628123')
        self.assertEqual(call.kwargs['data']['message'], 'caption tagihan')
        self.assertEqual(call.kwargs['files']['file'], ('INV-001.pdf', b'%PDF-fake', 'application/pdf'))

    @patch('hw.services.fonnte.requests.post')
    def test_connection_error_returns_clean_dict(self, mock_post):
        import requests as _req
        from hw.services.fonnte import send_wa_file
        mock_post.side_effect = _req.exceptions.ConnectionError('getaddrinfo failed')
        result = send_wa_file('628123', 'x', b'%PDF', 'a.pdf')
        self.assertFalse(result['status'])
        self.assertIn('Fonnte', result['reason'])
