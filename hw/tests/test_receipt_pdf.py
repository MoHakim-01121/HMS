"""Receipt PDF: allocation rows, reconciliation, and the void cascade.

The receipt PDF had no test at all, so a template change could only be caught
by a human printing one. These pin down the two properties that matter:

- the printed "Application of funds" column always sums to the receipt total,
  whichever allocation shape the payment has;
- a payment that has been voided or reversed stops producing an ACTIVE receipt.
"""
from datetime import date

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

from hw.models import Client, Receipt
from hw.models.payment import PaymentAllocation, PaymentRecord
from hw.models.period import FinancialPeriod
from hw.tests.factories import make_hotel_line, make_invoice, make_payment
from hw.views.receipt_views import _allocation_rows, _number_in_words, _stay_label


class ReceiptPdfBase(TestCase):
    def setUp(self):
        user = User.objects.create_user('receipt', password='pw12345')
        user.profile.role = 'finance'  # money is Finance's (2026-10-09)
        user.profile.save(update_fields=['role'])
        self.user = user
        self.client.force_login(user)
        s = self.client.session
        s['active_company'] = 'konoz'
        s.save()
        self.period = FinancialPeriod.objects.create(
            name='2020-2030', date_from=date(2020, 1, 1), date_to=date(2030, 12, 31),
        )
        self.client_obj = Client.objects.create(name='PT Receipt')
        self.invoice = make_invoice(
            invoice_type='hotel', client=self.client_obj,
            invoice_number='INV-RCP-001', customer_name='PT Receipt',
        )
        self.r1 = make_hotel_line(
            invoice=self.invoice, reservation_number='RCP-R1', hotel='Dar Al Eiman',
            check_in=date(2026, 10, 5), check_out=date(2026, 10, 12), total_sar=30000,
        )
        self.r2 = make_hotel_line(
            invoice=self.invoice, reservation_number='RCP-R2', hotel='Anjum Makkah',
            check_in=date(2026, 10, 14), check_out=date(2026, 10, 18), total_sar=15000,
        )

    def _payment(self, amount_sar=48750, number='PAY-RCP-001', **kw):
        return make_payment(
            payment_number=number, invoice=self.invoice, client=self.client_obj,
            payment_date=date(2026, 9, 17), amount=amount_sar, currency='SAR',
            exchange_rate=1, amount_sar=amount_sar, method='Bank Transfer',
            status=PaymentRecord.STATUS_CONFIRMED, period=self.period,
            created_by=self.user, **kw
        )

    def _receipt(self, payment, number='RCP-0001', status=Receipt.STATUS_ACTIVE):
        return Receipt.objects.create(
            receipt_number=number, receipt_date=payment.payment_date,
            payment=payment, invoice=self.invoice, client=self.client_obj,
            amount_sar=payment.amount_sar, payment_method=payment.method,
            status=status, created_by=self.user,
        )


