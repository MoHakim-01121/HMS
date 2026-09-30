"""Dead payments must not keep allocations; a refused deposit apply must not
bind the deposit to an invoice.

1. Reverse used to flip the status without dropping PaymentAllocation rows
   (Void and Reject already did), so a reversed payment still read as
   allocated and blocked its reservations from being deleted off the invoice.
2. Reverse accepted a PENDING payment -- no journal to reverse, so it must go
   through Reject.
3. Applying a deposit saved the target invoice before the reservations were
   validated: a refused request left the deposit stuck on that invoice.
"""
import json
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hw.finance import posting
from hw.finance_helpers import confirm_payment, create_payment_record
from hw.models import Client, PaymentRecord
from hw.models.payment import PaymentLog
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_hotel_line, make_invoice


class DeadPaymentAllocationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('deadalloc', password='pw12345')
        self.user.profile.role = 'manager'
        self.user.profile.save(update_fields=['role'])
        self.client.force_login(self.user)
        FinancialPeriod.objects.create(
            name='2020-2030', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.client_obj = Client.objects.create(name='PT Dead Alloc')
        self.invoice = make_invoice(
            invoice_type='hotel', client=self.client_obj,
            invoice_number='INV-DEAD-001', customer_name='PT Dead Alloc',
        )
        self.res = make_hotel_line(
            invoice=self.invoice, reservation_number='DEAD-R1', total_sar=10000,
        )
        other_invoice = make_invoice(
            invoice_type='hotel', client=self.client_obj,
            invoice_number='INV-DEAD-002', customer_name='PT Dead Alloc',
        )
        self.foreign_res = make_hotel_line(
            invoice=other_invoice, reservation_number='DEAD-R9', total_sar=5000,
        )

    def _payment(self, invoice, amount=6000, allocate=True, confirm=True):
        pr = create_payment_record(
            invoice=invoice, client=self.client_obj,
            payment_date=date(2026, 8, 20), amount=amount, currency='SAR',
            method='Transfer', created_by=self.user,
        )
        if allocate:
            posting.allocate_payment(pr, [(self.res, amount)], created_by=self.user)
        if confirm:
            confirm_payment(pr, confirmed_by=self.user)
            pr.status = pr.derive_status()
            pr.save(update_fields=['status'])
        return pr

    # -- 1 + 2: reverse ------------------------------------------------------

    def test_reverse_drops_allocations_and_logs_them(self):
        pr = self._payment(self.invoice)
        self.assertTrue(pr.allocations.exists())

        self.client.post(f'/finance/payments/{pr.pk}/reverse/')

        pr.refresh_from_db()
        self.assertEqual(pr.status, PaymentRecord.STATUS_REVERSED)
        self.assertFalse(pr.allocations.exists())
        log = pr.logs.filter(action=PaymentLog.ACTION_REVERSED).get()
        self.assertEqual(log.before_state['allocations'][0]['amount_sar'], 6000)

    def test_reverse_refuses_pending_payment(self):
        pr = self._payment(self.invoice, confirm=False)
        self.assertEqual(pr.status, PaymentRecord.STATUS_PENDING)

        self.client.post(f'/finance/payments/{pr.pk}/reverse/')

        pr.refresh_from_db()
        self.assertEqual(pr.status, PaymentRecord.STATUS_PENDING)
        self.assertTrue(pr.allocations.exists())

    # -- 3: deposit apply ----------------------------------------------------

    def test_refused_deposit_apply_leaves_deposit_unbound(self):
        deposit = self._payment(None, allocate=False)
        self.assertIsNone(deposit.invoice_id)

        self.client.post(f'/finance/payments/{deposit.pk}/apply/', {
            'invoice_id': str(self.invoice.pk),
            'allocations': json.dumps([{'reservation_id': self.foreign_res.pk, 'amount': 3000}]),
        })

        deposit.refresh_from_db()
        self.assertIsNone(deposit.invoice_id)
        self.assertFalse(deposit.allocations.exists())

    def test_accepted_deposit_apply_binds_invoice(self):
        deposit = self._payment(None, allocate=False)

        self.client.post(f'/finance/payments/{deposit.pk}/apply/', {
            'invoice_id': str(self.invoice.pk),
            'allocations': json.dumps([{'reservation_id': self.res.pk, 'amount': 6000}]),
        })

        deposit.refresh_from_db()
        self.assertEqual(deposit.invoice_id, self.invoice.pk)
        self.assertEqual(deposit.status, PaymentRecord.STATUS_APPLIED)
