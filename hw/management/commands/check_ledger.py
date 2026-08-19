"""Consistency audit for the Charge/Allocation/CashMovement ledger.

Run after every phase of the remittance ledger redesign. Exits non-zero if
any check fails, so it can be wired into CI later.

Checks:
1. Reservation.total_sar (cache) matches the sum of that reservation's Charges.
2. The four derived-money identities from the design doc hold for every
   company that has ledger activity.
"""
from django.core.management.base import BaseCommand

from hw.models import Reservation, ServiceItem, CancellationPenalty, Client, Charge, Allocation, CashMovement, Account
from hw import ledger


class Command(BaseCommand):
    help = __doc__

    def handle(self, *args, **options):
        problems = []
        problems += self._check_reservation_cache()
        problems += self._check_identities()

        if problems:
            self.stdout.write(self.style.ERROR(f'{len(problems)} problem(s) found:'))
            for p in problems:
                self.stdout.write(self.style.ERROR(f'  {p}'))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS('Ledger consistent: no problems found.'))

    def _check_reservation_cache(self):
        problems = []
        for r in Reservation.objects.all():
            expected = ledger.tagihan(r)
            if r.total_sar != expected:
                problems.append(
                    f"Reservation {r.reservation_number} (id={r.id}): total_sar cache={r.total_sar} "
                    f"tapi Sum Charge={expected}"
                )
        return problems

    def _check_identities(self):
        problems = []
        companies = set(Charge.objects.values_list('company', flat=True)) \
            | set(Allocation.objects.values_list('company', flat=True)) \
            | set(CashMovement.objects.values_list('company', flat=True))

        for company in companies:
            kas_sby = ledger.kas_surabaya(company)
            kas_pusat = ledger.kas_pusat(company)
            fx = ledger.selisih_kurs(company)
            client_in = sum(
                m.amount_sar for m in CashMovement.objects.filter(company=company, from_account=Account.CLIENT)
            )
            client_out = sum(
                m.amount_sar for m in CashMovement.objects.filter(company=company, to_account=Account.CLIENT)
            )
            if kas_sby + kas_pusat + fx != client_in - client_out:
                problems.append(
                    f"[{company}] kas_sby+kas_pusat+fx ({kas_sby + kas_pusat + fx}) != "
                    f"client_in-client_out ({client_in - client_out})"
                )

            clients = Client.objects.filter(company=company)
            total_saldo_dana = sum(ledger.saldo_dana(c) for c in clients)
            total_alloc = sum(a.amount_sar for a in Allocation.objects.filter(company=company))
            if total_saldo_dana != kas_sby + kas_pusat + fx - total_alloc:
                problems.append(
                    f"[{company}] Sum saldo_dana ({total_saldo_dana}) != "
                    f"kas_sby+kas_pusat+fx-Sum_alloc ({kas_sby + kas_pusat + fx - total_alloc})"
                )

            labeled_reservations = Reservation.objects.filter(
                pk__in=CashMovement.objects.filter(company=company, reservation_label__isnull=False)
                .values_list('reservation_label', flat=True).distinct()
            )
            labeled_service_items = ServiceItem.objects.filter(
                pk__in=CashMovement.objects.filter(company=company, service_item_label__isnull=False)
                .values_list('service_item_label', flat=True).distinct()
            )
            labeled_penalties = CancellationPenalty.objects.filter(
                pk__in=CashMovement.objects.filter(company=company, penalty_label__isnull=False)
                .values_list('penalty_label', flat=True).distinct()
            )
            total_mengendap = (
                sum(ledger.mengendap_per_res(r) for r in labeled_reservations)
                + sum(ledger.mengendap_per_service_item(s) for s in labeled_service_items)
                + sum(ledger.mengendap_per_penalty(p) for p in labeled_penalties)
            )
            if total_mengendap != kas_sby:
                problems.append(f"[{company}] Sum mengendap (res+service) ({total_mengendap}) != kas_surabaya ({kas_sby})")

            kewajiban = ledger.kewajiban_kirim_sby(company)
            if kewajiban != kas_sby - total_saldo_dana:
                problems.append(
                    f"[{company}] kewajiban_kirim_sby ({kewajiban}) != kas_sby-Sum_saldo_dana ({kas_sby - total_saldo_dana})"
                )

        return problems
