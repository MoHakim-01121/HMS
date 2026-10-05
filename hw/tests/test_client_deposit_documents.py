"""Schema v2 F5d: refund dan transfer deposit adalah dokumen bernomor."""
from datetime import date

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

from hw.finance import posting, queries as fq
from hw.finance.deposit import request_refund, request_transfer
from hw.finance.errors import FinanceError
from hw.models import ClientRefund, ClientTransfer, Client
from hw.models.bank_transaction import BankTransaction
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_account, refund_now as refund_deposit, transfer_now as transfer_deposit


class _Base(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('dd', password='pw12345')
        self.client.force_login(self.user)
        FinancialPeriod.objects.create(name='2026', date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        self.a = Client.objects.create(name='PT Asal')
        self.b = Client.objects.create(name='PT Tujuan')
        posting.post_adjustment(
            lines=[{"account": posting.coa.CASH_SBY, "debit": 5_000},
                   {"account": posting.coa.CUST_CREDIT, "credit": 5_000, "client": self.a.pk}],
            description='deposit awal', entry_date=date(2026, 3, 1), created_by=self.user,
        )


class RefundDocumentTest(_Base):
    def test_refund_is_a_numbered_document_with_its_entry(self):
        idr = make_account('sby', 'IDR')
        refund = refund_deposit(self.a, account=idr, amount_sar=2_000, amount_paid=9_800_000,
                                refund_date=date(2026, 3, 10), created_by=self.user)
        self.assertEqual(refund.refund_number, 'RFD-202603-001')
        self.assertEqual(fq.client_credit_balance(self.a.pk), 3_000)
        credit = refund.journal_entry.lines.get(credit__gt=0)
        self.assertEqual((credit.account_id, credit.credit), (idr.ledger_account_id, 2_000))
        tx = BankTransaction.objects.get(source_type='Refund', source_id=refund.journal_entry.pk)
        self.assertEqual((tx.amount, tx.currency), (9_800_000, 'IDR'))

    def test_refund_cannot_exceed_the_deposit(self):
        with self.assertRaisesMessage(FinanceError, 'hanya 5,000'):
            request_refund(self.a, account=make_account('sby', 'SAR'), amount_sar=6_000, amount_paid=6_000,
                           refund_date=date(2026, 3, 10), created_by=self.user)
        self.assertFalse(ClientRefund.objects.exists())

    def test_sar_account_pays_the_same_amount(self):
        with self.assertRaises(FinanceError):
            request_refund(self.a, account=make_account('sby', 'SAR'), amount_sar=1_000, amount_paid=900,
                           refund_date=date(2026, 3, 10), created_by=self.user)


class DepositTransferTest(_Base):
    def test_deposit_moves_to_another_client(self):
        resp = self.client.post(f'/finance/clients/{self.a.pk}/deposit-transfer/', {
            'to_client': str(self.b.pk), 'amount_sar': '1500', 'note': 'grup digabung',
        })
        self.assertEqual(resp.status_code, 302)
        transfer = ClientTransfer.objects.get()
        self.assertEqual((transfer.transfer_number, transfer.amount_sar), ('DTR-' + date.today().strftime('%Y%m') + '-001', 1_500))
        # Recorded, not yet moved: a second person (or an admin) approves it.
        self.assertEqual(transfer.status, 'pending')
        self.assertEqual((fq.client_credit_balance(self.a.pk), fq.client_credit_balance(self.b.pk)), (5_000, 0))
        self.client.post(f'/finance/deposit-transfers/{transfer.pk}/confirm/')
        self.assertEqual((fq.client_credit_balance(self.a.pk), fq.client_credit_balance(self.b.pk)), (3_500, 1_500))

    def test_transfer_cannot_exceed_the_deposit_or_go_to_itself(self):
        with self.assertRaises(FinanceError):
            request_transfer(self.a, self.b, amount_sar=9_000, transfer_date=date(2026, 3, 10), created_by=self.user)
        with self.assertRaises(FinanceError):
            request_transfer(self.a, self.a, amount_sar=100, transfer_date=date(2026, 3, 10), created_by=self.user)
        self.assertFalse(ClientTransfer.objects.exists())

    def test_database_refuses_a_transfer_to_the_same_client(self):
        t = transfer_deposit(self.a, self.b, amount_sar=100, transfer_date=date(2026, 3, 10), created_by=self.user)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ClientTransfer.objects.filter(pk=t.pk).update(to_client=self.a)

    def test_form_renders(self):
        resp = self.client.get(f'/finance/clients/{self.a.pk}/deposit-transfer/', HTTP_X_INERTIA='true')
        props = resp.json()['props']
        self.assertEqual((resp.json()['component'], props['client']['saldo_dana']), ('Finance/DepositTransfer', 5_000))
        self.assertNotIn(self.a.pk, [c['id'] for c in props['clients']])
