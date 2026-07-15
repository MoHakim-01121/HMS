from django.contrib.auth.models import User
from django.test import TestCase
from unittest.mock import patch

from hw.models import BillingLog, Client, Invoice


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


class BillingSendEndpointTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('staff1', password='pw12345')
        self.client.force_login(self.user)
        s = self.client.session; s['active_company'] = 'konoz'; s.save()
        self.wa_client = Client.objects.create(
            company='konoz', name='Travel Amanah',
            wa='628111222333', wa_group='120363abc@g.us',
        )
        self.invoice = _make_invoice(invoice_number='INV-EP-001', client=self.wa_client)

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
            'hw.tasks.send_billing_task', self.invoice.pk, '628111222333', 'halo',
        )

    @patch('hw.views.billing_views.async_task')
    def test_send_to_client_group(self, mock_task):
        resp = self._post({'pk': self.invoice.pk, 'message': 'halo', 'target_kind': 'client_group'})
        self.assertTrue(resp.json()['ok'])
        mock_task.assert_called_once_with(
            'hw.tasks.send_billing_task', self.invoice.pk, '120363abc@g.us', 'halo',
        )

    @patch('hw.views.billing_views.async_task')
    def test_send_to_manual_target(self, mock_task):
        resp = self._post({
            'pk': self.invoice.pk, 'message': 'halo',
            'target_kind': 'manual', 'manual_target': '628999888777',
        })
        self.assertTrue(resp.json()['ok'])
        mock_task.assert_called_once_with(
            'hw.tasks.send_billing_task', self.invoice.pk, '628999888777', 'halo',
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
        invoice = _make_invoice(invoice_number='INV-PR-001', client=self.wa_client)
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

    def test_services_detail_has_wa_send_and_last_billing(self):
        invoice = _make_invoice(
            invoice_number='INV-PR-003', invoice_type='visa', client=self.wa_client,
        )
        resp = self.client.get(f'/services/{invoice.pk}/', HTTP_X_INERTIA='true')
        props = resp.json()['props']
        self.assertTrue(props['wa_send']['has_wa'])
        self.assertIsNone(props['last_billing'])
