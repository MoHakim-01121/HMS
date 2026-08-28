"""backfill_legacy_journal: bangun jurnal dari tabel lama, balance & idempoten."""
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase

from hw.finance import accounts as coa
from hw.models import Client, Invoice, Payment, Reservation
from hw.models.journal import JournalEntry, JournalLine


def _net(**f):
    agg = JournalLine.objects.filter(**f).aggregate(d=Sum("debit"), c=Sum("credit"))
    return (agg["d"] or 0) - (agg["c"] or 0)


class BackfillLegacyJournalTest(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(company="konoz", name="PT Uji")
        self.invoice = Invoice.objects.create(
            company="konoz", invoice_type="hotel", invoice_number="INV-BF-1",
            customer_name="PT Uji", client=self.client_obj, issued_date=date(2024, 3, 1),
        )
        Reservation.objects.create(
            invoice=self.invoice, reservation_number="R-BF-1", total_sar=100000,
        )
        Payment.objects.create(
            invoice=self.invoice, linked_number="R-BF-1", payment_date=date(2024, 3, 10),
            method="cash", amount=40000, currency="SAR", exchange_rate=1,
        )

    def _run(self, commit):
        out = StringIO()
        call_command("backfill_legacy_journal", *(["--commit"] if commit else []), stdout=out)
        return out.getvalue()

    def test_dry_run_writes_nothing(self):
        self._run(commit=False)
        self.assertEqual(JournalEntry.objects.count(), 0)

    def test_commit_builds_balanced_journal(self):
        self._run(commit=True)

        # Setiap entry balance, dan total debit == total credit.
        agg = JournalLine.objects.aggregate(d=Sum("debit"), c=Sum("credit"))
        self.assertEqual(agg["d"], agg["c"])
        self.assertTrue(all(e.is_balanced for e in JournalEntry.objects.all()))

        # Charge 100k: DR Piutang / CR Pendapatan. Payment 40k: DR Kas SBY / CR Piutang.
        self.assertEqual(_net(account_id=coa.AR, client_id=self.client_obj.pk), 60000)
        self.assertEqual(_net(account_id=coa.CASH_SBY), 40000)
        self.assertEqual(_net(account_id=coa.INC_HOTEL), -100000)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.total_paid_sar, 40000)

    def test_commit_is_idempotent(self):
        self._run(commit=True)
        entries = JournalEntry.objects.count()
        lines = JournalLine.objects.count()

        self._run(commit=True)
        self.assertEqual(JournalEntry.objects.count(), entries)
        self.assertEqual(JournalLine.objects.count(), lines)

    def test_dry_run_payment_count_matches_commit(self):
        # B3: validasi yang menentukan skip (mis. tanggal tak resolve) jalan di
        # dry-run juga, jadi angka preview == angka commit.
        no_date_invoice = Invoice.objects.create(
            company="konoz", invoice_type="hotel", invoice_number="INV-BF-2",
            customer_name="PT Uji", client=self.client_obj, issued_date=None,
        )
        Payment.objects.create(
            invoice=no_date_invoice, linked_number="x", payment_date=None,
            method="cash", amount=5000, currency="SAR", exchange_rate=1,
        )
        dry = self._run(commit=False)
        self.assertIn("payment", dry.lower())
        self.assertIn("tanpa tanggal", dry)

        from hw.models import PaymentRecord
        self._run(commit=True)
        # 1 pembayaran valid → 1 PaymentRecord; yang tanpa tanggal di-skip
        self.assertEqual(
            PaymentRecord.objects.filter(reference__startswith="backfill:").count(), 1
        )
