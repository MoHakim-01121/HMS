"""check_finance — audit integritas jurnal (read-only), pra-cutover."""
from datetime import date
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from hw.db_pg import user_triggers_disabled
from hw.finance import posting
from hw.finance_helpers import create_payment_record
from hw.models import Client
from hw.models.journal import JournalEntry, JournalLine
from hw.models.payment import PaymentRecord
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_hotel_line, make_invoice, make_payment, set_line_total


class CheckFinanceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("cf", password="x")
        FinancialPeriod.objects.create(
            name="2046",            date_from=date(2046, 1, 1), date_to=date(2046, 12, 31),
        )
        self.client_obj = Client.objects.create( name="PT Uji")
        self.invoice = make_invoice(
 invoice_type="hotel", invoice_number="INV-CF1",
            customer_name="PT Uji", client=self.client_obj, issued_date=date(2046, 1, 5),
        )
        self.res = make_hotel_line(
            invoice=self.invoice, reservation_number="R-CF1", total_sar=100000,
        )
        posting.post_invoice_charge(self.invoice, created_by=self.user)
        pr = create_payment_record(
            invoice=self.invoice, client=self.client_obj, payment_date=date(2046, 2, 1),
            amount=60000, method="transfer", created_by=self.user, reservation=self.res,
        )
        posting.post_payment(pr, created_by=self.user)
        pr.status = PaymentRecord.STATUS_CONFIRMED
        pr.save(update_fields=["status"])

    def _run(self):
        out = StringIO()
        try:
            call_command("check_finance", "--verbose", stdout=out, stderr=out)
            return 0, out.getvalue()
        except SystemExit as e:
            return int(e.code or 1), out.getvalue()

    def test_clean_journal_passes(self):
        code, output = self._run()
        self.assertEqual(code, 0, output)
        self.assertIn("Semua cek lolos", output)

    def test_stale_charge_is_flagged(self):
        # Ubah total invoice tanpa re-post charge → cek #5 harus gagal.
        self.res = set_line_total(self.res, 120000)
        code, output = self._run()
        self.assertEqual(code, 1)
        self.assertIn("charge basi", output)

    def test_unbalanced_entry_is_flagged(self):
        # Rusak satu baris jurnal langsung di DB (bypass AppendOnly via queryset;
        # di PostgreSQL trigger append-only harus dimatikan dulu, seperti orang
        # yang punya akses pemilik tabel).
        line = JournalLine.objects.filter(
            journal_entry__entry_type=JournalEntry.TYPE_PAYMENT, debit__gt=0,
        ).first()
        with user_triggers_disabled('hw_journalline'):
            JournalLine.objects.filter(pk=line.pk).update(debit=line.debit + 999)
        code, output = self._run()
        self.assertEqual(code, 1)
        self.assertIn("Balance per entry", output)

    def test_payment_record_mismatch_is_flagged(self):
        # PaymentRecord confirmed tanpa jejak jurnal → cek #6 gagal.
        make_payment(
            payment_number="PAY-9999", invoice=self.invoice, client=self.client_obj,
            payment_date=date(2046, 3, 1), amount=5000, amount_sar=5000,
            method="cash", status=PaymentRecord.STATUS_CONFIRMED,
 created_by=self.user,
            period=FinancialPeriod.objects.get(),
        )
        code, output = self._run()
        self.assertEqual(code, 1)
        self.assertIn("PaymentRecord", output)
