from datetime import date, timedelta

from django.core.management.base import BaseCommand

from hw.models import ConfirmationLetter, ReminderLog
from hw.services.fonnte import send_wa
from hw.services.recap import build_reminder_message


class Command(BaseCommand):
    help = 'Kirim WA reminder check-in ke tamu (H-1 dan Hari H)'

    def handle(self, *args, **options):
        today = date.today()
        self._send_reminders(today, 'H0_GUEST')
        self._send_reminders(today + timedelta(days=1), 'H1_GUEST')

    def _send_reminders(self, check_in_date, reminder_type):
        qs = (
            ConfirmationLetter.objects
            .filter(check_in=check_in_date)
            .exclude(reservation_status='CANCELLED')
            .prefetch_related('rooms')
        )
        for cl in qs:
            if not cl.guest_phone:
                self.stdout.write(f'  SKIP {cl.confirmation_number}: no phone')
                continue
            if ReminderLog.objects.filter(
                cl=cl, reminder_type=reminder_type,
                status='SENT', sent_at__date=date.today(),
            ).exists():
                self.stdout.write(f'  SKIP {cl.confirmation_number}: already sent')
                continue
            message = build_reminder_message(cl, reminder_type)
            try:
                result = send_wa(cl.guest_phone, message)
                status = 'SENT' if result.get('status') else 'FAILED'
                error  = result.get('reason', '') if not result.get('status') else ''
            except Exception as exc:
                status, error = 'FAILED', str(exc)
            ReminderLog.objects.create(
                cl=cl, reminder_type=reminder_type,
                phone=cl.guest_phone, status=status, error=error,
            )
            self.stdout.write(f'  [{reminder_type}] {cl.confirmation_number} -> {status}')
