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
    Charge, Allocation, CashMovement, ChargeReason,
)
from hw.models.period import FinancialPeriod
from hw.models.payment import PaymentRecord, PaymentLog
from hw.models.journal import JournalEntry, JournalLine, Account as LedgerAccount


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
        self._migrate_charges(dry_run)
        self._migrate_cash_movements(dry_run)

        self.stdout.write(self.style.SUCCESS('\nMigration complete!'))

    def _create_periods(self, dry_run):
        self.stdout.write('\n--- Creating Financial Periods ---')
        years = set()
        for inv in Invoice.objects.dates('created_at', 'year'):
            years.add(inv.year)
        for p in Payment.objects.filter(payment_date__isnull=False).dates('payment_date', 'year'):
            years.add(p.year)
        for c in CashMovement.objects.dates('date', 'year'):
            years.add(c.year)
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

    def _migrate_charges(self, dry_run):
        """Migrate existing Charges -> JournalEntries (charge type)."""
        self.stdout.write('\n--- Migrating Charges -> JournalEntries ---')
        count = 0

        for charge in Charge.objects.select_related('client', 'invoice', 'reservation', 'service_item', 'penalty').all():
            # Skip if already migrated (check by reference)
            exists = JournalEntry.objects.filter(
                reference_type='Charge', reference_id=charge.pk,
            ).exists()
            if exists:
                continue

            # Determine account based on reason
            if charge.reason == ChargeReason.CANCELLATION:
                debit_account = LedgerAccount.EXPENSE_PENALTY
            else:
                debit_account = LedgerAccount.INCOME_HOTEL

            # Get period
            try:
                period = FinancialPeriod.objects.filter(
                    date_from__lte=charge.date,
                    date_to__gte=charge.date,
                ).first()
                if not period:
                    period = FinancialPeriod.objects.first()
            except Exception:
                period = FinancialPeriod.objects.first()

            if not period:
                self.stdout.write(self.style.WARNING(f'  No period for {charge.date}, skipping'))
                continue

            # Build journal lines
            lines = [
                {
                    'account': debit_account,
                    'amount_sar': charge.amount_sar,
                    'client': charge.client,
                    'invoice': charge.invoice,
                    'reservation': charge.reservation,
                    'service_item': charge.service_item,
                    'penalty': charge.penalty,
                    'note': charge.description or charge.get_reason_display(),
                },
                {
                    'account': LedgerAccount.RECEIVABLE,
                    'amount_sar': -charge.amount_sar,
                    'client': charge.client,
                    'invoice': charge.invoice,
                    'reservation': charge.reservation,
                    'service_item': charge.service_item,
                    'penalty': charge.penalty,
                    'note': charge.description or charge.get_reason_display(),
                },
            ]

            if not dry_run:
                user = User.objects.first()
                JournalEntry.objects.create(
                    entry_number=JournalEntry.generate_number(),
                    entry_type=JournalEntry.TYPE_CHARGE,
                    description=charge.description or f'Charge: {charge.get_reason_display()}',
                    entry_date=charge.date,
                    reference_type='Charge',
                    reference_id=charge.pk,
                    period=period,
                    company=charge.company,
                    created_by=user,
                )
                entry = JournalEntry.objects.filter(reference_type='Charge', reference_id=charge.pk).first()
                for line_data in lines:
                    JournalLine.objects.create(
                        journal_entry=entry,
                        account=line_data['account'],
                        amount_sar=line_data['amount_sar'],
                        client=line_data['client'],
                        invoice=line_data['invoice'],
                        reservation=line_data['reservation'],
                        service_item=line_data['service_item'],
                        penalty=line_data['penalty'],
                        note=line_data['note'],
                    )

            count += 1
            self.stdout.write(
                f'  {"Would create" if dry_run else "Created"}: Charge #{charge.pk} '
                f'{charge.amount_sar} SAR -> JE'
            )

        self.stdout.write(f'  Total: {count} charges migrated')

    def _migrate_cash_movements(self, dry_run):
        """Migrate existing CashMovements -> JournalEntries (payment type)."""
        self.stdout.write('\n--- Migrating CashMovements -> JournalEntries ---')
        count = 0

        for mov in CashMovement.objects.select_related('client', 'invoice', 'reservation_label', 'service_item_label', 'penalty_label').all():
            # Skip if already migrated
            exists = JournalEntry.objects.filter(
                reference_type='CashMovement', reference_id=mov.pk,
            ).exists()
            if exists:
                continue

            # Determine accounts
            if mov.from_account == 'client' and mov.to_account in ('sby', 'pusat'):
                # Client payment → Cash in, Receivable down
                debit_account = LedgerAccount.CASH_SBY if mov.to_account == 'sby' else LedgerAccount.CASH_PUSAT
                credit_account = LedgerAccount.RECEIVABLE
            elif mov.from_account in ('sby', 'pusat') and mov.to_account == 'client':
                # Refund → Receivable up, Cash out
                debit_account = LedgerAccount.RECEIVABLE
                credit_account = LedgerAccount.CASH_SBY if mov.from_account == 'sby' else LedgerAccount.CASH_PUSAT
            elif mov.from_account == 'sby' and mov.to_account == 'pusat':
                # Transfer SBY → PUSAT
                debit_account = LedgerAccount.CASH_PUSAT
                credit_account = LedgerAccount.CASH_SBY
            elif mov.from_account == 'pusat' and mov.to_account == 'sby':
                # Transfer PUSAT → SBY
                debit_account = LedgerAccount.CASH_SBY
                credit_account = LedgerAccount.CASH_PUSAT
            else:
                self.stdout.write(self.style.WARNING(f'  Unknown movement type for #{mov.pk}, skipping'))
                continue

            # Get period
            try:
                period = FinancialPeriod.objects.filter(
                    date_from__lte=mov.date,
                    date_to__gte=mov.date,
                ).first()
                if not period:
                    period = FinancialPeriod.objects.first()
            except Exception:
                period = FinancialPeriod.objects.first()

            if not period:
                self.stdout.write(self.style.WARNING(f'  No period for {mov.date}, skipping'))
                continue

            # Determine note
            note = mov.note or f'{mov.get_from_account_display()} -> {mov.get_to_account_display()}'

            if not dry_run:
                user = User.objects.first()
                entry = JournalEntry.objects.create(
                    entry_number=JournalEntry.generate_number(),
                    entry_type=JournalEntry.TYPE_PAYMENT,
                    description=note,
                    entry_date=mov.date,
                    reference_type='CashMovement',
                    reference_id=mov.pk,
                    period=period,
                    company=mov.company,
                    created_by=user,
                )
                JournalLine.objects.create(
                    journal_entry=entry,
                    account=debit_account,
                    amount_sar=mov.amount_sar,
                    client=mov.client,
                    invoice=mov.invoice,
                    reservation=mov.reservation_label,
                    service_item=mov.service_item_label,
                    penalty=mov.penalty_label,
                    note=note,
                )
                JournalLine.objects.create(
                    journal_entry=entry,
                    account=credit_account,
                    amount_sar=-mov.amount_sar,
                    client=mov.client,
                    invoice=mov.invoice,
                    reservation=mov.reservation_label,
                    service_item=mov.service_item_label,
                    penalty=mov.penalty_label,
                    note=note,
                )

            count += 1
            self.stdout.write(
                f'  {"Would create" if dry_run else "Created"}: CashMovement #{mov.pk} '
                f'{mov.amount_sar} SAR -> JE'
            )

        self.stdout.write(f'  Total: {count} cash movements migrated')


def _sum_sar(qs):
    return sum(m.amount_sar for m in qs)
