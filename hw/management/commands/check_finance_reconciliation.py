"""Reconciliation audit between the legacy CashMovement ledger and the new
double-entry JournalLine ledger -- run before ever retiring the legacy
ledger (remittance-ledger-redesign Fase 7).

allocate_payment() mirrors every PaymentRecord allocation into
CashMovement (see hw/finance_helpers.py), and confirm_payment() posts the
same payment into JournalLine, so the two ledgers should agree on "how
much has been paid" for every invoice that has any PaymentRecord
activity. Invoices paid only through the invoice/services/CL/remittance/
penalty forms have no JournalLine activity at all (those views don't post
to the double-entry ledger), so this only compares invoices where both
ledgers have something to say -- it is not a full-database audit.

This only reports; it never writes. Run it against a copy of production
data before deciding whether to retire the legacy ledger.
"""
from django.core.management.base import BaseCommand

from hw.finance_helpers import invoice_paid_sar_jl
from hw.models import Invoice
from hw.models.journal import JournalLine


class Command(BaseCommand):
    help = __doc__

    def handle(self, *args, **options):
        invoice_ids = set(
            JournalLine.objects.filter(invoice__isnull=False)
            .values_list('invoice_id', flat=True).distinct()
        )

        problems = []
        for invoice in Invoice.objects.filter(pk__in=invoice_ids):
            legacy_paid = invoice.total_paid_sar
            jl_paid = -invoice_paid_sar_jl(invoice.id)
            if legacy_paid != jl_paid:
                problems.append(
                    f"Invoice {invoice.invoice_number} (id={invoice.id}): "
                    f"CashMovement ledger paid={legacy_paid} SAR, "
                    f"JournalLine ledger paid={jl_paid} SAR"
                )

        if problems:
            self.stdout.write(self.style.ERROR(f'{len(problems)} invoice(s) disagree between ledgers:'))
            for p in problems:
                self.stdout.write(self.style.ERROR(f'  {p}'))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS(
            f'{len(invoice_ids)} invoice(s) with JournalLine activity checked -- both ledgers agree.'
        ))
