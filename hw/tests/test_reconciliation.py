"""FASE I remainder — BankStatement / BankStatementLine matching (v2.0 §52)."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import reconciliation_service as rs
from hw.finance_helpers import confirm_payment, create_payment_record
from hw.models import CashAccount, Client
from hw.models.bank_transaction import BankTransaction
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_invoice


class ReconciliationBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('recon', password='pw12345')
        FinancialPeriod.objects.create(
            name='2020-2030',            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.cash_sby = CashAccount.objects.get(branch_id='sby')
        self.client_obj = Client.objects.create( name='PT Recon')
        self.inv = make_invoice(invoice_number='INV-RC-1', customer_name='PT Recon', client=self.client_obj)


class CreateStatementTest(ReconciliationBase):
    def test_create_statement_with_lines(self):
        statement = rs.create_statement(
            account=self.cash_sby, period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
            opening_balance=0, closing_balance=5000, created_by=self.user,
            lines=[{'line_date': date(2026, 8, 5), 'direction': 'in', 'amount': 5000, 'description': 'Transfer masuk'}],
        )
        self.assertEqual(statement.lines.count(), 1)
        self.assertFalse(statement.is_fully_matched)


class MatchLineTest(ReconciliationBase):
    def setUp(self):
        super().setUp()
        pr = create_payment_record(
            self.inv, self.client_obj, date(2026, 8, 5), 5000, method='Transfer',
            receiving_account=self.cash_sby, created_by=self.user,
        )
        confirm_payment(pr, self.user)
        self.tx = BankTransaction.objects.get(source_type='PaymentRecord', source_id=pr.pk)
        self.statement = rs.create_statement(
            account=self.cash_sby, period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
            opening_balance=0, closing_balance=5000,
            lines=[{'line_date': date(2026, 8, 5), 'direction': 'in', 'amount': 5000, 'description': 'Transfer masuk'}],
        )
        self.line = self.statement.lines.get()

    def test_matching_line_marks_transaction_reconciled(self):
        rs.match_line(self.line, self.tx)
        self.line.refresh_from_db()
        self.tx.refresh_from_db()
        self.assertEqual(self.line.match_id, self.tx.match_id)
        self.assertIsNotNone(self.line.match_id)
        self.assertEqual(self.tx.status, BankTransaction.STATUS_RECONCILED)
        self.assertTrue(self.statement.is_fully_matched)

    def test_mismatched_amount_rejected_without_force(self):
        self.line.amount = 4000
        self.line.save(update_fields=['amount'])
        with self.assertRaises(rs.MatchMismatchError):
            rs.match_line(self.line, self.tx)

    def test_mismatch_allowed_with_force(self):
        self.line.amount = 4000
        self.line.save(update_fields=['amount'])
        rs.match_line(self.line, self.tx, force=True)
        self.line.refresh_from_db()
        self.tx.refresh_from_db()
        self.assertEqual(self.line.match_id, self.tx.match_id)
        self.assertIsNotNone(self.line.match_id)

    def test_unmatch_reverts_transaction_status(self):
        rs.match_line(self.line, self.tx)
        rs.unmatch_line(self.line)
        self.line.refresh_from_db()
        self.tx.refresh_from_db()
        self.assertIsNone(self.line.match_id)
        self.assertEqual(self.tx.status, BankTransaction.STATUS_POSTED)

    def test_candidates_scoped_to_account_and_unmatched(self):
        candidates = rs.unmatched_transaction_candidates(self.line)
        self.assertIn(self.tx, list(candidates))
        rs.match_line(self.line, self.tx)
        self.assertNotIn(self.tx, list(rs.unmatched_transaction_candidates(self.line)))


class MatchGroupTest(ReconciliationBase):
    """One transfer for two invoices, and a salary run with its fee booked as one row."""

    def setUp(self):
        super().setUp()
        self.txs = []
        for amount in (3000, 2000):
            pr = create_payment_record(
                self.inv, self.client_obj, date(2026, 8, 5), amount, method='Transfer',
                receiving_account=self.cash_sby, created_by=self.user,
            )
            confirm_payment(pr, self.user)
            self.txs.append(BankTransaction.objects.get(source_type='PaymentRecord', source_id=pr.pk))
        self.statement = rs.create_statement(
            account=self.cash_sby, period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
            opening_balance=0, closing_balance=5000,
            lines=[{'line_date': date(2026, 8, 5), 'direction': 'in', 'amount': 5000, 'description': 'Dua invoice'}],
        )
        self.line = self.statement.lines.get()

    def test_one_line_two_transactions(self):
        match = rs.match_group([self.line], self.txs, created_by=self.user)
        self.line.refresh_from_db()
        self.assertEqual(self.line.match_id, match.pk)
        for tx in self.txs:
            tx.refresh_from_db()
            self.assertEqual((tx.match_id, tx.status), (match.pk, BankTransaction.STATUS_RECONCILED))
        self.assertTrue(self.statement.is_fully_matched)
        self.assertEqual(rs.suggest_matches(self.statement), {})

    def test_totals_must_agree_without_force(self):
        with self.assertRaises(rs.MatchMismatchError):
            rs.match_group([self.line], self.txs[:1])
        rs.match_group([self.line], self.txs[:1], force=True)
        self.line.refresh_from_db()
        self.assertIsNotNone(self.line.match_id)

    def test_money_in_and_out_net_out(self):
        refund = rs.create_statement(
            account=self.cash_sby, period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
            opening_balance=5000, closing_balance=3000,
            lines=[{'line_date': date(2026, 9, 2), 'direction': 'out', 'amount': 2000, 'description': 'Refund'}],
        ).lines.get()
        # Bank +5000 then −2000 refunded; the book kept only the 3000 net.
        with self.assertRaises(rs.MatchMismatchError):
            rs.match_group([self.line, refund], self.txs)
        rs.match_group([self.line, refund], self.txs[:1])
        refund.refresh_from_db()
        self.line.refresh_from_db()
        self.assertEqual(refund.match_id, self.line.match_id)

    def test_unmatch_frees_the_whole_group(self):
        rs.match_group([self.line], self.txs)
        rs.unmatch_line(self.line)
        self.line.refresh_from_db()
        self.assertIsNone(self.line.match_id)
        for tx in self.txs:
            tx.refresh_from_db()
            self.assertEqual((tx.match_id, tx.status), (None, BankTransaction.STATUS_POSTED))
        self.assertEqual(len(rs.unmatched_transaction_candidates(self.line)), 2)

    def test_matched_row_cannot_join_another_match(self):
        rs.match_group([self.line], self.txs)
        other = rs.create_statement(
            account=self.cash_sby, period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
            opening_balance=0, closing_balance=3000,
            lines=[{'line_date': date(2026, 8, 5), 'direction': 'in', 'amount': 3000, 'description': 'x'}],
        ).lines.get()
        with self.assertRaises(rs.FinanceError):
            rs.match_group([other], self.txs[:1])


class StatementSummaryTest(ReconciliationBase):
    def test_summary_reports_difference_against_book_balance(self):
        pr = create_payment_record(
            self.inv, self.client_obj, date(2026, 8, 5), 4500, method='Transfer',
            receiving_account=self.cash_sby, created_by=self.user,
        )
        confirm_payment(pr, self.user)
        statement = rs.create_statement(
            account=self.cash_sby, period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
            opening_balance=0, closing_balance=5000,
            lines=[{'line_date': date(2026, 8, 5), 'direction': 'in', 'amount': 4500, 'description': 'x'}],
        )
        summary = rs.statement_summary(statement)
        self.assertEqual(summary['book_balance'], 4500)
        self.assertEqual(summary['difference'], 500)
        self.assertEqual(summary['lines_matched'], 0)
