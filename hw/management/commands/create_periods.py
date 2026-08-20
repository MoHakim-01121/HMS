"""Create financial periods for the current and next year.

Usage:
    python manage.py create_periods
    python manage.py create_periods --year 2026
"""
from datetime import date
from dateutil.relativedelta import relativedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from hw.models.period import FinancialPeriod


class Command(BaseCommand):
    help = 'Create monthly financial periods for a given year'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year', type=int, default=timezone.now().year,
            help='Year to create periods for (default: current year)',
        )
        parser.add_argument(
            '--months', type=int, default=12,
            help='Number of months to create (default: 12)',
        )

    def handle(self, *args, **options):
        year = options['year']
        months = options['months']

        created = 0
        skipped = 0

        for m in range(1, months + 1):
            date_from = date(year, m, 1)
            if m == 12:
                date_to = date(year + 1, 1, 1) - relativedelta(days=1)
            else:
                date_to = date(year, m + 1, 1) - relativedelta(days=1)

            name = f"{year}-{m:02d}"

            _, was_created = FinancialPeriod.objects.get_or_create(
                name=name,
                defaults={
                    'date_from': date_from,
                    'date_to': date_to,
                },
            )

            if was_created:
                created += 1
                self.stdout.write(f"  Created: {name} ({date_from} → {date_to})")
            else:
                skipped += 1
                self.stdout.write(f"  Exists:  {name}")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone: {created} created, {skipped} already exist"
        ))
