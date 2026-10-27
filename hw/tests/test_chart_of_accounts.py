"""Fase 1 · Task 1.1 — Chart of Accounts (LedgerAccount) + seed."""
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from hw.finance.accounts import ACCOUNTS, seed_chart_of_accounts
from hw.models.journal import AccountType, LedgerAccount


class ChartOfAccountsSeedTests(TestCase):
    def test_seed_creates_every_account(self):
        seed_chart_of_accounts()
        self.assertEqual(LedgerAccount.objects.count(), len(ACCOUNTS))

    def test_seed_is_idempotent(self):
        seed_chart_of_accounts()
        seed_chart_of_accounts()
        self.assertEqual(LedgerAccount.objects.count(), len(ACCOUNTS))

    def test_command_seeds(self):
        call_command("seed_chart_of_accounts")
        self.assertEqual(LedgerAccount.objects.count(), len(ACCOUNTS))

    def test_types_and_normal_balance(self):
        seed_chart_of_accounts()
        ar = LedgerAccount.objects.get(code="1100-AR")
        self.assertEqual(ar.type, AccountType.ASSET)
        self.assertEqual(ar.normal_balance, LedgerAccount.NORMAL_DEBIT)

        cust = LedgerAccount.objects.get(code="2100-CUST-CREDIT")
        self.assertEqual(cust.type, AccountType.LIABILITY)
        self.assertEqual(cust.normal_balance, LedgerAccount.NORMAL_CREDIT)

        inc = LedgerAccount.objects.get(code="4100-INC-HOTEL")
        self.assertEqual(inc.normal_balance, LedgerAccount.NORMAL_CREDIT)

        exp = LedgerAccount.objects.get(code="5100-EXP-BANKFEE")
        self.assertEqual(exp.normal_balance, LedgerAccount.NORMAL_DEBIT)

    def test_invalid_type_rejected_by_db(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LedgerAccount.objects.create(
                    code="9999-X", name="bogus", type="not-a-type",
                    normal_balance=LedgerAccount.NORMAL_DEBIT,
                )

    def test_all_seeded_accounts_postable_by_default(self):
        # Except Retained Earnings: the trial balance computes it (virtual
        # year-end close), nothing posts to it.
        seed_chart_of_accounts()
        accounts = LedgerAccount.objects.all()
        self.assertTrue(all(a.is_active for a in accounts))
        self.assertEqual([a.code for a in accounts if not a.is_postable], ['3200-RETAINED'])
