"""Regression tests for FinancialPeriod.close()/.lock().

Covers the bug where close()/lock() referenced JournalEntry.STATUS_POSTED
and a `status` field that do not exist on JournalEntry, and filtered on
total_debit/total_credit (Python @property, not queryable DB fields) —
any call crashed with AttributeError/FieldError instead of the intended
ValueError, and hw.views.period_views only catches ValueError. This left
period locking (the immutability guarantee for the finance system of
record) completely non-functional, with no test coverage.
"""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance_helpers import create_journal_entry
from hw.models.journal import Account, JournalEntry, JournalLine
from hw.models.period import FinancialPeriod


class FinancialPeriodCloseLockTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('fin_ops', password='pw12345')
        self.period = FinancialPeriod.objects.create(
            name='2099-01', date_from=date(2099, 1, 1), date_to=date(2099, 1, 31),
        )

    def test_close_succeeds_when_all_entries_balanced(self):
        create_journal_entry(
            entry_type=JournalEntry.TYPE_ADJUSTMENT,
            description='balanced entry',
            entry_date=date(2099, 1, 15),
            lines=[
                {'account': Account.CASH_SBY, 'amount_sar': 100},
                {'account': Account.EQUITY, 'amount_sar': -100},
            ],
            created_by=self.user,
        )

        self.period.close(self.user)

        self.period.refresh_from_db()
        self.assertEqual(self.period.status, FinancialPeriod.STATUS_CLOSED)
        self.assertEqual(self.period.closed_by, self.user)
        self.assertIsNotNone(self.period.closed_at)

    def test_close_rejects_unbalanced_entry(self):
        entry = JournalEntry.objects.create(
            entry_number='JE-TEST-UNBAL', entry_type=JournalEntry.TYPE_ADJUSTMENT,
            description='unbalanced', entry_date=date(2099, 1, 15),
            period=self.period, created_by=self.user,
        )
        JournalLine.objects.create(journal_entry=entry, account=Account.CASH_SBY, amount_sar=50)

        with self.assertRaises(ValueError):
            self.period.close(self.user)

        self.period.refresh_from_db()
        self.assertEqual(self.period.status, FinancialPeriod.STATUS_OPEN)

    def test_lock_requires_closed_status(self):
        with self.assertRaises(ValueError):
            self.period.lock(self.user)

    def test_lock_succeeds_after_close(self):
        self.period.close(self.user)

        self.period.lock(self.user)

        self.period.refresh_from_db()
        self.assertEqual(self.period.status, FinancialPeriod.STATUS_LOCKED)
        self.assertEqual(self.period.locked_by, self.user)
        self.assertIsNotNone(self.period.locked_at)

    def test_lock_rejects_pending_payments(self):
        from hw.finance_helpers import create_payment_record
        from hw.models import Client, Invoice

        client = Client.objects.create(company='konoz', name='Test Client')
        invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel', invoice_number='INV-LOCK-1',
            customer_name='Test Client', issued_date=date(2099, 1, 1),
        )
        create_payment_record(
            invoice=invoice, client=client, payment_date=date(2099, 1, 10),
            amount=100, method='transfer', created_by=self.user,
        )
        self.period.close(self.user)

        with self.assertRaises(ValueError):
            self.period.lock(self.user)
