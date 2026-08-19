"""One-time bulk conversion of Payment/RemittanceLine/Reservation/ServiceItem/
CancellationPenalty into the Charge/Allocation/CashMovement ledger (Fase 2 of
the remittance ledger redesign).

Idempotent for its intended use window (before Fase 4 introduces other ledger
writers): a --commit run always deletes any existing Charge/Allocation/
CashMovement rows first, then rebuilds them fresh from the current source
data, inside one atomic transaction. Running it twice in a row converges to
the same state.

Default is --dry-run (report only, no writes). Pass --commit to write.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from hw.models import (
    Invoice, InvoiceType, Reservation, ServiceItem, Payment, CancellationPenalty,
    RemittanceLine, Charge, Allocation, CashMovement,
    ChargeReason, AllocationReason, Account,
)
from hw.views.invoice_billing import _billing_client
from hw import ledger

SURABAYA_METHODS = {'cash', 'bank transfer', 'deposit'}


def _resolve_payment_target(payment, reservations_by_number, service_items_by_number):
    """Match a Payment.linked_number to a Reservation (hotel invoices) or
    ServiceItem (visa invoices) within the same invoice. Returns (reservation,
    service_item), both None if unmatched."""
    invoice = payment.invoice
    linked = (payment.linked_number or '').strip()
    if not linked:
        return None, None
    if invoice.invoice_type == InvoiceType.HOTEL:
        res = reservations_by_number.get((invoice.id, linked))
        return res, None
    try:
        svc_no = int(linked)
    except (ValueError, TypeError):
        return None, None
    return None, service_items_by_number.get((invoice.id, svc_no))


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument(
            '--commit', action='store_true',
            help='Actually write the ledger rows. Without this flag, runs as a dry-run report only.',
        )

    def handle(self, *args, **options):
        commit = options['commit']
        report = self._build_report()
        self._print_report(report)

        if not commit:
            self.stdout.write(self.style.WARNING('\nDry-run only -- no rows written. Pass --commit to write.'))
            return

        with transaction.atomic():
            Allocation.objects.all().delete()
            Charge.objects.all().delete()
            CashMovement.objects.all().delete()
            self._write(report)

        mismatches = self._verify(report)
        if mismatches:
            self.stdout.write(self.style.ERROR('\nVerification FAILED -- rolling back is your responsibility (see mismatches above).'))
            for m in mismatches:
                self.stdout.write(self.style.ERROR(f'  {m}'))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS('\nMigration committed and verified: totals match exactly.'))

    # -- planning (no DB writes) -------------------------------------------------

    def _build_report(self):
        invoices = list(Invoice.objects.prefetch_related(
            'reservations', 'service_items', 'payments', 'confirmation_letters',
        ))

        client_by_invoice = {}
        unresolved_invoices = []
        for inv in invoices:
            c = _billing_client(inv)
            client_by_invoice[inv.id] = c
            if c is None:
                unresolved_invoices.append(inv)

        reservations_by_number = {
            (r.invoice_id, r.reservation_number): r
            for inv in invoices for r in inv.reservations.all()
        }
        service_items_by_number = {
            (s.invoice_id, s.service_number): s
            for inv in invoices for s in inv.service_items.all()
        }

        unmapped_payments = []
        for inv in invoices:
            for p in inv.payments.all():
                if not (p.linked_number or '').strip():
                    continue
                res, svc = _resolve_payment_target(p, reservations_by_number, service_items_by_number)
                if res is None and svc is None:
                    unmapped_payments.append(p)

        return {
            'invoices': invoices,
            'client_by_invoice': client_by_invoice,
            'unresolved_invoices': unresolved_invoices,
            'reservations_by_number': reservations_by_number,
            'service_items_by_number': service_items_by_number,
            'unmapped_payments': unmapped_payments,
        }

    def _print_report(self, report):
        self.stdout.write(f"Invoices: {len(report['invoices'])}")
        self.stdout.write(f"Invoices with no resolvable client: {len(report['unresolved_invoices'])}")
        for inv in report['unresolved_invoices']:
            self.stdout.write(f"  - {inv.invoice_number} ({inv.customer_name})")
        self.stdout.write(f"Payments with unmapped linked_number (become unattributed client cash): {len(report['unmapped_payments'])}")
        for p in report['unmapped_payments']:
            self.stdout.write(f"  - invoice {p.invoice.invoice_number}, linked_number={p.linked_number!r}, amount={p.amount} {p.currency}")

    # -- writing -------------------------------------------------------------

    def _write(self, report):
        client_by_invoice = report['client_by_invoice']
        reservations_by_number = report['reservations_by_number']
        service_items_by_number = report['service_items_by_number']

        for inv in report['invoices']:
            client = client_by_invoice[inv.id]
            base_date = inv.issued_date or inv.created_at.date()

            for r in inv.reservations.all():
                if r.total_sar:
                    Charge.objects.create(
                        company=inv.company, client=client, date=base_date,
                        amount_sar=r.total_sar, invoice=inv, reservation=r,
                        reason=ChargeReason.INITIAL, description=f'Migrasi: {r.reservation_number}',
                    )
            for s in inv.service_items.all():
                if s.total:
                    Charge.objects.create(
                        company=inv.company, client=client, date=base_date,
                        amount_sar=s.total, invoice=inv, service_item=s,
                        reason=ChargeReason.INITIAL, description=f'Migrasi: {s.name}',
                    )

            for p in inv.payments.all():
                date = p.payment_date or base_date
                res, svc = _resolve_payment_target(p, reservations_by_number, service_items_by_number)
                is_direct = (p.method or '').strip().lower() == 'direct'
                to_account = Account.PUSAT if is_direct else Account.SBY
                mov = CashMovement.objects.create(
                    company=inv.company, client=client, date=date, invoice=inv,
                    from_account=Account.CLIENT, to_account=to_account,
                    # int(round(...)) not int(p.amount): a handful of legacy Payment
                    # rows hold fractional amounts despite PositiveIntegerField
                    # (SQLite never enforced the column type) -- round explicitly
                    # to match Payment.amount_sar's own convention, rather than
                    # silently truncating on save.
                    amount=int(round(p.amount)), currency=p.currency, exchange_rate=p.exchange_rate,
                    method=p.method, reservation_label=res, service_item_label=svc,
                    note=f'Migrasi dari Payment #{p.id}',
                )
                if res is not None or svc is not None:
                    Allocation.objects.create(
                        company=inv.company, client=client, date=date,
                        amount_sar=mov.amount_sar, invoice=inv,
                        reservation=res, service_item=svc,
                        reason=AllocationReason.INITIAL, note=f'Migrasi dari Payment #{p.id}',
                    )
                # Unmapped: cash movement recorded (counts toward wallets), but no
                # Allocation -- the money becomes unattributed client balance,
                # exactly as spelled out in the plan for review-worthy rows.

        for cl in CancellationPenalty.objects.select_related('cl__invoice', 'cl__client'):
            invoice = cl.cl.invoice
            client = client_by_invoice.get(invoice.id) if invoice else (cl.cl.client)
            company = invoice.company if invoice else 'konoz'
            if cl.penalty_amount_sar:
                Charge.objects.create(
                    company=company, client=client, date=cl.cancellation_date,
                    amount_sar=cl.penalty_amount_sar, invoice=invoice, penalty=cl,
                    reason=ChargeReason.CANCELLATION, description=f'Migrasi: {cl.penalty_number}',
                )
                if cl.is_paid:
                    pay_date = cl.payment_date or cl.cancellation_date
                    is_direct = (cl.payment_method or '').strip().lower() == 'direct'
                    to_account = Account.PUSAT if is_direct else Account.SBY
                    mov = CashMovement.objects.create(
                        company=company, client=client, date=pay_date, invoice=invoice,
                        from_account=Account.CLIENT, to_account=to_account,
                        amount=cl.penalty_amount, currency=cl.penalty_currency, exchange_rate=cl.exchange_rate,
                        method=cl.payment_method, penalty_label=cl,
                        note=f'Migrasi: {cl.penalty_number} (lunas)',
                    )
                    Allocation.objects.create(
                        company=company, client=client, date=pay_date,
                        amount_sar=mov.amount_sar, invoice=invoice, penalty=cl,
                        reason=AllocationReason.CANCELLATION, note=f'Migrasi: {cl.penalty_number} (lunas)',
                    )

        for line in RemittanceLine.objects.select_related('remittance', 'invoice'):
            rem = line.remittance
            res = reservations_by_number.get((line.invoice_id, line.linked_number)) if line.invoice_id else None
            svc = None
            if res is None and line.invoice_id and line.invoice.invoice_type == InvoiceType.VISA:
                try:
                    svc = service_items_by_number.get((line.invoice_id, int(line.linked_number)))
                except (ValueError, TypeError):
                    svc = None
            client = client_by_invoice.get(line.invoice_id) if line.invoice_id else None
            CashMovement.objects.create(
                company=rem.company, client=client, date=rem.date, invoice_id=line.invoice_id,
                from_account=Account.SBY, to_account=Account.PUSAT,
                amount=line.amount_sar, currency='SAR', exchange_rate=1,
                remittance=rem, reservation_label=res, service_item_label=svc,
                note=f'Migrasi dari RemittanceLine #{line.id} ({rem.remittance_number})',
            )

    # -- verification ----------------------------------------------------------

    def _verify(self, report):
        """Compare source-derived totals against what actually landed in the
        ledger tables. Returns a list of human-readable mismatch descriptions
        (empty list = clean)."""
        mismatches = []
        client_by_invoice = report['client_by_invoice']

        old_charge_by_client = defaultdict(int)
        old_cash_in_by_client = defaultdict(int)
        for inv in report['invoices']:
            client = client_by_invoice[inv.id]
            for r in inv.reservations.all():
                old_charge_by_client[client] += r.total_sar
            for s in inv.service_items.all():
                old_charge_by_client[client] += s.total
            for p in inv.payments.all():
                old_cash_in_by_client[client] += p.amount_sar
        for cl in CancellationPenalty.objects.select_related('cl__invoice', 'cl__client'):
            invoice = cl.cl.invoice
            client = client_by_invoice.get(invoice.id) if invoice else cl.cl.client
            old_charge_by_client[client] += cl.penalty_amount_sar
            if cl.is_paid:
                # Penalty payments were never tracked as a Payment row in the
                # old system (CancellationPenalty has its own is_paid/method
                # fields, entirely outside the Payment table) -- but _write()
                # now converts them into a real CashMovement, so the "old"
                # baseline here must count them too or every paid penalty
                # would show up as a false Cash-in mismatch below.
                old_cash_in_by_client[client] += cl.penalty_amount_sar

        clients = set(old_charge_by_client) | set(old_cash_in_by_client)
        for client in clients:
            new_charge = sum(c.amount_sar for c in Charge.objects.filter(client=client))
            if new_charge != old_charge_by_client[client]:
                mismatches.append(
                    f"Charge client={client}: lama={old_charge_by_client[client]} baru={new_charge}"
                )
            new_cash_in = sum(
                m.amount_sar for m in CashMovement.objects.filter(client=client, from_account=Account.CLIENT)
            )
            if new_cash_in != old_cash_in_by_client[client]:
                mismatches.append(
                    f"Cash-in client={client}: lama={old_cash_in_by_client[client]} baru={new_cash_in}"
                )

        for company in ('konoz', 'ijabah'):
            old_terbayar_sby = sum(
                p.amount_sar for p in Payment.objects.filter(invoice__company=company)
                if (p.method or '').strip().lower() in SURABAYA_METHODS
            )
            old_terbayar_pusat = sum(
                p.amount_sar for p in Payment.objects.filter(invoice__company=company)
                if (p.method or '').strip().lower() == 'direct'
            )
            for cl in CancellationPenalty.objects.filter(is_paid=True).select_related('cl__invoice'):
                # Mirror _write()'s exact company fallback (invoice.company, or
                # 'konoz' when the penalty's CL has no linked invoice at all).
                cl_company = cl.cl.invoice.company if cl.cl.invoice else 'konoz'
                if cl_company != company:
                    continue
                if (cl.payment_method or '').strip().lower() == 'direct':
                    old_terbayar_pusat += cl.penalty_amount_sar
                else:
                    old_terbayar_sby += cl.penalty_amount_sar
            old_terkirim = sum(
                l.amount_sar for l in RemittanceLine.objects.filter(remittance__company=company)
            )
            old_kas_sby = old_terbayar_sby - old_terkirim
            old_kas_pusat = old_terkirim + old_terbayar_pusat

            new_kas_sby = ledger.kas_surabaya(company)
            new_kas_pusat = ledger.kas_pusat(company)
            if new_kas_sby != old_kas_sby:
                mismatches.append(f"kas_surabaya[{company}]: lama={old_kas_sby} baru={new_kas_sby}")
            if new_kas_pusat != old_kas_pusat:
                mismatches.append(f"kas_pusat[{company}]: lama={old_kas_pusat} baru={new_kas_pusat}")

        return mismatches
