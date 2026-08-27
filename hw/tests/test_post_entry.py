"""Fase 2 · Task 2.2/2.4/2.5 — post_entry() primitive."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import accounts as coa
from hw.finance.hashing import verify_chain
from hw.finance.posting import MissingDimensionError, post_entry, reverse_entry
from hw.finance_helpers import JournalImbalanceError, PeriodLockedError
from hw.models import Client
from hw.models.choices import Company
from hw.models.journal import JournalEntry, JournalLine
from hw.models.period import FinancialPeriod


class PostEntryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("fin", password="x")
        self.period = FinancialPeriod.objects.create(
            name="2040-01", company=Company.KONOZ,
            date_from=date(2040, 1, 1), date_to=date(2040, 1, 31),
        )
        self.client_obj = Client.objects.create(company="konoz", name="PT Uji")

    def _balanced(self, **kw):
        return post_entry(
            entry_type=JournalEntry.TYPE_ADJUSTMENT,
            description="t", entry_date=date(2040, 1, 10),
            lines=[
                {"account": coa.CASH_SBY, "debit": 100, "credit": 0},
                {"account": coa.OPENING_EQUITY, "debit": 0, "credit": 100},
            ],
            created_by=self.user, **kw,
        )

    def test_balanced_entry_persists_with_two_lines(self):
        e = self._balanced()
        self.assertEqual(e.lines.count(), 2)
        self.assertTrue(e.is_balanced)

    def test_imbalanced_rolls_back(self):
        with self.assertRaises(JournalImbalanceError):
            post_entry(
                entry_type=JournalEntry.TYPE_ADJUSTMENT, description="x",
                entry_date=date(2040, 1, 10),
                lines=[
                    {"account": coa.CASH_SBY, "debit": 100, "credit": 0},
                    {"account": coa.OPENING_EQUITY, "debit": 0, "credit": 90},
                ],
                created_by=self.user,
            )
        self.assertEqual(JournalEntry.objects.count(), 0)
        self.assertEqual(JournalLine.objects.count(), 0)

    def test_idempotency_key_returns_same_entry(self):
        a = self._balanced(idempotency_key="evt:1")
        b = self._balanced(idempotency_key="evt:1")
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(JournalEntry.objects.count(), 1)

    def test_seq_is_monotonic_per_company(self):
        a = self._balanced()
        b = self._balanced()
        self.assertEqual((a.seq, b.seq), (1, 2))

    def test_hash_chain_links_and_verifies(self):
        a = self._balanced()
        b = self._balanced()
        self.assertEqual(a.prev_hash, "")
        self.assertEqual(b.prev_hash, a.entry_hash)
        self.assertEqual(verify_chain(Company.KONOZ), [])

    def test_tamper_breaks_chain(self):
        self._balanced()
        e = self._balanced()
        JournalLine.objects.filter(journal_entry=e, debit__gt=0).update(debit=999, credit=0)
        problems = verify_chain(Company.KONOZ)
        self.assertTrue(any("tampered" in p or "hash" in p for p in problems))

    def test_closed_period_rejected(self):
        self.period.status = FinancialPeriod.STATUS_CLOSED
        self.period.save()
        with self.assertRaises(PeriodLockedError):
            self._balanced()

    def test_ar_line_without_client_rejected(self):
        with self.assertRaises(MissingDimensionError):
            post_entry(
                entry_type=JournalEntry.TYPE_CHARGE, description="charge",
                entry_date=date(2040, 1, 10),
                lines=[
                    {"account": coa.AR, "debit": 100, "credit": 0},
                    {"account": coa.INC_HOTEL, "debit": 0, "credit": 100},
                ],
                created_by=self.user,
            )

    def test_reverse_entry_flips_and_links(self):
        orig = post_entry(
            entry_type=JournalEntry.TYPE_CHARGE, description="charge",
            entry_date=date(2040, 1, 10),
            lines=[
                {"account": coa.AR, "debit": 100, "credit": 0, "client": self.client_obj},
                {"account": coa.INC_HOTEL, "debit": 0, "credit": 100},
            ],
            created_by=self.user,
        )
        rev = reverse_entry(orig, reversal_date=date(2040, 1, 12), created_by=self.user)
        self.assertTrue(rev.is_reversal)
        self.assertEqual(rev.reverses_id, orig.pk)
        ar_line = rev.lines.get(account_id=coa.AR)
        self.assertEqual((ar_line.debit, ar_line.credit), (0, 100))
        self.assertEqual(verify_chain(Company.KONOZ), [])
