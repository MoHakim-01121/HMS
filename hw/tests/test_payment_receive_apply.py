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

from hw.models import Client, PaymentRecord, PaymentAllocation
from hw.models.period import FinancialPeriod
from hw.models.journal import JournalEntry, JournalLine
from hw.finance import accounts as coa
from hw.finance import queries as fq
from hw.finance import posting
from hw.tests.factories import make_hotel_line, make_invoice


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

        self.client_obj = Client.objects.create( name='PT Apply')
        self.invoice = make_invoice(
 invoice_type='hotel', client=self.client_obj,
            invoice_number='INV-APPLY-001', customer_name='PT Apply',
        )
        self.r1 = make_hotel_line(
            invoice=self.invoice, reservation_number='AP-1', total_sar=15000,
        )
        self.r2 = make_hotel_line(
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
            source_type='Invoice', source_id=self.invoice.pk,
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

    def _confirm(self, payment):
        return self.client.post(f'/finance/payments/{payment.pk}/confirm/')


class RecordPendingFlowTest(ReceiveApplyFlowTest):
    def test_record_without_allocation_is_pending_and_not_posted(self):
        """Recording a payment with no allocation → status pending, no journal."""
        self._post(5000)
        payment = PaymentRecord.objects.get(invoice=self.invoice)
        self.assertEqual(payment.status, PaymentRecord.STATUS_PENDING)
        self.assertEqual(payment.amount_sar, 5000)
        self.assertIsNone(payment.confirmed_by)

        # No journal is posted until the payment is manually confirmed.
        live = JournalEntry.objects.filter(
            reference_type='PaymentRecord', reference_id=payment.pk,
            is_reversal=False,
        ).exclude(reverses__isnull=False)
        self.assertFalse(live.exists())

        self.assertEqual(fq.payment_unallocated_sar(payment.pk), 5000)

    def test_record_fully_allocated_is_pending_until_confirmed(self):
        """Recording with allocations → status pending + allocations saved,
        journal posted only after confirm."""
        self._post(5000, [
            {'reservation_id': self.r1.pk, 'amount': 3000},
            {'reservation_id': self.r2.pk, 'amount': 2000},
        ])
        payment = PaymentRecord.objects.get(invoice=self.invoice)
        self.assertEqual(payment.status, PaymentRecord.STATUS_PENDING)
        self.assertEqual(PaymentAllocation.objects.filter(payment=payment).count(), 2)

        self.client.post(f'/finance/payments/{payment.pk}/confirm/')
        payment.refresh_from_db()
        # Fully allocated → applied after confirm.
        self.assertEqual(payment.display_status, 'applied')
        self.assertEqual(fq.payment_unallocated_sar(payment.pk), 0)


class ApplyEndpointTest(ReceiveApplyFlowTest):
    def _record_unallocated(self, amount=7000):
        self._post(amount)
        payment = PaymentRecord.objects.get(invoice=self.invoice)
        self._confirm(payment)
        payment.refresh_from_db()
        self.assertEqual(payment.display_status, 'received')
        return payment

    def test_apply_received_payment_to_reservation(self):
        payment = self._record_unallocated(7000)
        self.assertEqual(payment.display_status, 'received')

        self.client.post(
            f'/finance/payments/{payment.pk}/apply/',
            {'allocations': json.dumps([
                {'reservation_id': self.r1.pk, 'amount': 4000},
                {'reservation_id': self.r2.pk, 'amount': 3000},
            ])},
        )

        payment.refresh_from_db()
        self.assertEqual(payment.display_status, 'applied')
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
        self.client.post(
            f'/finance/payments/{payment.pk}/apply/',
            {'allocations': json.dumps([
                {'reservation_id': self.r1.pk, 'amount': 3000},
            ])},
        )
        payment.refresh_from_db()
        self.assertEqual(payment.display_status, 'partially_applied')
        self.assertEqual(fq.payment_unallocated_sar(payment.pk), 4000)

    def test_apply_via_json_body(self):
        """The browser's Inertia client posts JSON, not urlencoded — the
        view must read allocations from request.body, never request.POST."""
        payment = self._record_unallocated(5000)
        self.client.post(
            f'/finance/payments/{payment.pk}/apply/',
            data=json.dumps({'allocations': json.dumps([
                {'reservation_id': self.r1.pk, 'amount': 5000},
            ])}),
            content_type='application/json',
        )
        payment.refresh_from_db()
        self.assertEqual(payment.display_status, 'applied')
        self.assertEqual(fq.payment_unallocated_sar(payment.pk), 0)

    def test_apply_allocated_legacy_payment(self):
        """A legacy confirmed/allocated payment can still be applied —
        same status set reallocate_payment accepts."""
        payment = self._record_unallocated(5000)
        payment.status = PaymentRecord.STATUS_CONFIRMED
        payment.save(update_fields=['status'])
        self.client.post(
            f'/finance/payments/{payment.pk}/apply/',
            {'allocations': json.dumps([
                {'reservation_id': self.r1.pk, 'amount': 5000},
            ])},
        )
        payment.refresh_from_db()
        self.assertEqual(payment.display_status, 'applied')
        self.assertEqual(fq.payment_unallocated_sar(payment.pk), 0)

    def test_apply_over_payment_rejected(self):
        payment = self._record_unallocated(5000)
        self.client.post(
            f'/finance/payments/{payment.pk}/apply/',
            {'allocations': json.dumps([
                {'reservation_id': self.r1.pk, 'amount': 6000},
            ])},
        )
        payment.refresh_from_db()
        # Unchanged — still received, no allocations.
        self.assertEqual(payment.display_status, 'received')
        self.assertEqual(PaymentAllocation.objects.filter(payment=payment).count(), 0)


class VoidEndpointTest(ReceiveApplyFlowTest):
    def _record_unallocated(self, amount=5000):
        self._post(amount)
        payment = PaymentRecord.objects.get(invoice=self.invoice)
        self._confirm(payment)
        payment.refresh_from_db()
        return payment

    def test_void_posts_reversal_and_marks_voided(self):
        payment = self._record_unallocated(5000)
        # Original journal is live.
        original_entry = JournalEntry.objects.filter(
            reference_type='PaymentRecord', reference_id=payment.pk,
            is_reversal=False,
        ).exclude(reverses__isnull=False).first()
        self.assertIsNotNone(original_entry)

        self.client.post(f'/finance/payments/{payment.pk}/void/')

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRecord.STATUS_VOIDED)

        # A reversal of the original entry now exists.
        self.assertTrue(
            JournalEntry.objects.filter(
                reverses=original_entry, is_reversal=True,
            ).exists()
        )


