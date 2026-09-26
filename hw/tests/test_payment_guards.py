"""Guards on the payment entry points (batch 1 hotfix).

Three regressions this pins down:

1. An invoice save that carries no `payments` key must not be read as "the
   payment list is now empty". Invoice/Form.jsx and Services/Form.jsx show
   payments read-only, so they never submit the field -- and the old default
   of '[]' made an unrelated edit (a due-date fix) reverse the invoice's live
   payments and flip them to REVERSED with nothing re-posted.
2. amount/amount_sar are PositiveIntegerField; a negative amount or rate used
   to reach the database and fail as an uncaught IntegrityError (HTTP 500)
   instead of a form message.
3. payment_apply reads request.body after request.POST. On a multipart POST
   that raises RawPostDataException, which is not a ValueError and so escaped
   the handler and turned a missing-allocations request into a 500.
"""
import base64
import json
from datetime import date

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from hw.models import Client, Invoice
from hw.models.journal import JournalEntry
from hw.models.payment import PaymentRecord
from hw.models.period import FinancialPeriod


class PaymentGuardBase(TestCase):
    def setUp(self):
        user = User.objects.create_user('guard', password='pw12345')
        user.profile.role = 'manager'
        user.profile.save(update_fields=['role'])
        self.user = user
        self.client.force_login(user)
        s = self.client.session
        s['active_company'] = 'konoz'
        s.save()
        FinancialPeriod.objects.create(
            name='2020-2030', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.client_obj = Client.objects.create(name='PT Guard')

    RESERVATIONS = json.dumps([{
        'reservation_number': 'G-1', 'hotel': 'Hotel Guard',
        'check_in': '2026-02-01', 'check_out': '2026-02-03',
        'reservation_total': '5000',
    }])

    def _create_invoice_with_payment(self, number='INV-GUARD-001'):
        resp = self.client.post('/invoice/new/', {
            'invoice_number': number,
            'customer_name': 'PT Guard',
            'client_id': str(self.client_obj.pk),
            'issued_date': '2026-01-01',
            'due_date': '',
            'reservations': self.RESERVATIONS,
            'payments': json.dumps([{
                'ref': 'G-1', 'date': '2026-01-05', 'method': 'Cash',
                'amount': '3000', 'currency': 'SAR', 'exchange': '1',
            }]),
        })
        self.assertEqual(resp.status_code, 302)
        invoice = Invoice.objects.get(invoice_number=number)
        payment = PaymentRecord.objects.get(invoice=invoice, reference='invoice-form')
        self.assertIn(payment.status, PaymentRecord.EFFECTIVE_STATUSES)
        return invoice, payment

    def _edit_payload(self, invoice):
        return {
            'invoice_number': invoice.invoice_number,
            'customer_name': 'PT Guard',
            'client_id': str(self.client_obj.pk),
            'issued_date': '2026-01-01',
            'due_date': '2026-03-01',
            'reservations': self.RESERVATIONS,
        }


class InvoiceSaveDoesNotWipePaymentsTest(PaymentGuardBase):
    def test_edit_without_payments_key_leaves_payments_untouched(self):
        invoice, payment = self._create_invoice_with_payment()
        before_status = payment.status
        reversals_before = JournalEntry.objects.filter(is_reversal=True).count()

        resp = self.client.post(f'/invoice/{invoice.pk}/edit/', self._edit_payload(invoice))
        self.assertEqual(resp.status_code, 302)

        payment.refresh_from_db()
        self.assertEqual(payment.status, before_status)
        self.assertNotEqual(payment.status, PaymentRecord.STATUS_REVERSED)
        self.assertEqual(
            JournalEntry.objects.filter(is_reversal=True).count(), reversals_before,
            'an edit that submits no payment list must post no reversal',
        )

    def test_edit_with_explicit_empty_payments_still_resyncs(self):
        """An explicitly submitted empty list is still a resync instruction."""
        invoice, payment = self._create_invoice_with_payment('INV-GUARD-002')

        payload = self._edit_payload(invoice)
        payload['payments'] = json.dumps([])
        resp = self.client.post(f'/invoice/{invoice.pk}/edit/', payload)
        self.assertEqual(resp.status_code, 302)

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRecord.STATUS_REVERSED)


