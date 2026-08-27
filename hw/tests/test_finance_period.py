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
from django.core.exceptions import ValidationError
from django.test import TestCase

from hw.finance_helpers import create_journal_entry
from hw.models.choices import Company
from hw.models.journal import Account, JournalEntry, JournalLine
from hw.models.period import FinancialPeriod


class FinancialPeriodOverlapTest(TestCase):
    """Fase 1 · Task 1.2 — periode tidak boleh tumpang tindih per company."""

    def test_overlapping_periods_same_company_rejected(self):
        FinancialPeriod.objects.create(
            name="2030-01", company=Company.KONOZ,
            date_from=date(2030, 1, 1), date_to=date(2030, 1, 31),
        )
        with self.assertRaises(ValidationError):
            FinancialPeriod.objects.create(
                name="2030-01b", company=Company.KONOZ,
                date_from=date(2030, 1, 15), date_to=date(2030, 2, 15),
            )

    def test_adjacent_periods_allowed(self):
        FinancialPeriod.objects.create(
            name="2031-01", company=Company.KONOZ,
            date_from=date(2031, 1, 1), date_to=date(2031, 1, 31),
        )
        FinancialPeriod.objects.create(
            name="2031-02", company=Company.KONOZ,
            date_from=date(2031, 2, 1), date_to=date(2031, 2, 28),
        )
        self.assertEqual(FinancialPeriod.objects.filter(name__startswith="2031").count(), 2)

    def test_overlap_across_companies_allowed(self):
        FinancialPeriod.objects.create(
            name="2032-01-konoz", company=Company.KONOZ,
            date_from=date(2032, 1, 1), date_to=date(2032, 1, 31),
        )
        FinancialPeriod.objects.create(
            name="2032-01-other", company="future_co",
            date_from=date(2032, 1, 1), date_to=date(2032, 1, 31),
        )
        self.assertEqual(FinancialPeriod.objects.filter(name__startswith="2032").count(), 2)

    def test_saving_same_period_again_does_not_self_conflict(self):
        p = FinancialPeriod.objects.create(
            name="2033-01", company=Company.KONOZ,
            date_from=date(2033, 1, 1), date_to=date(2033, 1, 31),
        )
        p.status = FinancialPeriod.STATUS_SOFT_CLOSE
        p.save()  # must not raise on its own row


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
