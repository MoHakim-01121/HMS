"""Cash routing: which kas wallet receives a client's payment.

cash_destination() is the single decision point shared by the Finance
page (PaymentRecord dual-write), invoice billing and penalty sync. The
Jakarta branch records payments that never touch Surabaya's kas, so they
must not count as Surabaya mengendap -- they idle in Jakarta instead and
get their own remittance obligation later.
"""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import (
    Client, Invoice, Reservation, CashMovement,
    CashAccount as WalletAccount,
)
from hw.models.journal import Account as JournalAccount
from hw.finance import accounts as coa
from hw.models.period import FinancialPeriod
from hw import ledger
from hw.finance_helpers import create_payment_record, confirm_payment, allocate_payment


class CashDestinationTest(TestCase):
    def test_explicit_jakarta_wins(self):
        self.assertEqual(
            ledger.cash_destination(method='cash', received_in='jkt'),
            WalletAccount.JKT,
        )
        self.assertEqual(
            ledger.cash_destination(method='transfer', received_in='jakarta'),
            WalletAccount.JKT,
        )

    def test_explicit_pusat_wins(self):
        self.assertEqual(
            ledger.cash_destination(method='transfer', received_in='pusat'),
            WalletAccount.PUSAT,
        )

    def test_legacy_direct_method_routes_to_pusat(self):
        # Pre-received_in rows only had method == 'direct'.
        self.assertEqual(ledger.cash_destination(method='direct'), WalletAccount.PUSAT)

    def test_direct_method_beats_received_in_default(self):
        # create_payment_record defaults received_in to 'sby'; an old-style
        # Direct payment must not become Surabaya idle money because of it.
        self.assertEqual(
            ledger.cash_destination(method='direct', received_in='sby'),
            WalletAccount.PUSAT,
        )

    def test_everything_else_lands_in_surabaya(self):
        self.assertEqual(ledger.cash_destination(method='cash'), WalletAccount.SBY)
        self.assertEqual(ledger.cash_destination(), WalletAccount.SBY)


class JournalCashAccountTest(TestCase):
    def test_each_wallet_maps_to_its_journal_account(self):
        self.assertEqual(ledger.cash_journal_account(WalletAccount.SBY), JournalAccount.CASH_SBY)
        self.assertEqual(ledger.cash_journal_account(WalletAccount.JKT), JournalAccount.CASH_JKT)
        self.assertEqual(ledger.cash_journal_account(WalletAccount.PUSAT), JournalAccount.CASH_PUSAT)


class PaymentRecordRoutingTest(TestCase):
    """confirm_payment/allocate_payment must honor received_in -- both in
    the journal's cash account and in the mirrored CashMovement."""

    def setUp(self):
        self.user = User.objects.create_user('router', password='pw12345')
        self.client_obj = Client.objects.create(company='konoz', name='PT Route')
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-ROUTE-001', customer_name='PT Route',
        )
        self.res = Reservation.objects.create(
            invoice=self.invoice, reservation_number='R1', total_sar=1000,
        )
        FinancialPeriod.objects.create(
            name='2026-01', date_from=date(2026, 1, 1), date_to=date(2026, 1, 31),
        )

    def _pay(self, received_in):
        payment = create_payment_record(
            invoice=self.invoice, client=self.client_obj, payment_date=date(2026, 1, 1),
            amount=300, method='transfer', created_by=self.user,
            reservation=self.res, received_in=received_in,
        )
        _, journal = confirm_payment(payment, confirmed_by=self.user)
        allocate_payment(payment, allocation_date=payment.payment_date, created_by=self.user)
        return journal

    def test_jakarta_payment_hits_kas_jakarta_and_not_sby_idle(self):
        journal = self._pay('jkt')

        cash_lines = [l for l in journal.lines.all() if l.amount_sar > 0]
        self.assertEqual(len(cash_lines), 1)
        self.assertEqual(cash_lines[0].account_id, coa.CASH_JKT)

        mov = CashMovement.objects.get(invoice=self.invoice)
        self.assertEqual(mov.to_account, WalletAccount.JKT)

        breakdown = ledger.reservation_cash_breakdown()
        row = breakdown[self.res.pk]
        self.assertEqual(row['terbayar_jkt'], 300)
        self.assertEqual(row['mengendap'], 0)          # bukan uang Surabaya
        self.assertEqual(row['mengendap_jkt'], 300)    # mengendap di Jakarta

    def test_pusat_payment_counts_as_already_sent(self):
        self._pay('pusat')

        mov = CashMovement.objects.get(invoice=self.invoice)
        self.assertEqual(mov.to_account, WalletAccount.PUSAT)

        row = ledger.reservation_cash_breakdown()[self.res.pk]
        self.assertEqual(row['terbayar_direct'], 300)
        self.assertEqual(row['sudah_dikirim'], 300)
        self.assertEqual(row['mengendap'], 0)
        self.assertEqual(row['mengendap_jkt'], 0)

    def test_surabaya_payment_still_idles_in_surabaya(self):
        self._pay('sby')

        row = ledger.reservation_cash_breakdown()[self.res.pk]
        self.assertEqual(row['terbayar_sby'], 300)
        self.assertEqual(row['mengendap'], 300)
        self.assertEqual(row['mengendap_jkt'], 0)


class KasJakartaWalletTest(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(company='konoz', name='PT Wallet')
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel',
            invoice_number='INV-WALLET-001', customer_name='PT Wallet',
        )

    def test_kas_jakarta_nets_in_and_out(self):
        CashMovement.objects.create(
            company='konoz', client=self.client_obj, invoice=self.invoice, date='2026-01-01',
            from_account=WalletAccount.CLIENT, to_account=WalletAccount.JKT,
            amount=500, currency='SAR', exchange_rate=1,
        )
        CashMovement.objects.create(
            company='konoz', client=self.client_obj, invoice=self.invoice, date='2026-01-02',
            from_account=WalletAccount.JKT, to_account=WalletAccount.PUSAT,
            amount=200, currency='SAR', exchange_rate=1,
        )
        self.assertEqual(ledger.kas_jakarta(), 300)
        self.assertEqual(ledger.kas_surabaya(), 0)
