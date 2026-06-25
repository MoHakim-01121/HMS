from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand

from hw.models import ConfirmationLetter, RecapLog
from hw.services.fonnte import send_wa
from hw.services.recap import build_recap_message


class Command(BaseCommand):
    help = 'Kirim rekap check-in hari ini ke tim operasional'

    def handle(self, *args, **options):
        today = date.today()
        cls = list(
            ConfirmationLetter.objects
            .filter(check_in=today)
            .exclude(reservation_status='CANCELLED')
            .prefetch_related('rooms')
            .order_by('hotel_name', 'guest_name')
        )
        if not cls:
            self.stdout.write('Tidak ada check-in hari ini.')
            return
        message = build_recap_message(cls, today)
        for target in settings.FONNTE_TEAM_TARGETS:
            target_type = 'GROUP' if len(target) < 10 or '-' in target else 'PHONE'
            try:
                result = send_wa(target, message)
                status = 'SENT' if result.get('status') else 'FAILED'
                error  = result.get('reason', '') if not result.get('status') else ''
            except Exception as exc:
                status, error = 'FAILED', str(exc)
            RecapLog.objects.create(
                target_type=target_type, target=target,
                cl_count=len(cls), message=message,
                status=status, triggered_by='AUTO', error=error,
            )
            self.stdout.write(f'  Recap -> {target}: {status}')
