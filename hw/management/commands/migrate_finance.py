"""Migrate existing finance data to the new double-entry system.

Usage:
    python manage.py migrate_finance --dry-run
    python manage.py migrate_finance --run
"""
from datetime import date, datetime

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from hw.models import (
    Invoice, Payment, CancellationPenalty, Reservation, ServiceItem,
    Charge, Allocation, CashMovement,
)
from hw.models.period import FinancialPeriod
from hw.models.payment import PaymentRecord, PaymentLog
from hw.models.journal import JournalEntry, JournalLine, Account as LedgerAccount
from hw.utils import convert_to_sar


class Command(BaseCommand):
    help = 'Migrate existing finance data to the new double-entry system'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--run', action='store_true')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        run = options['run']

        if not dry_run and not run:
            self.stdout.write(self.style.WARNING('Use --dry-run or --run'))
            return

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write('FINANCE DATA MIGRATION')
        self.stdout.write('=' * 60)

        self._create_periods(dry_run)
        self._migrate_invoices(dry_run)
        self._migrate_penalties(dry_run)

        self.stdout.write(self.style.SUCCESS('\nMigration complete!'))

    def _create_periods(self, dry_run):
        self.stdout.write('\n--- Creating Financial Periods ---')
        years = set()
        for inv in Invoice.objects.dates('created_at', 'year'):
            years.add(inv.year)
        for p in Payment.objects.filter(payment_date__isnull=False).dates('payment_date', 'year'):
            years.add(p.year)
        if not years:
            years.add(date.today().year)

        for year in sorted(years):
            for m in range(1, 13):
                date_from = date(year, m, 1)
                if m == 12:
                    date_to = date(year + 1, 1, 1)
                else:
                    date_to = date(year, m + 1, 1)
                name = f'{year}-{m:02d}'
                exists = FinancialPeriod.objects.filter(name=name).exists()
                if not exists and not dry_run:
                    FinancialPeriod.objects.create(name=name, date_from=date_from, date_to=date_to)
                    self.stdout.write(f'  Created: {name}')
                elif not exists:
                    self.stdout.write(f'  Would create: {name}')

    def _migrate_invoices(self, dry_run):
        self.stdout.write('\n--- Migrating Invoices ---')
        for inv in Invoice.objects.all():
            cl = inv.confirmation_letters.first()
            client = cl.client if cl and cl.client else None

            total_sar = sum(r.total_sar for r in inv.reservations.all())
            total_sar += sum(s.total for s in inv.service_items.all())

            paid_sar = _sum_sar(CashMovement.objects.filter(
                invoice=inv, from_account='client', penalty_label__isnull=True,
            ))

            if not dry_run:
                inv.client = client
                inv.total_sar = total_sar
                inv.paid_sar = paid_sar
                if paid_sar >= total_sar and total_sar > 0:
                    inv.status = Invoice.STATUS_PAID
                elif paid_sar > 0:
                    inv.status = Invoice.STATUS_PARTIAL
                inv.save(update_fields=['client', 'total_sar', 'paid_sar', 'status'])

            self.stdout.write(
                f'  {"Would update" if dry_run else "Updated"}: {inv.invoice_number} '
                f'client={client}, total={total_sar}, paid={paid_sar}'
            )

    def _migrate_penalties(self, dry_run):
        self.stdout.write('\n--- Migrating Penalties ---')
        for penalty in CancellationPenalty.objects.all():
            cl = penalty.cl
            client = cl.client if cl and cl.client else None
            invoice = cl.invoice if cl.invoice else None
            amount_sar = penalty.penalty_amount_sar

            if not dry_run:
                penalty.client = client
                penalty.invoice = invoice
                penalty.amount_sar = amount_sar
                penalty.save(update_fields=['client', 'invoice', 'amount_sar'])

            self.stdout.write(
                f'  {"Would update" if dry_run else "Updated"}: {penalty.penalty_number} '
                f'client={client}, amount_sar={amount_sar}'
            )


def _sum_sar(qs):
    return sum(m.amount_sar for m in qs)
