"""Schema v2 F5c: pembayaran X/Y/Z, kelebihan → deposit, Services ke cabang penerbit."""
import json
from datetime import date

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

from hw.finance import posting, queries as fq
from hw.finance.errors import FinanceError
from hw.finance_helpers import confirm_payment, create_payment_record
from hw.models import CancellationPenalty, Client, ConfirmationLetter, Invoice, PaymentRecord
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_account, make_hotel_line, make_invoice


class _Base(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('dep', password='pw12345')
        self.client.force_login(self.user)
        FinancialPeriod.objects.create(name='2026', date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        self.client_obj = Client.objects.create(name='PT Deposit')
        self.inv = make_invoice(client=self.client_obj, issued_date=date(2026, 3, 1))
        self.line = make_hotel_line(invoice=self.inv, reservation_number='7701', total_sar=10_000)
        posting.post_invoice_charge(self.inv, created_by=self.user)


class PaymentColumnsTest(_Base):
    def test_currency_and_branch_come_from_the_receiving_account(self):
        idr = make_account('jkt', 'IDR')
        p = create_payment_record(self.inv, self.client_obj, date(2026, 3, 5), 49_000_000, currency='IDR',
                                  exchange_rate=4900, method='Transfer', receiving_account=idr, created_by=self.user)
        self.assertEqual((p.currency, p.receiving_branch_code, p.received_in, p.amount_sar), ('IDR', 'jkt', 'jkt', 10_000))
        fields = {f.name for f in PaymentRecord._meta.get_fields()}
        self.assertFalse({'currency', 'received_in', 'bank_name', 'account_number', 'period'} & fields)
        self.assertEqual(p.period.name, '2026')

    def test_status_is_lifecycle_and_allocation_state_is_derived(self):
        p = create_payment_record(self.inv, self.client_obj, date(2026, 3, 5), 4_000, method='Transfer', created_by=self.user)
        self.assertEqual((p.status, p.allocation_state, p.display_status), ('pending', None, 'pending'))
        confirm_payment(p, self.user)
        self.assertEqual((p.status, p.allocation_state, p.display_status), ('confirmed', 'unallocated', 'received'))
        posting.reallocate_payment(p, [(self.line, 1_000)], created_by=self.user)
        p = PaymentRecord.objects.get(pk=p.pk)
        self.assertEqual((p.status, p.allocation_state, p.display_status), ('confirmed', 'partial', 'partially_applied'))
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentRecord.objects.filter(pk=p.pk).update(status='applied')

    def test_whole_amounts_only(self):
        resp = self.client.post('/finance/payments/record/', {
            'invoice_id': self.inv.pk, 'payment_date': '2026-03-05', 'amount': '100.5', 'method': 'Transfer',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(PaymentRecord.objects.exists())


class ExcessToDepositTest(_Base):
    def _pay(self, amount, allocate=None):
        p = create_payment_record(self.inv, self.client_obj, date(2026, 3, 5), amount, method='Transfer',
                                  created_by=self.user)
        if allocate:
            posting.allocate_payment(p, [(self.line, allocate)], created_by=self.user)
        confirm_payment(p, self.user)
        return PaymentRecord.objects.get(pk=p.pk)

    def test_payment_excess_stays_until_moved(self):
        p = self._pay(12_000, allocate=10_000)
        self.assertEqual((p.unallocated_sar, fq.client_credit_balance(self.client_obj.pk)), (2_000, 0))
        resp = self.client.post(f'/finance/payments/{p.pk}/to-deposit/')
        self.assertEqual(resp.status_code, 302)
        p = PaymentRecord.objects.get(pk=p.pk)
        self.assertEqual((p.deposited_sar, p.unallocated_sar, p.allocation_state), (2_000, 0, 'allocated'))
        self.assertEqual(fq.client_credit_balance(self.client_obj.pk), 2_000)
        self.assertEqual(fq.invoice_paid_sar(self.inv.pk), 10_000)      # the excess left the invoice
        self.assertEqual(Invoice.objects.get(pk=self.inv.pk).remaining_sar, 0)
        with self.assertRaises(FinanceError):                            # nothing left to move
            posting.move_payment_excess_to_deposit(p, created_by=self.user)

    def test_moved_money_cannot_be_allocated_again(self):
        p = self._pay(12_000, allocate=10_000)
        posting.move_payment_excess_to_deposit(p, created_by=self.user)
        p = PaymentRecord.objects.get(pk=p.pk)
        with self.assertRaises(FinanceError):
            posting.reallocate_payment(p, [(self.line, 12_000)], created_by=self.user)

    def test_voiding_a_payment_brings_its_deposit_back_first(self):
        p = self._pay(12_000, allocate=10_000)
        posting.move_payment_excess_to_deposit(p, created_by=self.user)
        resp = self.client.post(f'/finance/payments/{p.pk}/void/', {'reason': 'salah input'})
        self.assertEqual(resp.status_code, 302)
        p = PaymentRecord.objects.get(pk=p.pk)
        self.assertEqual((p.status, p.deposited_sar), ('voided', 0))
        self.assertEqual(fq.client_credit_balance(self.client_obj.pk), 0)

    def test_reservation_overpayment_after_a_penalty_moves_to_deposit(self):
        from hw.finance.penalty_billing import bill_penalty
        self._pay(10_000, allocate=10_000)
        cl = self.line.confirmation_letter
        ConfirmationLetter.objects.filter(pk=cl.pk).update(reservation_status='CANCELLED')
        pen = CancellationPenalty.objects.create(cl=cl, penalty_number='PNL-77', cancellation_date=date(2026, 3, 9),
                                                 penalty_amount=4_000)
        bill_penalty(pen, user=self.user)
        detail = self.client.get(f'/invoice/{self.inv.pk}/', HTTP_X_INERTIA='true').json()['props']
        self.assertEqual(detail['excess_sar'], 6_000)
        resp = self.client.post(f'/finance/invoices/{self.inv.pk}/excess-to-deposit/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(fq.client_credit_balance(self.client_obj.pk), 6_000)
        inv = Invoice.objects.get(pk=self.inv.pk)
        self.assertEqual((inv.total_sar, inv.remaining_sar), (4_000, 0))
        self.assertTrue(CancellationPenalty.objects.get(pk=pen.pk).is_paid)   # the penalty stays paid


