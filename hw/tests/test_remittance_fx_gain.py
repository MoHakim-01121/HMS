"""Laba kurs cabang masuk buku besar saat remittance dikirim.

Rekening asal dikredit sebesar nilai tercatat (rata-rata) rupiah yang dikirim;
selisihnya dengan SAR yang akan diterima Pusat adalah laba/rugi kurs cabang.
Sisa rupiah setelah setoran adalah laba itu, jadi harus tetap bernilai dan bisa
dipakai (keputusan user 2026-10-19). Skenario = contoh kerja test_fund_flow:
97.125.000 IDR senilai 20.000 SAR."""
from datetime import date

from django.test import TestCase

from hw.finance import accounts as coa
from hw.finance import fund_flow, posting
from hw.finance.errors import FinanceError
from hw.models import Remittance
from hw.models.journal import JournalEntry
from hw.tests.factories import make_remittance
from hw.tests import test_fund_flow   # module import: its TestCases must not run twice

DAY = date(2026, 9, 10)


class RemittanceFxGainTest(TestCase):
    setUp = test_fund_flow.FundFlowScenario.setUp
    _send = test_fund_flow.FundFlowScenario._send

    def _rem(self):
        return Remittance.objects.get()

    def _lines(self, rem):
        entries = JournalEntry.objects.for_source('Remittance', rem.pk).filter(
            entry_type=JournalEntry.TYPE_REMITTANCE,
        ).live()
        return {
            (l.account_id, l.debit, l.credit, l.amount_txn, l.branch_id)
            for e in entries for l in e.lines.all()
        }

    def test_send_books_fx_gain(self):
        self._send(95_000_000)
        self.assertEqual(self._lines(self._rem()), {
            (coa.TRANSIT, 20_000, 0, None, 'sby'),
            (self.idr.ledger_account_id, 0, 19_562, 95_000_000, 'sby'),
            (coa.INC_FX_GAIN, 0, 438, None, 'sby'),
        })

    def test_leftover_idr_keeps_value_and_can_pay_expense(self):
        from hw.tests.factories import paid_expense
        self._send(95_000_000)
        self.assertEqual(posting._ledger_holding(self.idr.ledger_account_id, DAY), (438, 2_125_000))
        paid_expense(self.idr.branch, self.idr, 500_000, date(2026, 9, 12), self.user)

    def test_ledger_gain_matches_fx_profit(self):
        self._send(95_000_000)
        (t,) = fund_flow.fx_profit(branch='sby')['transfers']
        gain = next(c for a, _d, c, *_ in self._lines(self._rem()) if a == coa.INC_FX_GAIN)
        self.assertLessEqual(abs(gain - round(t['profit_idr'] / t['avg_rate'])), 1)

    def test_send_below_average_books_fx_loss(self):
        self._send(47_500_000, sar_rate='4950')        # expected 9,596 SAR, carried 9,781
        lines = self._lines(self._rem())
        self.assertIn((coa.EXP_FX_LOSS, 185, 0, None, 'sby'), lines)
        self.assertIn((self.idr.ledger_account_id, 0, 9_781, 47_500_000, 'sby'), lines)
        self.assertFalse(any(a == coa.INC_FX_GAIN for a, *_ in lines))

    def test_resync_twice_posts_nothing_new(self):
        self._send(95_000_000)
        rem = self._rem()
        before = JournalEntry.objects.count()
        posting.resync_remittance(rem, created_by=self.user)
        posting.resync_remittance(rem, created_by=self.user)
        self.assertEqual(JournalEntry.objects.count(), before)

    def test_resync_after_a_later_same_day_inflow_keeps_the_posted_gain(self):
        """A note-only edit resyncs; money that reached the account later (even
        dated the same day) must not re-value a send that did not change."""
        from hw.tests.factories import fund_ledger
        self._send(95_000_000)
        rem = self._rem()
        fund_ledger(self.idr, 10_000_000, 2_105, DAY)
        before = JournalEntry.objects.count()
        posting.resync_remittance(rem, created_by=self.user)
        self.assertEqual(JournalEntry.objects.count(), before)
        self.assertIn((coa.INC_FX_GAIN, 0, 438, None, 'sby'), self._lines(rem))

    def test_edit_amount_reverses_and_reposts_with_fx(self):
        self._send(95_000_000)
        rem = self._rem()
        rem.amount_sent = 47_500_000                     # 10,000 SAR @4,750
        rem.save()
        posting.resync_remittance(rem, created_by=self.user)
        self.assertEqual(self._lines(rem), {
            (coa.TRANSIT, 10_000, 0, None, 'sby'),
            (self.idr.ledger_account_id, 0, 9_781, 47_500_000, 'sby'),
            (coa.INC_FX_GAIN, 0, 219, None, 'sby'),
        })

    def test_send_more_than_ledger_holds_is_refused(self):
        rem = make_remittance(from_account=self.idr, amount_sent=200_000_000, exchange_rate=4750,
                              date=DAY, remittance_number='RMT-TOO-MUCH')
        before = JournalEntry.objects.count()
        with self.assertRaises(FinanceError):
            posting.resync_remittance(rem, created_by=self.user)
        self.assertEqual(JournalEntry.objects.count(), before)

    def test_legacy_remittance_keeps_old_posting(self):
        rem = make_remittance(from_account=self.idr, amount_sent=475_000_000, exchange_rate=4750,
                              date=DAY, remittance_number='RMT-LEGACY', is_legacy=True)
        posting.resync_remittance(rem, created_by=self.user)
        self.assertEqual(self._lines(rem), {
            (coa.TRANSIT, 100_000, 0, None, 'sby'),
            (self.idr.ledger_account_id, 0, 100_000, 475_000_000, 'sby'),
        })
