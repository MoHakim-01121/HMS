from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from hw.models import (
    Client, ConfirmationLetter, Invoice, Reservation, Payment, Remittance, RemittanceLine,
    Charge, Allocation, CashMovement,
)


class MigrateToLedgerTest(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(company='konoz', name='PT Migrasi')
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-MIG-001', customer_name='PT Migrasi', issued_date='2026-01-01',
        )
        # Invoice has no client FK of its own -- client is resolved via the
        # linked ConfirmationLetter, same as in production (_billing_client).
        ConfirmationLetter.objects.create(
            company='konoz', confirmation_number='CL-MIG-001', guest_name='PT Migrasi',
            client=self.client_obj, invoice=self.invoice,
        )
        self.res = Reservation.objects.create(invoice=self.invoice, reservation_number='R1', total_sar=10000)
        Payment.objects.create(
            invoice=self.invoice, linked_number='R1', payment_date='2026-01-02',
            method='cash', amount=6000, currency='SAR', exchange_rate=1,
        )
        rem = Remittance.objects.create(company='konoz', date='2026-01-05', status='received')
        RemittanceLine.objects.create(remittance=rem, invoice=self.invoice, linked_number='R1', amount_sar=4000)

    def _run(self, commit=False):
        out = StringIO()
        try:
            call_command('migrate_to_ledger', commit=commit, stdout=out)
        except SystemExit:
            pass
        return out.getvalue()

    def test_dry_run_writes_nothing(self):
        self._run(commit=False)
        self.assertEqual(Charge.objects.count(), 0)
        self.assertEqual(Allocation.objects.count(), 0)
        self.assertEqual(CashMovement.objects.count(), 0)

    def test_commit_creates_expected_rows_and_matches_source_totals(self):
        self._run(commit=True)

        self.assertEqual(Charge.objects.count(), 1)
        charge = Charge.objects.get()
        self.assertEqual(charge.amount_sar, 10000)
        self.assertEqual(charge.client, self.client_obj)
        self.assertEqual(charge.reservation, self.res)

        # satu Payment (cash) -> satu CashMovement CLIENT->SBY + satu Allocation
        self.assertEqual(CashMovement.objects.filter(from_account='client', to_account='sby').count(), 1)
        self.assertEqual(Allocation.objects.filter(reason='initial').count(), 1)

        # satu RemittanceLine -> satu CashMovement SBY->PUSAT
        self.assertEqual(CashMovement.objects.filter(from_account='sby', to_account='pusat').count(), 1)

        from hw import ledger
        self.assertEqual(ledger.tagihan(self.res), 10000)
        self.assertEqual(ledger.terbayar(self.res), 6000)
        self.assertEqual(ledger.kas_surabaya('konoz'), 2000)   # 6000 in - 4000 sent
        self.assertEqual(ledger.kas_pusat('konoz'), 4000)

    def test_commit_reports_success_in_output(self):
        output = self._run(commit=True)
        self.assertIn('verified', output)

    def test_running_twice_is_idempotent(self):
        self._run(commit=True)
        first_counts = (Charge.objects.count(), Allocation.objects.count(), CashMovement.objects.count())
        self._run(commit=True)
        second_counts = (Charge.objects.count(), Allocation.objects.count(), CashMovement.objects.count())
        self.assertEqual(first_counts, second_counts)

    def test_unresolvable_client_still_migrates_with_null_client(self):
        orphan_invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-MIG-ORPHAN', customer_name='Tanpa Client', issued_date='2026-01-01',
        )
        Reservation.objects.create(invoice=orphan_invoice, reservation_number='RO1', total_sar=5000)
        self._run(commit=True)
        orphan_charge = Charge.objects.get(invoice=orphan_invoice)
        self.assertIsNone(orphan_charge.client)
        self.assertEqual(orphan_charge.amount_sar, 5000)