class DepositFlowTest(ReceiveApplyFlowTest):
    """Pembayaran tanpa invoice (deposit) → diformat client dulu, dialokasikan
    belakangan ke invoice tujuan via /apply/."""

    def _post_deposit(self, amount=7000, client_id=None, allocations=None):
        payload = {
            'payment_date': '2026-08-15',
            'amount': amount,
            'currency': 'SAR',
            'exchange_rate': '1',
            'received_in': 'sby',
            'method': 'Transfer',
        }
        if client_id:
            payload['client_id'] = client_id
        if allocations:
            payload['allocations'] = json.dumps(allocations)
        payload['proof'] = SimpleUploadedFile(
            'proof.png',
            base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='
            ),
            content_type='image/png',
        )
        return self.client.post('/finance/payments/record/', payload)

    def test_record_deposit_without_invoice(self):
        """Tanpa invoice: client wajib, payment PENDING tanpa alokasi."""
        resp = self._post_deposit(5000, client_id=self.client_obj.pk)
        self.assertEqual(resp.status_code, 302)
        payment = PaymentRecord.objects.get(client=self.client_obj, invoice__isnull=True)
        self.assertEqual(payment.amount_sar, 5000)
        self.assertEqual(payment.status, PaymentRecord.STATUS_PENDING)
        self.assertEqual(PaymentAllocation.objects.filter(payment=payment).count(), 0)
        self.assertEqual(fq.payment_unallocated_sar(payment.pk), 5000)

    def test_record_deposit_requires_client(self):
        """Tanpa invoice DAN tanpa client → ditolak, tidak ada record."""
        resp = self._post_deposit(5000)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(PaymentRecord.objects.filter(invoice__isnull=True).exists())

    def test_record_deposit_rejects_allocations(self):
        """Deposit tidak boleh langsung dialokasikan saat record."""
        resp = self._post_deposit(
            7000, client_id=self.client_obj.pk,
            allocations=[{'reservation_id': self.r1.pk, 'amount': 3000}],
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(PaymentRecord.objects.filter(invoice__isnull=True).exists())

    def test_confirm_deposit_posts_journal_without_invoice_dim(self):
        """Confirm deposit → jurnal terposting (dimensi client, invoice kosong),
        dan kwitansi deposit tetap dibuat dengan invoice None."""
        self._post_deposit(7000, client_id=self.client_obj.pk)
        payment = PaymentRecord.objects.get(client=self.client_obj, invoice__isnull=True)
        self.client.post(f'/finance/payments/{payment.pk}/confirm/')
        payment.refresh_from_db()
        self.assertEqual(payment.display_status, 'received')

        line = JournalLine.objects.filter(
            journal_entry__reference_type='PaymentRecord',
            journal_entry__reference_id=payment.pk,
            account_id=coa.AR, credit__gt=0,
        ).first()
        self.assertIsNotNone(line)
        self.assertEqual(line.client_id, self.client_obj.pk)
        self.assertIsNone(line.invoice_id)

        from hw.models import Receipt
        receipt = Receipt.objects.get(payment=payment, status=Receipt.STATUS_ACTIVE)
        self.assertIsNone(receipt.invoice_id)
        self.assertEqual(receipt.client_id, self.client_obj.pk)
        self.assertEqual(receipt.amount_sar, 7000)

        pdf = self.client.get(f'/receipts/{receipt.pk}/pdf/')
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf['Content-Type'], 'application/pdf')

    def test_apply_deposit_attaches_invoice_and_allocates(self):
        """Apply deposit → invoice tujuan terpasang, alokasi dibuat, jurnal
        re-posted dengan dimensi invoice + reservasi, status applied."""
        self._post_deposit(7000, client_id=self.client_obj.pk)
        payment = PaymentRecord.objects.get(client=self.client_obj, invoice__isnull=True)
        self.client.post(f'/finance/payments/{payment.pk}/confirm/')
        payment.refresh_from_db()
        self.assertEqual(payment.display_status, 'received')

        self.client.post(
            f'/finance/payments/{payment.pk}/apply/',
            {'allocations': json.dumps([
                {'reservation_id': self.r1.pk, 'amount': 4000},
                {'reservation_id': self.r2.pk, 'amount': 3000},
            ]), 'invoice_id': self.invoice.pk},
        )

        payment.refresh_from_db()
        self.assertEqual(payment.invoice_id, self.invoice.pk)
        self.assertEqual(payment.display_status, 'applied')
        self.assertEqual(fq.payment_unallocated_sar(payment.pk), 0)
        self.assertEqual(PaymentAllocation.objects.filter(payment=payment).count(), 2)

        line = JournalLine.objects.filter(
            journal_entry__reference_type='PaymentRecord',
            journal_entry__reference_id=payment.pk,
            account_id=coa.AR, credit__gt=0, reservation_id=self.r1.pk,
        ).first()
        self.assertIsNotNone(line)
        self.assertEqual(line.invoice_id, self.invoice.pk)
        self.assertEqual(line.credit, 4000)

    def test_apply_deposit_requires_invoice(self):
        """Deposit tanpa invoice_id di payload apply → ditolak."""
        self._post_deposit(7000, client_id=self.client_obj.pk)
        payment = PaymentRecord.objects.get(client=self.client_obj, invoice__isnull=True)
        self.client.post(f'/finance/payments/{payment.pk}/confirm/')
        payment.refresh_from_db()
        self.assertEqual(payment.display_status, 'received')

        self.client.post(
            f'/finance/payments/{payment.pk}/apply/',
            {'allocations': json.dumps([
                {'reservation_id': self.r1.pk, 'amount': 5000},
            ])},
        )
        payment.refresh_from_db()
        self.assertIsNone(payment.invoice_id)
        self.assertEqual(payment.display_status, 'received')
        self.assertEqual(PaymentAllocation.objects.filter(payment=payment).count(), 0)
