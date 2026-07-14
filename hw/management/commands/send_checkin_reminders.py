from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand

from hw.models import ConfirmationLetter, ReminderLog
from hw.services.fonnte import send_wa
from hw.services.recap import (
    build_grouped_reminder_message, resolve_reminder_targets, resolve_guest_target, group_guests,
)


class Command(BaseCommand):
    help = 'Kirim WA reminder check-in ke tamu (H-1 dan Hari H)'

    def handle(self, *args, **options):
        if not settings.REMINDER_H1_H0_ENABLED:
            self.stdout.write('Reminder H-1/H-0 dinonaktifkan sementara (settings.REMINDER_H1_H0_ENABLED=False)')
            return
        today = date.today()
        self._send_reminders(today, 'H0_GUEST')
        self._send_reminders(today + timedelta(days=1), 'H1_GUEST')

    def _send_reminders(self, check_in_date, reminder_type):
        qs = (
            ConfirmationLetter.objects
            .filter(check_in=check_in_date)
            .exclude(reservation_status='CANCELLED')
            .select_related('client')
            .prefetch_related('rooms')
        )
        by_client = {}
        no_client = []
        for cl in qs:
            if cl.client_id is None:
                no_client.append(cl)
            else:
                by_client.setdefault(cl.client_id, []).append(cl)

        for cls in by_client.values():
            self._send_client_group(cls, reminder_type)
        for cls in group_guests(no_client).values():
            self._send_guest_group(cls, reminder_type)

    def _already_sent(self, cl, reminder_type):
        return ReminderLog.objects.filter(
            cl=cl, reminder_type=reminder_type,
            status='SENT', sent_at__date=date.today(),
        ).exists()

    def _dispatch(self, pending, reminder_type, targets, message, label):
        for channel, phone in targets:
            try:
                result = send_wa(phone, message)
                status = 'SENT' if result.get('status') else 'FAILED'
                error  = result.get('reason', '') if not result.get('status') else ''
            except Exception as exc:
                status, error = 'FAILED', str(exc)
            for cl in pending:
                ReminderLog.objects.create(
                    cl=cl, reminder_type=reminder_type,
                    phone=phone, status=status, error=error,
                )
            self.stdout.write(f'  [{reminder_type}] {label} ({channel}) -> {status} ({len(pending)} booking)')

    def _send_client_group(self, cls, reminder_type):
        client = cls[0].client
        pending = [cl for cl in cls if not self._already_sent(cl, reminder_type)]
        if not pending:
            self.stdout.write(f'  SKIP {client.name}: already sent')
            return
        targets = resolve_reminder_targets(client, pending)
        if not targets:
            self.stdout.write(f'  SKIP {client.name}: no WA number configured')
            return
        message = build_grouped_reminder_message(pending, reminder_type, recipient_name=client.name)
        self._dispatch(pending, reminder_type, targets, message, client.name)

    def _send_guest_group(self, cls, reminder_type):
        guest_name = cls[0].guest_name
        pending = [cl for cl in cls if not self._already_sent(cl, reminder_type)]
        if not pending:
            self.stdout.write(f'  SKIP {guest_name}: already sent')
            return
        # Resolve from the whole group, not just pending: the phone may live on
        # a sibling booking that was already sent (blank-phone retry case).
        targets = resolve_guest_target(cls)
        if not targets:
            for cl in pending:
                self.stdout.write(f'  SKIP {cl.confirmation_number}: no phone')
            return
        message = build_grouped_reminder_message(pending, reminder_type, recipient_name=guest_name)
        self._dispatch(pending, reminder_type, targets, message, guest_name)
