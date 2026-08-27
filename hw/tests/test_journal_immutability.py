"""Fase 2 · Task 2.3 — journal append-only enforcement (app layer)."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import accounts as coa
from hw.finance.posting import post_entry
from hw.models.choices import Company
from hw.models.journal import ImmutableLedgerError, JournalEntry, JournalLine
from hw.models.period import FinancialPeriod


class JournalImmutabilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("fin", password="x")
        FinancialPeriod.objects.create(
            name="2041-01", company=Company.KONOZ,
            date_from=date(2041, 1, 1), date_to=date(2041, 1, 31),
        )
        self.entry = post_entry(
            entry_type=JournalEntry.TYPE_ADJUSTMENT, description="t",
            entry_date=date(2041, 1, 10),
            lines=[
                {"account": coa.CASH_SBY, "debit": 100, "credit": 0},
                {"account": coa.OPENING_EQUITY, "debit": 0, "credit": 100},
            ],
            created_by=self.user,
        )

    def test_entry_update_blocked(self):
        self.entry.description = "changed"
        with self.assertRaises(ImmutableLedgerError):
            self.entry.save()

    def test_entry_reloaded_update_blocked(self):
        e = JournalEntry.objects.get(pk=self.entry.pk)
        e.entry_hash = "x" * 64
        with self.assertRaises(ImmutableLedgerError):
            e.save()

    def test_entry_delete_blocked(self):
        with self.assertRaises(ImmutableLedgerError):
            self.entry.delete()

    def test_line_update_blocked(self):
        line = self.entry.lines.first()
        line.debit = 999
        with self.assertRaises(ImmutableLedgerError):
            line.save()

    def test_line_delete_blocked(self):
        with self.assertRaises(ImmutableLedgerError):
            self.entry.lines.first().delete()

    def test_fresh_insert_still_allowed(self):
        # setUp already posted one entry successfully; a second must also work
        e2 = post_entry(
            entry_type=JournalEntry.TYPE_ADJUSTMENT, description="t2",
            entry_date=date(2041, 1, 11),
            lines=[
                {"account": coa.CASH_SBY, "debit": 50, "credit": 0},
                {"account": coa.OPENING_EQUITY, "debit": 0, "credit": 50},
            ],
            created_by=self.user,
        )
        self.assertEqual(e2.seq, 2)
