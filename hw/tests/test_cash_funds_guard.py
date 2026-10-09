"""Kas dan bank tidak bisa minus: uang keluar ditolak bila rekening (dalam
mata uang aslinya) tidak memegangnya -- pada tanggalnya maupun sesudahnya.
Rupiah Surabaya pernah tercatat minus karena penukaran riyal yang membiayai
transfer tidak dicatat; penjaga ini membuat kejadian seperti itu ketahuan saat
input, bukan berbulan-bulan kemudian."""
from datetime import date
from itertools import count

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance.bank_ledger import record_bank_transaction
from hw.finance.errors import InsufficientFundsError
from hw.management.commands.check_finance import Command as CheckFinance
from hw.models import BankTransaction, Remittance
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_account

_ids = count(1)


class CashFundsGuardTest(TestCase):
    def setUp(self):
        FinancialPeriod.objects.create(name='2026', date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        self.user = User.objects.create_user('guard_mgr', password='pw12345')
        self.user.profile.role = 'finance'  # money is Finance's (2026-10-09)
        self.user.profile.save(update_fields=['role'])
        self.client.force_login(self.user)
        self.idr = make_account('sby', 'IDR')
        make_account('pusat', 'SAR')
        self._move('in', 10_000_000, date(2026, 3, 1))

    def _move(self, direction, amount, day, source_id=None):
        return record_bank_transaction(
            account=self.idr, direction=direction, amount_sar=amount // 4750, currency='IDR', amount=amount,
            source_type='Test', source_id=source_id or next(_ids), transaction_date=day,
        )

    def _new_transfer(self, amount_idr, day='2026-03-10'):
        return self.client.post('/remittance/new/', {
            'date': day, 'amount_idr': str(amount_idr), 'exchange_rate': '4750',
            'from_bank_account': str(self.idr.pk),
        }, HTTP_X_INERTIA='true')

    def test_a_transfer_cannot_send_rupiah_the_account_does_not_hold(self):
        resp = self._new_transfer(12_000_000)
        self.assertIn('Saldo', resp.json()['props']['error'])
        self.assertFalse(Remittance.objects.exists())
        self.assertFalse(BankTransaction.objects.filter(direction='out').exists())

    def test_a_transfer_within_the_balance_goes_through(self):
        resp = self._new_transfer(9_500_000)
        self.assertEqual(resp.status_code, 302)
        rem = Remittance.objects.get()
        self.assertTrue(BankTransaction.objects.filter(source_type='Remittance', source_id=rem.pk).exists())

    def test_a_backdated_outflow_cannot_empty_a_later_balance(self):
        self._move('out', 8_000_000, date(2026, 3, 20))
        # On 10 March the account held 10M, but after the 20 March outflow only
        # 2M is left; a 5M outflow dated 10 March would push that below zero.
        with self.assertRaises(InsufficientFundsError):
            self._move('out', 5_000_000, date(2026, 3, 10))
        self._move('out', 2_000_000, date(2026, 3, 10))

    def test_editing_a_transfer_checks_the_balance_without_its_own_row(self):
        self._new_transfer(9_500_000)
        rem = Remittance.objects.get()
        self.client.post(f'/remittance/{rem.pk}/edit/', {
            'date': '2026-03-10', 'amount_idr': '9900000', 'exchange_rate': '4750',
        })
        rem.refresh_from_db()
        self.assertEqual(rem.amount_sent, 9_900_000)
        self.client.post(f'/remittance/{rem.pk}/edit/', {
            'date': '2026-03-10', 'amount_idr': '10500000', 'exchange_rate': '4750',
        })
        rem.refresh_from_db()
        self.assertEqual(rem.amount_sent, 9_900_000)

    def test_a_repeated_recording_moves_no_new_money(self):
        first = self._move('out', 6_000_000, date(2026, 3, 5), source_id=999)
        again = self._move('out', 6_000_000, date(2026, 3, 5), source_id=999)
        self.assertEqual(first.pk, again.pk)

    def test_check_finance_reports_negative_cash(self):
        # Legacy rows were written before the guard existed.
        BankTransaction.objects.create(
            account=self.idr, direction='out', amount_sar=0, currency='IDR', amount=12_000_000,
            source_type='Legacy', source_id=1, transaction_date=date(2026, 3, 5),
        )
        found = CheckFinance()._negative_cash()
        self.assertEqual(len(found), 1)
        self.assertIn('-2,000,000 IDR', found[0])
