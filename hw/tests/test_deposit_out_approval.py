"""Uang keluar dari deposit butuh dua orang: refund dan transfer deposit dicatat
pending tanpa jurnal, lalu disetujui user lain (admin boleh menyetujui
catatannya sendiri). Saldo diperiksa lagi saat disetujui."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import posting
from hw.finance import queries as fq
from hw.finance.deposit import (
    confirm_refund,
    confirm_transfer,
    reject_refund,
    request_refund,
    request_transfer,
)
from hw.finance.errors import FinanceError
from hw.models import Client
from hw.models.bank_transaction import BankTransaction
from hw.models.journal import JournalEntry
from hw.models.period import FinancialPeriod
from hw.tests.factories import fund_cash, make_account


def _user(name, role=None, superuser=False):
    user = User.objects.create_user(name, password='pw12345', is_superuser=superuser)
    if role:
        user.profile.role = role
        user.profile.save(update_fields=['role'])
    return user


class _Base(TestCase):
    def setUp(self):
        FinancialPeriod.objects.create(name='2026', date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        # Two Finance users: the maker-checker rule, not a missing permission,
        # is what stops the maker.
        self.maker = _user('dep_maker', role='finance')
        self.checker = _user('dep_checker', role='finance')
        self.admin = _user('dep_admin', superuser=True)
        self.a = Client.objects.create(name='PT Deposit A')
        self.b = Client.objects.create(name='PT Deposit B')
        self.sar = make_account('sby', 'SAR')
        fund_cash(self.sar, 5_000)
        posting.post_adjustment(
            lines=[{"account": posting.coa.CASH_SBY, "debit": 5_000},
                   {"account": posting.coa.CUST_CREDIT, "credit": 5_000, "client": self.a.pk}],
            description='deposit awal', entry_date=date(2026, 3, 1), created_by=self.admin,
        )

    def _refund(self, amount=2_000, by=None):
        return request_refund(self.a, account=self.sar, amount_sar=amount, amount_paid=amount,
                              refund_date=date(2026, 3, 10), created_by=by or self.maker)

    def _refund_entries(self):
        return JournalEntry.objects.filter(entry_type=JournalEntry.TYPE_REFUND)


class RefundApprovalTest(_Base):
    def test_request_records_a_pending_document_without_moving_money(self):
        refund = self._refund()
        self.assertEqual(refund.status, 'pending')
        self.assertFalse(self._refund_entries().exists())
        self.assertEqual(fq.client_credit_balance(self.a.pk), 5_000)

    def test_recorder_cannot_approve_their_own_refund(self):
        refund = self._refund()
        with self.assertRaisesMessage(FinanceError, 'user lain'):
            confirm_refund(refund, confirmed_by=self.maker)
        refund.refresh_from_db()
        self.assertEqual(refund.status, 'pending')
        self.assertFalse(self._refund_entries().exists())

    def test_another_user_approves_and_the_money_leaves(self):
        refund = confirm_refund(self._refund(), confirmed_by=self.checker)
        self.assertEqual((refund.status, refund.confirmed_by), ('confirmed', self.checker))
        entry = refund.journal_entry
        self.assertEqual(entry.entry_date, date(2026, 3, 10))
        self.assertEqual(fq.client_credit_balance(self.a.pk), 3_000)
        self.assertTrue(BankTransaction.objects.filter(source_type='Refund', source_id=entry.pk).exists())

    def test_admin_may_approve_their_own(self):
        refund = confirm_refund(self._refund(by=self.admin), confirmed_by=self.admin)
        self.assertEqual(refund.confirmed_by_id, refund.created_by_id)

    def test_balance_is_checked_again_on_approval(self):
        first, second = self._refund(3_000), self._refund(3_000)
        confirm_refund(first, confirmed_by=self.checker)
        with self.assertRaisesMessage(FinanceError, 'hanya 2,000'):
            confirm_refund(second, confirmed_by=self.checker)
        second.refresh_from_db()
        self.assertEqual(second.status, 'pending')

    def test_rejection_needs_a_reason_and_moves_nothing(self):
        refund = self._refund()
        with self.assertRaises(FinanceError):
            reject_refund(refund, rejected_by=self.checker, reason='  ')
        refund = reject_refund(refund, rejected_by=self.checker, reason='rekening salah')
        self.assertEqual((refund.status, refund.rejected_reason), ('rejected', 'rekening salah'))
        with self.assertRaises(FinanceError):
            confirm_refund(refund, confirmed_by=self.checker)
        self.assertFalse(self._refund_entries().exists())
        self.assertEqual(fq.client_credit_balance(self.a.pk), 5_000)


class TransferApprovalTest(_Base):
    def test_transfer_needs_another_user(self):
        transfer = request_transfer(self.a, self.b, amount_sar=1_500, transfer_date=date(2026, 3, 10),
                                    created_by=self.maker)
        with self.assertRaises(FinanceError):
            confirm_transfer(transfer, confirmed_by=self.maker)
        confirm_transfer(transfer, confirmed_by=self.checker)
        self.assertEqual((fq.client_credit_balance(self.a.pk), fq.client_credit_balance(self.b.pk)), (3_500, 1_500))


class ApprovalScreenTest(_Base):
    def _login(self, user):
        self.client.force_login(user)
        s = self.client.session
        s['active_company'] = 'konoz'
        s.save()

    def _pending_rows(self, user):
        self._login(user)
        resp = self.client.get(f'/finance/clients/{self.a.pk}/statement/', HTTP_X_INERTIA='true')
        return resp.json()['props']['pending_out']

    def test_statement_lists_pending_and_who_may_decide(self):
        refund = self._refund()
        [row] = self._pending_rows(self.checker)
        self.assertEqual((row['kind'], row['number'], row['can_decide']), ('refund', refund.refund_number, True))
        [row] = self._pending_rows(self.maker)
        self.assertFalse(row['can_decide'])

    def test_maker_post_to_confirm_is_refused(self):
        refund = self._refund()
        self._login(self.maker)
        self.client.post(f'/finance/refunds/{refund.pk}/confirm/')
        refund.refresh_from_db()
        self.assertEqual(refund.status, 'pending')

    def test_checker_rejects_through_the_screen(self):
        refund = self._refund()
        self._login(self.checker)
        self.client.post(f'/finance/refunds/{refund.pk}/reject/', {'reason': 'dobel'})
        refund.refresh_from_db()
        self.assertEqual(refund.status, 'rejected')


class DepositLockTest(_Base):
    """Pengeluaran deposit berbaris di baris Client. Kunci lama (FOR UPDATE +
    aggregate atas baris jurnal) dibuang diam-diam oleh Django, jadi dua
    persetujuan paralel bisa sama-sama lolos cek saldo."""

    def test_approval_locks_the_client_row(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        if not connection.features.has_select_for_update:
            self.skipTest('database tanpa SELECT ... FOR UPDATE')
        refund = self._refund()
        table = Client._meta.db_table
        with CaptureQueriesContext(connection) as ctx:
            confirm_refund(refund, confirmed_by=self.checker)
        self.assertTrue(any(
            'FOR UPDATE' in q['sql'] and f'"{table}"' in q['sql'] for q in ctx.captured_queries
        ))
