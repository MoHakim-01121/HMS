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
