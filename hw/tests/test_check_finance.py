"""check_finance — audit integritas jurnal (read-only), pra-cutover."""
from datetime import date
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from hw.finance import posting
from hw.finance_helpers import create_payment_record
from hw.models import Client, Invoice, Reservation
from hw.models.choices import Company
from hw.models.journal import JournalEntry, JournalLine
from hw.models.payment import PaymentRecord
from hw.models.period import FinancialPeriod


class CheckFinanceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("cf", password="x")
        FinancialPeriod.objects.create(
            name="2046", company=Company.KONOZ,
            date_from=date(2046, 1, 1), date_to=date(2046, 12, 31),
        )
        self.client_obj = Client.objects.create(company="konoz", name="PT Uji")
        self.invoice = Invoice.objects.create(
            company="konoz", invoice_type="hotel", invoice_number="INV-CF1",
            customer_name="PT Uji", client=self.client_obj, issued_date=date(2046, 1, 5),
        )
        self.res = Reservation.objects.create(
            invoice=self.invoice, reservation_number="R-CF1", total_sar=100000,
        )
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        pr = create_payment_record(
            invoice=self.invoice, client=self.client_obj, payment_date=date(2046, 2, 1),
            amount=60000, method="transfer", created_by=self.user, reservation=self.res,
        )
        posting.post_payment(pr, created_by=self.user)
        pr.status = PaymentRecord.STATUS_ALLOCATED
        pr.save(update_fields=["status"])

    def _run(self):
        out = StringIO()
        try:
            call_command("check_finance", "--company", "konoz", "--verbose", stdout=out, stderr=out)
            return 0, out.getvalue()
        except SystemExit as e:
            return int(e.code or 1), out.getvalue()

    def test_clean_journal_passes(self):
        code, output = self._run()
        self.assertEqual(code, 0, output)
        self.assertIn("Semua cek lolos", output)

    def test_stale_charge_is_flagged(self):
        # Ubah total invoice tanpa re-post charge → cek #5 harus gagal.
        self.res.total_sar = 120000
        self.res.save(update_fields=["total_sar"])
        code, output = self._run()
        self.assertEqual(code, 1)
        self.assertIn("charge basi", output)

    def test_unbalanced_entry_is_flagged(self):
        # Rusak satu baris jurnal langsung di DB (bypass AppendOnly via queryset).
        line = JournalLine.objects.filter(
            journal_entry__entry_type=JournalEntry.TYPE_PAYMENT, debit__gt=0,
        ).first()
        JournalLine.objects.filter(pk=line.pk).update(debit=line.debit + 999)
        code, output = self._run()
        self.assertEqual(code, 1)
        self.assertIn("Balance per entry", output)

    def test_payment_record_mismatch_is_flagged(self):
        # PaymentRecord confirmed tanpa jejak jurnal → cek #6 gagal.
        PaymentRecord.objects.create(
            payment_number="PAY-9999", invoice=self.invoice, client=self.client_obj,
            payment_date=date(2046, 3, 1), amount=5000, amount_sar=5000,
            method="cash", status=PaymentRecord.STATUS_CONFIRMED,
            company="konoz", created_by=self.user,
            period=FinancialPeriod.objects.get(company=Company.KONOZ),
        )
        code, output = self._run()
        self.assertEqual(code, 1)
        self.assertIn("PaymentRecord", output)