class AllocationRowsTest(ReceiptPdfBase):
    def test_rows_reconcile_when_fully_applied(self):
        payment = self._payment(45000)
        PaymentAllocation.objects.create(payment=payment, invoice_line=self.r1, amount_sar=30000)
        PaymentAllocation.objects.create(payment=payment, invoice_line=self.r2, amount_sar=15000)

        rows = _allocation_rows(payment)
        self.assertEqual([r['label'] for r in rows], ['RCP-R1', 'RCP-R2'])
        self.assertEqual(sum(r['amount_sar'] for r in rows), payment.amount_sar)

    def test_partially_applied_leaves_a_remainder(self):
        payment = self._payment(48750)
        PaymentAllocation.objects.create(payment=payment, invoice_line=self.r1, amount_sar=30000)

        rows = _allocation_rows(payment)
        allocated = sum(r['amount_sar'] for r in rows)
        self.assertEqual(allocated, 30000)
        self.assertEqual(payment.amount_sar - allocated, 18750)

    def test_payment_bound_to_one_reservation_counts_as_fully_applied(self):
        """A payment made for one reservation carries a single full allocation."""
        payment = self._payment(30000)
        PaymentAllocation.objects.create(payment=payment, invoice_line=self.r1, amount_sar=30000)
        rows = _allocation_rows(payment)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['label'], 'RCP-R1')
        self.assertEqual(rows[0]['amount_sar'], 30000)

    def test_unallocated_payment_has_no_rows(self):
        payment = self._payment(48750)
        self.assertEqual(_allocation_rows(payment), [])

    def test_deleting_an_allocated_reservation_is_refused_by_the_database(self):
        """PaymentAllocation.reservation is SET_NULL, but the model also has a
        CHECK requiring exactly one of reservation/penalty. The two
        contradict: nulling the target violates the constraint, so the delete
        raises instead of orphaning the row.

        This is why _allocation_rows' "target no longer available" branch is
        defensive only -- the database will not currently produce such a row.
        Recorded here so the day the constraint or on_delete changes, the
        expectation is visible rather than inferred.
        """
        payment = self._payment(30000)
        PaymentAllocation.objects.create(payment=payment, invoice_line=self.r1, amount_sar=30000)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.r1.delete()


class StayLabelTest(TestCase):
    def test_same_year_collapses_the_first_year(self):
        self.assertEqual(
            _stay_label(date(2026, 10, 5), date(2026, 10, 12)), '05 Oct – 12 Oct 2026',
        )

    def test_cross_year_keeps_both_years(self):
        self.assertEqual(
            _stay_label(date(2026, 12, 28), date(2027, 1, 3)), '28 Dec 2026 – 03 Jan 2027',
        )

    def test_missing_dates_render_empty(self):
        self.assertEqual(_stay_label(None, None), '')


class NumberInWordsTest(TestCase):
    def test_thousands(self):
        self.assertEqual(_number_in_words(48750), 'forty-eight thousand seven hundred fifty')

    def test_hundreds(self):
        self.assertEqual(_number_in_words(300), 'three hundred')

    def test_tens_and_teens(self):
        self.assertEqual(_number_in_words(15), 'fifteen')
        self.assertEqual(_number_in_words(90), 'ninety')

    def test_zero(self):
        self.assertEqual(_number_in_words(0), 'zero')


