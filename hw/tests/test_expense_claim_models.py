"""Klaim penggantian operasional: model, akun antar kantor, sumber jurnal."""
from datetime import date

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

from hw.finance import accounts as coa
from hw.finance.posting import post_entry
from hw.models import ExpenseClaim, ExpenseClaimItem
from hw.models.journal import JournalEntry, LedgerAccount
from hw.models.period import FinancialPeriod
from hw.tests.factories import fund_account, make_account, paid_expense


class ExpenseClaimModelTest(TestCase):
    def setUp(self):
        FinancialPeriod.objects.create(name='2026', date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        self.user = User.objects.create_superuser('claim-model', password='pw12345')
        self.idr = make_account('sby', 'IDR')
        fund_account(self.idr, 9_500_000, 2_000, date(2026, 1, 1), self.user)
        self.expense, _payment = paid_expense(self.idr.branch, self.idr, 500_000, date(2026, 1, 5), self.user)

    def _claim(self):
        return ExpenseClaim.objects.create(
            claim_number=ExpenseClaim.generate_number(), branch_id='sby',
            date_from=date(2026, 1, 1), date_to=date(2026, 1, 31), created_by=self.user,
        )

    def test_one_active_claim_per_expense(self):
        first = ExpenseClaimItem.objects.create(claim=self._claim(), expense=self.expense, amount=500_000, amount_sar=105)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExpenseClaimItem.objects.create(claim=self._claim(), expense=self.expense, amount=500_000, amount_sar=105)
        first.is_active = False
        first.save(update_fields=['is_active'])
        ExpenseClaimItem.objects.create(claim=self._claim(), expense=self.expense, amount=500_000, amount_sar=105)

    def test_ho_account_seeded(self):
        self.assertEqual(LedgerAccount.objects.get(code=coa.HO_PUSAT).type, 'equity')

    def test_journal_entry_accepts_claim_source(self):
        claim = self._claim()
        post_entry(
            entry_type=JournalEntry.TYPE_REIMBURSEMENT, description='test', entry_date=date(2026, 2, 1),
            lines=[{'account': self.idr.ledger_account_id, 'debit': 105, 'branch': 'sby'},
                   {'account': coa.HO_PUSAT, 'credit': 105, 'branch': 'sby'}],
            source_type='ExpenseClaim', source_id=claim.pk, created_by=self.user,
        )
        self.assertEqual(JournalEntry.objects.for_source('ExpenseClaim', claim.pk).count(), 1)

    def test_claim_number_sequence(self):
        self.assertEqual([self._claim().claim_number, self._claim().claim_number], ['CLM-0001', 'CLM-0002'])

    def test_date_range_must_be_ordered(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExpenseClaim.objects.create(claim_number='CLM-X', branch_id='sby', date_from=date(2026, 2, 1),
                                        date_to=date(2026, 1, 1), created_by=self.user)