class PaymentAmountGuardTest(PaymentGuardBase):
    def _record(self, **overrides):
        invoice = Invoice.objects.create(
            invoice_type='hotel', client=self.client_obj,
            invoice_number=overrides.pop('invoice_number', 'INV-AMT-001'),
            customer_name='PT Guard',
        )
        payload = {
            'invoice_id': invoice.pk,
            'payment_date': '2026-01-10',
            'amount': '5000',
            'currency': 'SAR',
            'exchange_rate': '1',
            'received_in': 'sby',
            'method': 'Transfer',
        }
        payload.update(overrides)
        # payment_record rejects a request with no proof before it ever reaches
        # the amount guard, so without a real attachment these assertions would
        # pass for the wrong reason. A 1x1 PNG satisfies the MIME sniff.
        payload['proof'] = SimpleUploadedFile(
            'proof.png',
            base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='
            ),
            content_type='image/png',
        )
        resp = self.client.post('/finance/payments/record/', payload)
        return invoice, resp

    def test_control_valid_amount_does_create_a_payment(self):
        """Control: without this the rejection tests could pass vacuously."""
        invoice, resp = self._record(invoice_number='INV-AMT-000')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(PaymentRecord.objects.filter(invoice=invoice).exists())

    def test_negative_amount_is_rejected_without_server_error(self):
        invoice, resp = self._record(amount='-5000')
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(PaymentRecord.objects.filter(invoice=invoice).exists())

    def test_zero_amount_is_rejected(self):
        invoice, resp = self._record(amount='0', invoice_number='INV-AMT-002')
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(PaymentRecord.objects.filter(invoice=invoice).exists())

    def test_negative_exchange_rate_is_rejected(self):
        invoice, resp = self._record(
            amount='5000', exchange_rate='-1', currency='IDR',
            invoice_number='INV-AMT-003',
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(PaymentRecord.objects.filter(invoice=invoice).exists())


class PaymentApplyBodyGuardTest(PaymentGuardBase):
    def test_multipart_apply_without_allocations_is_not_a_server_error(self):
        invoice = Invoice.objects.create(
            invoice_type='hotel', client=self.client_obj,
            invoice_number='INV-APPLY-GUARD', customer_name='PT Guard',
        )
        payment = PaymentRecord.objects.create(
            payment_number='PAY-GUARD-001', invoice=invoice, client=self.client_obj,
            payment_date=date(2026, 1, 10), amount=5000, currency='SAR',
            exchange_rate=1, amount_sar=5000, method='Transfer',
            status=PaymentRecord.STATUS_RECEIVED,
            period=FinancialPeriod.objects.first(), created_by=self.user,
        )
        # Django's test client posts a dict as multipart, so request.POST
        # consumes the stream before payment_apply reaches request.body.
        resp = self.client.post(f'/finance/payments/{payment.pk}/apply/', {'noise': 'x'})
        self.assertEqual(resp.status_code, 302)


class PaymentDoubleSubmitTest(PaymentGuardBase):
    """A second Reverse/Void on a payment object read before the first one
    finished (double click) must re-read the status and refuse, not reverse
    the journal again."""

    def _live_payment_entries(self, payment):
        reversed_ids = JournalEntry.objects.filter(reverses__isnull=False).values_list('reverses_id', flat=True)
        return JournalEntry.objects.filter(
            reference_type='PaymentRecord', reference_id=payment.pk, is_reversal=False,
        ).exclude(pk__in=reversed_ids).count()

    def test_stale_second_retire_is_refused(self):
        from hw.finance.errors import FinanceError
        from hw.models.payment import PaymentLog
        from hw.views.payment_views import _retire_payment

        _, payment = self._create_invoice_with_payment()
        stale = PaymentRecord.objects.get(pk=payment.pk)  # read before the first click lands
        _retire_payment(
            payment, status=PaymentRecord.STATUS_REVERSED, action=PaymentLog.ACTION_REVERSED,
            reversal_date=date(2026, 1, 6), journal_note='first', user=self.user,
        )
        reversals = JournalEntry.objects.filter(is_reversal=True).count()

        with self.assertRaises(FinanceError):
            _retire_payment(
                stale, status=PaymentRecord.STATUS_VOIDED, action=PaymentLog.ACTION_VOIDED,
                reversal_date=date(2026, 1, 6), journal_note='second', user=self.user,
            )
        self.assertEqual(JournalEntry.objects.filter(is_reversal=True).count(), reversals)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRecord.STATUS_REVERSED)
