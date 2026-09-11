"""FASE E — HQObligation / RemittanceSettlement / RemittanceAllocation."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import Branch, HQObligation, Remittance
from hw.models.journal import JournalEntry
from hw.models.period import FinancialPeriod
from hw.finance import posting, settlement_service as svc
from hw.finance import queries as fq
from hw.finance.errors import FinanceError


class SettlementBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('stl', password='pw12345')
        FinancialPeriod.objects.create(
            name='2020-2030', company='konoz',
            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.sby = Branch.objects.get(code='sby')
        self.rmt = Remittance.objects.create(
            company='konoz', date=date(2026, 4, 1), remittance_number='RMT-STL1',
        )


class ObligationTest(SettlementBase):
    def test_create_obligation_defaults_to_open(self):
        ob = svc.create_obligation(branch=self.sby, amount_sar=20000)
        self.assertEqual(ob.status, HQObligation.STATUS_OPEN)
        self.assertEqual(ob.outstanding_sar, 20000)

    def test_rejects_non_positive_amount(self):
        with self.assertRaises(FinanceError):
            svc.create_obligation(branch=self.sby, amount_sar=0)


class SettlementFlowTest(SettlementBase):
    """Skenario §38: 50,000 SAR kewajiban, satu transfer, dua settlement."""

    def setUp(self):
        super().setUp()
        self.ob1 = svc.create_obligation(branch=self.sby, amount_sar=20000)
        self.ob2 = svc.create_obligation(branch=self.sby, amount_sar=15000)
        self.ob3 = svc.create_obligation(branch=self.sby, amount_sar=10000)
        self.ob4 = svc.create_obligation(branch=self.sby, amount_sar=5000)

    def test_partial_then_full_settlement_closes_obligations(self):
        s1 = svc.add_settlement(
            self.rmt, received_amount_sar=40000, received_date=date(2026, 4, 5),
            created_by=self.user,
        )
        self.assertEqual(fq.account_balance('1000-KAS-PUSAT'), 40000)
        svc.allocate_settlement(
            s1, [(self.ob1, 20000), (self.ob2, 15000), (self.ob3, 5000)],
        )
        self.ob1.refresh_from_db(); self.ob2.refresh_from_db(); self.ob3.refresh_from_db()
        self.assertEqual(self.ob1.status, HQObligation.STATUS_SETTLED)
        self.assertEqual(self.ob2.status, HQObligation.STATUS_SETTLED)
        self.assertEqual(self.ob3.status, HQObligation.STATUS_PARTIALLY_SETTLED)
        self.assertEqual(self.ob3.outstanding_sar, 5000)

        s2 = svc.add_settlement(
            self.rmt, received_amount_sar=10000, received_date=date(2026, 4, 8),
            created_by=self.user,
        )
        svc.allocate_settlement(s2, [(self.ob3, 5000), (self.ob4, 5000)])
        for ob in (self.ob1, self.ob2, self.ob3, self.ob4):
            ob.refresh_from_db()
            self.assertEqual(ob.status, HQObligation.STATUS_SETTLED)
            self.assertEqual(ob.outstanding_sar, 0)

        self.assertEqual(fq.account_balance('1000-KAS-PUSAT'), 50000)
        self.assertEqual(self.rmt.settlements.count(), 2)

    def test_allocation_cannot_exceed_settlement_unallocated(self):
        s1 = svc.add_settlement(
            self.rmt, received_amount_sar=1000, received_date=date(2026, 4, 5),
            created_by=self.user,
        )
        with self.assertRaises(FinanceError):
            svc.allocate_settlement(s1, [(self.ob1, 2000)])

    def test_settlement_posts_balanced_journal_entry(self):
        s1 = svc.add_settlement(
            self.rmt, received_amount_sar=7000, received_date=date(2026, 4, 5),
            created_by=self.user,
        )
        je = JournalEntry.objects.get(reference_type='RemittanceSettlement', reference_id=s1.pk)
        self.assertTrue(je.is_balanced)


class RemittanceSettlementStatusTest(SettlementBase):
    def test_none_without_amount_idr(self):
        self.assertIsNone(self.rmt.settlement_status)

    def test_sent_partially_fully(self):
        self.rmt.amount_idr = 240_000_000
        self.rmt.exchange_rate = 4800
        self.rmt.save(update_fields=['amount_idr', 'exchange_rate'])
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
        self.rmt.save(update_fields=['amount_idr', 'exchange_rate'])
        posting.post_remittance_send(
            self.rmt, from_location='sby', amount_sar=50000, created_by=self.user,
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
        self.assertTrue(all(r['kind'] == 'cash' for r in rows))  # no bank accounts seeded
