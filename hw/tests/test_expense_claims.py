"""Klaim penggantian operasional (keputusan user 2026-10-19): cabang mengklaim
beban yang sudah dibayar dalam satu rentang; saat rupiah dari Pusat masuk,
Finance cabang menandai klaim lunas (Pusat tidak memakai HMS)."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import accounts as coa
from hw.finance import claim_service as svc
from hw.finance import expense_service, posting
from hw.finance.errors import FinanceError, PeriodLockedError
from hw.models import BankTransaction, ExpenseClaim
from hw.models.branch import Branch
from hw.models.journal import JournalEntry
from hw.models.period import FinancialPeriod
from hw.tests.factories import fund_account, make_account, paid_expense

JAN, FEB, MAR = date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15)


class ExpenseClaimServiceTest(TestCase):
    def setUp(self):
        import calendar
        for m in range(1, 13):   # monthly books, so one month can be closed
            FinancialPeriod.objects.create(name=f'2026-{m:02d}', date_from=date(2026, m, 1),
                                           date_to=date(2026, m, calendar.monthrange(2026, m)[1]))
        self.user = User.objects.create_superuser('claims', password='pw12345')
        self.sby = Branch.objects.get(code='sby')
        self.idr = make_account('sby', 'IDR')
        fund_account(self.idr, 95_000_000, 20_000, date(2026, 1, 1), self.user)
        self.e1, _ = paid_expense(self.sby, self.idr, 1_000_000, JAN, self.user)
        self.e2, _ = paid_expense(self.sby, self.idr, 2_000_000, FEB, self.user)
        self.e3, _ = paid_expense(self.sby, self.idr, 3_000_000, MAR, self.user)

    def _claim(self, date_from=date(2026, 1, 1), date_to=date(2026, 2, 28), **kw):
        return svc.create_claim(branch=self.sby, date_from=date_from, date_to=date_to, created_by=self.user, **kw)

    def _sar(self, *expenses):
        return sum(l.amount_sar for e in expenses for l in e.lines.all())

    def _submitted(self):
        claim = self._claim()
        svc.submit_claim(claim, by=self.user)
        return claim

    def test_create_claim_takes_paid_unclaimed_in_range(self):
        claim = self._claim()
        self.assertEqual(claim.status, ExpenseClaim.STATUS_DRAFT)
        self.assertEqual([i.expense_id for i in claim.items.all()], [self.e1.pk, self.e2.pk])
        self.assertEqual(claim.total_amount, 3_000_000)
        self.assertEqual(claim.total_sar, self._sar(self.e1, self.e2))

    def test_exclude_and_empty_claim(self):
        claim = self._claim(exclude_ids=[self.e1.pk])
        self.assertEqual([i.expense_id for i in claim.items.all()], [self.e2.pk])
        with self.assertRaisesMessage(FinanceError, 'Tidak ada pengeluaran yang bisa diklaim di rentang ini.'):
            self._claim(date_from=date(2026, 3, 1), date_to=date(2026, 3, 31), exclude_ids=[self.e3.pk])

    def test_expense_cannot_be_in_two_active_claims(self):
        self._claim()
        self.assertEqual(list(svc.claimable_expenses(self.sby, date(2026, 1, 1), date(2026, 2, 28))), [])
        with self.assertRaises(FinanceError):
            self._claim()

    def test_concurrent_claim_hits_the_db_constraint_as_finance_error(self):
        first = self._claim(date_from=date(2026, 1, 1), date_to=date(2026, 1, 31))
        from hw.models import ExpenseClaimItem
        with self.assertRaisesMessage(FinanceError, self.e1.expense_number):
            svc._add_items(ExpenseClaim.objects.create(
                claim_number='CLM-RACE', branch=self.sby, date_from=JAN, date_to=JAN, created_by=self.user,
            ), [self.e1])
        self.assertEqual(ExpenseClaimItem.objects.filter(expense=self.e1, is_active=True).get().claim, first)

    def test_cancelled_or_rejected_claim_frees_its_expenses(self):
        svc.cancel_claim(self._claim(), by=self.user)
        claim = self._submitted()
        svc.reject_claim(claim, by=self.user, note='belum ada nota')
        self.assertEqual(ExpenseClaim.objects.get(pk=claim.pk).status, ExpenseClaim.STATUS_REJECTED)
        self.assertEqual(len(svc.claimable_expenses(self.sby, date(2026, 1, 1), date(2026, 2, 28))), 2)
        with self.assertRaises(FinanceError):
            svc.reject_claim(self._submitted(), by=self.user, note='')

    def test_mark_paid_posts_ho_entry_and_cash_row(self):
        claim = self._submitted()
        svc.mark_paid(claim, account=self.idr, paid_date=MAR, by=self.user, reference='TRF-1')
        claim.refresh_from_db()
        self.assertEqual(claim.status, ExpenseClaim.STATUS_PAID)
        (entry,) = JournalEntry.objects.for_source('ExpenseClaim', claim.pk).live()
        self.assertEqual(entry.entry_type, JournalEntry.TYPE_REIMBURSEMENT)
        self.assertEqual(
            {(l.account_id, l.debit, l.credit, l.amount_txn, l.branch_id) for l in entry.lines.all()},
            {(self.idr.ledger_account_id, claim.total_sar, 0, 3_000_000, 'sby'),
             (coa.HO_PUSAT, 0, claim.total_sar, None, 'sby')},
        )
        row = BankTransaction.objects.get(source_type=svc.PAYMENT_SOURCE, source_id=claim.payments.get().pk)
        self.assertEqual((row.direction, row.amount, row.account_id), ('in', 3_000_000, self.idr.pk))

    def test_mark_paid_keeps_idr_average(self):
        before = posting.carrying_sar(self.idr, 1_000_000, date(2026, 1, 1))
        svc.mark_paid(self._submitted(), account=self.idr, paid_date=MAR, by=self.user)
        self.assertLessEqual(abs(posting.carrying_sar(self.idr, 1_000_000, MAR) - before), 1)

    def test_mark_paid_backdated_and_closed_period(self):
        claim = self._submitted()
        FinancialPeriod.objects.filter(name='2026-02').update(status=FinancialPeriod.STATUS_CLOSED)
        with self.assertRaises(PeriodLockedError):
            svc.mark_paid(claim, account=self.idr, paid_date=FEB, by=self.user)
        self.assertEqual(ExpenseClaim.objects.get(pk=claim.pk).status, ExpenseClaim.STATUS_SUBMITTED)
        svc.mark_paid(claim, account=self.idr, paid_date=JAN, by=self.user)   # backdated, open month

    def test_paid_to_must_be_branch_idr_account(self):
        claim = self._submitted()
        for account in (make_account('sby', 'SAR'), make_account('jkt', 'SAR')):
            with self.assertRaises(FinanceError):
                svc.mark_paid(claim, account=account, paid_date=MAR, by=self.user)

    def test_only_submitted_claims_can_be_paid(self):
        with self.assertRaises(FinanceError):
            svc.mark_paid(self._claim(), account=self.idr, paid_date=MAR, by=self.user)

    def test_unpay_reverses_and_returns_to_submitted(self):
        claim = self._submitted()
        svc.mark_paid(claim, account=self.idr, paid_date=MAR, by=self.user)
        svc.unpay_claim(claim, by=self.user, reason='salah rekening')
        claim.refresh_from_db()
        self.assertEqual((claim.status, claim.paid_date, claim.paid_to_id), (ExpenseClaim.STATUS_SUBMITTED, None, None))
        self.assertFalse(JournalEntry.objects.for_source('ExpenseClaim', claim.pk).live().exists())
        self.assertEqual(BankTransaction.objects.get(source_type=svc.PAYMENT_SOURCE, source_id=claim.payments.get().pk).status,
                         BankTransaction.STATUS_VOIDED)

    def test_unpay_in_closed_period_is_refused(self):
        claim = self._submitted()
        svc.mark_paid(claim, account=self.idr, paid_date=MAR, by=self.user)
        FinancialPeriod.objects.filter(name='2026-03').update(status=FinancialPeriod.STATUS_CLOSED)
        with self.assertRaises(PeriodLockedError):
            svc.unpay_claim(claim, by=self.user, reason='x')
        self.assertEqual(ExpenseClaim.objects.get(pk=claim.pk).status, ExpenseClaim.STATUS_PAID)

    def test_void_expense_in_submitted_claim_is_refused(self):
        self._submitted()
        with self.assertRaises(FinanceError):
            expense_service.void_expense(self.e1, voided_by=self.user, date=MAR)

    def test_void_expense_in_draft_drops_it_from_claim(self):
        claim = self._claim()
        expense_service.void_expense(self.e1, voided_by=self.user, date=MAR)
        claim.refresh_from_db()
        self.assertEqual([i.expense_id for i in claim.items.filter(is_active=True)], [self.e2.pk])
        self.assertEqual(claim.total_amount, 2_000_000)

    def test_remove_item_only_from_draft(self):
        claim = self._claim()
        svc.remove_item(claim, self.e1, by=self.user)
        self.assertEqual(ExpenseClaim.objects.get(pk=claim.pk).total_amount, 2_000_000)
        svc.submit_claim(claim, by=self.user)
        with self.assertRaises(FinanceError):
            svc.remove_item(claim, self.e2, by=self.user)

    def test_reimbursement_summary_splits_paid_claimed_unclaimed(self):
        paid = self._claim(date_from=date(2026, 1, 1), date_to=date(2026, 1, 31))
        svc.submit_claim(paid, by=self.user)
        svc.mark_paid(paid, account=self.idr, paid_date=MAR, by=self.user)
        svc.create_claim(branch=self.sby, date_from=date(2026, 2, 1), date_to=date(2026, 2, 28), created_by=self.user)
        self.assertEqual(svc.reimbursement_summary(self.sby),
                         {'paid': 1_000_000, 'claimed': 2_000_000, 'unclaimed': 3_000_000, 'borne': 0})
        # As of February the January claim was not paid yet.
        self.assertEqual(svc.reimbursement_summary(self.sby, as_of=date(2026, 2, 28)),
                         {'paid': 0, 'claimed': 3_000_000, 'unclaimed': 0, 'borne': 0})

    def _book(self):
        rows = BankTransaction.objects.filter(account=self.idr).exclude(status=BankTransaction.STATUS_VOIDED)
        return sum(r.amount if r.direction == 'in' else -r.amount for r in rows)

    def test_partial_then_rest_settles_the_claim(self):
        claim = self._submitted()
        before = self._book()
        svc.mark_paid(claim, account=self.idr, paid_date=MAR, by=self.user, amount=2_000_000, remainder=svc.REMAINDER_OPEN)
        claim.refresh_from_db()
        self.assertEqual((claim.status, claim.received_amount, claim.remaining),
                         (ExpenseClaim.STATUS_PARTIAL, 2_000_000, 1_000_000))
        self.assertEqual(self._book(), before + 2_000_000)
        self.assertEqual(svc.reimbursement_summary(self.sby),
                         {'paid': 2_000_000, 'claimed': 1_000_000, 'unclaimed': 3_000_000, 'borne': 0})
        svc.mark_paid(claim, account=self.idr, paid_date=MAR, by=self.user)
        claim.refresh_from_db()
        self.assertEqual((claim.status, claim.remaining, claim.received_sar), (ExpenseClaim.STATUS_PAID, 0, claim.total_sar))
        self.assertEqual(self._book(), before + 3_000_000)
        self.assertEqual(claim.payments.count(), 2)
        entries = JournalEntry.objects.for_source('ExpenseClaim', claim.pk).live()
        self.assertEqual(sum(l.credit for e in entries for l in e.lines.all() if l.account_id == coa.HO_PUSAT), claim.total_sar)

    def test_partial_with_rest_borne_by_branch(self):
        claim = self._submitted()
        svc.mark_paid(claim, account=self.idr, paid_date=MAR, by=self.user, amount=2_000_000, remainder=svc.REMAINDER_BORNE)
        claim.refresh_from_db()
        self.assertEqual((claim.status, claim.borne_amount, claim.remaining), (ExpenseClaim.STATUS_PAID, 1_000_000, 0))
        self.assertEqual(svc.reimbursement_summary(self.sby),
                         {'paid': 2_000_000, 'claimed': 0, 'unclaimed': 3_000_000, 'borne': 1_000_000})
        self.assertLess(claim.received_sar, claim.total_sar)

    def test_close_remainder_after_partial(self):
        claim = self._submitted()
        svc.mark_paid(claim, account=self.idr, paid_date=MAR, by=self.user, amount=2_000_000, remainder=svc.REMAINDER_OPEN)
        svc.close_remainder(claim, by=self.user, closed_date=MAR, note='Pusat menolak sisanya')
        claim.refresh_from_db()
        self.assertEqual((claim.status, claim.borne_amount, claim.borne_date), (ExpenseClaim.STATUS_PAID, 1_000_000, MAR))
        self.assertEqual(JournalEntry.objects.for_source('ExpenseClaim', claim.pk).live().count(), 1)

    def _overpaid(self):
        """Claim of 3 M, head office sends 3.5 M: 500 k stays as its credit."""
        claim = self._submitted()
        svc.mark_paid(claim, account=self.idr, paid_date=MAR, by=self.user, amount=3_500_000, excess_use=svc.EXCESS_CREDIT)
        return claim

    def _next_claim(self):
        return svc.create_claim(branch=self.sby, date_from=MAR, date_to=MAR, created_by=self.user)

    def test_overpaid_claim_keeps_the_extra_as_head_office_credit(self):
        before = self._book()
        claim = self._overpaid()
        claim.refresh_from_db()
        self.assertEqual((claim.status, claim.received_amount, claim.remaining), (ExpenseClaim.STATUS_PAID, 3_000_000, 0))
        self.assertEqual(claim.received_sar, claim.total_sar)
        self.assertEqual(self._book(), before + 3_500_000)
        self.assertEqual(svc.head_office_credit('sby'), 500_000)
        (entry,) = JournalEntry.objects.for_source('ExpenseClaim', claim.pk).live()
        lines = {l.account_id: l for l in entry.lines.all()}
        self.assertEqual(lines[self.idr.ledger_account_id].amount_txn, 3_500_000)
        self.assertGreater(lines[coa.HO_PUSAT].credit, claim.total_sar)
        self.assertEqual(svc.reimbursement_summary(self.sby)['paid'], 3_000_000)

    def test_extra_kept_as_branch_funds_does_not_cut_the_next_claim(self):
        before = self._book()
        claim = self._submitted()
        svc.mark_paid(claim, account=self.idr, paid_date=MAR, by=self.user, amount=3_500_000, excess_use=svc.EXCESS_KEEP)
        self.assertEqual(self._book(), before + 3_500_000)
        self.assertEqual(svc.head_office_credit('sby'), 0)
        following = self._next_claim()
        svc.submit_claim(following, by=self.user)
        following.refresh_from_db()
        self.assertEqual((following.received_amount, following.remaining), (0, 3_000_000))
        svc.unpay_claim(claim, by=self.user, reason='salah')   # nothing used it, so it can be undone
        self.assertEqual(self._book(), before)

    def test_extra_needs_a_choice(self):
        claim = self._submitted()
        with self.assertRaises(FinanceError):
            svc.mark_paid(claim, account=self.idr, paid_date=MAR, by=self.user, amount=3_500_000)
        self.assertFalse(claim.payments.exists())

    def test_next_claim_is_cut_by_the_credit_when_submitted(self):
        self._overpaid()
        following = self._next_claim()
        self.assertEqual(following.remaining, 3_000_000)   # a draft keeps the credit free
        self.assertEqual(svc.head_office_credit('sby'), 500_000)
        svc.submit_claim(following, by=self.user)
        following.refresh_from_db()
        self.assertEqual((following.status, following.received_amount, following.remaining),
                         (ExpenseClaim.STATUS_SUBMITTED, 500_000, 2_500_000))
        self.assertEqual(svc.head_office_credit('sby'), 0)
        book = self._book()
        svc.mark_paid(following, account=self.idr, paid_date=MAR, by=self.user)
        following.refresh_from_db()
        self.assertEqual((following.status, following.remaining, following.received_sar),
                         (ExpenseClaim.STATUS_PAID, 0, following.total_sar))
        self.assertEqual(self._book(), book + 2_500_000)

    def test_credit_larger_than_the_claim_pays_it_and_keeps_the_rest(self):
        claim = self._submitted()
        svc.mark_paid(claim, account=self.idr, paid_date=MAR, by=self.user, amount=7_000_000, excess_use=svc.EXCESS_CREDIT)
        following = self._next_claim()
        svc.submit_claim(following, by=self.user)
        following.refresh_from_db()
        self.assertEqual((following.status, following.remaining), (ExpenseClaim.STATUS_PAID, 0))
        self.assertEqual(svc.head_office_credit('sby'), 1_000_000)
        self.assertFalse(JournalEntry.objects.for_source('ExpenseClaim', following.pk).live().exists())
        with self.assertRaises(FinanceError):
            svc.unpay_claim(following, by=self.user, reason='x')
        svc.cancel_claim(following, by=self.user)
        self.assertEqual(svc.head_office_credit('sby'), 4_000_000)

    def test_cancel_gives_the_credit_back(self):
        self._overpaid()
        following = self._next_claim()
        svc.submit_claim(following, by=self.user)
        svc.cancel_claim(following, by=self.user)
        following.refresh_from_db()
        self.assertEqual((following.status, following.received_amount), (ExpenseClaim.STATUS_CANCELLED, 0))
        self.assertEqual(svc.head_office_credit('sby'), 500_000)

    def test_unpay_keeps_the_credit_cut_and_refuses_a_spent_excess(self):
        claim = self._overpaid()
        following = self._next_claim()
        svc.submit_claim(following, by=self.user)
        with self.assertRaises(FinanceError):
            svc.unpay_claim(claim, by=self.user, reason='x')   # its 500 k already cut the next claim
        svc.mark_paid(following, account=self.idr, paid_date=MAR, by=self.user)
        svc.unpay_claim(following, by=self.user, reason='salah')
        following.refresh_from_db()
        self.assertEqual((following.status, following.received_amount, following.remaining),
                         (ExpenseClaim.STATUS_SUBMITTED, 500_000, 2_500_000))

    def test_partial_refuses_bad_amounts_and_missing_choice(self):
        claim = self._submitted()
        for kwargs in ({'amount': 0}, {'amount': 2_000_000}, {'amount': 2_000_000, 'remainder': 'x'}):
            with self.assertRaises(FinanceError):
                svc.mark_paid(claim, account=self.idr, paid_date=MAR, by=self.user, **kwargs)
        self.assertFalse(claim.payments.exists())

    def test_unpay_undoes_every_payment_of_a_partial_claim(self):
        claim = self._submitted()
        before = self._book()
        svc.mark_paid(claim, account=self.idr, paid_date=MAR, by=self.user, amount=1_000_000, remainder=svc.REMAINDER_OPEN)
        svc.mark_paid(claim, account=self.idr, paid_date=MAR, by=self.user, amount=500_000, remainder=svc.REMAINDER_OPEN)
        svc.unpay_claim(claim, by=self.user, reason='salah catat')
        claim.refresh_from_db()
        self.assertEqual((claim.status, claim.received_amount, claim.remaining), (ExpenseClaim.STATUS_SUBMITTED, 0, 3_000_000))
        self.assertEqual(self._book(), before)
        self.assertFalse(JournalEntry.objects.for_source('ExpenseClaim', claim.pk).live().exists())

    def test_summary_as_of_counts_only_transfers_by_that_date(self):
        claim = self._submitted()
        svc.mark_paid(claim, account=self.idr, paid_date=FEB, by=self.user, amount=1_000_000, remainder=svc.REMAINDER_OPEN)
        svc.mark_paid(claim, account=self.idr, paid_date=MAR, by=self.user, amount=2_000_000)
        self.assertEqual(svc.reimbursement_summary(self.sby, as_of=FEB)['paid'], 1_000_000)
        self.assertEqual(svc.reimbursement_summary(self.sby, as_of=MAR)['paid'], 3_000_000)

    def test_expense_voided_after_it_was_read_does_not_join_a_claim(self):
        stale = svc.claimable_expenses(self.sby, JAN, JAN).get()
        expense_service.void_expense(self.e1, voided_by=self.user, date=MAR)
        claim = ExpenseClaim.objects.create(claim_number='CLM-STALE', branch=self.sby, date_from=JAN, date_to=JAN,
                                            created_by=self.user)
        with self.assertRaises(FinanceError):
            svc._add_items(claim, [stale])

    def test_unpay_clears_the_previous_payment_details(self):
        claim = self._submitted()
        svc.mark_paid(claim, account=self.idr, paid_date=MAR, by=self.user, reference='TRF-OLD')
        svc.unpay_claim(claim, by=self.user, reason='salah')
        claim.refresh_from_db()
        self.assertEqual((claim.reference, bool(claim.proof)), ('', False))

    def test_claim_link_is_in_the_hash_chain(self):
        from hw.finance import hashing
        self.assertIn('source_expense_claim_id', hashing._LATER_ENTRY_FIELDS)

    def test_hq_branch_has_no_claims(self):
        with self.assertRaises(FinanceError):
            svc.create_claim(branch=Branch.objects.get(code='pusat'), date_from=JAN, date_to=MAR,
                             created_by=self.user)
