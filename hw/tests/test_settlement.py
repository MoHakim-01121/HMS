"""FASE E — RemittanceSettlement (penerimaan bertahap di Pusat)."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Branch, Remittance
from hw.models.journal import JournalEntry
from hw.models.period import FinancialPeriod
from hw.finance import posting, settlement_service as svc
from hw.finance import queries as fq
from hw.finance.errors import FinanceError
from hw.tests.factories import fund_ledger_for, make_remittance


class SettlementBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('stl', password='pw12345')
        FinancialPeriod.objects.create(
            name='2020-2030',            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.sby = Branch.objects.get(code='sby')
        self.rmt = make_remittance(
 date=date(2026, 4, 1), remittance_number='RMT-STL1',
        )


class SettlementFlowTest(SettlementBase):
    """Skenario §38: satu transfer 50,000 SAR diterima Pusat dalam dua tahap."""

    def test_partial_then_full_settlement(self):
        svc.add_settlement(
            self.rmt, received_amount_sar=40000, received_date=date(2026, 4, 5),
            created_by=self.user,
        )
        self.assertEqual(fq.account_balance('1000-KAS-PUSAT'), 40000)

        svc.add_settlement(
            self.rmt, received_amount_sar=10000, received_date=date(2026, 4, 8),
            created_by=self.user,
        )
        self.assertEqual(fq.account_balance('1000-KAS-PUSAT'), 50000)
        self.assertEqual(self.rmt.settlements.count(), 2)

    def test_rejects_non_positive_amount(self):
        with self.assertRaises(FinanceError):
            svc.add_settlement(self.rmt, received_amount_sar=0, received_date=date(2026, 4, 5))

    def test_settlement_posts_balanced_journal_entry(self):
        s1 = svc.add_settlement(
            self.rmt, received_amount_sar=7000, received_date=date(2026, 4, 5),
            created_by=self.user,
        )
        je = JournalEntry.objects.get(source_remittance_settlement=s1.pk)
        self.assertTrue(je.is_balanced)


class RemittanceSettlementStatusTest(SettlementBase):
    def test_sent_partially_fully(self):
        self.rmt.amount_idr = 240_000_000
        self.rmt.exchange_rate = 4800
        self.rmt.save(update_fields=['amount_sent', 'exchange_rate'])
        self.assertEqual(self.rmt.settlement_status, 'sent')

        svc.add_settlement(self.rmt, received_amount_sar=30000, received_date=date(2026, 4, 5),
                           created_by=self.user)
        self.assertEqual(self.rmt.settlement_status, 'partially_settled')

        svc.add_settlement(self.rmt, received_amount_sar=20000, received_date=date(2026, 4, 8),
                           created_by=self.user)
        self.assertEqual(self.rmt.settlement_status, 'fully_settled')


class CloseRemittanceDiffTest(SettlementBase):
    def setUp(self):
        super().setUp()
        self.rmt.amount_idr = 240_000_000
        self.rmt.exchange_rate = 4800  # expected_sar = 50000
        self.rmt.save(update_fields=['amount_sent', 'exchange_rate'])
        fund_ledger_for(self.rmt, 50000)
        posting.post_remittance_send(
            self.rmt, amount_sar=50000, created_by=self.user,
        )

    def test_shortfall_books_bank_fee(self):
        svc.add_settlement(self.rmt, received_amount_sar=49500, received_date=date(2026, 4, 5),
                           created_by=self.user)
        svc.close_remittance_diff(self.rmt, created_by=self.user)
        self.assertEqual(fq.account_balance('5100-EXP-BANKFEE'), 500)
        self.assertEqual(fq.account_balance('1200-TRANSIT'), 0)

    def test_double_close_is_rejected(self):
        svc.add_settlement(self.rmt, received_amount_sar=49500, received_date=date(2026, 4, 5),
                           created_by=self.user)
        svc.close_remittance_diff(self.rmt, created_by=self.user)
        with self.assertRaises(FinanceError):
            svc.close_remittance_diff(self.rmt, created_by=self.user)

    def test_no_diff_is_a_noop(self):
        svc.add_settlement(self.rmt, received_amount_sar=50000, received_date=date(2026, 4, 5),
                           created_by=self.user)
        result = svc.close_remittance_diff(self.rmt, created_by=self.user)
        self.assertIsNone(result)


class MoneyAccountsOverviewTest(SettlementBase):
    def test_overview_lists_seeded_cash_accounts(self):
        rows = fq.money_accounts_overview()
        codes = {r['branch'] for r in rows}
        self.assertIn('sby', codes)
        self.assertTrue(all(r['kind'] == 'cash' for r in rows if r['branch'] == 'pusat'))


class SettlementBasisAndStatusSyncTest(SettlementBase):
    """Satu sumber kebenaran 'sudah diterima': Remittance.status ikut
    tersinkron dari settlement, dan basis selisih = total kirim yang
    terposting di TRANSIT (bukan amount_idr/kurs)."""

    def _send(self, amount):
        fund_ledger_for(self.rmt, amount)
        posting.post_remittance_send(
            self.rmt, amount_sar=amount, created_by=self.user,
        )

    def test_full_settlement_marks_remittance_received(self):
        self._send(50000)
        svc.add_settlement(self.rmt, received_amount_sar=30000, received_date=date(2026, 4, 5),
                           created_by=self.user)
        self.rmt.refresh_from_db()
        self.assertEqual(self.rmt.status, Remittance.STATUS_PENDING)
        svc.add_settlement(self.rmt, received_amount_sar=20000, received_date=date(2026, 4, 6),
                           created_by=self.user)
        self.rmt.refresh_from_db()
        self.assertEqual(self.rmt.status, Remittance.STATUS_RECEIVED)

    def test_close_diff_marks_remittance_received(self):
        self._send(50000)
        svc.add_settlement(self.rmt, received_amount_sar=49500, received_date=date(2026, 4, 5),
                           created_by=self.user)
        svc.close_remittance_diff(self.rmt, created_by=self.user)
        self.rmt.refresh_from_db()
        self.assertEqual(self.rmt.status, Remittance.STATUS_RECEIVED)
        self.assertTrue(svc.diff_is_closed(self.rmt))

    def test_diff_basis_is_posted_send_total_not_idr_rate(self):
        # amount_idr/kurs -> 50,000, tapi baris yang benar-benar terposting
        # ke TRANSIT cuma 48,000. Selisih harus menutup TRANSIT ke nol.
        self.rmt.amount_idr = 240_000_000
        self.rmt.exchange_rate = 4800
        self.rmt.save(update_fields=['amount_sent', 'exchange_rate'])
        self._send(48000)
        svc.add_settlement(self.rmt, received_amount_sar=47500, received_date=date(2026, 4, 5),
                           created_by=self.user)
        svc.close_remittance_diff(self.rmt, created_by=self.user)
        self.assertEqual(fq.account_balance('5100-EXP-BANKFEE'), 500)
        self.assertEqual(fq.account_balance('1200-TRANSIT'), 0)

    def test_rejects_settlement_on_received_remittance(self):
        from hw.models.settlement import RemittanceSettlement
        RemittanceSettlement.objects.create(
            remittance=self.rmt, received_amount_sar=self.rmt.settlement_basis_sar, received_date=self.rmt.date,
        )
        with self.assertRaises(FinanceError):
            svc.add_settlement(self.rmt, received_amount_sar=1000, received_date=date(2026, 4, 5))

    def test_close_diff_requires_a_settlement(self):
        self._send(50000)
        with self.assertRaises(FinanceError):
            svc.close_remittance_diff(self.rmt, created_by=self.user)
        self.assertEqual(fq.account_balance('5100-EXP-BANKFEE'), 0)


class ReopenClosedDiffTest(CloseRemittanceDiffTest):
    """Reverse the diff entry, then close again: the unique idempotency_key of
    the reversed entry must not block the new one."""

    def test_close_again_after_reversing_diff(self):
        svc.add_settlement(self.rmt, received_amount_sar=49500, received_date=date(2026, 4, 5),
                           created_by=self.user)
        first = svc.close_remittance_diff(self.rmt, created_by=self.user)
        posting.reverse_entry(first, reversal_date=date(2026, 4, 9), created_by=self.user)
        self.assertEqual(fq.account_balance('5100-EXP-BANKFEE'), 0)

        second = svc.close_remittance_diff(self.rmt, created_by=self.user)
        self.assertNotEqual(first.pk, second.pk)
        self.assertNotEqual(first.idempotency_key, second.idempotency_key)
        self.assertEqual(fq.account_balance('5100-EXP-BANKFEE'), 500)
        self.assertEqual(fq.account_balance('1200-TRANSIT'), 0)

    def test_reversals_do_not_count_as_sent(self):
        """Reversing a receipt or a closed diff debits TRANSIT; that is not
        money sent, so the send total (= settlement basis) must not move."""
        s1 = svc.add_settlement(self.rmt, received_amount_sar=20000, received_date=date(2026, 4, 5),
                                created_by=self.user)
        svc.delete_settlement(s1, created_by=self.user, entry_date=date(2026, 4, 6))
        self.assertEqual(self.rmt.total_sar, 50000)

        svc.add_settlement(self.rmt, received_amount_sar=49500, received_date=date(2026, 4, 7),
                           created_by=self.user)
        diff = svc.close_remittance_diff(self.rmt, created_by=self.user)
        posting.reverse_entry(diff, reversal_date=date(2026, 4, 9), created_by=self.user)
        self.assertEqual(self.rmt.total_sar, 50000)


class ReopenDiffTest(CloseRemittanceDiffTest):
    """Reopen Difference: the only in-app way to correct receipts after the
    difference was closed."""

    def test_reopen_reverses_diff_and_returns_to_pending(self):
        s = svc.add_settlement(self.rmt, received_amount_sar=49500, received_date=date(2026, 4, 5),
                               created_by=self.user)
        svc.close_remittance_diff(self.rmt, created_by=self.user)
        self.rmt.refresh_from_db()
        self.assertEqual(self.rmt.status, Remittance.STATUS_RECEIVED)
        with self.assertRaises(FinanceError):
            svc.delete_settlement(s, created_by=self.user)

        svc.reopen_remittance_diff(self.rmt, created_by=self.user, entry_date=date(2026, 4, 9))
        self.rmt.refresh_from_db()
        self.assertEqual(self.rmt.status, Remittance.STATUS_PENDING)
        self.assertFalse(svc.diff_is_closed(self.rmt))
        self.assertEqual(fq.account_balance('5100-EXP-BANKFEE'), 0)

        # Receipts are correctable again, and the difference can be re-closed.
        svc.delete_settlement(s, created_by=self.user, entry_date=date(2026, 4, 10))
        svc.add_settlement(self.rmt, received_amount_sar=49800, received_date=date(2026, 4, 11),
                           created_by=self.user)
        svc.close_remittance_diff(self.rmt, created_by=self.user)
        self.assertEqual(fq.account_balance('5100-EXP-BANKFEE'), 200)
        self.assertEqual(fq.account_balance('1200-TRANSIT'), 0)

    def test_reopen_without_closed_diff_is_refused(self):
        svc.add_settlement(self.rmt, received_amount_sar=49500, received_date=date(2026, 4, 5),
                           created_by=self.user)
        with self.assertRaises(FinanceError):
            svc.reopen_remittance_diff(self.rmt, created_by=self.user)

    def test_reopen_view(self):
        from django.contrib.auth.models import User
        admin = User.objects.create_superuser('reopen', password='pw12345')
        self.client.force_login(admin)
        svc.add_settlement(self.rmt, received_amount_sar=49500, received_date=date(2026, 4, 5),
                           created_by=self.user)
        svc.close_remittance_diff(self.rmt, created_by=self.user)
        self.assertEqual(self.client.get(f'/remittance/{self.rmt.pk}/reopen-diff/').status_code, 405)
        resp = self.client.post(f'/remittance/{self.rmt.pk}/reopen-diff/')
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(svc.diff_is_closed(self.rmt))
