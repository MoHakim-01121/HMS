"""FASE C — receiving_account + branch dimension threaded into journal lines."""
from datetime import date

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase

from hw.models import BankAccount, Branch, CashAccount, Client, Invoice, Reservation
from hw.models.journal import LedgerAccount
from hw.models.journal import JournalEntry, JournalLine
from hw.models.payment import PaymentRecord
from hw.models.period import FinancialPeriod
from hw.finance import posting
from hw.finance_helpers import create_payment_record, confirm_payment


class ReceivingAccountTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('fc', password='pw12345')
        FinancialPeriod.objects.create(
            name='2020-2030', company='konoz',
            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.client_obj = Client.objects.create(company='konoz', name='PT FaseC')
        self.inv = Invoice.objects.create(invoice_number='INV-FC-1', customer_name='PT FaseC',
                                          client=self.client_obj)
        self.res = Reservation.objects.create(
            invoice=self.inv, reservation_number='R1', total_sar=5000,
            owner_branch=Branch.objects.get(code='sby'),
        )

    def test_at_most_one_receiving_account(self):
        cash = CashAccount.objects.get(branch_id='sby')
        bank = BankAccount.objects.create(
            branch=Branch.objects.get(code='sby'), name='Ops', currency='SAR',
            ledger_account=LedgerAccount.objects.get(code='1000-KAS-SBY'),
            bank_name='BCA', account_identifier='1',
        )
        with self.assertRaises(IntegrityError):
            PaymentRecord.objects.create(
                payment_number='PAY-X', invoice=self.inv, client=self.client_obj,
                payment_date=date(2026, 1, 1), amount=1, amount_sar=1,
                method='Cash', status=PaymentRecord.STATUS_PENDING,
                company='konoz', created_by=self.user,
                period=FinancialPeriod.objects.first(),
                bank_account=bank, cash_account=cash,
            )

    def test_create_payment_record_derives_cash_account_from_received_in(self):
        pr = create_payment_record(
            self.inv, self.client_obj, date(2026, 1, 5), 3000,
            method='Transfer', received_in='jkt', created_by=self.user,
        )
        self.assertEqual(pr.cash_account.branch_id, 'jkt')
        self.assertEqual(pr.receiving_branch_code, 'jkt')

    def test_payment_journal_lines_carry_receiving_branch(self):
        pr = create_payment_record(
            self.inv, self.client_obj, date(2026, 1, 5), 3000,
            method='Transfer', received_in='jkt', created_by=self.user,
        )
        confirm_payment(pr, self.user)
        lines = JournalLine.objects.filter(
            journal_entry__entry_type=JournalEntry.TYPE_PAYMENT,
            journal_entry__reference_id=pr.pk,
        )
        self.assertTrue(lines.exists())
        self.assertTrue(all(l.branch_id == 'jkt' for l in lines))

    def test_charge_journal_lines_carry_owner_branch(self):
        posting.post_invoice_charge(self.inv, created_by=self.user, entry_date=date(2026, 1, 1))
        lines = JournalLine.objects.filter(
            journal_entry__entry_type=JournalEntry.TYPE_CHARGE,
            journal_entry__reference_id=self.inv.pk,
        )
        self.assertTrue(lines.exists())
        self.assertTrue(all(l.branch_id == 'sby' for l in lines))
