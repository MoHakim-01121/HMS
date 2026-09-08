"""Receive → Apply flow: auto-post at receive, derived status, apply & void endpoints.

Covers the new Receive→Apply redesign:
- Recording a payment auto-posts the journal (no manual confirm) and sets
  a derived status (received / partially_applied / applied).
- The apply endpoint re-allocates an existing received payment to
  reservations and derives the new status.
- Over-allocation is rejected.
- Void posts a reversal and marks the payment voided.
"""
import json
import base64
from datetime import date

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from hw.models import Client, Invoice, Reservation, PaymentRecord, PaymentAllocation
from hw.models.period import FinancialPeriod
from hw.models.journal import JournalEntry, JournalLine
from hw.finance import accounts as coa
from hw.finance import queries as fq
from hw.finance import posting


class ReceiveApplyFlowTest(TestCase):
    def setUp(self):
        u = User.objects.create_user('apply', password='pw12345')
        u.profile.role = 'manager'
        u.profile.save(update_fields=['role'])
        self.user = u
        self.client.force_login(u)
        s = self.client.session
        s['active_company'] = 'konoz'
        s.save()

        self.client_obj = Client.objects.create(company='konoz', name='PT Apply')
        self.invoice = Invoice.objects.create(
            company='konoz', invoice_type='hotel', client=self.client_obj,
            invoice_number='INV-APPLY-001', customer_name='PT Apply',
        )
        self.r1 = Reservation.objects.create(
            invoice=self.invoice, reservation_number='AP-1', total_sar=15000,
        )
        self.r2 = Reservation.objects.create(
            invoice=self.invoice, reservation_number='AP-2', total_sar=8000,
        )
        FinancialPeriod.objects.create(
            name='2026-08', date_from=date(2026, 8, 1), date_to=date(2026, 8, 31),
        )

        posting.post_entry(
            entry_type=JournalEntry.TYPE_CHARGE,
            description='Charge INV-APPLY-001',
            entry_date=date(2026, 8, 10),
            lines=[
                {"account": coa.AR, "debit": 23000, "client": self.client_obj.pk, "invoice": self.invoice.pk},
                {"account": coa.INC_HOTEL, "credit": 23000, "client": self.client_obj.pk, "invoice": self.invoice.pk},
            ],
            company='konoz', source_type='Invoice', source_id=self.invoice.pk,
            idempotency_key='charge:INV-APPLY-001',
            created_by=u,
        )

    def _post(self, amount, allocations=None):
        payload = {
            'invoice_id': self.invoice.pk,
            'payment_date': '2026-08-15',
            'amount': amount,
            'currency': 'SAR',
            'exchange_rate': '1',
            'received_in': 'sby',
            'method': 'Transfer',
        }
        if allocations:
            payload['allocations'] = json.dumps(allocations)
        # A real 1x1 PNG so the proof MIME sniff (magic.from_buffer) passes.
        payload['proof'] = SimpleUploadedFile(
            'proof.png',
            base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='
            ),
            content_type='image/png',
        )
        return self.client.post('/finance/payments/record/', payload)


class RecordAutoPostTest(ReceiveApplyFlowTest):
    def test_record_without_allocation_is_received_and_posted(self):
        """Recording a payment with no allocation → status received, journal posted."""
        resp = self._post(5000)
        payment = PaymentRecord.objects.get(invoice=self.invoice)
        self.assertEqual(payment.status, PaymentRecord.STATUS_RECEIVED)
        self.assertEqual(payment.amount_sar, 5000)

        # Journal is posted immediately (DR Cash / CR AR).
        live = JournalEntry.objects.filter(
            reference_type='PaymentRecord', reference_id=payment.pk,
            is_reversal=False,
        ).exclude(reverses__isnull=False)
        self.assertTrue(live.exists())

        # Unallocated = the full amount.
        self.assertEqual(fq.payment_unallocated_sar(payment.pk), 5000)

    def test_record_fully_allocated_is_applied(self):
        """Recording with allocations summing to the amount → status applied."""
        resp = self._post(5000, [
            {'reservation_id': self.r1.pk, 'amount': 3000},
            {'reservation_id': self.r2.pk, 'amount': 2000},
        ])
        payment = PaymentRecord.objects.get(invoice=self.invoice)
        self.assertEqual(payment.status, PaymentRecord.STATUS_APPLIED)
        self.assertEqual(fq.payment_unallocated_sar(payment.pk), 0)


class ApplyEndpointTest(ReceiveApplyFlowTest):
    def _record_unallocated(self, amount=7000):
        resp = self._post(amount)
        return PaymentRecord.objects.get(invoice=self.invoice)

    def test_apply_received_payment_to_reservation(self):
        payment = self._record_unallocated(7000)
        self.assertEqual(payment.status, PaymentRecord.STATUS_RECEIVED)

        resp = self.client.post(
            f'/finance/payments/{payment.pk}/apply/',
            {'allocations': json.dumps([
                {'reservation_id': self.r1.pk, 'amount': 4000},
                {'reservation_id': self.r2.pk, 'amount': 3000},
            ])},
        )

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRecord.STATUS_APPLIED)
        self.assertEqual(fq.payment_unallocated_sar(payment.pk), 0)

        # Journal CR AR carries reservation dimensions now.
        line = JournalLine.objects.filter(
            journal_entry__reference_type='PaymentRecord',
            journal_entry__reference_id=payment.pk,
            account_id=coa.AR, credit__gt=0, reservation_id=self.r1.pk,
        ).first()
        self.assertIsNotNone(line)
        self.assertEqual(line.credit, 4000)

    def test_apply_partial_sets_partially_applied(self):
        payment = self._record_unallocated(7000)
        resp = self.client.post(
            f'/finance/payments/{payment.pk}/apply/',
            {'allocations': json.dumps([
                {'reservation_id': self.r1.pk, 'amount': 3000},
            ])},
        )
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRecord.STATUS_PARTIALLY_APPLIED)
        self.assertEqual(fq.payment_unallocated_sar(payment.pk), 4000)

    def test_apply_over_payment_rejected(self):
        payment = self._record_unallocated(5000)
        resp = self.client.post(
            f'/finance/payments/{payment.pk}/apply/',
            {'allocations': json.dumps([
                {'reservation_id': self.r1.pk, 'amount': 6000},
            ])},
        )
        payment.refresh_from_db()
        # Unchanged — still received, no allocations.
        self.assertEqual(payment.status, PaymentRecord.STATUS_RECEIVED)
        self.assertEqual(PaymentAllocation.objects.filter(payment=payment).count(), 0)


class VoidEndpointTest(ReceiveApplyFlowTest):
    def _record_unallocated(self, amount=5000):
        self._post(amount)
        return PaymentRecord.objects.get(invoice=self.invoice)

    def test_void_posts_reversal_and_marks_voided(self):
        payment = self._record_unallocated(5000)
        # Original journal is live.
        original_entry = JournalEntry.objects.filter(
            reference_type='PaymentRecord', reference_id=payment.pk,
            is_reversal=False,
        ).exclude(reverses__isnull=False).first()
        self.assertIsNotNone(original_entry)

        resp = self.client.post(f'/finance/payments/{payment.pk}/void/')

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRecord.STATUS_VOIDED)

        # A reversal of the original entry now exists.
        self.assertTrue(
            JournalEntry.objects.filter(
                reverses=original_entry, is_reversal=True,
            ).exists()
        )
