"""FASE I (partial) — BankTransaction recorded as a side effect of cash-affecting posting."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.models import BankTransaction, Branch, CashAccount, Client, Invoice, Remittance
from hw.models.period import FinancialPeriod
from hw.finance import expense_service, posting, settlement_service
from hw.finance_helpers import create_payment_record, confirm_payment


class BankTransactionBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('bt', password='pw12345')
        FinancialPeriod.objects.create(
            name='2020-2030',            date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.sby = Branch.objects.get(code='sby')
        self.cash_sby = CashAccount.objects.get(branch_id='sby')


class PaymentBankTransactionTest(BankTransactionBase):
    def test_confirming_payment_with_receiving_account_records_transaction(self):
        client_obj = Client.objects.create( name='PT BT')
        inv = Invoice.objects.create(invoice_number='INV-BT-1', customer_name='PT BT', client=client_obj)
        pr = create_payment_record(
            inv, client_obj, date(2026, 7, 1), 5000, method='Transfer',
            cash_account=self.cash_sby, created_by=self.user,
        )
        confirm_payment(pr, self.user)
        tx = BankTransaction.objects.get(source_type='PaymentRecord', source_id=pr.pk)
        self.assertEqual(tx.cash_account_id, self.cash_sby.pk)
        self.assertEqual(tx.direction, 'in')
        self.assertEqual(tx.amount_sar, 5000)

    def test_legacy_payment_without_receiving_account_records_nothing(self):
        # A genuinely legacy row -- created directly (bypassing
        # create_payment_record's auto-derivation of cash_account from
        # received_in) to simulate data from before FASE C existed.
        from hw.models.payment import PaymentRecord
        from hw.models.period import FinancialPeriod as FP
        client_obj = Client.objects.create( name='PT BT2')
        inv = Invoice.objects.create(invoice_number='INV-BT-2', customer_name='PT BT2', client=client_obj)
        pr = PaymentRecord.objects.create(
            payment_number='PAY-BT-2', invoice=inv, client=client_obj,
            payment_date=date(2026, 7, 1), amount=5000, amount_sar=5000,
            method='Transfer', received_in='jkt', status=PaymentRecord.STATUS_PENDING,
 created_by=self.user, period=FP.objects.first(),
        )
        confirm_payment(pr, self.user)
        self.assertFalse(BankTransaction.objects.filter(source_type='PaymentRecord', source_id=pr.pk).exists())

    def test_reconfirm_does_not_duplicate_transaction(self):
        client_obj = Client.objects.create( name='PT BT3')
        inv = Invoice.objects.create(invoice_number='INV-BT-3', customer_name='PT BT3', client=client_obj)
        pr = create_payment_record(
            inv, client_obj, date(2026, 7, 1), 5000, method='Transfer',
            cash_account=self.cash_sby, created_by=self.user,
        )
        confirm_payment(pr, self.user)
        posting.post_payment(pr, created_by=self.user)  # idempotent re-post
        self.assertEqual(BankTransaction.objects.filter(source_type='PaymentRecord', source_id=pr.pk).count(), 1)


class ExpensePaymentBankTransactionTest(BankTransactionBase):
    def test_expense_payment_records_out_transaction(self):
        from hw.models import ExpenseCategory
        util = ExpenseCategory.objects.get(code='UTIL')
        exp = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 7, 2), created_by=self.user,
            lines=[{'category': util, 'amount': 1500}],
        )
        ep = expense_service.add_expense_payment(
            exp, amount=1500, payment_date=date(2026, 7, 3),
            cash_account=self.cash_sby, created_by=self.user,
        )
        tx = BankTransaction.objects.get(source_type='ExpensePayment', source_id=ep.pk)
        self.assertEqual(tx.direction, 'out')
        self.assertEqual(tx.amount_sar, 1500)


class SettlementBankTransactionTest(BankTransactionBase):
    def test_settlement_records_in_transaction_against_pusat_cash(self):
        rmt = Remittance.objects.create( date=date(2026, 7, 4), remittance_number='RMT-BT-1')
        settlement = settlement_service.add_settlement(
            rmt, received_amount_sar=20000, received_date=date(2026, 7, 5), created_by=self.user,
        )
        tx = BankTransaction.objects.get(source_type='RemittanceSettlement', source_id=settlement.pk)
        self.assertEqual(tx.cash_account.branch_id, 'pusat')
        self.assertEqual(tx.direction, 'in')
        self.assertEqual(tx.amount_sar, 20000)


class OriginalAmountTest(BankTransactionBase):
    """The cash log keeps the money that actually moved (rupiah/dollars), not
    only its SAR value — the fund-flow report reads it from here."""

    def _idr_account(self):
        from hw.models import BankAccount, LedgerAccount
        return BankAccount.objects.create(branch_id='sby', name='IDR', currency='IDR', bank_name='Mandiri',
                                          account_identifier='901', ledger_account=LedgerAccount.objects.get(code='1000-KAS-SBY'))

    def test_idr_payment_keeps_rupiah_amount(self):
        client_obj = Client.objects.create(name='PT BT IDR')
        inv = Invoice.objects.create(invoice_number='INV-BT-IDR', customer_name='PT BT IDR', client=client_obj)
        pr = create_payment_record(
            inv, client_obj, date(2026, 7, 1), 49_000_000, currency='IDR', exchange_rate=4900,
            method='Transfer', bank_account=self._idr_account(), created_by=self.user,
        )
        confirm_payment(pr, self.user)
        tx = BankTransaction.objects.get(source_type='PaymentRecord', source_id=pr.pk)
        self.assertEqual((tx.currency, tx.amount, tx.amount_sar), ('IDR', 49_000_000, 10_000))

    def test_idr_expense_payment_keeps_rupiah_amount(self):
        from hw.models import ExpenseCategory
        exp = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 7, 2), created_by=self.user,
            lines=[{'category': ExpenseCategory.objects.get(code='UTIL'), 'amount': 100}],
        )
        ep = expense_service.add_expense_payment(
            exp, amount=475_000, currency='IDR', exchange_rate=4750, payment_date=date(2026, 7, 3),
            bank_account=self._idr_account(), created_by=self.user,
        )
        tx = BankTransaction.objects.get(source_type='ExpensePayment', source_id=ep.pk)
        self.assertEqual((tx.direction, tx.currency, tx.amount, tx.amount_sar), ('out', 'IDR', 475_000, 100))

    def test_sar_settlement_amount_equals_sar_value(self):
        rmt = Remittance.objects.create(date=date(2026, 7, 4), remittance_number='RMT-BT-2')
        s = settlement_service.add_settlement(
            rmt, received_amount_sar=20000, received_date=date(2026, 7, 5), created_by=self.user,
        )
        tx = BankTransaction.objects.get(source_type='RemittanceSettlement', source_id=s.pk)
        self.assertEqual((tx.currency, tx.amount), ('SAR', 20000))

    def test_non_sar_movement_without_amount_is_refused(self):
        from hw.finance.bank_ledger import record_bank_transaction
        with self.assertRaises(ValueError):
            record_bank_transaction(
                account=self.cash_sby, direction='in', amount_sar=10, currency='IDR',
                source_type='Test', source_id=1, transaction_date=date(2026, 7, 1),
            )


class VoidedCashRowTest(BankTransactionBase):
    """A reversed/voided document's cash row stops counting as money that
    moved, unless it was already matched to a bank statement line."""

    def _paid(self, number):
        client_obj = Client.objects.create(name=f'PT {number}')
        inv = Invoice.objects.create(invoice_number=number, customer_name='X', client=client_obj)
        pr = create_payment_record(
            inv, client_obj, date(2026, 7, 1), 5000, method='Transfer',
            cash_account=self.cash_sby, created_by=self.user,
        )
        confirm_payment(pr, self.user)
        return pr

    def _retire(self, pr):
        from hw.models.payment import PaymentLog, PaymentRecord
        from hw.views.payment_views import _retire_payment
        _retire_payment(
            pr, status=PaymentRecord.STATUS_REVERSED, action=PaymentLog.ACTION_REVERSED,
            reversal_date=date(2026, 7, 2), journal_note='test', user=self.user,
        )

    def test_reversed_payment_voids_its_cash_row(self):
        from hw.finance import queries
        pr = self._paid('INV-BT-V1')
        self._retire(pr)
        tx = BankTransaction.objects.get(source_type='PaymentRecord', source_id=pr.pk)
        self.assertEqual(tx.status, BankTransaction.STATUS_VOIDED)
        ids = [r['id'] for r in queries.account_transactions('cash', self.cash_sby.pk)['rows']]
        self.assertNotIn(tx.pk, ids)

    def test_reconciled_payment_cannot_be_reversed(self):
        from hw.finance import reconciliation_service as rs
        from hw.finance.errors import FinanceError
        from hw.models.payment import PaymentRecord
        pr = self._paid('INV-BT-V2')
        tx = BankTransaction.objects.get(source_type='PaymentRecord', source_id=pr.pk)
        st = rs.create_statement(
            account=self.cash_sby, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            opening_balance=0, closing_balance=5000,
            lines=[{'line_date': date(2026, 7, 1), 'description': 'in', 'direction': 'in', 'amount': 5000}],
        )
        rs.match_line(st.lines.first(), tx)
        with self.assertRaises(FinanceError):
            self._retire(pr)
        pr.refresh_from_db()
        self.assertNotEqual(pr.status, PaymentRecord.STATUS_REVERSED)  # rolled back

    def test_voided_expense_voids_its_cash_row(self):
        from hw.models import ExpenseCategory
        exp = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 7, 2), created_by=self.user,
            lines=[{'category': ExpenseCategory.objects.get(code='UTIL'), 'amount': 700}],
        )
        ep = expense_service.add_expense_payment(
            exp, amount=700, payment_date=date(2026, 7, 3), cash_account=self.cash_sby, created_by=self.user,
        )
        expense_service.void_expense(exp, created_by=self.user, date=date(2026, 7, 4))
        tx = BankTransaction.objects.get(source_type='ExpensePayment', source_id=ep.pk)
        self.assertEqual(tx.status, BankTransaction.STATUS_VOIDED)


class AccountCurrencyTest(BankTransactionBase):
    """Money is received into / paid from an account of its own currency."""

    def _idr_bank(self):
        from hw.models import BankAccount, LedgerAccount
        return BankAccount.objects.create(branch_id='sby', name='IDR', currency='IDR', bank_name='Mandiri',
                                          account_identifier='900', ledger_account=LedgerAccount.objects.get(code='1000-KAS-SBY'))

    def _inv(self, number):
        client_obj = Client.objects.create(name=f'PT {number}')
        return Invoice.objects.create(invoice_number=number, customer_name='X', client=client_obj), client_obj

    def test_idr_payment_defaults_to_the_branch_idr_account(self):
        acc = self._idr_bank()
        inv, client_obj = self._inv('INV-CUR-1')
        pr = create_payment_record(inv, client_obj, date(2026, 7, 1), 4_900_000, currency='IDR', exchange_rate=4900,
                                   method='Transfer', received_in='sby', created_by=self.user)
        self.assertEqual((pr.bank_account_id, pr.cash_account_id), (acc.pk, None))

    def test_idr_payment_without_idr_account_is_not_put_in_the_sar_till(self):
        inv, client_obj = self._inv('INV-CUR-2')
        pr = create_payment_record(inv, client_obj, date(2026, 7, 1), 4_900_000, currency='IDR', exchange_rate=4900,
                                   method='Transfer', received_in='sby', created_by=self.user)
        self.assertIsNone(pr.bank_account_id)
        self.assertIsNone(pr.cash_account_id)

    def test_explicit_account_in_another_currency_is_refused(self):
        from hw.finance.errors import FinanceError
        inv, client_obj = self._inv('INV-CUR-3')
        with self.assertRaises(FinanceError):
            create_payment_record(inv, client_obj, date(2026, 7, 1), 4_900_000, currency='IDR', exchange_rate=4900,
                                  method='Transfer', cash_account=self.cash_sby, created_by=self.user)

    def test_expense_paid_from_account_in_another_currency_is_refused(self):
        from hw.finance.errors import FinanceError
        from hw.models import ExpenseCategory
        exp = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 7, 2), created_by=self.user,
            lines=[{'category': ExpenseCategory.objects.get(code='UTIL'), 'amount': 100}],
        )
        with self.assertRaises(FinanceError):
            expense_service.add_expense_payment(exp, amount=475_000, currency='IDR', exchange_rate=4750,
                                                payment_date=date(2026, 7, 3), cash_account=self.cash_sby, created_by=self.user)

    def test_expense_paid_from_another_branch_account_is_refused(self):
        from hw.finance.errors import FinanceError
        from hw.models import ExpenseCategory
        exp = expense_service.record_expense(
            branch=self.sby, expense_date=date(2026, 7, 2), created_by=self.user,
            lines=[{'category': ExpenseCategory.objects.get(code='UTIL'), 'amount': 100}],
        )
        with self.assertRaises(FinanceError):
            expense_service.add_expense_payment(exp, amount=100, payment_date=date(2026, 7, 3),
                                                cash_account=CashAccount.objects.get(branch_id='jkt'),
                                                created_by=self.user)


class HqReceivesSarOnlyTest(BankTransactionBase):
    """Pusat only ever receives SAR; rupiah/dollars are collected and
    exchanged at a branch and reach HQ as SAR through remittances."""

    def test_idr_payment_received_at_hq_is_refused(self):
        from hw.finance.errors import FinanceError
        client_obj = Client.objects.create(name='PT HQ')
        inv = Invoice.objects.create(invoice_number='INV-HQ-1', customer_name='X', client=client_obj)
        with self.assertRaises(FinanceError):
            create_payment_record(inv, client_obj, date(2026, 7, 1), 4_900_000, currency='IDR', exchange_rate=4900,
                                  method='Transfer', received_in='pusat', created_by=self.user)
        pr = create_payment_record(inv, client_obj, date(2026, 7, 1), 1000, method='Transfer',
                                   received_in='pusat', created_by=self.user)
        self.assertEqual(pr.cash_account.branch_id, 'pusat')

    def test_non_sar_penalty_paid_at_hq_is_refused(self):
        from types import SimpleNamespace
        from hw.finance.errors import FinanceError
        with self.assertRaises(FinanceError):
            posting.post_penalty_payment(SimpleNamespace(penalty_currency='IDR', pk=1), created_by=self.user,
                                         received_in='pusat')

    def test_hq_cannot_hold_a_rupiah_account(self):
        u = User.objects.create_superuser('hqadm', password='pw12345')
        self.client.force_login(u)
        resp = self.client.post('/finance/bank-accounts/new/', {
            'branch': 'pusat', 'bank_name': 'Mandiri', 'account_identifier': '123', 'currency': 'IDR',
            'is_active': 'on',
        }, HTTP_X_INERTIA='true')
        self.assertIn('currency', resp.json()['props']['errors'])