class ReceiptPdfRenderTest(ReceiptPdfBase):
    def _render(self, receipt):
        resp = self.client.get(f'/receipts/{receipt.pk}/pdf/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertTrue(resp.content.startswith(b'%PDF'))
        return resp

    def test_fully_applied_receipt_renders(self):
        payment = self._payment(45000)
        PaymentAllocation.objects.create(payment=payment, invoice_line=self.r1, amount_sar=30000)
        PaymentAllocation.objects.create(payment=payment, invoice_line=self.r2, amount_sar=15000)
        self._render(self._receipt(payment))

    def test_partially_applied_receipt_renders(self):
        payment = self._payment(48750)
        PaymentAllocation.objects.create(payment=payment, invoice_line=self.r1, amount_sar=30000)
        self._render(self._receipt(payment, number='RCP-0002'))

    def test_unapplied_receipt_renders(self):
        payment = self._payment(48750)
        self._render(self._receipt(payment, number='RCP-0003'))

    def test_voided_receipt_renders(self):
        payment = self._payment(48750)
        receipt = self._receipt(payment, number='RCP-0004', status=Receipt.STATUS_VOIDED)
        receipt.voided_reason = 'Payment PAY-RCP-001 voided'
        receipt.save(update_fields=['voided_reason'])
        self._render(receipt)

    def test_foreign_currency_receipt_renders(self):
        payment = make_payment(
            payment_number='PAY-RCP-IDR', invoice=self.invoice, client=self.client_obj,
            payment_date=date(2026, 9, 17), amount=204750000, currency='IDR',
            exchange_rate=4200, amount_sar=48750, method='Bank Transfer',
            status=PaymentRecord.STATUS_CONFIRMED, period=self.period, created_by=self.user,
        )
        self._render(self._receipt(payment, number='RCP-0005'))

    def test_deposit_receipt_without_invoice_renders(self):
        """Kwitansi deposit (invoice None) harus bisa dicetak — blok 'Paid for'
        menampilkan keterangan deposit, tanpa rincian alokasi."""
        payment = make_payment(
            payment_number='PAY-RCP-DPT', invoice=None, client=self.client_obj,
            payment_date=date(2026, 9, 17), amount=7000, currency='SAR',
            exchange_rate=1, amount_sar=7000, method='Bank Transfer',
            status=PaymentRecord.STATUS_CONFIRMED, period=self.period, created_by=self.user,
        )
        receipt = Receipt.objects.create(
            receipt_number='RCP-0006', receipt_date=payment.payment_date,
            payment=payment, invoice=None, client=self.client_obj,
            amount_sar=payment.amount_sar, payment_method=payment.method,
            status=Receipt.STATUS_ACTIVE, created_by=self.user,
        )
        self._render(receipt)

    def test_ensure_receipt_creates_deposit_receipt_after_confirm(self):
        """Confirm flow (ensure_receipt) membuat kwitansi untuk deposit:
        invoice None, client & amount sesuai payment, idempotent (1 aktif)."""
        from hw.finance.receipt_service import ensure_receipt
        payment = make_payment(
            payment_number='PAY-RCP-DPT2', invoice=None, client=self.client_obj,
            payment_date=date(2026, 9, 17), amount=7000, currency='SAR',
            exchange_rate=1, amount_sar=7000, method='Bank Transfer',
            status=PaymentRecord.STATUS_CONFIRMED, period=self.period, created_by=self.user,
        )
        self.assertIsNone(payment.invoice_id)

        receipt = ensure_receipt(payment, created_by=self.user)
        self.assertIsNotNone(receipt)
        self.assertIsNone(receipt.invoice_id)
        self.assertEqual(receipt.client_id, self.client_obj.pk)
        self.assertEqual(receipt.amount_sar, 7000)

        again = ensure_receipt(payment, created_by=self.user)
        self.assertEqual(again.pk, receipt.pk)
        self.assertEqual(
            Receipt.objects.filter(payment=payment, status=Receipt.STATUS_ACTIVE).count(), 1,
        )

        self._render(receipt)


class ReceiptVoidCascadeTest(ReceiptPdfBase):
    def test_voiding_a_payment_voids_its_receipt(self):
        payment = self._payment(48750)
        receipt = self._receipt(payment)

        resp = self.client.post(f'/finance/payments/{payment.pk}/void/')
        self.assertEqual(resp.status_code, 302)

        receipt.refresh_from_db()
        self.assertEqual(receipt.status, Receipt.STATUS_VOIDED)
        self.assertIn(payment.payment_number, receipt.voided_reason)

    def test_reversing_a_payment_voids_its_receipt(self):
        payment = self._payment(48750, number='PAY-RCP-002')
        receipt = self._receipt(payment, number='RCP-0010')

        resp = self.client.post(f'/finance/payments/{payment.pk}/reverse/')
        self.assertEqual(resp.status_code, 302)

        receipt.refresh_from_db()
        self.assertEqual(receipt.status, Receipt.STATUS_VOIDED)
        self.assertIn(payment.payment_number, receipt.voided_reason)

    def test_an_already_voided_receipt_is_left_alone(self):
        payment = self._payment(48750, number='PAY-RCP-003')
        receipt = self._receipt(payment, number='RCP-0011', status=Receipt.STATUS_VOIDED)
        receipt.voided_reason = 'Voided by hand'
        receipt.save(update_fields=['voided_reason'])

        self.client.post(f'/finance/payments/{payment.pk}/void/')

        receipt.refresh_from_db()
        self.assertEqual(receipt.voided_reason, 'Voided by hand')
