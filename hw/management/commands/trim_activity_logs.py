from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from hw.models import ActivityLog


class Command(BaseCommand):
    help = 'Trim ActivityLog to the latest 50 entries per user.'

    def add_arguments(self, parser):
        parser.add_argument('--keep', type=int, default=50, help='Number of entries to keep per user')

    def handle(self, *args, **options):
        keep = options['keep']
        total_deleted = 0
        for user in User.objects.all():
            old_ids = list(
                ActivityLog.objects.filter(user=user)
                .order_by('-timestamp')
                .values_list('id', flat=True)[keep:]
            )
            if old_ids:
                deleted, _ = ActivityLog.objects.filter(id__in=old_ids).delete()
                total_deleted += deleted
        self.stdout.write(self.style.SUCCESS(f'Deleted {total_deleted} old log entries.'))
