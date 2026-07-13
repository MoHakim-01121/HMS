from unittest.mock import patch
from django.test import TestCase
from hw.models import RecapLog, ReminderLog


class SendRecapTaskTest(TestCase):
    @patch('hw.tasks.send_wa')
    def test_creates_sent_log_on_success(self, mock_send):
        from hw.tasks import send_recap_task
        mock_send.return_value = {'status': True}
        send_recap_task('PHONE', '628111', 'Tim Ops', 'pesan rekap', 3)
        log = RecapLog.objects.get(target='628111')
        self.assertEqual(log.status, 'SENT')
        self.assertEqual(log.cl_count, 3)
        self.assertEqual(log.triggered_by, 'MANUAL')

    @patch('hw.tasks.send_wa')
    def test_creates_failed_log_on_failure(self, mock_send):
        from hw.tasks import send_recap_task
        mock_send.return_value = {'status': False, 'reason': 'invalid token'}
        send_recap_task('PHONE', '628111', 'Tim Ops', 'pesan rekap', 3)
        log = RecapLog.objects.get(target='628111')
        self.assertEqual(log.status, 'FAILED')
        self.assertEqual(log.error, 'invalid token')


class SendReminderTaskTest(TestCase):
    @patch('hw.tasks.send_wa')
    def test_creates_sent_log_on_success(self, mock_send):
        from hw.tasks import send_reminder_task
        from datetime import date
        from hw.models import ConfirmationLetter
        cl = ConfirmationLetter.objects.create(
            company='konoz', confirmation_number='CL-TASK1', guest_name='Ahmad',
            check_in=date.today(),
        )
        mock_send.return_value = {'status': True}
        send_reminder_task(cl.pk, 'H0_GUEST', '628999', 'pesan reminder')
        log = ReminderLog.objects.get(cl=cl)
        self.assertEqual(log.status, 'SENT')
        self.assertEqual(log.phone, '628999')


class SendReminderGroupTaskTest(TestCase):
    @patch('hw.tasks.send_wa')
    def test_creates_one_log_per_cl_on_success(self, mock_send):
        from hw.tasks import send_reminder_group_task
        from datetime import date
        from hw.models import ConfirmationLetter
        cl1 = ConfirmationLetter.objects.create(
            company='konoz', confirmation_number='CL-GT1', guest_name='Ahmad', check_in=date.today(),
        )
        cl2 = ConfirmationLetter.objects.create(
            company='konoz', confirmation_number='CL-GT2', guest_name='Budi', check_in=date.today(),
        )
        mock_send.return_value = {'status': True}
        send_reminder_group_task([cl1.pk, cl2.pk], 'H0_GUEST', '628999', 'pesan gabungan')
        self.assertEqual(mock_send.call_count, 1)
        logs = ReminderLog.objects.filter(cl__in=[cl1, cl2])
        self.assertEqual(logs.count(), 2)
        self.assertTrue(all(l.status == 'SENT' and l.phone == '628999' for l in logs))

    @patch('hw.tasks.send_wa')
    def test_creates_failed_logs_on_failure(self, mock_send):
        from hw.tasks import send_reminder_group_task
        from datetime import date
        from hw.models import ConfirmationLetter
        cl = ConfirmationLetter.objects.create(
            company='konoz', confirmation_number='CL-GT3', guest_name='Cici', check_in=date.today(),
        )
        mock_send.return_value = {'status': False, 'reason': 'invalid token'}
        send_reminder_group_task([cl.pk], 'H1_GUEST', '628999', 'pesan gabungan')
        log = ReminderLog.objects.get(cl=cl)
        self.assertEqual(log.status, 'FAILED')
        self.assertEqual(log.error, 'invalid token')
