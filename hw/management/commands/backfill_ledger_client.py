"""Backfill client on Charge/Allocation/CashMovement rows left NULL by the
invoice_new/invoice_edit CL-linking order bug (fixed in invoice_views.py:
ConfirmationLetter used to get linked to the invoice AFTER _save_reservations/
_save_hotel_payments already resolved and wrote client=None via
_billing_client). This command only fills in what _billing_client would have
resolved at write time -- it does not touch amount_sar or any other field, so
check_ledger's identities are unaffected.

Default is --dry-run (report only, no writes). Pass --commit to write.
Only fills rows that are unambiguous: exactly one distinct, non-null client
among the invoice's linked ConfirmationLetters. Everything else (no CL linked,
CL has no client, or multiple different clients) is reported separately and
left untouched for manual review.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from hw.models import Allocation, CashMovement, Charge, Invoice
from hw.views.invoice_billing import _billing_client

LEDGER_MODELS = [
    ('Charge', Charge),
    ('Allocation', Allocation),
    ('CashMovement', CashMovement),
]


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument(
            '--commit', action='store_true',
            help='Actually write the resolved client. Without this flag, runs as a dry-run report only.',
        )

    def handle(self, *args, **options):
        commit = options['commit']

        affected_invoice_ids = set()
        for _, model in LEDGER_MODELS:
            affected_invoice_ids |= set(
                model.objects.filter(client__isnull=True, invoice__isnull=False)
                .values_list('invoice_id', flat=True).distinct()
            )

        resolvable = []      # (invoice, client)
        no_cl_linked = []
        cl_without_client = []
        ambiguous = []

        for invoice in Invoice.objects.filter(pk__in=affected_invoice_ids).order_by('invoice_number'):
            client = _billing_client(invoice)
            if client is not None:
                resolvable.append((invoice, client))
                continue
            cls = list(invoice.confirmation_letters.all())
            if not cls:
                no_cl_linked.append(invoice)
            elif all(cl.client_id is None for cl in cls):
                cl_without_client.append(invoice)
            else:
                ambiguous.append(invoice)

        self._print_report(resolvable, no_cl_linked, cl_without_client, ambiguous)

        if not commit:
            self.stdout.write(self.style.WARNING('\nDry-run only -- no rows written. Pass --commit to write.'))
            return

        with transaction.atomic():
            totals = {name: 0 for name, _ in LEDGER_MODELS}
            for invoice, client in resolvable:
                for name, model in LEDGER_MODELS:
                    n = model.objects.filter(invoice=invoice, client__isnull=True).update(client=client)
                    if n:
                        totals[name] += n
                        self.stdout.write(f'  {invoice.invoice_number}: {n} {name} row(s) -> client={client.name}')

        self.stdout.write(self.style.SUCCESS(
            f'\nCommitted: {sum(totals.values())} row(s) updated '
            f'({", ".join(f"{v} {k}" for k, v in totals.items())}).'
        ))
        self.stdout.write(self.style.WARNING('Run `manage.py check_ledger` to confirm invariants still hold.'))

    def _print_report(self, resolvable, no_cl_linked, cl_without_client, ambiguous):
        total_rows = sum(
            model.objects.filter(client__isnull=True, invoice__isnull=False).count()
            for _, model in LEDGER_MODELS
        )
        self.stdout.write(f'Ledger rows with client=NULL but invoice set: {total_rows}')
        self.stdout.write(f'Invoices affected: {len(resolvable) + len(no_cl_linked) + len(cl_without_client) + len(ambiguous)}')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Resolvable (single unambiguous client): {len(resolvable)}'))
        for invoice, client in resolvable[:20]:
            self.stdout.write(f'  {invoice.invoice_number} -> {client.name}')
        if len(resolvable) > 20:
            self.stdout.write(f'  ... and {len(resolvable) - 20} more')

        self.stdout.write('')
        self.stdout.write(self.style.WARNING(f'No CL linked to invoice (unresolvable): {len(no_cl_linked)}'))
        for invoice in no_cl_linked[:10]:
            self.stdout.write(f'  {invoice.invoice_number}')
        if len(no_cl_linked) > 10:
            self.stdout.write(f'  ... and {len(no_cl_linked) - 10} more')

        self.stdout.write('')
        self.stdout.write(self.style.WARNING(f'Linked CL(s) have no client set (unresolvable): {len(cl_without_client)}'))
        for invoice in cl_without_client[:10]:
            self.stdout.write(f'  {invoice.invoice_number}')
        if len(cl_without_client) > 10:
            self.stdout.write(f'  ... and {len(cl_without_client) - 10} more')

        self.stdout.write('')
        self.stdout.write(self.style.ERROR(f'Ambiguous -- multiple different clients among linked CLs: {len(ambiguous)}'))
        for invoice in ambiguous:
            self.stdout.write(f'  {invoice.invoice_number} (needs manual review)')
