"""Angka transfer yang dipakai bersama Recap, KPI tab Transfer, dan PDF rekap,
serta hapus penerimaan yang salah catat.

"Diterima" = nominal yang benar-benar masuk Kas Pusat (penerimaan bertahap,
atau nominal manual untuk transfer lama), bukan nominal kirim transfer yang
berstatus received. Skenario memakai AllocationBase (a/b/c, 50.000 SAR).
"""
from datetime import date

from django.contrib.auth.models import User
from django.db.models import Q, Sum

from hw.finance import accounts as coa
from hw.finance import remittance_allocation as ra
from hw.finance import settlement_service as svc
from hw.finance.errors import FinanceError
from hw.management.commands.check_finance import Command as CheckFinance
from hw.models import Remittance, RemittanceLine
from hw.models.bank_transaction import BankTransaction
from hw.models.journal import JournalLine
from hw.models.settlement import RemittanceSettlement
from hw.tests.test_remittance_allocation import AllocationBase
from hw.views.remittance_views import _compute_recap_data, _compute_stats


def _net(account_id):
    # Kas cabang = akun induk + akun anak per mata uang.
    agg = JournalLine.objects.filter(
        Q(account_id=account_id) | Q(account__parent_id=account_id),
    ).aggregate(d=Sum('debit'), c=Sum('credit'))
    return (agg['d'] or 0) - (agg['c'] or 0)


def _figures(rem):
    rem = Remittance.objects.get(pk=rem.pk)
    f = ra.transfer_figures(rem)
    return (f['state'], f['sent'], f['received'], f['outstanding'], f['difference'])


class TransferFiguresTest(AllocationBase):
    def test_pending_then_partial_then_received_with_fee(self):
        self.assertEqual(_figures(self.rem), ('pending', 50000, 0, 50000, 0))
        self._receive(40000, date(2026, 9, 12), None)
        self.assertEqual(_figures(self.rem), ('partial', 50000, 40000, 10000, 0))
        self._receive(9850, date(2026, 9, 15), None)
        svc.close_remittance_diff(self.rem, created_by=self.user, entry_date=date(2026, 9, 16))
        self.assertEqual(_figures(self.rem), ('received', 50000, 49850, 0, 150))

class RecapTest(AllocationBase):
    def test_month_totals_use_actual_received_and_partial_state(self):
        self._transfer(9_600_000, 4800, date(2026, 10, 2), number='RMT-ALC-2')
        self._receive(40000, date(2026, 9, 12), None)

        request = type('R', (), {'user': self.user})()  # covers every branch
        months = {m['period']: m for m in _compute_recap_data(request)}
        self.assertEqual(list(months), ['2026-10', '2026-09'])
        sept = months['2026-09']
        self.assertEqual(
            (sept['total_sent'], sept['total_received'], sept['total_outstanding'], sept['total_difference']),
            (50000, 40000, 10000, 0),
        )
        self.assertEqual((sept['count_partial'], sept['count_pending'], sept['count_received']), (1, 0, 0))
        row = sept['remittances'][0]
        self.assertEqual((row['state'], row['sent'], row['received']), ('partial', 50000, 40000))
        self.assertEqual((months['2026-10']['total_outstanding'], months['2026-10']['count_pending']), (2000, 1))


class TransferKpiTest(AllocationBase):
    def test_kpis_follow_the_four_terms(self):
        self._receive(40000, date(2026, 9, 12), [{'linked_number': 'A', 'amount_sar': 32000}])
        stats = _compute_stats()
        self.assertEqual(
            (stats['sent'], stats['received'], stats['in_transit'], stats['received_unallocated']),
            (50000, 40000, 10000, 8000),
        )
        for key in ('kewajiban_kirim', 'saldo_dana_klien', 'fx_profit_idr', 'client_idr_held'):
            self.assertIn(key, stats)


