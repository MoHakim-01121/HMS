"""Kelebihan bayar invoice -> deposit lewat pembayaran yang membayarnya, supaya
alokasi pembayaran (detail pembayaran, kwitansi) tetap sama dengan buku besar.
Juga: perintah reconcile_allocations untuk data lama, dan cek check_finance."""
from datetime import date
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from hw.finance import accounts as coa
from hw.finance import posting
from hw.finance_helpers import confirm_payment, create_payment_record
from hw.management.commands.check_finance import Command as CheckFinance
from hw.models import Client
from hw.models.period import FinancialPeriod
from hw.tests.factories import ensure_current_period, make_hotel_line, make_invoice, set_line_total


class _Base(TestCase):
    def setUp(self):
        self.maker = User.objects.create_user('ex_maker', password='pw12345')
        self.checker = User.objects.create_user('ex_checker', password='pw12345')
        FinancialPeriod.objects.create(name='2026-08', date_from=date(2026, 8, 1), date_to=date(2026, 8, 31))
        ensure_current_period()
        self.client_obj = Client.objects.create(name='PT Excess')
        self.inv = make_invoice(invoice_type='hotel', client=self.client_obj, invoice_number='INV-EX-1',
                                issued_date=date(2026, 8, 5))
        self.r1 = make_hotel_line(invoice=self.inv, reservation_number='EX-1', total_sar=15000)
        self.r2 = make_hotel_line(invoice=self.inv, reservation_number='EX-2', total_sar=5000)
        posting.post_invoice_charge(self.inv, created_by=self.maker)

    def _pay(self, allocations, day=10):
        amount = sum(a for _, a in allocations)
        payment = create_payment_record(
            invoice=self.inv, client=self.client_obj, payment_date=date(2026, 8, day),
            amount=amount, method='Transfer', created_by=self.maker,
        )
        posting.allocate_payment(payment, allocations, created_by=self.maker)
        confirm_payment(payment, confirmed_by=self.checker)
        payment.refresh_from_db()
        return payment

    def _amend(self, line, total):
        line = set_line_total(line, total)
        posting.post_invoice_charge(self.inv, created_by=self.maker)
        return line

    def _line_findings(self):
        return CheckFinance()._allocation_line_mismatch()

    def _allocs(self, payment):
        return dict(payment.allocations.values_list('invoice_line_id', 'amount_sar'))


class InvoiceExcessThroughPaymentsTest(_Base):
    def test_moving_the_excess_reduces_the_paying_allocation(self):
        payment = self._pay([(self.r1, 15000)])
        self._amend(self.r1, 13000)

        moved = posting.move_invoice_excess_to_deposit(self.inv, created_by=self.maker)

        payment.refresh_from_db()
        self.assertEqual(moved, 2000)
        self.assertEqual(self._allocs(payment), {self.r1.pk: 13000})
        self.assertEqual((payment.deposited_sar, payment.unallocated_sar), (2000, 0))
        self.assertEqual(posting.client_credit_balance(self.client_obj.pk), 2000)
        self.assertEqual(self._line_findings(), [])
        self.assertEqual(CheckFinance()._payment_record_mismatch(), [])

    def test_one_payment_over_two_overpaid_lines_is_reallocated_once(self):
        payment = self._pay([(self.r1, 15000), (self.r2, 5000)])
        self._amend(self.r1, 14000)
        self._amend(self.r2, 4000)

        posting.move_invoice_excess_to_deposit(self.inv, created_by=self.maker)

        payment.refresh_from_db()
        self.assertEqual(self._allocs(payment), {self.r1.pk: 14000, self.r2.pk: 4000})
        self.assertEqual(payment.deposited_sar, 2000)
        self.assertEqual(self._line_findings(), [])

    def test_the_newest_payment_gives_back_first(self):
        older = self._pay([(self.r1, 10000)], day=10)
        newer = self._pay([(self.r1, 5000)], day=20)
        self._amend(self.r1, 13000)

        posting.move_invoice_excess_to_deposit(self.inv, created_by=self.maker)

        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertEqual((self._allocs(older), older.deposited_sar), ({self.r1.pk: 10000}, 0))
        self.assertEqual((self._allocs(newer), newer.deposited_sar), ({self.r1.pk: 3000}, 2000))


class ReconcileOldExcessMovesTest(_Base):
    def _old_style_move(self, line, amount):
        """What "Pindahkan ke deposit" posted before the fix: journal only."""
        posting.post_entry(
            entry_type='transfer', description=f'Kelebihan bayar {self.inv.invoice_number} → deposit client',
            entry_date=date(2026, 8, 25),
            lines=[
                {"account": coa.AR, "debit": amount, "client": self.client_obj.pk, "invoice": self.inv.pk,
                 "invoice_line": line.pk},
                {"account": coa.CUST_CREDIT, "credit": amount, "client": self.client_obj.pk, "invoice": self.inv.pk},
            ],
            source_type='Invoice', source_id=self.inv.pk, created_by=self.maker,
        )

    def test_reconcile_moves_the_old_excess_through_the_payment(self):
        payment = self._pay([(self.r1, 15000)])
        self._amend(self.r1, 13000)
        self._old_style_move(self.r1, 2000)
        self.assertEqual(len(self._line_findings()), 1)

        out = StringIO()
        call_command('reconcile_allocations', stdout=out)        # dry run writes nothing
        self.assertIn('1 entry akan diperbaiki', out.getvalue())
        self.assertEqual(len(self._line_findings()), 1)

        call_command('reconcile_allocations', '--apply', '--user', 'ex_maker', stdout=StringIO())
        payment.refresh_from_db()
        self.assertEqual(self._allocs(payment), {self.r1.pk: 13000})
        self.assertEqual(payment.deposited_sar, 2000)
        self.assertEqual(posting.client_credit_balance(self.client_obj.pk), 2000)
        self.assertEqual(self._line_findings(), [])

        out = StringIO()
        call_command('reconcile_allocations', stdout=out)        # idempotent
        self.assertIn('Tidak ada yang perlu diperbaiki', out.getvalue())


class CrossInvoiceCheckTest(_Base):
    def test_a_payment_split_across_invoices_is_not_a_finding(self):
        other = make_invoice(invoice_type='hotel', client=self.client_obj, invoice_number='INV-EX-2',
                             issued_date=date(2026, 8, 6))
        r3 = make_hotel_line(invoice=other, reservation_number='EX-3', total_sar=2000)
        posting.post_invoice_charge(other, created_by=self.maker)
        payment = self._pay([(self.r1, 15000)])
        self._amend(self.r1, 13000)
        posting.reallocate_payment(payment, [(self.r1, 13000), (r3, 2000)], created_by=self.maker)
        self.assertEqual(CheckFinance()._payment_record_mismatch(), [])
        self.assertEqual(self._line_findings(), [])
