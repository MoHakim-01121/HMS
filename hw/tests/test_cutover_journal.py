"""F11 — cutover_journal membukukan dokumen yang belum punya jurnal, sekali saja."""
from datetime import date
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from hw.finance import queries
from hw.models import PaymentAllocation, PaymentRecord
from hw.models.journal import JournalEntry
from hw.tests.factories import make_hotel_line, make_invoice, make_payment, set_line_total


def run(*args):
    out = StringIO()
    call_command('cutover_journal', *args, stdout=out)
    return out.getvalue()


class CutoverJournalTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('cut', password='x')
        self.invoice = make_invoice(issued_date=date(2026, 6, 1))
        self.line = make_hotel_line(self.invoice)
        set_line_total(self.line, 10_000)
        self.payment = make_payment(
            payment_number='PAY-L0001', payment_date=date(2026, 6, 5), amount=4_000, amount_sar=4_000,
            exchange_rate=1, method='Transfer', status=PaymentRecord.STATUS_CONFIRMED,
            client=self.invoice.client, invoice=self.invoice, created_by=self.user,
        )
        PaymentAllocation.objects.create(payment=self.payment, invoice_line=self.line, amount_sar=4_000)

    def test_dry_run_changes_nothing(self):
        before = JournalEntry.objects.count()
        out = run()
        self.assertIn('UJI COBA', out)
        self.assertEqual(JournalEntry.objects.count(), before)

    def test_commit_books_charge_and_payment_once(self):
        run('--commit')
        self.assertEqual(queries.invoice_paid_sar(self.invoice.pk), 4_000)
        self.assertTrue(JournalEntry.objects.for_source('PaymentRecord', self.payment.pk).exists())
        count = JournalEntry.objects.count()
        out = run('--commit')
        self.assertEqual(JournalEntry.objects.count(), count)
        self.assertIn('pembayaran 0', out)
        self.assertIn('semua cek lolos', out)

    def test_balance_adjustment_matches_the_real_balance_once(self):
        from hw.finance.bank_ledger import default_account
        cash = default_account('sby', 'SAR')
        run('--commit', '--tanggal', '2026-06-30', '--saldo', f'{cash.pk}=4500')
        self.assertEqual(queries.cash_balance('1000-KAS-SBY'), 4_500)
        out = run('--commit', '--tanggal', '2026-06-30', '--saldo', f'{cash.pk}=4500')
        self.assertIn('selisih 0', out)
        self.assertEqual(queries.cash_balance('1000-KAS-SBY'), 4_500)