class DeleteReceiptTest(AllocationBase):
    def setUp(self):
        super().setUp()
        self.s1 = self._receive(40000, date(2026, 9, 12), [
            {'linked_number': 'A', 'amount_sar': 32000},
            {'linked_number': 'C', 'amount_sar': 8000},
        ])
        self.s2 = self._receive(10000, date(2026, 9, 15), [
            {'linked_number': 'C', 'amount_sar': 1000},
            {'linked_number': 'B', 'amount_sar': 9000},
        ])

    def _delete(self, settlement):
        svc.delete_settlement(settlement, created_by=self.user, entry_date=date(2026, 9, 20))

    def test_delete_last_receipt_restores_state(self):
        self.rem.refresh_from_db()
        self.assertEqual(self.rem.status, Remittance.STATUS_RECEIVED)
        self._delete(self.s2)

        self.rem.refresh_from_db()
        self.assertEqual(self.rem.status, Remittance.STATUS_PENDING)
        self.assertEqual(_net(coa.TRANSIT), 10000)
        self.assertEqual(_net(coa.CASH_PUSAT), 40000)
        self.assertEqual(_net(coa.CASH_SBY), 0)
        self.assertEqual(self._idle(), {'A': 0, 'B': 9000, 'C': 1000})
        self.assertEqual(list(RemittanceSettlement.objects.values_list('pk', flat=True)), [self.s1.pk])
        self.assertFalse(RemittanceLine.objects.filter(settlement_id=self.s2.pk).exists())
        self.assertFalse(BankTransaction.objects.filter(source_type='RemittanceSettlement', source_id=self.s2.pk).exclude(status=BankTransaction.STATUS_VOIDED).exists())
        self.assertIsNotNone(RemittanceSettlement.all_objects.get(pk=self.s2.pk).voided_at)
        self.assertEqual(CheckFinance()._remittance_line_mismatch(), [])

    def test_blocked_when_difference_already_closed(self):
        self._delete(self.s2)
        self._receive(9850, date(2026, 9, 21), None)
        svc.close_remittance_diff(self.rem, created_by=self.user, entry_date=date(2026, 9, 22))
        with self.assertRaises(FinanceError):
            self._delete(self.s1)
        self.assertTrue(RemittanceSettlement.objects.filter(pk=self.s1.pk).exists())

    def test_blocked_when_bank_transaction_reconciled(self):
        BankTransaction.objects.filter(source_type='RemittanceSettlement', source_id=self.s2.pk).update(
            status=BankTransaction.STATUS_RECONCILED,
        )
        with self.assertRaises(FinanceError):
            self._delete(self.s2)
        self.assertEqual(_net(coa.CASH_PUSAT), 50000)


class DeleteReceiptViewTest(AllocationBase):
    def setUp(self):
        super().setUp()
        self.s1 = self._receive(40000, date(2026, 9, 12), [{'linked_number': 'A', 'amount_sar': 32000}])
        self.url = f'/remittance/{self.rem.pk}/receipt/{self.s1.pk}/delete/'

    def test_manager_can_delete(self):
        self.user.is_superuser = True
        self.user.save(update_fields=['is_superuser'])
        self.client.force_login(self.user)
        resp = self.client.post(self.url)
        self.assertRedirects(resp, f'/remittance/{self.rem.pk}/', fetch_redirect_response=False)
        self.assertFalse(RemittanceSettlement.objects.exists())

    def test_staff_cannot_delete(self):
        staff = User.objects.create_user('alloc_staff', password='pw12345')
        staff.profile.role = 'staff'
        staff.profile.save(update_fields=['role'])
        self.client.force_login(staff)
        self.client.post(self.url)
        self.assertTrue(RemittanceSettlement.objects.exists())

    def test_detail_exposes_can_delete(self):
        self.user.is_superuser = True
        self.user.save(update_fields=['is_superuser'])
        self.client.force_login(self.user)
        props = self.client.get(f'/remittance/{self.rem.pk}/', HTTP_X_INERTIA='true').json()['props']
        self.assertTrue(props['rem']['settlements'][0]['can_delete'])

